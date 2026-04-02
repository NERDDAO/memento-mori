"""Tests for rate limiting."""

import pytest
from fastapi import HTTPException
from gateway.rate_limit import RateLimiter


def test_allows_under_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    limiter.check("user1")
    limiter.check("user1")
    limiter.check("user1")
    # Should not raise


def test_blocks_over_limit():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("user1")
    limiter.check("user1")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("user1")
    assert exc_info.value.status_code == 429


def test_separate_keys():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("user1")
    limiter.check("user2")  # Different key, should not raise


def test_window_expiry():
    limiter = RateLimiter(max_requests=1, window_seconds=0)
    limiter.check("user1")
    # With window=0, all previous entries are pruned
    limiter.check("user1")  # Should not raise
