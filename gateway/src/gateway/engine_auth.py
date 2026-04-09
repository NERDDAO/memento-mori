# gateway/src/gateway/engine_auth.py
"""Auth + capability gating for engine tool endpoints.

Two authentication layers:

1. **JWT** — the only Bearer token accepted on ``/mcp``. Both NPCs and
   players present a JWT whose ``sub`` claim is the entity's KG UUID.
   NPCs get their JWTs from ``POST /api/admin/npc-jwt`` (admin-only);
   players get theirs from ``POST /api/player/signup`` (x402 in prod).

2. **Capability gate** — once the caller's UUID is resolved from the JWT,
   ``check_tool_access`` looks up the entity's KG labels and verifies the
   requested tool is in the allowed set for those labels.

There is no legacy static-token fallback — everything goes through JWTs.
"""

import asyncio
import os
import time
from typing import Any

import jwt
from fastapi import HTTPException


# ── JWT helpers ─────────────────────────────────────────────────────────────

_JWT_ALGO = "HS256"


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET env var is not set — the gateway cannot sign or verify JWTs. "
            "Generate one with `python -c 'import secrets; print(secrets.token_urlsafe(32))'` "
            "and add it to .env."
        )
    return secret


def sign_jwt(
    sub: str,
    *,
    type: str,
    ttl_seconds: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Sign an HS256 JWT.

    ``sub`` is the entity UUID (NPC or player). ``type`` is ``"npc"`` or
    ``"player"`` — used by tools that want to differentiate callers.
    ``ttl_seconds`` controls expiry; callers are expected to pick a
    sensible default (e.g. 24h for players, 1y for NPCs).
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "type": type,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGO)


def validate_jwt(token: str) -> dict[str, Any] | None:
    """Decode + verify a JWT. Returns the claims dict on success, ``None``
    on any validation failure (bad signature, expired, malformed, etc.).

    Never raises — callers get a nullable result so they can distinguish
    "invalid token" from "no token" without catching exceptions.
    """
    if not token:
        return None
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGO])
    except jwt.PyJWTError:
        return None
    if not isinstance(claims, dict) or not claims.get("sub"):
        return None
    return claims


def identity_from_authorization(authorization: str) -> dict[str, Any] | None:
    """Pure predicate — extract the JWT claims from an ``Authorization`` header.

    Safe to call from raw ASGI scope (no FastAPI context needed). Returns
    ``None`` if the header is missing, malformed, or the JWT fails to validate.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return validate_jwt(authorization[7:])


# ── Admin key for NPC JWT issuance ──────────────────────────────────────────


def admin_key_valid(header_value: str) -> bool:
    """Constant-time compare the ``X-Admin-Api-Key`` header against
    ``ENGINE_ADMIN_KEY`` env var. Fails closed when the env var is unset.
    """
    import hmac as _hmac
    expected = os.getenv("ENGINE_ADMIN_KEY", "")
    if not expected:
        return False
    return _hmac.compare_digest(header_value or "", expected)


# ── Capability gate ─────────────────────────────────────────────────────────


async def check_tool_access(npc_id: str, tool_name: str) -> None:
    """Check if this entity can call this tool based on its KG labels.

    Resolves ``npc_id`` → KG UUID via npc_registry (for legacy agent IDs
    that aren't already UUIDs), then fetches labels from KG. Raises 403 if
    the tool is not in the allowed set.

    Innate tools bypass the KG fetch entirely.
    """
    from memento.tools.tool_labels import get_allowed_tools, INNATE_TOOLS

    if tool_name in INNATE_TOOLS:
        return

    if not npc_id:
        raise HTTPException(
            status_code=403,
            detail={"error": "identity_missing", "tool": tool_name},
        )

    from gateway.npc_registry import resolve_npc_kg_uuid
    kg_uuid = resolve_npc_kg_uuid(npc_id)
    entity_id = kg_uuid or npc_id

    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        labels = entity.get("labels", []) if isinstance(entity, dict) else []
    except Exception:
        labels = []

    allowed = get_allowed_tools(labels)
    if tool_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "capability_missing",
                "tool": tool_name,
                "entity_labels": labels,
                "message": f"This entity doesn't have access to {tool_name}. "
                           f"Add the required label to unlock it.",
            },
        )
