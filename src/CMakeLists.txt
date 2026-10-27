# PX4's documented external-module entry point (EXTERNAL_MODULES_LOCATION/src).
# External modules are visited before PX4's internal libraries are created.
set(config_module_list_external
    drivers/hygrometer/shtc3
    systemcmds/shtc3_probe
    PARENT_SCOPE
)

# Sensor modules can also run without the surveyor MAVLink extension. The fork
# appends its messages to the board's selected dialect when explicitly enabled.
option(HYRUS_MAVLINK "Build the HyRUS surveyor MAVLink extension" ON)
if(HYRUS_MAVLINK)
    foreach(_hyrus_file hyrus/dialect.cmake hyrus/hyrus.xml.in streams/SENS_ATMOS.hpp)
        if(NOT EXISTS "${PX4_SOURCE_DIR}/src/modules/mavlink/${_hyrus_file}")
            message(FATAL_ERROR
                "HyRUS MAVLink addon is missing ${_hyrus_file}. Use the integration fork or apply the addon commit; sensor-only builds can set HYRUS_MAVLINK=OFF.")
        endif()
    endforeach()
endif()
