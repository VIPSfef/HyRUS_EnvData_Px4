#!/usr/bin/env bash
# Build the supplied PX4 checkout directly with CMake; never change Git sources.
set -euo pipefail

usage() {
    printf '%s\n' 'Usage: bash Tools/hyrus/build.sh [options]
  --px4-dir PATH       Prepared PX4 checkout (default: repository/build/px4)
  --target BOARD      PX4 CONFIG (default: project.json firmware_target)
  --build-dir PATH    Build output (default: PX4/build/BOARD)
  --jobs N            Parallel jobs (default: available processors)
  --configure-only    Configure CMake without compiling
  --simulink          Attach HyRUS to a Simulink build and verify linked modules
  --help              Show this help
  -- -DNAME=VALUE ... Additional CMake definitions, e.g. -DHYRUS_MAVLINK=OFF

Requires the PX4 development toolchain and initialized submodules. This script
does not download, check out, patch, install, or flash anything. It builds the
current checkout; use validate.py separately for a pinned validation report.'
}

fail() { printf 'HyRUS build: %s\n' "$*" >&2; exit 1; }
value_required() { [[ $# -ge 2 && -n $2 ]] || fail "$1 needs a value"; }

px4_dir=
target=
build_dir=
jobs=
configure_only=false
simulink=false
cmake_args=()
while (($#)); do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --px4-dir) value_required "$@"; px4_dir=$2; shift 2 ;;
        --target) value_required "$@"; target=$2; shift 2 ;;
        --build-dir) value_required "$@"; build_dir=$2; shift 2 ;;
        --jobs) value_required "$@"; jobs=$2; shift 2 ;;
        --configure-only) configure_only=true; shift ;;
        --simulink) simulink=true; shift ;;
        --) shift; cmake_args=("$@"); break ;;
        *) fail "Unknown option: $1 (use --help)" ;;
    esac
done
for argument in "${cmake_args[@]}"; do
    [[ $argument =~ ^-D([a-zA-Z_][a-zA-Z0-9_]*)(:[a-zA-Z_]+)?= ]] ||
        fail "Only CMake -DNAME=VALUE definitions are accepted after --"
    case "${BASH_REMATCH[1]}" in
        CONFIG|EXTERNAL_MODULES_LOCATION|CMAKE_HOME_DIRECTORY|CMAKE_GENERATOR|CMAKE_CACHEFILE_DIR)
            fail "Use the script's source, target, and build options instead of overriding ${BASH_REMATCH[1]}" ;;
    esac
    if $simulink && [[ ${BASH_REMATCH[1]} == HYRUS_MAVLINK && ${argument#*=} != ON ]]; then
        fail "--simulink requires HYRUS_MAVLINK=ON"
    fi
done
if $simulink && ! $configure_only; then
    command -v arm-none-eabi-nm >/dev/null 2>&1 || fail "Required tool 'arm-none-eabi-nm' is missing"
fi

for tool in cmake git realpath dirname ninja make python3 gcc g++ arm-none-eabi-gcc arm-none-eabi-g++; do
    command -v "$tool" >/dev/null 2>&1 ||
        fail "Required tool '$tool' is missing. Set up the PX4 toolchain with Tools/setup/ubuntu.sh --no-sim-tools."
done

module_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
helper="$module_dir/Tools/hyrus/build_config.cmake"
if [[ -z $target ]]; then
    target=$(cmake "-DHYRUS_MANIFEST=$module_dir/Tools/hyrus/project.json" -P "$helper")
fi
[[ $target =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]] || fail "Invalid PX4 target: $target"
if [[ -z $jobs ]]; then
    jobs=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')
fi
[[ $jobs =~ ^[1-9][0-9]*$ ]] || fail "--jobs must be a positive integer"

px4_dir=$(realpath -m -- "${px4_dir:-$module_dir/build/px4}")
[[ -f $px4_dir/CMakeLists.txt ]] || fail "PX4 source is missing at $px4_dir; clone the firmware repository and initialize its submodules first."
git_root=$(git -C "$px4_dir" rev-parse --show-toplevel) || fail "PX4 source must be a Git checkout"
[[ $(realpath -m -- "$git_root") == "$px4_dir" ]] || fail "--px4-dir must be the root of the PX4 Git checkout"
if $simulink && ! $configure_only && [[ ! -f $px4_dir/src/modules/px4_simulink_app/CMakeLists.txt ]]; then
    fail "Generate the Simulink model into this PX4 checkout first (src/modules/px4_simulink_app/CMakeLists.txt is missing)."
fi
build_dir=$(realpath -m -- "${build_dir:-$px4_dir/build/$target}")
case "$px4_dir/" in "$build_dir/"*) fail "Build output must not contain the PX4 source directory" ;; esac
case "$module_dir/" in "$build_dir/"*) fail "Build output must not contain the external module source directory" ;; esac

submodule_status=$(git -C "$px4_dir" submodule status --recursive) || fail "Cannot read PX4 submodule state"
while IFS= read -r line; do
    case "${line:0:1}" in
        -|+|U) fail "PX4 submodules are missing or do not match this checkout. Run git submodule update --init --recursive in the PX4 directory first." ;;
    esac
done <<< "$submodule_status"

# CMake reads its cache as data and rejects output from another source or target.
cmake "-DHYRUS_BUILD_DIR=$build_dir" "-DHYRUS_PX4_SOURCE=$px4_dir" \
    "-DHYRUS_EXTERNAL_SOURCE=$module_dir" "-DHYRUS_TARGET=$target" \
    "-DHYRUS_ALLOW_EMPTY_EXTERNAL=$simulink" -P "$helper"

if $simulink; then
    cmake_args+=("-DHYRUS_MAVLINK:BOOL=ON")
fi

configure=(cmake -S "$px4_dir" -B "$build_dir" -G Ninja
    "-DCONFIG:STRING=$target" "-DCMAKE_BUILD_TYPE:STRING=MinSizeRel"
    "-DEXTERNAL_MODULES_LOCATION:PATH=$module_dir" "${cmake_args[@]}")
printf 'PX4 source: %s\nExternal modules: %s\nTarget: %s\n' "$px4_dir" "$module_dir" "$target"
"${configure[@]}"
if $configure_only; then
    printf 'Configured: %s\n' "$build_dir"
    exit 0
fi
cmake --build "$build_dir" --parallel "$jobs"
image="$build_dir/$target.px4"
[[ -s $image ]] || fail "CMake completed without the expected firmware image: $image"
if $simulink; then
    elf="$build_dir/$target.elf"
    [[ -s $elf ]] || fail "The linked ELF is missing: $elf"
    symbols=$(arm-none-eabi-nm --defined-only "$elf") || fail "Cannot inspect linked firmware modules"
    declare -A linked=()
    while read -r address kind name; do
        case "$name" in
            px4_simulink_app_main|shtc3_main|shtc3_probe_main) linked[$name]=1 ;;
            *MavlinkStreamSensAtmos*) linked[MavlinkStreamSensAtmos]=1 ;;
        esac
    done <<< "$symbols"
    for required in px4_simulink_app_main shtc3_main shtc3_probe_main MavlinkStreamSensAtmos; do
        [[ ${linked[$required]:-0} == 1 ]] || fail "Required module is absent from the linked firmware: $required. Check the Simulink board configuration."
    done
    printf 'Verified linked modules: Simulink, SHTC3, probe, atmospheric MAVLink stream\n'
fi
printf 'Firmware: %s\n' "$image"
