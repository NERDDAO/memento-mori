"""Per-location threading locks — replaces global _turn_lock."""

from __future__ import annotations

import threading


class LocationLockManager:
    """Per-location locks so different locations process in parallel."""

    _locks: dict[str, threading.Lock] = {}
    _meta_lock = threading.Lock()

    @classmethod
    def acquire(cls, location: str) -> threading.Lock:
        """Return (or create) the lock for a location."""
        with cls._meta_lock:
            if location not in cls._locks:
                cls._locks[location] = threading.Lock()
            return cls._locks[location]

    @classmethod
    def reset(cls) -> None:
        """Clear all locks. For tests only."""
        with cls._meta_lock:
            cls._locks.clear()
