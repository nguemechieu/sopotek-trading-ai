from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        now = monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - float(window_seconds)
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(bucket[0] + float(window_seconds) - now, 0.0)
                return False, retry_after
            bucket.append(now)
            return True, 0.0
