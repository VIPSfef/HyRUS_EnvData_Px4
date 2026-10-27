cmake_minimum_required(VERSION 3.21)
project(HyRUS_EnvData_Px4 LANGUAGES CXX)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
  message(FATAL_ERROR "Use an out-of-source build, e.g. cmake -S . -B build/native")
endif()

# Host tests compile the production protocol and stream cores with stub buses.
# The actual firmware is built in the pinned external PX4 checkout.
enable_testing()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME overlay_safety
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/support/px4/test_apply_overlay.py)
foreach(module shtc3 shtc3_probe sens_atmos)
  add_subdirectory(src/px4/${module}/tests)
endforeach()
