// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstdint>

namespace shtc3
{
// Local allocation shared by device identity and the driver's bus iterator.
// Compatibility checks reject collisions with the selected PX4 drv_sensor.h.
enum class DeviceType : uint8_t {
	Shtc3 = 0xB9,
};
}
