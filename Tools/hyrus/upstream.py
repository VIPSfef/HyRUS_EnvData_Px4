"""Prepare a candidate that changes only the approved official PX4 pin."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from ci_common import POLICY_PATH, SHA, check_workflows, fail, git, git_text, json_write, read_policy

def outputs(values: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            for key in ("base", "upstream", "candidate", "changed"):
                if key in values:
                    output.write(key + "=" + str(values[key]).lower() + "\n")

def check_pin_candidate(root: Path, base: str, candidate: str, upstream: str) -> None:
    if git_text(root, "show", "-s", "--format=%P", candidate).split() != [base]:
        raise ValueError("Candidate must be one commit on the trusted external-module base")
    if git_text(root, "diff", "--name-only", base, candidate).splitlines() != [POLICY_PATH]:
        raise ValueError("Candidate changes files other than the PX4 version manifest")
    old = json.loads(git_text(root, "show", base + ":" + POLICY_PATH))
    new = json.loads(git_text(root, "show", candidate + ":" + POLICY_PATH))
    old["px4_commit"] = upstream
    if new != old:
        raise ValueError("Candidate changes policy other than px4_commit")

def prepare(root: Path, output: Path) -> dict:
    policy = read_policy(root)
    check_workflows(root)
    if git_text(root, "status", "--porcelain"):
        raise ValueError("Prepare requires a clean external-module checkout")
    base = git_text(root, "rev-parse", "HEAD")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    report = {"format": "hyrus-upstream/v2", "base": base, "changed": False,
              "upstream_url": policy["upstream_url"], "upstream_branch": "main", "state": "checking"}
    detached = False
    try:
        lines = git_text(root, "ls-remote", policy["upstream_url"], "refs/heads/main").splitlines()
        if len(lines) != 1 or len(lines[0].split()) != 2:
            raise ValueError("Official main did not resolve to exactly one ref")
        upstream = lines[0].split()[0]
        if not SHA.fullmatch(upstream):
            raise ValueError("Invalid official PX4 commit")
        report["upstream"] = upstream
        if upstream == policy["px4_commit"]:
            report.update(state="current", candidate=base)
            return report
        git(root, "switch", "--detach", base)
        detached = True
        policy["px4_commit"] = upstream
        json_write(root / POLICY_PATH, policy)
        git(root, "add", "--", POLICY_PATH)
        timestamp = int(git_text(root, "show", "-s", "--format=%ct", base)) + 1
        env = dict(os.environ, GIT_AUTHOR_DATE=f"@{timestamp} +0000", GIT_COMMITTER_DATE=f"@{timestamp} +0000")
        git(root, "-c", "user.name=HyRUS upstream checker", "-c", "user.email=actions@users.noreply.github.com",
            "-c", "commit.gpgsign=false", "commit", "-m", "Validate PX4 main " + upstream[:12], env=env)
        candidate = git_text(root, "rev-parse", "HEAD")
        check_pin_candidate(root, base, candidate, upstream)
        report.update(state="prepared", changed=True, candidate=candidate)
        return report
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report.update(state="rejected", error=str(error))
        if detached:
            # Only our single manifest edit exists in this initially clean checkout.
            git(root, "reset", "--hard", base)
            git(root, "switch", branch if branch else "--detach", *([] if branch else [base]))
        raise
    finally:
        json_write(output / "candidate.json", report)
        outputs(report)

def package(root: Path, output: Path) -> None:
    report = json.loads((output / "candidate.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    head = git_text(root, "rev-parse", "HEAD")
    if report.get("state") != "prepared" or report.get("candidate") != head:
        raise ValueError("HEAD is not the prepared candidate")
    if (not validation.get("passed") or validation.get("source_commit") != head
            or validation.get("px4_commit") != report["upstream"]):
        raise ValueError("The exact module candidate and PX4 pin have not passed validation")
    if git_text(root, "status", "--porcelain"):
        raise ValueError("External source changed during validation")
    check_pin_candidate(root, report["base"], head, report["upstream"])
    bundle = output / "candidate.bundle"
    if bundle.exists():
        raise ValueError("Candidate bundle already exists; use a fresh output directory")
    git(root, "bundle", "create", str(bundle), "HEAD", "^" + report["base"])
    report["state"] = "validated"
    json_write(output / "candidate.json", report)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "package"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path("build/hyrus-upstream"))
    args = parser.parse_args()
    root = args.repo.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        (prepare if args.action == "prepare" else package)(root, output.resolve())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
