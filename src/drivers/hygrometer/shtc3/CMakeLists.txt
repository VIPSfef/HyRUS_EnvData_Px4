px4_add_module(
	MODULE hyrus__shtc3
	MAIN shtc3
	EXTERNAL
	SRCS
		SHTC3.cpp
		SHTC3.hpp
		SHTC3Device.hpp
		SHTC3Protocol.hpp
	MODULE_CONFIG
		shtc3_params.yaml
)

# PX4 configures external modules before these internal library targets exist.
# Normal links resolve after configure; px4_add_module DEPENDS queries them early.
target_link_libraries(hyrus__shtc3 PRIVATE drivers__device px4_work_queue)
