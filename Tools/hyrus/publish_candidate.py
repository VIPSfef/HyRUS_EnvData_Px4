"""Publish a tested candidate as a PR; never execute candidate code or merge it."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from ci_common import ACTIVE_WORKFLOWS, SHA, fail, git, git_text
from upstream import check_pin_candidate


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def publish(root: Path, artifact: Path, repository: str, base_branch: str,
            expected_base: str, expected_candidate: str, expected_upstream: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    git(root, "check-ref-format", "refs/heads/" + base_branch)
    if not all(SHA.fullmatch(value) for value in (expected_base, expected_candidate, expected_upstream)):
        raise ValueError("Expected refs must be full commit SHAs")
    report = json.loads((artifact / "candidate.json").read_text(encoding="utf-8"))
    validation = json.loads((artifact / "validation.json").read_text(encoding="utf-8"))
    if report.get("state") != "validated" or any(report.get(key) != expected for key, expected in (
            ("base", expected_base), ("candidate", expected_candidate), ("upstream", expected_upstream))):
        raise ValueError("Candidate metadata does not match the validation job outputs")
    if (not validation.get("passed") or validation.get("source_commit") != expected_candidate
            or validation.get("px4_commit") != expected_upstream):
        raise ValueError("Candidate validation is missing or refers to different code")
    if git_text(root, "rev-parse", "HEAD") != expected_base:
        raise ValueError("Publisher must run trusted helper code from the original base")

    # Import objects without checking out the candidate or executing its hooks,
    # setup scripts, build files, or validation helper implementation.
    git(root, "bundle", "verify", str(artifact / "candidate.bundle"))
    git(root, "fetch", "--no-tags", str(artifact / "candidate.bundle"), "HEAD")
    if git_text(root, "rev-parse", "FETCH_HEAD") != expected_candidate:
        raise ValueError("Bundle does not contain the expected candidate")
    check_pin_candidate(root, expected_base, expected_candidate, expected_upstream)
    files = git_text(root, "ls-tree", "-r", "--name-only", expected_candidate, ".github/workflows").splitlines()
    if set(files) != {".github/workflows/" + name for name in ACTIVE_WORKFLOWS}:
        raise ValueError("Candidate introduces active workflows outside the allowlist")
    if git(root, "diff", "--quiet", expected_base, expected_candidate, "--", ".github/workflows", check=False).returncode:
        raise ValueError("Candidate modifies the trusted active workflows")

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("The publishing job needs a repository-scoped GitHub token")
    api = "https://api.github.com/repos/" + repository
    opener = urllib.request.build_opener(NoRedirect)

    def request(method, path, body=None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(api + path, data=payload, method=method, headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "User-Agent": "HyRUS-upstream-compatibility",
        })
        try:
            with opener.open(req, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            raise ValueError(f"GitHub {method}: HTTP {error.code}; check Actions PR permissions") from None

    current = request("GET", "/git/ref/heads/" + urllib.parse.quote(base_branch, safe=""))
    if current["object"]["sha"] != expected_base:
        raise ValueError("Default branch advanced during validation; prepare a fresh candidate")
    branch = "upstream/main-" + expected_upstream[:12] + "-onto-" + expected_base[:12]
    url = "https://github.com/" + repository + ".git"
    # Keep credentials out of argv, logs, the checked-out Git config and files.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
               GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
               GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + base64.b64encode(
                   ("x-access-token:" + token).encode("utf-8")).decode("ascii"))
    for key in list(env):
        if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
            del env[key]
    existing = subprocess.check_output(["git", "ls-remote", url, "refs/heads/" + branch],
                                       cwd=root, env=env, text=True).split()
    if existing and existing[0] != expected_candidate:
        raise ValueError("Existing candidate branch differs; refusing to overwrite it")
    if not existing:
        subprocess.run(["git", "push", url, expected_candidate + ":refs/heads/" + branch],
                       cwd=root, env=env, check=True)

    def ensure_ci():
        # GITHUB_TOKEN-created PRs do not trigger ordinary pull_request runs.
        # Explicit dispatch is permitted and checks the unchanged trusted CI
        # workflow on this candidate SHA. Resume an interrupted publication
        # without dispatching another run for a candidate already checked.
        runs = request("GET", "/actions/workflows/hyrus-ci.yml/runs?head_sha=" + expected_candidate + "&per_page=1")
        if not runs["workflow_runs"]:
            request("POST", "/actions/workflows/hyrus-ci.yml/dispatches", {"ref": branch})

    pulls = request("GET", "/pulls?state=all&head=" + urllib.parse.quote(repository.split("/")[0] + ":" + branch))
    if pulls:
        if pulls[0]["state"] != "open":
            raise ValueError("This candidate PR was already closed; manual review is required")
        ensure_ci()
        return pulls[0]["html_url"]
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = "https://github.com/" + repository + "/actions/runs/" + run_id if run_id.isdecimal() else "the compatibility workflow artifacts"
    body = (
        "Updates the official PX4 pin to `" + expected_upstream + "` for HyRUS external modules based on `" + expected_base + "`.\n\n"
        "The exact candidate `" + expected_candidate + "` passed native sensor/stream tests and the `" +
        validation["firmware_target"] + "` ARM firmware build. Results, logs and the firmware SHA256 are in " + run_url + ".\n\n"
        "This does not include hardware, flight, or full SITL validation. Review source changes and deployment suitability before merging. "
        "No automatic merge or device upload is enabled.\n")
    pull = request("POST", "/pulls", {"title": "Integrate PX4 main " + expected_upstream[:12],
                                      "head": branch, "base": base_branch, "body": body, "draft": False})
    ensure_ci()
    return pull["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--upstream", required=True)
    args = parser.parse_args()
    try:
        print(publish(args.repo.resolve(), args.artifact.resolve(), args.repository,
                      args.base_branch, args.base, args.candidate, args.upstream))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
