# PX4's documented external-module entry point (EXTERNAL_MODULES_LOCATION/src).
# External modules are visited before PX4's internal libraries are created.
set(config_module_list_external
    drivers/hygrometer/shtc3
    systemcmds/shtc3_probe
    PARENT_SCOPE
)

# The sensor module is external; connecting its stream to PX4's existing
# MAVLink task uses integration already committed in the pinned firmware fork.
file(READ "${PX4_SOURCE_DIR}/src/modules/mavlink/CMakeLists.txt" _hyrus_mavlink_cmake)
string(FIND "${_hyrus_mavlink_cmake}" "hyrus/dialect.cmake" _hyrus_mavlink_hook)
if(_hyrus_mavlink_hook LESS 0)
    message(FATAL_ERROR
        "HyRUS MAVLink integration is missing. Use the firmware fork commit recorded in Tools/hyrus/project.json.")
endif()
foreach(_hyrus_file hyrus/dialect.cmake hyrus/weather.xml streams/SENS_ATMOS.hpp)
    if(NOT EXISTS "${PX4_SOURCE_DIR}/src/modules/mavlink/${_hyrus_file}")
        message(FATAL_ERROR "HyRUS firmware fork is missing ${_hyrus_file}.")
    endif()
endforeach()

# Keep other consumers (for example simulator_mavlink) on the same dialect.
# This is a normal configure variable; it does not edit PX4's board files.
set(CONFIG_MAVLINK_DIALECT weather PARENT_SCOPE)
