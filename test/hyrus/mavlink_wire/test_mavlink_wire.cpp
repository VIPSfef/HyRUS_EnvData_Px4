// Validate the firmware's generated dialect against the Router input contract.
#include <weather/mavlink.h>
#include <cstdio>
#include <cstdlib>

static unsigned checks, failures;
#define CHECK(condition) do { ++checks; if (!(condition)) { \
  ++failures; std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
} } while (0)

static mavlink_message_t roundtrip(const mavlink_message_t &message)
{
  uint8_t bytes[MAVLINK_MAX_PACKET_LEN] {};
  const uint16_t size = mavlink_msg_to_send_buffer(bytes, &message);
  mavlink_message_t decoded {};
  mavlink_status_t status {};
  unsigned received = 0;
  CHECK(message.magic == MAVLINK_STX);
  CHECK(message.magic == 0xfd); // These extended IDs require MAVLink 2.
  for (uint16_t i = 0; i < size; ++i) {
    received += mavlink_parse_char(MAVLINK_COMM_0, bytes[i], &decoded, &status);
  }
  CHECK(received == 1);
  CHECK(decoded.msgid == message.msgid);
  CHECK(decoded.sysid == 1 && decoded.compid == 1);
  return decoded;
}

int main()
{
  static_assert(MAVLINK_MSG_ID_SENS_ATMOS == 8009, "Router SENS_ATMOS message ID changed");
  static_assert(MAVLINK_MSG_ID_SENS_ATMOS_LEN == 16, "Router SENS_ATMOS payload changed");
  static_assert(MAVLINK_MSG_ID_SENS_ATMOS_CRC == 144, "Router SENS_ATMOS field contract changed");
  static_assert(MAVLINK_MSG_ID_HYGROMETER_SENSOR == 12920, "Router HYGROMETER_SENSOR message ID changed");
  static_assert(MAVLINK_MSG_ID_HYGROMETER_SENSOR_CRC == 20, "Router hygrometer field contract changed");
  mavlink_message_t message {};
  constexpr uint64_t timestamp = 123456789;
  mavlink_msg_sens_atmos_pack(1, 1, &message, timestamp, 23.5f, 65.25f);
  mavlink_message_t received = roundtrip(message);
  mavlink_sens_atmos_t atmosphere {};
  mavlink_msg_sens_atmos_decode(&received, &atmosphere);
  CHECK(atmosphere.timestamp == timestamp);
  CHECK(atmosphere.TempAmbient == 23.5f);
  CHECK(atmosphere.Humidity == 65.25f); // percent RH, not centipercent

  mavlink_msg_hygrometer_sensor_pack(1, 1, &message, 0, 2350, 6525);
  received = roundtrip(message);
  mavlink_hygrometer_sensor_t hygrometer {};
  mavlink_msg_hygrometer_sensor_decode(&received, &hygrometer);
  CHECK(hygrometer.id == 0);
  CHECK(hygrometer.temperature == 2350); // 0.01 degree C
  CHECK(hygrometer.humidity == 6525); // 0.01 percent RH
  std::printf("Generated MAVLink wire: %u checks, %u failures\n", checks, failures);
  return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
