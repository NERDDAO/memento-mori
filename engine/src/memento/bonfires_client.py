"""Lazy-initialized Bonfires SDK client."""

from __future__ import annotations

from bonfires.sdk import BonfiresClient

_client: BonfiresClient | None = None


def get_client() -> BonfiresClient:
    """Return a shared BonfiresClient instance, initialized from env vars."""
    global _client
    if _client is None:
        _client = BonfiresClient()
    return _client
