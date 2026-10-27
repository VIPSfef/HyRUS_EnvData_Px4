# Read policy/cache data without requiring a custom Python build entrypoint.
cmake_minimum_required(VERSION 3.21)

if(DEFINED HYRUS_MANIFEST)
    file(READ "${HYRUS_MANIFEST}" _policy)
    string(JSON _target ERROR_VARIABLE _error GET "${_policy}" firmware_target)
    if(_error OR NOT _target MATCHES "^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
        message(FATAL_ERROR "project.json must contain a valid firmware_target")
    endif()
    execute_process(COMMAND "${CMAKE_COMMAND}" -E echo "${_target}" COMMAND_ERROR_IS_FATAL ANY)
    return()
endif()

foreach(_required HYRUS_BUILD_DIR HYRUS_PX4_SOURCE HYRUS_EXTERNAL_SOURCE HYRUS_TARGET)
    if(NOT DEFINED ${_required} OR "${${_required}}" STREQUAL "")
        message(FATAL_ERROR "Missing build configuration input: ${_required}")
    endif()
endforeach()
if(NOT EXISTS "${HYRUS_BUILD_DIR}/CMakeCache.txt")
    return()
endif()

load_cache("${HYRUS_BUILD_DIR}" READ_WITH_PREFIX _previous_
    CMAKE_HOME_DIRECTORY EXTERNAL_MODULES_LOCATION CONFIG CMAKE_GENERATOR)
foreach(_key CMAKE_HOME_DIRECTORY EXTERNAL_MODULES_LOCATION CONFIG CMAKE_GENERATOR)
    if(NOT DEFINED _previous_${_key} OR "${_previous_${_key}}" STREQUAL "")
        message(FATAL_ERROR "Existing CMake cache lacks ${_key}; select a new --build-dir")
    endif()
endforeach()
file(REAL_PATH "${_previous_CMAKE_HOME_DIRECTORY}" _previous_source)
file(REAL_PATH "${_previous_EXTERNAL_MODULES_LOCATION}" _previous_external)
if(NOT "${_previous_source}" STREQUAL "${HYRUS_PX4_SOURCE}"
   OR NOT "${_previous_external}" STREQUAL "${HYRUS_EXTERNAL_SOURCE}"
   OR NOT "${_previous_CONFIG}" STREQUAL "${HYRUS_TARGET}"
   OR NOT "${_previous_CMAKE_GENERATOR}" STREQUAL "Ninja")
    message(FATAL_ERROR "Existing CMake cache belongs to a different source, module, target, or generator; select a new --build-dir")
endif()
