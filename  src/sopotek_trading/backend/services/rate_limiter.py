import os

import redis
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL"))

class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window = window_seconds

    def allow(self, key: str):
        current = redis_client.get(key)

        if current is None:
            redis_client.set(key, 1, ex=self.window)
            return True

        if int(current) >= self.max_requests:
            return False

        redis_client.incr(key)
        return True