"""Prepare a pinned PX4 fork; its MAVLink integration is already committed."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys
from ci_common import INTEGRATION_PATHS, fail, git, git_text, read_policy, require_clean_checkout

MODULE_FILES = (
    "src/CMakeLists.txt", "src/drivers/hygrometer/shtc3/CMakeLists.txt",
    "src/drivers/hygrometer/shtc3/SHTC3.cpp", "src/drivers/hygrometer/shtc3/SHTC3Device.hpp",
    "src/systemcmds/shtc3_probe/CMakeLists.txt",
)


def require_clean_firmware(px4: Path) -> None:
    # A clean submodule at an older revision can be refreshed; user edits cannot.
    require_clean_checkout(px4, "PX4 fork", ignore_submodules=True)
    if git_text(px4, "submodule", "foreach", "--quiet", "--recursive",
                "git status --porcelain --ignore-submodules=all"):
        raise ValueError("PX4 submodules contain local changes; existing work is preserved")


def verify_fork(root: Path, px4: Path, policy: dict | None = None) -> list[str]:
    """Check source identity, ancestry and the complete fork delta, without editing it."""
    policy = policy or read_policy(root)
    for name in MODULE_FILES:
        if not (root / name).is_file():
            raise ValueError("External module source missing: " + name)
    require_clean_firmware(px4)
    if git_text(px4, "rev-parse", "HEAD") != policy["px4_commit"]:
        raise ValueError("PX4 checkout does not match project.json px4_commit")
    if git(px4, "merge-base", "--is-ancestor", policy["upstream_commit"], policy["px4_commit"], check=False).returncode:
        raise ValueError("The recorded official upstream commit is not an ancestor of the fork")
    changed = git_text(px4, "diff", "--no-renames", "--name-only",
                       policy["upstream_commit"], policy["px4_commit"]).splitlines()
    if not changed or not set(changed) <= INTEGRATION_PATHS:
        raise ValueError("Fork changes must be confined to the MAVLink integration allowlist: " +
                         ", ".join(sorted(set(changed) - INTEGRATION_PATHS)))
    return changed


def prepare(root: Path, px4: Path, update_submodules: bool = True) -> dict:
    policy = read_policy(root)
    px4 = px4.resolve()
    if px4 == root or root.is_relative_to(px4):
        raise ValueError("PX4 checkout must be separate from the external module repository")
    cloned = not px4.exists()
    if cloned:
        px4.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "--single-branch",
                        "--branch", policy["fork_branch"], policy["fork_url"], str(px4)], check=True)
    elif not (px4 / ".git").exists():
        raise ValueError("Existing PX4 directory is not a Git checkout; it will not be overwritten")
    else:
        require_clean_firmware(px4)
    if git_text(px4, "rev-parse", "--is-shallow-repository") == "true":
        git(px4, "fetch", "--unshallow", policy["fork_url"])
    if git(px4, "cat-file", "-e", policy["px4_commit"] + "^{commit}", check=False).returncode:
        git(px4, "fetch", policy["fork_url"], policy["px4_commit"])
    # Fork tags can lag behind its branch. PX4 derives version metadata from
    # official tags, so fetch them without changing the selected firmware pin.
    git(px4, "fetch", "--no-recurse-submodules", "--filter=blob:none", "--tags",
        policy["upstream_url"], "refs/heads/" + policy["upstream_branch"])
    if git(px4, "merge-base", "--is-ancestor", policy["upstream_commit"], "FETCH_HEAD", check=False).returncode:
        raise ValueError("The recorded upstream commit is outside the fetched official main history")
    git(px4, "checkout", "--detach", policy["px4_commit"])
    # Source is committed in the fork. Never apply patches or copy drivers here.
    # Check ancestry/delta before downloading dependencies for an invalid pin.
    verify_fork(root, px4, policy)
    if update_submodules:
        git(px4, "submodule", "sync", "--recursive")
        subprocess.run(["git", "submodule", "update", "--init", "--recursive", "--jobs", "4"], cwd=px4, check=True)
    verify_fork(root, px4, policy)
    return policy


def make_command(root: Path, policy: dict, jobs: int) -> list[str]:
    # PX4's Makefile expands CMAKE_ARGS through a shell. Keep spaces quoted.
    path = str(root.resolve())
    if any(char in path for char in '"$\\\n\r') or chr(96) in path:
        raise ValueError("Use a Linux source path without shell expansion characters")
    return ["make", policy["firmware_target"], "-j" + str(jobs),
            'EXTERNAL_MODULES_LOCATION="' + path + '"']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare",))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--px4-dir", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    try:
        prepare(root, (args.px4_dir or root / "build/px4").resolve())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
