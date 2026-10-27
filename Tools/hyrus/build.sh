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
cmake_args=()
while (($#)); do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --px4-dir) value_required "$@"; px4_dir=$2; shift 2 ;;
        --target) value_required "$@"; target=$2; shift 2 ;;
        --build-dir) value_required "$@"; build_dir=$2; shift 2 ;;
        --jobs) value_required "$@"; jobs=$2; shift 2 ;;
        --configure-only) configure_only=true; shift ;;
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
done

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
    "-DHYRUS_EXTERNAL_SOURCE=$module_dir" "-DHYRUS_TARGET=$target" -P "$helper"

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
printf 'Firmware: %s\n' "$image"
