"""Build a reviewed fork/main merge candidate without changing remote branches."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from ci_common import POLICY_PATH, SHA, check_workflows, fail, git, git_text, json_write, read_policy
from firmware import prepare as prepare_firmware, verify_fork


def outputs(values: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            for key in ("base", "fork_base", "upstream", "fork_candidate", "candidate", "changed"):
                if key in values:
                    output.write(key + "=" + str(values[key]).lower() + "\n")


def check_pin_candidate(root: Path, base: str, candidate: str, upstream: str, fork_commit: str) -> None:
    if git_text(root, "show", "-s", "--format=%P", candidate).split() != [base]:
        raise ValueError("Candidate must be one commit on the trusted external-module base")
    if git_text(root, "diff", "--name-only", base, candidate).splitlines() != [POLICY_PATH]:
        raise ValueError("Candidate changes files other than the PX4 version manifest")
    old = json.loads(git_text(root, "show", base + ":" + POLICY_PATH))
    new = json.loads(git_text(root, "show", candidate + ":" + POLICY_PATH))
    old.update(upstream_commit=upstream, px4_commit=fork_commit)
    if new != old:
        raise ValueError("Candidate changes policy other than the upstream and fork commits")


def commit_candidate(directory: Path, message: str, parents: tuple[str, ...]) -> str:
    """The same source pair produces the same reviewable commit and bundle refs."""
    timestamp = max(int(git_text(directory, "show", "-s", "--format=%ct", parent)) for parent in parents) + 1
    env = dict(os.environ, GIT_AUTHOR_DATE=f"@{timestamp} +0000", GIT_COMMITTER_DATE=f"@{timestamp} +0000")
    git(directory, "-c", "user.name=HyRUS upstream checker", "-c", "user.email=actions@users.noreply.github.com",
        "-c", "commit.gpgsign=false", "commit", "-m", message, env=env)
    return git_text(directory, "rev-parse", "HEAD")


def require_ancestor(directory: Path, ancestor: str, descendant: str, message: str) -> None:
    if git(directory, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode:
        raise ValueError(message)


def check_fork_candidate(px4: Path, fork_base: str, upstream: str, candidate: str) -> None:
    require_ancestor(px4, fork_base, candidate, "Fork candidate discards the recorded integration history")
    require_ancestor(px4, upstream, candidate, "Fork candidate does not include the selected official main")
    if candidate != fork_base and git_text(px4, "show", "-s", "--format=%P", candidate).split() != [fork_base, upstream]:
        raise ValueError("Fork candidate must be the exact two-parent upstream merge")


def prepare(root: Path, output: Path, px4: Path | None = None) -> dict:
    policy = read_policy(root)
    check_workflows(root)
    if git_text(root, "status", "--porcelain"):
        raise ValueError("Prepare requires a clean external-module checkout")
    px4 = (px4 or root / "build/px4").resolve()
    base = git_text(root, "rev-parse", "HEAD")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    report = {"format": "hyrus-upstream/v3", "base": base, "fork_base": policy["px4_commit"],
              "changed": False, "upstream_url": policy["upstream_url"], "upstream_branch": "main",
              "fork_url": policy["fork_url"], "fork_branch": policy["fork_branch"], "state": "checking"}
    fork_prepared = False
    module_detached = False
    try:
        lines = git_text(root, "ls-remote", policy["upstream_url"], "refs/heads/main").splitlines()
        if len(lines) != 1 or len(lines[0].split()) != 2 or not SHA.fullmatch(lines[0].split()[0]):
            raise ValueError("Official main did not resolve to exactly one full commit SHA")
        upstream = lines[0].split()[0]
        report["upstream"] = upstream
        if upstream == policy["upstream_commit"]:
            report.update(state="current", candidate=base, fork_candidate=policy["px4_commit"])
            return report

        # Build only from the reviewed fork pin. A moving remote branch is not
        # permission to incorporate unrelated changes into an update candidate.
        prepare_firmware(root, px4, update_submodules=False)
        fork_prepared = True
        git(px4, "fetch", "--no-tags", policy["upstream_url"], upstream)
        require_ancestor(px4, policy["upstream_commit"], upstream,
                         "Official main rewrote the recorded history; manual review is required")
        merge = git(px4, "-c", "user.name=HyRUS upstream checker",
                    "-c", "user.email=actions@users.noreply.github.com",
                    "merge", "--no-ff", "--no-commit", upstream, check=False)
        if merge.returncode:
            raise ValueError("Official main conflicts with the fork integration:\n" + merge.stdout + merge.stderr)
        if git(px4, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode == 0:
            fork_candidate = commit_candidate(px4, "Merge official PX4 main " + upstream[:12],
                                              (policy["px4_commit"], upstream))
        else:
            fork_candidate = policy["px4_commit"]
        candidate_policy = dict(policy, upstream_commit=upstream, px4_commit=fork_candidate)
        check_fork_candidate(px4, policy["px4_commit"], upstream, fork_candidate)
        verify_fork(root, px4, candidate_policy)
        report["fork_candidate"] = fork_candidate

        git(root, "switch", "--detach", base)
        module_detached = True
        json_write(root / POLICY_PATH, candidate_policy)
        git(root, "add", "--", POLICY_PATH)
        candidate = commit_candidate(root, "Validate fork with PX4 main " + upstream[:12], (base,))
        check_pin_candidate(root, base, candidate, upstream, fork_candidate)
        report.update(state="prepared", changed=True, candidate=candidate)
        return report
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report.update(state="rejected", error=str(error))
        # Both worktrees were checked clean before our own detached edits.
        # Restore only those edits; never reset a branch or overwrite user work.
        if module_detached:
            git(root, "restore", "--source=" + base, "--staged", "--worktree", "--", POLICY_PATH)
            git(root, "switch", branch if branch else "--detach", *([] if branch else [base]))
        if fork_prepared:
            if git(px4, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode == 0:
                git(px4, "merge", "--abort")
            git(px4, "switch", "--detach", policy["px4_commit"])
        raise
    finally:
        json_write(output / "candidate.json", report)
        outputs(report)


def package(root: Path, output: Path, px4: Path | None = None) -> None:
    px4 = (px4 or root / "build/px4").resolve()
    report = json.loads((output / "candidate.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    head = git_text(root, "rev-parse", "HEAD")
    if report.get("state") != "prepared" or report.get("candidate") != head:
        raise ValueError("HEAD is not the prepared candidate")
    if (not validation.get("passed") or validation.get("source_commit") != head
            or validation.get("px4_commit") != report["fork_candidate"]
            or validation.get("upstream_commit") != report["upstream"]):
        raise ValueError("The exact module candidate and fork/upstream pair have not passed validation")
    if git_text(root, "status", "--porcelain"):
        raise ValueError("External source changed during validation")
    check_pin_candidate(root, report["base"], head, report["upstream"], report["fork_candidate"])
    check_fork_candidate(px4, report["fork_base"], report["upstream"], report["fork_candidate"])
    verify_fork(root, px4)
    bundles = ((root, "candidate.bundle", report["base"]),
               (px4, "firmware-candidate.bundle", report["fork_base"]))
    if any((output / name).exists() for _, name, _ in bundles):
        raise ValueError("Candidate bundle already exists; use a fresh output directory")
    for directory, name, parent in bundles:
        bundle = output / name
        if git_text(directory, "rev-parse", "HEAD") == parent:
            # The fork already contains this upstream revision. No new fork
            # objects are needed; metadata identifies its published pin.
            continue
        git(directory, "bundle", "create", str(bundle), "HEAD", "^" + parent)
        git(directory, "bundle", "verify", str(bundle))
    report["state"] = "validated"
    report["bundles"] = [name for _, name, _ in bundles if (output / name).exists()]
    json_write(output / "candidate.json", report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "package"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--px4-dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/hyrus-upstream"))
    args = parser.parse_args()
    root = args.repo.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        (prepare if args.action == "prepare" else package)(root, output.resolve(), args.px4_dir)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
