"""Validate external sensor modules against their pinned MAVLink firmware fork."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from ci_common import PROFILES, check_device_type, check_history, check_workflows, fail, firmware_profile, git_text, json_write, logged, read_policy, require_clean_checkout
from firmware import prepare, verify_fork


def verify_source_snapshot(root: Path, px4: Path, source_commit: str, submodules: list[str]) -> None:
    if git_text(root, "rev-parse", "HEAD") != source_commit:
        raise ValueError("External module commit changed during validation")
    require_clean_checkout(root, "External module validation")
    current = git_text(px4, "submodule", "status", "--recursive").splitlines()
    # Tag descriptions are informational; status, commit and path identify pins.
    if [line.split(" (", 1)[0] for line in current] != [line.split(" (", 1)[0] for line in submodules]:
        raise ValueError("PX4 submodule commits changed during validation")


def validate(root: Path, px4: Path, output: Path, jobs: int, *, profile: str = "main") -> dict:
    selected = firmware_profile(profile)
    policy = read_policy(root, profile)
    target = policy["firmware_target"]
    report = {"format": "hyrus-compatibility/v4", "profile": profile,
              "upstream_ref": selected.upstream_ref, "source_commit": git_text(root, "rev-parse", "HEAD"),
              "px4_commit": policy["px4_commit"], "firmware_target": target,
              "upstream_commit": policy["upstream_commit"], "fork_url": policy["fork_url"],
              "passed": False, "completed_checks": [],
              "coverage": "external-module host tests, actual generated MAVLink wire, ARM compile/link; no hardware or flight test"}
    output.mkdir(parents=True, exist_ok=True)
    try:
        check_workflows(root)
        if git_text(root, "status", "--porcelain"):
            raise ValueError("Validation requires a clean committed external-module checkout")
        prepare(root, px4, profile=profile)
        report["integration_paths"] = verify_fork(root, px4, policy)
        report["completed_checks"].append("external_source_and_committed_fork")
        report["device_type"] = check_device_type(root, px4)
        report["completed_checks"].append("device_type_collision")
        report["versions"] = check_history(px4)
        report["submodules"] = git_text(px4, "submodule", "status", "--recursive").splitlines()
        if any(line.startswith(("-", "+", "U")) for line in report["submodules"]):
            raise ValueError("PX4 submodules are not at their recorded commits")
        report["completed_checks"].append("version_history")
        native = selected.build_dir(root, "hyrus-native")
        firmware_build = px4 / "build" / target
        commands = [
            ("workflow_helpers", root, [sys.executable, "-m", "unittest", "discover", "-s", "Tools/hyrus/tests", "-v"]),
            ("native_configure", root, ["cmake", "-S", "test/hyrus", "-B", str(native), "-G", "Ninja",
                                       "-DCMAKE_BUILD_TYPE=Release", "-DHYRUS_PX4_SOURCE=" + str(px4),
                                       "-DHYRUS_MAVLINK_HEADERS="]),
            ("native_build", root, ["cmake", "--build", str(native), "--parallel", str(jobs)]),
            ("native_tests", root, ["ctest", "--test-dir", str(native), "--output-on-failure"]),
            ("arm_firmware", root, ["bash", str(root / "Tools/hyrus/build.sh"),
                                    "--px4-dir", str(px4), "--target", target, "--jobs", str(jobs),
                                    "--", "-DHYRUS_MAVLINK=ON"]),
            ("wire_configure", root, ["cmake", "-S", "test/hyrus", "-B", str(native), "-G", "Ninja",
                                     "-DCMAKE_BUILD_TYPE=Release", "-DHYRUS_MAVLINK_HEADERS=" + str(firmware_build / "mavlink")]),
            ("wire_build", root, ["cmake", "--build", str(native), "--parallel", str(jobs)]),
            ("wire_tests", root, ["ctest", "--test-dir", str(native), "--output-on-failure"]),
        ]
        for name, directory, command in commands:
            logged(directory, command, output / (name + ".log"))
            report["completed_checks"].append(name)
        # A successful board build must actually contain both external commands
        # and the parameter generated from the module's external YAML file.
        symbols = subprocess.check_output(["arm-none-eabi-nm", str(firmware_build / (target + ".elf"))],
                                          cwd=px4, text=True)
        names = {line.split()[-1] for line in symbols.splitlines() if line.split()}
        if not {"shtc3_main", "shtc3_probe_main"} <= names:
            raise ValueError("External sensor/probe commands are missing from the linked firmware")
        if not any("MavlinkStreamSensAtmos" in name for name in names):
            raise ValueError("The surveyor MAVLink stream is missing from the linked firmware")
        parameters = (firmware_build / "src/lib/parameters/px4_parameters.hpp").read_text(encoding="utf-8")
        if "SENS_EN_SHTC3" not in parameters:
            raise ValueError("External SHTC3 parameter metadata is missing from the firmware")
        report["completed_checks"].append("linked_external_commands_and_parameters")
        verify_fork(root, px4, policy)
        verify_source_snapshot(root, px4, report["source_commit"], report["submodules"])
        image = firmware_build / (target + ".px4")
        if not image.is_file() or image.stat().st_size == 0:
            raise ValueError("Firmware build did not produce the expected .px4 image")
        integration = git_text(px4, "diff", "--binary", policy["upstream_commit"], policy["px4_commit"])
        report["integration_sha256"] = hashlib.sha256(integration.encode("utf-8")).hexdigest()
        report["firmware"] = {"file": image.name, "bytes": image.stat().st_size,
                              "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
        shutil.copyfile(image, output / image.name)
        report["passed"] = True
        return report
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            report["diagnostics"] = error.stderr[-8000:]
        raise
    finally:
        json_write(output / "validation.json", report)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--px4-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", choices=PROFILES, default="main")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    root = args.repo.resolve()
    selected = firmware_profile(args.profile)
    output = args.output or selected.build_dir(root, "hyrus-ci")
    output = output if output.is_absolute() else root / output
    if not 1 <= args.jobs <= 32:
        parser.error("--jobs must be in 1..32")
    try:
        validate(root, (args.px4_dir or selected.build_dir(root, "px4")).resolve(), output.resolve(),
                 args.jobs, profile=args.profile)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        fail(error)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
