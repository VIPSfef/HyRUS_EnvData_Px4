"""Prepare official PX4 with only the reviewed MAVLink integration patch."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from ci_common import PATCH_PATHS, fail, git, git_text, read_policy

MODULE_FILES = (
    "src/CMakeLists.txt", "src/drivers/hygrometer/shtc3/CMakeLists.txt",
    "src/drivers/hygrometer/shtc3/SHTC3.cpp", "src/drivers/hygrometer/shtc3/SHTC3Device.hpp",
    "src/systemcmds/shtc3_probe/CMakeLists.txt", "mavlink/dialect.cmake",
    "mavlink/weather.xml", "mavlink/streams/SENS_ATMOS.hpp",
)

def patch_file(root: Path) -> Path:
    for name in MODULE_FILES:
        if not (root / name).is_file():
            raise ValueError("External module source missing: " + name)
    patch = root / "patches/px4-mavlink.patch"
    stats = git(root, "apply", "--numstat", "-z", str(patch)).stdout
    paths = {entry.split("\t", 2)[2] for entry in stats.split("\0") if entry}
    if not paths or not paths <= PATCH_PATHS:
        raise ValueError("PX4 patch touches paths outside the MAVLink allowlist: " + ", ".join(sorted(paths - PATCH_PATHS)))
    return patch

def expected_tree(px4: Path, patch: Path) -> str:
    """Build the reviewed tree in a temporary index without touching files."""
    with tempfile.TemporaryDirectory(prefix="hyrus-index-") as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git(px4, "read-tree", "HEAD", env=env)
        git(px4, "apply", "--cached", str(patch), env=env)
        return git(px4, "write-tree", env=env).stdout.strip()

def verify_patch(root: Path, px4: Path, pin: str | None = None) -> None:
    patch = patch_file(root)
    if pin and git_text(px4, "rev-parse", "HEAD") != pin:
        raise ValueError("PX4 checkout does not match project.json px4_commit")
    tree = expected_tree(px4, patch)
    if git(px4, "diff", "--quiet", tree, "--ignore-submodules=untracked", "--", check=False).returncode:
        raise ValueError("PX4 tracked source differs from the exact reviewed MAVLink patch")
    if git_text(px4, "ls-files", "--others", "--exclude-standard"):
        raise ValueError("PX4 has untracked source files; use a clean dedicated checkout")

def prepare(root: Path, px4: Path, update_submodules: bool = True) -> dict:
    policy = read_policy(root)
    patch = patch_file(root)
    px4 = px4.resolve()
    if px4 == root or root.is_relative_to(px4):
        raise ValueError("PX4 checkout must be separate from the external module repository")
    cloned = not px4.exists()
    if cloned:
        px4.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", policy["upstream_url"], str(px4)], check=True)
    elif not (px4 / ".git").exists():
        raise ValueError("Existing PX4 directory is not a Git checkout; it will not be overwritten")
    if not cloned:
        if git_text(px4, "ls-files", "--others", "--exclude-standard"):
            raise ValueError("PX4 has untracked files; it will not be overwritten")
        if git(px4, "diff", "--quiet", "HEAD", "--ignore-submodules=untracked", check=False).returncode:
            verify_patch(root, px4)
            git(px4, "apply", "--reverse", str(patch))
    if git_text(px4, "rev-parse", "--is-shallow-repository") == "true":
        git(px4, "fetch", "--unshallow", policy["upstream_url"])
    if git(px4, "cat-file", "-e", policy["px4_commit"] + "^{commit}", check=False).returncode:
        git(px4, "fetch", policy["upstream_url"], policy["px4_commit"])
    git(px4, "checkout", "--detach", policy["px4_commit"])
    # Reject an incompatible upstream before downloading its submodule trees.
    git(px4, "apply", "--check", str(patch))
    if update_submodules:
        git(px4, "submodule", "sync", "--recursive")
        subprocess.run(["git", "submodule", "update", "--init", "--recursive", "--jobs", "4"], cwd=px4, check=True)
    git(px4, "apply", str(patch))
    verify_patch(root, px4, policy["px4_commit"])
    return policy

def make_command(root: Path, policy: dict, jobs: int) -> list[str]:
    # PX4's Makefile expands CMAKE_ARGS through a shell. Keep spaces quoted.
    path = str(root.resolve())
    if any(char in path for char in '\"`$\\\n\r'):
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
