from unittest import TestCase

from app.rate_limit import UserRateLimiter


class RateLimiterTests(TestCase):
    def test_limits_each_user_independently(self) -> None:
        limiter = UserRateLimiter(max_actions=2, window_seconds=10)

        self.assertTrue(limiter.allow(1, now=0))
        self.assertTrue(limiter.allow(1, now=1))
        self.assertFalse(limiter.allow(1, now=2))
        self.assertTrue(limiter.allow(2, now=2))
        self.assertTrue(limiter.allow(1, now=11))
