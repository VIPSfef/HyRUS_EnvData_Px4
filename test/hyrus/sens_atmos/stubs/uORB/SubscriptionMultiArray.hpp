// Test adapter for the production multi-instance interface; subscription
// state and delivery remain in the same Subscription boundary as SENS_ATMOS.
#pragma once
#include <uORB/Subscription.hpp>

namespace uORB
{
template<typename T, uint8_t Size = fake::TOPIC_COUNT>
class SubscriptionMultiArray
{
public:
	static_assert(Size <= fake::TOPIC_COUNT, "Test topic storage must cover every instance");
	explicit SubscriptionMultiArray(ORB_ID topic)
	{
		for (uint8_t i = 0; i < Size; ++i) {
			_subscriptions[i] = Subscription(topic, i);
		}
	}
	static constexpr uint8_t size() { return Size; }
	Subscription &operator[](int index) { return _subscriptions[index]; }
	uint8_t advertised_count() const
	{
		uint8_t count = 0;

		for (const auto &subscription : _subscriptions) {
			if (subscription.advertised()) { ++count; }
		}

		return count;
	}
private:
	Subscription _subscriptions[Size];
};
}
