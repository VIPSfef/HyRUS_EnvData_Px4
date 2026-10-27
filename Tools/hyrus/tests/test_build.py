"""Exercise the Bash entrypoint without compiling ARM firmware or editing Git."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipIf(os.name == "nt", "The direct build entrypoint targets Ubuntu/WSL")
class DirectBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hyrus build ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        # Shell syntax in paths must remain ordinary filename characters.
        self.root = self.base / "external $(touch injected); modules"
        self.px4 = self.base / "PX4 source"
        self.bin = self.base / "tools"
        self.bin.mkdir()
        self.px4.mkdir()
        self.log = self.base / "commands.jsonl"
        self.bash = shutil.which("bash")
        self.real_cmake = shutil.which("cmake")
        if not self.bash or not self.real_cmake:
            self.skipTest("bash and cmake are required for CLI tests")
        source = Path(__file__).resolve().parents[1]
        scripts = self.root / "Tools/hyrus"
        scripts.mkdir(parents=True)
        for name in ("build.sh", "build_config.cmake"):
            shutil.copyfile(source / name, scripts / name)
        self.script = scripts / "build.sh"
        (scripts / "project.json").write_text(json.dumps({"firmware_target": "fixture_board_default"}))
        (self.px4 / "CMakeLists.txt").write_text("# User source must be preserved\n")
        self.env = dict(os.environ, PATH=str(self.bin), HYRUS_TEST_LOG=str(self.log),
                        HYRUS_TEST_REAL_CMAKE=self.real_cmake)
        for name in ("dirname", "realpath"):
            os.symlink(shutil.which(name), self.bin / name)
        for name in ("ninja", "make", "python3", "gcc", "g++", "arm-none-eabi-gcc", "arm-none-eabi-g++"):
            self.tool(name, "import sys\nsys.exit(0)\n")
        self.tool("nproc", "print(3)\n")
        self.tool("git", """import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['HYRUS_TEST_LOG'], 'a') as f:
    f.write(json.dumps(['git', *args]) + '\\n')
if args[0] != '-C':
    raise SystemExit('Unexpected Git invocation')
if args[2:] == ['rev-parse', '--show-toplevel']:
    print(Path(args[1]).resolve())
elif args[2:] == ['submodule', 'status', '--recursive']:
    print(os.environ.get('HYRUS_TEST_SUBMODULES', ''))
else:
    raise SystemExit('Unexpected Git mutation or command')
""")
        self.tool("cmake", """import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if '-P' in args:
    os.execv(os.environ['HYRUS_TEST_REAL_CMAKE'], [os.environ['HYRUS_TEST_REAL_CMAKE'], *args])
with open(os.environ['HYRUS_TEST_LOG'], 'a') as f:
    f.write(json.dumps(['cmake', *args]) + '\\n')
if '--build' in args:
    directory = Path(args[args.index('--build') + 1])
    target = next(line.split('=', 1)[1] for line in (directory / 'CMakeCache.txt').read_text().splitlines() if line.startswith('CONFIG:'))
    if not os.environ.get('HYRUS_TEST_NO_IMAGE'):
        (directory / (target + '.px4')).write_bytes(b'firmware fixture')
else:
    directory = Path(args[args.index('-B') + 1])
    directory.mkdir(parents=True, exist_ok=True)
    target = next(arg.split('=', 1)[1] for arg in args if arg.startswith('-DCONFIG:'))
    external = next(arg.split('=', 1)[1] for arg in args if arg.startswith('-DEXTERNAL_MODULES_LOCATION:'))
    source = args[args.index('-S') + 1]
    (directory / 'CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL=' + source + '\\nEXTERNAL_MODULES_LOCATION:PATH=' + external + '\\nCONFIG:STRING=' + target + '\\nCMAKE_GENERATOR:INTERNAL=Ninja\\n')
