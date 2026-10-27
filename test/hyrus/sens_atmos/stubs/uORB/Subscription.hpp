// Test-only uORB boundary; never opens a real subscription or a device.
#pragma once
#include <uORB/topics/sensor_hygrometer.h>
enum class ORB_ID : unsigned { sensor_hygrometer = 42 };
#define ORB_ID(topic) static_cast<unsigned>(ORB_ID::topic)
namespace fake
{
inline constexpr unsigned TOPIC_COUNT = 2;
struct Topic {
	sensor_hygrometer_s sample{};
	bool advertised{false};
	bool unread{false};
};
extern Topic topics[TOPIC_COUNT];
extern unsigned selected_instance;
extern unsigned selected_topic;
extern unsigned update_calls;
extern unsigned advertised_calls;
}
namespace uORB
{
class Subscription
{
public:
	Subscription() = default;
	Subscription(unsigned topic, unsigned instance) : _instance(instance)
	{
		fake::selected_topic = topic;
		fake::selected_instance = instance;
	}
	Subscription(ORB_ID topic, unsigned instance) : Subscription(static_cast<unsigned>(topic), instance) {}
	bool advertised() const
	{
		++fake::advertised_calls;
		return _instance < fake::TOPIC_COUNT && fake::topics[_instance].advertised;
	}
	bool update(sensor_hygrometer_s *sample)
	{
		++fake::update_calls;

		if (_instance >= fake::TOPIC_COUNT || !fake::topics[_instance].advertised || !fake::topics[_instance].unread) { return false; }

		*sample = fake::topics[_instance].sample;
		fake::topics[_instance].unread = false;
		return true;
	}
private:
	unsigned _instance{fake::TOPIC_COUNT};
};
}
