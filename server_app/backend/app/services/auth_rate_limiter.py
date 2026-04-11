from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque


class AuthRateLimiter:
    """Simple in-memory limiter for auth-sensitive endpoints."""

    def __init__(self, *, max_attempts: int = 6, window_seconds: int = 60) -> None:
        self.max_attempts = max(1, int(max_attempts or 6))
        self.window_seconds = max(1, int(window_seconds or 60))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, scope: str, key: str) -> tuple[bool, float]:
        normalized = f"{str(scope or 'auth').strip().lower()}::{str(key or 'global').strip().lower()}"
        now = time.monotonic()
        async with self._lock:
            bucket = self._events[normalized]
            while bucket and (now - bucket[0]) > float(self.window_seconds):
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                retry_after = max(1.0, float(self.window_seconds) - (now - bucket[0]))
                return False, retry_after
            bucket.append(now)
            return True, 0.0

    async def reset(self, scope: str, key: str) -> None:
        normalized = f"{str(scope or 'auth').strip().lower()}::{str(key or 'global').strip().lower()}"
        async with self._lock:
            self._events.pop(normalized, None)
