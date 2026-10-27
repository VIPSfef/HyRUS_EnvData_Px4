cmake_minimum_required(VERSION 3.21)
project(hyrus_firmware_core_tests LANGUAGES CXX)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
  message(FATAL_ERROR "Use cmake -S test/hyrus -B build/hyrus-native")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
enable_testing()
get_filename_component(HYRUS_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

function(hyrus_core_test module test_name)
  add_executable(test_${module} ${module}/test_${module}.cpp)
  target_include_directories(test_${module} PRIVATE ${ARGN})
  if(MSVC)
    target_compile_options(test_${module} PRIVATE /W4 /WX)
  else()
    target_compile_options(test_${module} PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
  add_test(NAME ${test_name} COMMAND test_${module})
endfunction()

set(SHTC3_INCLUDE "${HYRUS_ROOT}/src/drivers/hygrometer/shtc3")
hyrus_core_test(shtc3 shtc3_core "${SHTC3_INCLUDE}")
hyrus_core_test(shtc3_probe shtc3_probe
  "${HYRUS_ROOT}/src/systemcmds/shtc3_probe" "${SHTC3_INCLUDE}")
set(HYRUS_PX4_SOURCE "${HYRUS_ROOT}/build/px4" CACHE PATH "Prepared firmware fork source")
if(NOT EXISTS "${HYRUS_PX4_SOURCE}/src/modules/mavlink/streams/SENS_ATMOS.hpp")
  message(FATAL_ERROR "Prepare the firmware fork first, or set HYRUS_PX4_SOURCE to its checkout")
endif()
hyrus_core_test(sens_atmos sens_atmos_stream
  "${CMAKE_CURRENT_SOURCE_DIR}/sens_atmos/stubs"
  "${HYRUS_PX4_SOURCE}/src/modules/mavlink/streams")

# Full firmware validation supplies its generated dialect, so these checks use
# the actual upstream generator output instead of the stream test's stubs.
set(HYRUS_MAVLINK_HEADERS "" CACHE PATH "Firmware-generated MAVLink header root")
if(HYRUS_MAVLINK_HEADERS)
  hyrus_core_test(mavlink_wire mavlink_wire)
  # Generated upstream C headers use packed anonymous structs. Treat those as
  # external headers while keeping strict warnings on our round-trip test.
  target_include_directories(test_mavlink_wire SYSTEM PRIVATE "${HYRUS_MAVLINK_HEADERS}")
endif()
