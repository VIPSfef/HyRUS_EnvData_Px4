"""Shared policy and execution for standalone HyRUS external modules."""
from __future__ import annotations
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

UPSTREAM_URL = "https://github.com/PX4/PX4-Autopilot.git"
FORK_URL = "https://github.com/VIPSfef/Firmware.git"
FORK_BRANCH = "hyrus/mavlink"
POLICY_PATH = "Tools/hyrus/project.json"
ACTIVE_WORKFLOWS = frozenset({"hyrus-ci.yml", "hyrus-upstream.yml"})
INTEGRATION_PATHS = frozenset("src/modules/mavlink/" + name for name in (
    "CMakeLists.txt", "mavlink_messages.cpp", "mavlink_main.cpp", "streams/HYGROMETER_SENSOR.hpp",
    "streams/SENS_ATMOS.hpp", "hyrus/dialect.cmake", "hyrus/weather.xml"))
SHA = re.compile(r"[0-9a-f]{40}\Z")

def git(root: Path, *arguments: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=root, check=check, text=True,
                          encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

def git_text(root: Path, *arguments: str) -> str:
    return git(root, *arguments).stdout.strip()

def read_policy(root: Path) -> dict:
    policy = json.loads((root / POLICY_PATH).read_text(encoding="utf-8"))
    if policy.get("upstream_url") != UPSTREAM_URL or policy.get("upstream_branch") != "main":
        raise ValueError("Only official PX4 main is supported")
    if policy.get("fork_url") != FORK_URL or policy.get("fork_branch") != FORK_BRANCH:
        raise ValueError("Only the HyRUS MAVLink firmware fork is supported")
    for key in ("upstream_commit", "px4_commit"):
        if not SHA.fullmatch(policy.get(key, "")):
            raise ValueError(key + " must be a full commit SHA")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", policy.get("firmware_target", "")):
        raise ValueError("Invalid firmware target")
    return policy


def require_clean_checkout(root: Path, label: str, *, ignore_submodules: bool = False) -> None:
    arguments = ["status", "--porcelain"]
    if ignore_submodules:
        arguments.append("--ignore-submodules=all")
    if git_text(root, *arguments):
        raise ValueError(label + " requires a clean committed checkout; existing work is preserved")

def check_workflows(root: Path) -> None:
    active = {p.name for p in (root / ".github/workflows").iterdir() if p.is_file()}
    if active != ACTIVE_WORKFLOWS:
        raise ValueError("Unexpected active workflow files")

def check_device_type(root: Path, px4: Path) -> dict:
    local = (root / "src/drivers/hygrometer/shtc3/SHTC3Device.hpp").read_text(encoding="utf-8")
    match = re.search(r"\bShtc3\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\b", local)
    if not match:
        raise ValueError("SHTC3 DeviceType::Shtc3 allocation is missing")
    value = int(match.group(1), 0)
    definitions = re.findall(r"^\s*#define\s+(DRV_\w*DEVTYPE\w*)\s+(0x[0-9a-fA-F]+|[0-9]+)\b",
                            (px4 / "src/drivers/drv_sensor.h").read_text(encoding="utf-8"), re.MULTILINE)
    conflicts = [name for name, number in definitions if int(number, 0) == value]
    if conflicts:
        raise ValueError("SHTC3 device type collides with PX4: " + ", ".join(conflicts))
    return {"name": "DeviceType::Shtc3", "value": value}

def check_history(px4: Path) -> dict:
    versions = {}
    for name, path in (("px4", px4), ("nuttx", px4 / "platforms/nuttx/NuttX/nuttx")):
        if git_text(path, "rev-parse", "--is-shallow-repository") != "false":
            raise ValueError(name + " history is shallow; use full history and original release tags")
        versions[name] = {"commit": git_text(path, "rev-parse", "HEAD"),
                          "git_description": git_text(path, "describe", "--always", "--tags")}
    return versions

def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def logged(root: Path, command: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as output:
        print("+ " + shlex.join(command), flush=True)
        output.write("+ " + shlex.join(command) + "\n")
        process = subprocess.Popen(command, cwd=root, text=True, encoding="utf-8", errors="replace",
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            for line in process.stdout:
                output.write(line)
                print(line, end="", flush=True)
            code = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
        if code:
            raise subprocess.CalledProcessError(code, command)

def fail(error: Exception) -> None:
    print(str(error), file=sys.stderr)
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        print(error.stderr[-8000:], file=sys.stderr)