""")

    def tool(self, name, code):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + code)
        path.chmod(0o755)

    def run_build(self, *arguments, **environment):
        env = dict(self.env, **environment)
        return subprocess.run([self.bash, str(self.script), "--px4-dir", str(self.px4), *arguments],
                              cwd=self.base, env=env, text=True, capture_output=True)

    def commands(self, tool=None):
        commands = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return [command for command in commands if tool is None or command[0] == tool]

    def test_help_needs_no_toolchain(self):
        result = self.run_build("--help", PATH="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--configure-only", result.stdout)
        self.assertEqual(self.commands(), [])

    def test_build_preserves_paths_and_sources_without_python_helpers(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        configure, build = self.commands("cmake")
        self.assertIn("-DEXTERNAL_MODULES_LOCATION:PATH=" + str(self.root), configure)
        self.assertIn("-DCONFIG:STRING=fixture_board_default", configure)
        self.assertEqual(build[-2:], ["--parallel", "3"])
        self.assertTrue((self.px4 / "build/fixture_board_default/fixture_board_default.px4").is_file())
        self.assertEqual((self.px4 / "CMakeLists.txt").read_text(), "# User source must be preserved\n")
        self.assertFalse((self.base / "injected").exists())
        self.assertEqual(len(self.commands("git")), 2)

    def test_override_target_jobs_and_build_directory(self):
        directory = self.base / "output with spaces"
        result = self.run_build("--target", "other_board_default", "--jobs", "7", "--build-dir", str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        configure, build = self.commands("cmake")
        self.assertIn("-DCONFIG:STRING=other_board_default", configure)
        self.assertEqual(build, ["cmake", "--build", str(directory), "--parallel", "7"])

    def test_configure_only_does_not_compile_or_require_an_image(self):
        result = self.run_build("--configure-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.commands("cmake")), 1)
        self.assertFalse(list(self.px4.rglob("*.px4")))

    def test_invalid_cli_values_stop_before_configure(self):
        for arguments in (("--jobs", "0"), ("--target", "../outside"), ("--jobs",), ("--unknown",)):
            with self.subTest(arguments=arguments):
                result = self.run_build(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.commands("cmake"), [])

    def test_missing_tool_has_setup_instruction(self):
        (self.bin / "arm-none-eabi-gcc").unlink()
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arm-none-eabi-gcc", result.stderr)
        self.assertIn("ubuntu.sh", result.stderr)
        self.assertEqual(self.commands("cmake"), [])

    def test_missing_or_mismatched_submodule_is_not_automatically_updated(self):
        for marker in ("-", "+", "U"):
            with self.subTest(marker=marker):
                result = self.run_build(HYRUS_TEST_SUBMODULES=marker + "a" * 40 + " source/module")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("submodule update --init --recursive", result.stderr)
                self.assertEqual(self.commands("cmake"), [])

    def test_build_output_cannot_replace_source_or_its_parent(self):
        for directory in (self.px4, self.root, self.base):
            with self.subTest(directory=directory):
                result = self.run_build("--build-dir", str(directory))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must not contain", result.stderr)
                self.assertEqual(self.commands("cmake"), [])

    def test_existing_matching_cache_can_be_reused(self):
        self.assertEqual(self.run_build("--configure-only").returncode, 0)
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cache_from_another_build_is_preserved_and_refused(self):
        directory = self.base / "cache test"
        directory.mkdir()
        original = {"CMAKE_HOME_DIRECTORY": str(self.px4), "EXTERNAL_MODULES_LOCATION": str(self.root),
                    "CONFIG": "fixture_board_default", "CMAKE_GENERATOR": "Ninja"}
        cache = directory / "CMakeCache.txt"
        for key in original:
            with self.subTest(key=key):
                wrong = dict(original, **{key: "different"})
                text = "".join(name + ":STRING=" + value + "\n" for name, value in wrong.items())
                cache.write_text(text)
                result = self.run_build("--build-dir", str(directory))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("different source, module, target, or generator", " ".join(result.stderr.split()))
                self.assertEqual(cache.read_text(), text)
                self.assertEqual(self.commands("cmake"), [])

    def test_successful_command_without_firmware_is_not_reported_as_success(self):
        result = self.run_build(HYRUS_TEST_NO_IMAGE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without the expected firmware image", result.stderr)

    def test_explicit_cmake_definitions_keep_argument_boundaries(self):
        result = self.run_build("--configure-only", "--", "-DHYRUS_MAVLINK=OFF", "-DMESSAGE:STRING=one two; three")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands("cmake")[0][-2:], ["-DHYRUS_MAVLINK=OFF", "-DMESSAGE:STRING=one two; three"])

    def test_extra_arguments_cannot_override_source_or_target(self):
        for argument in ("-S/another/source", "-DCONFIG=other", "-DEXTERNAL_MODULES_LOCATION:PATH=/another/module"):
            with self.subTest(argument=argument):
                result = self.run_build("--", argument)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.commands("cmake"), [])


if __name__ == "__main__":
    unittest.main()
