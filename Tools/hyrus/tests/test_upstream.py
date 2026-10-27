"""Real Git regressions for fork preparation, merges and paired review bundles."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_common
from ci_common import POLICY_PATH, check_device_type, firmware_profile, git, git_text, json_write, read_policy
from firmware import MODULE_FILES, prepare as firmware_prepare, require_clean_firmware, verify_fork
from upstream import check_pin_candidate, package, prepare
from validate import verify_source_snapshot


class ExternalFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hyrus test ")
        self.addCleanup(self.temp.cleanup)
        self.base_dir = Path(self.temp.name)
        self.root = self.base_dir / "external modules"
        self.source = self.base_dir / "official"
        self.fork = self.base_dir / "fork"
        self.px4 = self.base_dir / "checkout"
        for directory in (self.root, self.source):
            directory.mkdir()
            git(directory, "init", "-b", "main")
            self.configure(directory)
        self.write(self.source, "src/modules/mavlink/CMakeLists.txt", "first\noriginal\nlast\n")
        self.write(self.source, "src/drivers/drv_sensor.h", "#define DRV_MAG_DEVTYPE_A 0xB8\n")
        self.commit(self.source, "Official baseline")
        self.upstream_pin = git_text(self.source, "rev-parse", "HEAD")
        git(self.base_dir, "clone", str(self.source), str(self.fork))
        self.configure(self.fork)
        git(self.fork, "switch", "-c", ci_common.FORK_BRANCH)
        self.write(self.fork, "src/modules/mavlink/CMakeLists.txt", "first\nexternal integration\nlast\n")
        self.commit(self.fork, "MAVLink integration")
        self.fork_pin = git_text(self.fork, "rev-parse", "HEAD")
        git(self.base_dir, "clone", str(self.fork), str(self.px4))
        self.configure(self.px4)
        for name in MODULE_FILES:
            self.write(self.root, name, "// fixture\n")
        self.write(self.root, "src/drivers/hygrometer/shtc3/SHTC3Device.hpp",
                   "enum class DeviceType : unsigned char { Shtc3 = 0xB9 };\n")
        self.write(self.root, ".gitignore", "build/\n")
        for name in ci_common.ACTIVE_WORKFLOWS:
            self.write(self.root, ".github/workflows/" + name, "name: fixture\n")
        self.policy = {"upstream_url": str(self.source), "upstream_branch": "main",
                       "upstream_commit": self.upstream_pin, "fork_url": str(self.fork),
                       "fork_branch": ci_common.FORK_BRANCH, "px4_commit": self.fork_pin,
                       "firmware_target": "test_target"}
        json_write(self.root / POLICY_PATH, self.policy)
        self.commit(self.root, "External modules baseline")
        self.external_base = git_text(self.root, "rev-parse", "HEAD")
        self.output = self.root / "build/proposal"
        constants = patch.multiple(ci_common, UPSTREAM_URL=str(self.source), FORK_URL=str(self.fork))
        constants.start()
        self.addCleanup(constants.stop)

    @staticmethod
    def configure(directory):
        git(directory, "config", "user.name", "Test")
        git(directory, "config", "user.email", "test@example.invalid")
        git(directory, "config", "core.autocrlf", "false")

    @staticmethod
    def write(root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def commit(root, message):
        git(root, "add", ".")
        git(root, "commit", "-m", message)

    def advance(self, conflict=False):
        name = "src/modules/mavlink/CMakeLists.txt" if conflict else "upstream.txt"
        content = "first\nupstream replacement\nlast\n" if conflict else "new upstream content\n"
        self.write(self.source, name, content)
        self.commit(self.source, "New official main")
        return git_text(self.source, "rev-parse", "HEAD")

    def candidate(self):
        self.advance()
        return prepare(self.root, self.output, self.px4)

    def stable_policy(self):
        selected = firmware_profile("r2026b")
        git(self.source, "tag", "-a", "v1.16.1", self.upstream_pin, "-m", "Official release")
        git(self.fork, "branch", selected.fork_branch, self.fork_pin)
        policy = dict(self.policy, upstream_ref=selected.upstream_ref, fork_branch=selected.fork_branch)
        del policy["upstream_branch"]
        json_write(self.root / selected.manifest, policy)
        self.commit(self.root, "Stable Simulink profile")
        self.external_base = git_text(self.root, "rev-parse", "HEAD")
        return policy

    def record_validation(self, report, **overrides):
        result = {"passed": True, "profile": "main", "source_commit": report["candidate"],
                  "px4_commit": report["fork_candidate"], "upstream_commit": report["upstream"]}
        result.update(overrides)
        json_write(self.output / "validation.json", result)

    def add_submodule(self):
        dependency = self.base_dir / "dependency"
        dependency.mkdir()
        git(dependency, "init", "-b", "main")
        self.configure(dependency)
        self.write(dependency, "data.txt", "original\n")
        self.commit(dependency, "Dependency")
        first = git_text(dependency, "rev-parse", "HEAD")
        self.write(dependency, "data.txt", "updated\n")
        self.commit(dependency, "Dependency update")
        git(self.px4, "-c", "protocol.file.allow=always", "submodule", "add", str(dependency), "dependency")
        self.commit(self.px4, "Recorded submodule")
        return self.px4 / "dependency", first

    def test_fork_preparation_is_repeatable_without_source_edits(self):
        for _ in range(2):
            firmware_prepare(self.root, self.px4, update_submodules=False)
            verify_fork(self.root, self.px4)
            self.assertEqual(git_text(self.px4, "status", "--porcelain"), "")
            self.assertEqual(git_text(self.px4, "rev-parse", "HEAD"), self.fork_pin)
        self.assertIn("external integration", (self.px4 / "src/modules/mavlink/CMakeLists.txt").read_text())

    def test_fresh_checkout_is_cloned_from_the_fork(self):
        fresh = self.base_dir / "fresh checkout"
        firmware_prepare(self.root, fresh, update_submodules=False)
        self.assertEqual(git_text(fresh, "remote", "get-url", "origin"), str(self.fork))
        self.assertEqual(git_text(fresh, "rev-parse", "HEAD"), self.fork_pin)

    def test_stable_profile_uses_annotated_release_tag_even_after_main_advances(self):
        stable = self.stable_policy()
        self.advance()
        fresh = self.base_dir / "stable checkout"
        firmware_prepare(self.root, fresh, update_submodules=False, profile="r2026b")
        self.assertEqual(git_text(fresh, "rev-parse", "HEAD"), self.fork_pin)
        self.assertEqual(git_text(fresh, "rev-parse", "v1.16.1^{commit}"), self.upstream_pin)
        self.assertEqual(verify_fork(self.root, fresh, profile="r2026b"),
                         ["src/modules/mavlink/CMakeLists.txt"])
        self.assertEqual(read_policy(self.root, "r2026b"), stable)
        self.assertEqual(read_policy(self.root), self.policy)

    def test_stable_profile_rejects_wrong_release_commit_without_moving_checkout(self):
        stable = self.stable_policy()
        stable["upstream_commit"] = self.advance()
        json_write(self.root / firmware_profile("r2026b").manifest, stable)
        with self.assertRaisesRegex(ValueError, "does not match the fetched official release tag"):
            firmware_prepare(self.root, self.px4, update_submodules=False, profile="r2026b")
        self.assertEqual(git_text(self.px4, "rev-parse", "HEAD"), self.fork_pin)
        self.assertEqual(git_text(self.px4, "status", "--porcelain"), "")

    def test_stable_profile_rejects_moving_main_reference_and_wrong_fork_branch(self):
        stable = self.stable_policy()
        path = self.root / firmware_profile("r2026b").manifest
        for changes, message in (({"upstream_ref": "refs/heads/main"}, "official PX4 refs/tags/v1.16.1"),
                                 ({"fork_branch": ci_common.FORK_BRANCH}, "firmware branch hyrus/r2026b")):
            with self.subTest(changes=changes):
                json_write(path, dict(stable, **changes))
                with self.assertRaisesRegex(ValueError, message):
                    read_policy(self.root, "r2026b")

    def test_profiles_keep_separate_default_sources_native_caches_and_results(self):
        for stem in ("px4", "hyrus-native", "hyrus-ci"):
            with self.subTest(stem=stem):
                main = firmware_profile().build_dir(self.root, stem)
                stable = firmware_profile("r2026b").build_dir(self.root, stem)
                self.assertEqual(main, self.root / "build" / stem)
                self.assertEqual(stable, self.root / "build" / (stem + "-r2026b"))
                self.assertNotEqual(main, stable)
        with self.assertRaisesRegex(ValueError, "Unknown firmware profile"):
            read_policy(self.root, "../other")

    def test_main_candidate_does_not_change_stable_manifest(self):
        stable = self.stable_policy()
        report = self.candidate()
        self.assertTrue(report["changed"])
        self.assertEqual(read_policy(self.root, "r2026b"), stable)
        self.assertEqual(git_text(self.root, "diff", "--name-only", self.external_base, report["candidate"]),
                         POLICY_PATH)

    def test_unrelated_px4_edit_is_preserved_and_refused(self):
        path = self.px4 / "src/modules/mavlink/CMakeLists.txt"
        path.write_text(path.read_text() + "user change\n")
        with self.assertRaisesRegex(ValueError, "clean"):
            firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertIn("user change", path.read_text())

    def test_untracked_px4_file_is_preserved_and_refused(self):
        self.write(self.px4, "user.txt", "do not remove\n")
        with self.assertRaisesRegex(ValueError, "clean"):
            firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertEqual((self.px4 / "user.txt").read_text(), "do not remove\n")

    def test_dirty_submodule_is_preserved_before_checkout(self):
        dependency, _ = self.add_submodule()
        self.write(dependency, "data.txt", "user submodule change\n")
        with self.assertRaisesRegex(ValueError, "submodules contain local changes"):
            firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertEqual((dependency / "data.txt").read_text(), "user submodule change\n")

    def test_clean_submodule_revision_can_be_refreshed(self):
        dependency, first = self.add_submodule()
        git(dependency, "checkout", "--detach", first)
        require_clean_firmware(self.px4)

    def test_snapshot_rejects_a_clean_external_commit_change(self):
        snapshot = git_text(self.px4, "submodule", "status", "--recursive").splitlines()
        verify_source_snapshot(self.root, self.px4, self.external_base, snapshot)
        self.write(self.root, "src/CMakeLists.txt", "// newly committed source\n")
        self.commit(self.root, "Source changed while validation was running")
        self.assertEqual(git_text(self.root, "status", "--porcelain"), "")
        with self.assertRaisesRegex(ValueError, "External module commit changed"):
            verify_source_snapshot(self.root, self.px4, self.external_base, snapshot)

    def test_snapshot_rejects_a_clean_submodule_revision_change(self):
        dependency, first = self.add_submodule()
        snapshot = git_text(self.px4, "submodule", "status", "--recursive").splitlines()
        verify_source_snapshot(self.root, self.px4, self.external_base, snapshot)
        git(dependency, "checkout", "--detach", first)
        self.assertEqual(git_text(dependency, "status", "--porcelain"), "")
        require_clean_firmware(self.px4)
        with self.assertRaisesRegex(ValueError, "submodule commits changed"):
            verify_source_snapshot(self.root, self.px4, self.external_base, snapshot)

    def test_snapshot_ignores_informational_submodule_tag_changes(self):
        dependency, _ = self.add_submodule()
        snapshot = git_text(self.px4, "submodule", "status", "--recursive").splitlines()
        git(dependency, "tag", "v1.0.0")
        current = git_text(self.px4, "submodule", "status", "--recursive").splitlines()
        self.assertNotEqual(snapshot, current)
        verify_source_snapshot(self.root, self.px4, self.external_base, snapshot)

    def test_custom_fork_commit_cannot_be_declared_as_official_base(self):
        self.write(self.px4, "src/modules/mavlink/mavlink_messages.cpp", "// more integration\n")
        self.commit(self.px4, "Additional integration")
        fork_head = git_text(self.px4, "rev-parse", "HEAD")
        spoofed = dict(self.policy, upstream_commit=self.fork_pin, px4_commit=fork_head)
        # An ancestry/diff-only check accepts this pair; provenance must also
        # prove that the claimed upstream is actually in official main.
        verify_fork(self.root, self.px4, spoofed)
        json_write(self.root / POLICY_PATH, spoofed)
        self.commit(self.root, "Incorrectly declared upstream")
        with self.assertRaisesRegex(ValueError, "outside the fetched official main history"):
            firmware_prepare(self.root, self.px4, update_submodules=False)
        self.assertEqual(git_text(self.px4, "rev-parse", "HEAD"), fork_head)
        self.assertEqual(git_text(self.px4, "status", "--porcelain"), "")


    def test_fork_changes_outside_mavlink_are_refused(self):
        self.write(self.px4, "src/drivers/drv_sensor.h", "// unrelated fork change\n")
        self.commit(self.px4, "Unexpected change")
        invalid = dict(self.policy, px4_commit=git_text(self.px4, "rev-parse", "HEAD"))
        with self.assertRaisesRegex(ValueError, "allowlist"):
            verify_fork(self.root, self.px4, invalid)

    def test_missing_external_source_is_rejected(self):
        (self.root / MODULE_FILES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            verify_fork(self.root, self.px4)

    def test_device_allocation_is_dynamic_and_collision_checked(self):
        self.assertEqual(check_device_type(self.root, self.px4)["value"], 185)
        self.write(self.px4, "src/drivers/drv_sensor.h", "#define DRV_IMU_DEVTYPE_NEW 185\n")
        with self.assertRaisesRegex(ValueError, "collides"):
            check_device_type(self.root, self.px4)

    def test_merge_candidate_keeps_both_trusted_branches_unchanged(self):
        report = self.candidate()
        check_pin_candidate(self.root, self.external_base, report["candidate"], report["upstream"], report["fork_candidate"])
        self.assertEqual(git_text(self.root, "rev-parse", "main"), self.external_base)
        self.assertEqual(git_text(self.fork, "rev-parse", ci_common.FORK_BRANCH), self.fork_pin)
        self.assertEqual(git_text(self.px4, "show", "-s", "--format=%P", "HEAD").split(),
                         [self.fork_pin, report["upstream"]])
        self.assertEqual((self.px4 / "upstream.txt").read_text(), "new upstream content\n")
        self.assertEqual(verify_fork(self.root, self.px4), ["src/modules/mavlink/CMakeLists.txt"])

    def test_two_bundles_contain_the_exact_validated_candidates(self):
        report = self.candidate()
        self.record_validation(report)
        package(self.root, self.output, self.px4)
        for directory, filename, commit in (
                (self.root, "candidate.bundle", report["candidate"]),
                (self.px4, "firmware-candidate.bundle", report["fork_candidate"])):
            bundle = str(self.output / filename)
            git(directory, "bundle", "verify", bundle)
            self.assertEqual(git_text(directory, "bundle", "list-heads", bundle).split(), [commit, "HEAD"])
        saved = json.loads((self.output / "candidate.json").read_text())
        self.assertEqual(saved["state"], "validated")
        self.assertEqual(saved["bundles"], ["candidate.bundle", "firmware-candidate.bundle"])

    def test_repeated_pair_makes_same_candidates_and_current_is_noop(self):
        current = prepare(self.root, self.output, self.px4)
        self.assertFalse(current["changed"])
        self.assertEqual(git_text(self.root, "symbolic-ref", "--short", "HEAD"), "main")
        self.advance()
        first = prepare(self.root, self.output, self.px4)
        git(self.root, "switch", "main")
        second = prepare(self.root, self.output, self.px4)
        self.assertEqual(first["candidate"], second["candidate"])
        self.assertEqual(first["fork_candidate"], second["fork_candidate"])

    def test_conflicting_upstream_does_not_advance_or_dirty_sources(self):
        self.advance(conflict=True)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            prepare(self.root, self.output, self.px4)
        self.assertEqual(git_text(self.root, "rev-parse", "HEAD"), self.external_base)
        self.assertEqual(git_text(self.px4, "rev-parse", "HEAD"), self.fork_pin)
        self.assertEqual(git_text(self.px4, "status", "--porcelain"), "")
        self.assertNotEqual(git(self.px4, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode, 0)
        self.assertEqual(json.loads((self.output / "candidate.json").read_text())["state"], "rejected")

    def test_unreviewed_fork_tip_is_not_used(self):
        self.write(self.fork, "unreviewed.txt", "moving branch\n")
        self.commit(self.fork, "Unreviewed change")
        self.candidate()
        self.assertFalse((self.px4 / "unreviewed.txt").exists())

    def test_dirty_external_source_is_preserved(self):
        self.write(self.root, "src/CMakeLists.txt", "user work\n")
        self.advance()
        with self.assertRaisesRegex(ValueError, "clean"):
            prepare(self.root, self.output, self.px4)
        self.assertEqual((self.root / "src/CMakeLists.txt").read_text(), "user work\n")

    def test_stale_validation_is_refused(self):
        report = self.candidate()
        self.record_validation(report, px4_commit=self.fork_pin)
        with self.assertRaisesRegex(ValueError, "exact module"):
            package(self.root, self.output, self.px4)
        self.assertFalse((self.output / "candidate.bundle").exists())

    def test_stable_validation_cannot_approve_main_candidate(self):
        report = self.candidate()
        self.record_validation(report, profile="r2026b")
        with self.assertRaisesRegex(ValueError, "exact module"):
            package(self.root, self.output, self.px4)
        self.assertFalse((self.output / "candidate.bundle").exists())

    def test_extra_candidate_file_is_refused(self):
        report = self.candidate()
        self.write(self.root, "extra.txt", "unexpected\n")
        git(self.root, "add", "extra.txt")
        git(self.root, "commit", "--amend", "--no-edit")
        with self.assertRaisesRegex(ValueError, "other than"):
            check_pin_candidate(self.root, self.external_base, git_text(self.root, "rev-parse", "HEAD"),
                                report["upstream"], report["fork_candidate"])

if __name__ == "__main__":
    unittest.main()
