import time
from collections import defaultdict, deque


class UserRateLimiter:
    def __init__(self, max_actions: int = 12, window_seconds: float = 10.0) -> None:
        if max_actions <= 0 or window_seconds <= 0:
            raise ValueError("Rate limit parameters must be positive")
        self.max_actions = max_actions
        self.window_seconds = window_seconds
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        events = self._events[user_id]
        cutoff = timestamp - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.max_actions:
            return False
        events.append(timestamp)
        return True
