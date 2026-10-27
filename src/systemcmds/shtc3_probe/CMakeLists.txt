px4_add_module(
    MODULE hyrus__shtc3_probe
    MAIN shtc3_probe
    EXTERNAL
    STACK_MAIN 2048
    SRCS
        shtc3_probe.cpp
        SHTC3Probe.hpp
    INCLUDES
        ${CMAKE_CURRENT_LIST_DIR}/../../drivers/hygrometer/shtc3
)
