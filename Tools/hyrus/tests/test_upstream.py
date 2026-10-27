"""Real local-Git regressions for external modules and upstream pin proposals."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_common
from ci_common import POLICY_PATH, check_device_type, git, git_text, json_write
from firmware import MODULE_FILES, make_command, patch_file, prepare as firmware_prepare, verify_patch
from upstream import check_pin_candidate, package, prepare

class ExternalFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hyrus test ")
        self.addCleanup(self.temp.cleanup)
        self.base_dir = Path(self.temp.name)
        self.root = self.base_dir / "external modules"
        self.source = self.base_dir / "official"
        self.px4 = self.base_dir / "checkout"
        self.root.mkdir()
        self.source.mkdir()
        for directory in (self.root, self.source):
            git(directory, "init", "-b", "main")
            git(directory, "config", "user.name", "Test")
            git(directory, "config", "user.email", "test@example.invalid")
            git(directory, "config", "core.autocrlf", "false")
        self.write(self.source, "src/modules/mavlink/CMakeLists.txt", "first\noriginal\nlast\n")
        self.write(self.source, "src/drivers/drv_sensor.h", "#define DRV_MAG_DEVTYPE_A 0xB8\n")
        self.commit(self.source, "Official baseline")
        self.pin = git_text(self.source, "rev-parse", "HEAD")
        self.write(self.source, "src/modules/mavlink/CMakeLists.txt", "first\nexternal integration\nlast\n")
        patch_text = git(self.source, "diff", "--binary").stdout
        git(self.source, "checkout", "--", ".")
        git(self.base_dir, "clone", str(self.source), str(self.px4))
        for name in MODULE_FILES:
            self.write(self.root, name, "// fixture\n")
        self.write(self.root, "src/drivers/hygrometer/shtc3/SHTC3Device.hpp",
                   "enum class DeviceType : unsigned char { Shtc3 = 0xB9 };\n")
        self.write(self.root, "patches/px4-mavlink.patch", patch_text)
        self.write(self.root, ".gitignore", "build/\n")
        for name in ci_common.ACTIVE_WORKFLOWS:
            self.write(self.root, ".github/workflows/" + name, "name: fixture\n")
        json_write(self.root / POLICY_PATH, {"upstream_url": str(self.source), "upstream_branch": "main",
                                            "baseline_commit": self.pin, "px4_commit": self.pin,
                                            "firmware_target": "test_target"})
        self.commit(self.root, "External modules baseline")
        self.external_base = git_text(self.root, "rev-parse", "HEAD")
        self.output = self.root / "build/proposal"
        self.policy_patch = patch.object(ci_common, "UPSTREAM_URL", str(self.source))
        self.policy_patch.start()
        self.addCleanup(self.policy_patch.stop)

    @staticmethod
    def write(root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def commit(root, message):
        git(root, "add", ".")
        git(root, "commit", "-m", message)

    def advance(self):
        self.write(self.source, "upstream.txt", "new upstream content\n")
        self.commit(self.source, "New official main")
        return git_text(self.source, "rev-parse", "HEAD")

    def test_exact_patch_preparation_is_repeatable(self):
        firmware_prepare(self.root, self.px4, update_submodules=False)
        verify_patch(self.root, self.px4, self.pin)
        firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertIn("external integration", (self.px4 / "src/modules/mavlink/CMakeLists.txt").read_text())
        self.assertEqual(git_text(self.px4, "diff", "--name-only"), "src/modules/mavlink/CMakeLists.txt")

    def test_unrelated_px4_edit_is_preserved_and_refused(self):
        firmware_prepare(self.root, self.px4, update_submodules=False)
        path = self.px4 / "src/modules/mavlink/CMakeLists.txt"
        path.write_text(path.read_text() + "user change\n")
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertIn("user change", path.read_text())

    def test_patch_cannot_modify_px4_driver_or_board(self):
        path = self.root / "patches/px4-mavlink.patch"
        path.write_text(path.read_text().replace("src/modules/mavlink/CMakeLists.txt", "src/drivers/drv_sensor.h"))
        with self.assertRaisesRegex(ValueError, "allowlist"):
            patch_file(self.root)

    def test_missing_external_source_is_rejected(self):
        (self.root / MODULE_FILES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            patch_file(self.root)

    def test_device_allocation_is_dynamic_and_collision_checked(self):
        self.assertEqual(check_device_type(self.root, self.px4)["value"], 185)
        self.write(self.px4, "src/drivers/drv_sensor.h", "#define DRV_IMU_DEVTYPE_NEW 185\n")
        with self.assertRaisesRegex(ValueError, "collides"):
            check_device_type(self.root, self.px4)

    def test_candidate_only_updates_pin_and_leaves_main_unchanged(self):
        new_pin = self.advance()
        report = prepare(self.root, self.output)
        check_pin_candidate(self.root, self.external_base, report["candidate"], new_pin)
        self.assertEqual(git_text(self.root, "rev-parse", "main"), self.external_base)
        json_write(self.output / "validation.json", {"passed": True, "source_commit": report["candidate"], "px4_commit": new_pin})
        package(self.root, self.output)
        git(self.root, "bundle", "verify", str(self.output / "candidate.bundle"))

    def test_repeated_pair_makes_same_candidate_and_current_is_noop(self):
        current = prepare(self.root, self.output)
        self.assertFalse(current["changed"])
        self.advance()
        first = prepare(self.root, self.output)["candidate"]
        git(self.root, "switch", "main")
        second = prepare(self.root, self.output)["candidate"]
        self.assertEqual(first, second)

    def test_dirty_external_source_is_preserved(self):
        self.write(self.root, "src/CMakeLists.txt", "user work\n")
        self.advance()
        with self.assertRaisesRegex(ValueError, "clean"):
            prepare(self.root, self.output)
        self.assertEqual((self.root / "src/CMakeLists.txt").read_text(), "user work\n")

    def test_stale_validation_or_extra_candidate_file_is_refused(self):
        new_pin = self.advance()
        report = prepare(self.root, self.output)
        json_write(self.output / "validation.json", {"passed": True, "source_commit": self.external_base, "px4_commit": new_pin})
        with self.assertRaisesRegex(ValueError, "exact module"):
            package(self.root, self.output)
        self.write(self.root, "extra.txt", "unexpected\n")
        git(self.root, "add", "extra.txt")
        git(self.root, "commit", "--amend", "--no-edit")
        with self.assertRaisesRegex(ValueError, "other than"):
            check_pin_candidate(self.root, self.external_base, git_text(self.root, "rev-parse", "HEAD"), new_pin)

    @unittest.skipIf(os.name == "nt", "Firmware builds use Linux/WSL")
    def test_make_passes_external_path_with_spaces_as_one_argument(self):
        self.write(self.px4, "Makefile",
                   "CMAKE_ARGS += -DEXTERNAL_MODULES_LOCATION:STRING=$(EXTERNAL_MODULES_LOCATION)\n"
                   "test_target:\n\t@python3 -c 'import sys,json;print(json.dumps(sys.argv[1:]))' $(CMAKE_ARGS)\n")
        output = subprocess.check_output(make_command(self.root, {"firmware_target": "test_target"}, 2),
                                         cwd=self.px4, text=True)
        self.assertEqual(json.loads(output), ["-DEXTERNAL_MODULES_LOCATION:STRING=" + str(self.root)])

if __name__ == "__main__":
    unittest.main()
