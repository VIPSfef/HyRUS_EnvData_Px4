# External-module build and PX4 main compatibility

HyRUS stores only the sensor/probe modules, MAVLink integration, tests, and
build policy. Official PX4 is a separate checkout, normally ignored under
build/px4. Its complete commit is fixed in Tools/hyrus/project.json
(px4_commit). baseline_commit records the original baseline.

## Build flow

1. Validate the external module files and the four-path MAVLink patch allowlist.
2. Clone official PX4 with full history and original tags, or reuse an explicitly
   supplied dedicated checkout. Check out px4_commit and its recorded submodules.
3. Apply patches/px4-mavlink.patch. Sensor files remain outside PX4.
4. Build with EXTERNAL_MODULES_LOCATION pointing to this repository.
5. Run native protocol/stream tests, generated-message wire tests, ARM linking,
   command/parameter presence checks, and the local Git workflow regressions.
6. Record both source commits, submodule pins, patch SHA256 and firmware SHA256.

The allowed PX4 changes are:
- src/modules/mavlink/CMakeLists.txt
- src/modules/mavlink/mavlink_messages.cpp
- src/modules/mavlink/mavlink_main.cpp
- src/modules/mavlink/streams/HYGROMETER_SENSOR.hpp

The official external-module API compiles the drivers. The small MAVLink CMake
hook is our maintained integration, not an upstream external-stream API.
Board config, sensor device registry, normal startup and flight-control files
are not patched. Driver startup uses the supplied SD-card extras.txt addon.

## Local commands

Use Ubuntu/WSL, with the checkouts on the Linux filesystem. A clean committed
external-module tree is required for a validation report.

~~~sh
python3 Tools/hyrus/firmware.py prepare
bash build/px4/Tools/setup/ubuntu.sh --no-sim-tools
python3 Tools/hyrus/validate.py --jobs 4
~~~

The official setup script installs development dependencies using sudo.
An existing dedicated PX4 checkout can be selected with --px4-dir /path/to/PX4
on both Python commands. It must be clean or contain exactly the reviewed
MAVLink patch; arbitrary edits and untracked PX4 source are rejected and retained.
Never use shallow submodule clones. Version text does not substitute for exact
source identity; reports record the actual PX4 and NuttX commits.

The firmware and logs are copied into build/hyrus-ci. Test/build failures return
a nonzero status and leave a failed validation.json when validation has begun.
Neither script flashes hardware or modifies the existing GitHub Firmware fork.

## Updates

hyrus-ci.yml runs on main pushes, pull requests, and manual dispatch.
hyrus-upstream.yml checks official main daily at 03:17 UTC (12:17 Korea time)
and by manual dispatch. It creates a detached candidate changing only px4_commit
in project.json. It then applies the same patch and runs the same validation
against that official revision. If source compatibility fails, the pin in main
stays unchanged. No PX4 release-branch history is merged into this module repo.

A passing candidate is packed as a Git bundle. A separate publication job uses
only helper code from the original trusted base, verifies that the candidate
changes only px4_commit, and creates a separate branch and PR. Candidate PX4
build scripts never receive that job's write token. The publisher rejects a
stale base or altered artifact/ref and explicitly dispatches the ordinary CI
workflow for its PR, because GITHUB_TOKEN-created PRs do not trigger it.

Enable Actions and allow Actions to create pull requests in repository settings.
The workflows use repository-scoped GITHUB_TOKEN, not a personal access token.
There is no automatic merge or upload to a device. Build success covers
compilation and the declared regressions, not actual I2C behavior, SITL, flight,
or all upstream behavioral changes.

To inspect a candidate locally, use a disposable clean clone:

~~~sh
python3 Tools/hyrus/upstream.py prepare --output build/hyrus-upstream
# Continue only if candidate.json says changed=true and state=prepared.
python3 Tools/hyrus/firmware.py prepare
bash build/px4/Tools/setup/ubuntu.sh --no-sim-tools
python3 Tools/hyrus/validate.py --output build/hyrus-upstream --jobs 4
python3 Tools/hyrus/upstream.py package --output build/hyrus-upstream
~~~

Artifacts retain reports, preparation/build/test logs, firmware, and successful
candidate bundles for 14 days. Rechecking the same module base and PX4 pin
produces the same candidate commit.
