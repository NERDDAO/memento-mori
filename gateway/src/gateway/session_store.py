"""Session token store — Redis-backed with in-memory fallback."""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)

SESSION_TTL = 86400  # 24 hours

# In-memory fallback when Redis is unavailable
_memory_store: dict[str, dict[str, Any]] = {}
_redis_client: Any = None
_redis_attempted = False


def _get_redis():
    """Lazy-connect to Redis. Returns client or None."""
    global _redis_client, _redis_attempted
    if _redis_attempted:
        return _redis_client
    _redis_attempted = True
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        logger.info("No REDIS_URL set, using in-memory session store")
        return None
    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Connected to Redis for session store")
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable, falling back to in-memory store", exc_info=True)
        _redis_client = None
        return None


def create_session(player_id: str, wallet_address: str) -> str:
    """Create a session token for a player. Returns the token string."""
    token = secrets.token_urlsafe(32)
    data = {
        "player_id": player_id,
        "wallet": wallet_address.lower(),
        "created": str(int(time.time())),
    }

    r = _get_redis()
    if r:
        key = f"session:{token}"
        r.hset(key, mapping=data)
        r.expire(key, SESSION_TTL)
    else:
        _memory_store[token] = {**data, "_expires": time.time() + SESSION_TTL}

    return token


def validate_session(token: str) -> dict[str, str] | None:
    """Validate a session token. Returns {player_id, wallet} or None."""
    if not token:
        return None

    r = _get_redis()
    if r:
        key = f"session:{token}"
        data = r.hgetall(key)
        if data and "player_id" in data:
            return {"player_id": data["player_id"], "wallet": data["wallet"]}
        return None
    else:
        data = _memory_store.get(token)
        if not data:
            return None
        if data.get("_expires", 0) < time.time():
            _memory_store.pop(token, None)
            return None
        return {"player_id": data["player_id"], "wallet": data["wallet"]}


def invalidate_session(token: str) -> None:
    """Delete a session token."""
    r = _get_redis()
    if r:
        r.delete(f"session:{token}")
    else:
        _memory_store.pop(token, None)


def cache_payment_receipt(tx_hash: str, wallet: str) -> None:
    """Cache a verified x402 payment receipt."""
    r = _get_redis()
    if r:
        key = f"x402:{tx_hash.lower()}"
        r.set(key, wallet.lower(), ex=SESSION_TTL)
    else:
        _memory_store[f"x402:{tx_hash.lower()}"] = {
            "wallet": wallet.lower(),
            "_expires": time.time() + SESSION_TTL,
        }


def is_receipt_cached(tx_hash: str) -> str | None:
    """Check if a receipt was already verified. Returns wallet address or None."""
    r = _get_redis()
    if r:
        return r.get(f"x402:{tx_hash.lower()}")
    else:
        data = _memory_store.get(f"x402:{tx_hash.lower()}")
        if data and data.get("_expires", 0) > time.time():
            return data.get("wallet")
        return None
