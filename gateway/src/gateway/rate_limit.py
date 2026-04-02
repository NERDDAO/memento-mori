"""Simple in-memory sliding-window rate limiter."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding-window rate limiter keyed by an identifier."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        """Raise HTTPException(429) if the key has exceeded the rate limit."""
        now = time.monotonic()
        window_start = now - self.window
        # Prune old entries
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        if len(self._requests[key]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window}s.",
            )
        self._requests[key].append(now)


# Shared limiters
action_limiter = RateLimiter(max_requests=10, window_seconds=60)
session_limiter = RateLimiter(max_requests=3, window_seconds=60)
