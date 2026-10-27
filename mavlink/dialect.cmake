# This small MAVLink hook is maintained by HyRUS. Sensor modules themselves
# enter PX4 through the official EXTERNAL_MODULES_LOCATION mechanism.
# Stage our XML wrapper beside unchanged official definitions in the build tree.
if(NOT CONFIG_MAVLINK_DIALECT STREQUAL "weather")
  message(FATAL_ERROR "HyRUS external modules must select the weather dialect")
endif()
include_directories("${CMAKE_CURRENT_LIST_DIR}")
add_compile_definitions(HYRUS_EXTERNAL_MAVLINK=1)
set(MAVLINK_PRIMARY_XML "${MAVLINK_GIT_DIR}/message_definitions/v1.0/${CONFIG_MAVLINK_DIALECT}.xml")
set(_hyrus_wrapper "${CMAKE_CURRENT_LIST_DIR}/${CONFIG_MAVLINK_DIALECT}.xml")
if(EXISTS "${_hyrus_wrapper}")
  set(_hyrus_definitions "${CMAKE_CURRENT_BINARY_DIR}/hyrus_message_definitions")
  set(MAVLINK_PRIMARY_XML "${_hyrus_definitions}/${CONFIG_MAVLINK_DIALECT}.xml")
  file(GLOB _hyrus_official_xml CONFIGURE_DEPENDS
    "${MAVLINK_GIT_DIR}/message_definitions/v1.0/*.xml")
  add_custom_command(
    OUTPUT "${MAVLINK_PRIMARY_XML}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${_hyrus_definitions}"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${MAVLINK_GIT_DIR}/message_definitions/v1.0" "${_hyrus_definitions}"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${_hyrus_wrapper}" "${MAVLINK_PRIMARY_XML}"
    COMMAND ${CMAKE_COMMAND} -E touch "${MAVLINK_PRIMARY_XML}"
    DEPENDS git_mavlink_v2 "${_hyrus_wrapper}" ${_hyrus_official_xml}
    COMMENT "Preparing ${CONFIG_MAVLINK_DIALECT} with unchanged official MAVLink definitions"
    VERBATIM)
endif()
