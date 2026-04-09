"""MCP-native player signup.

``POST /api/player/signup`` creates a new player entity in the KG (same
entry point as the legacy ``POST /api/session/create`` used by the web
client) and returns a JWT the player drops into their MCP client's
``.mcp.json`` headers. That JWT is the player's identity for every tool
call on ``/mcp``.

Payment gate — ``X402_REQUIRED=true`` in env enforces x402 via delve's
CDP facilitator. In dev the env var is unset and signup is free so the
core loop is testable immediately.
"""

import asyncio
import os

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from gateway.engine_auth import sign_jwt
from gateway.log import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/player", tags=["player"])


# Default player session JWT TTL — 24h matches the voice-session precedent
# in delve's payment stack.
_PLAYER_JWT_TTL_SECONDS = 24 * 60 * 60


def _x402_required() -> bool:
    """Production deployments set ``X402_REQUIRED=true`` to enforce payment.
    Dev leaves it unset and signup is free.
    """
    return os.getenv("X402_REQUIRED", "").lower() in ("1", "true", "yes")


class SignupRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30, pattern=r'^[a-zA-Z0-9_ -]+$')
    archetype: str = Field("warrior", max_length=20, pattern=r'^[a-zA-Z]*$')
    wallet_address: str = Field(
        "0x0000000000000000000000000000000000000000",
        min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$',
    )


class SignupResponse(BaseModel):
    jwt: str
    player_id: str
    session_id: str
    location: str
    archetype: str
    health: int
    max_health: int
    skills: dict
    inventory: list
    room_map: dict | None = None
    opening_narrative: str = ""
    expires_in_seconds: int
    mcp_setup: dict


@router.post("/signup", response_model=SignupResponse)
async def signup(
    req: SignupRequest,
    request: Request,
    x_payment: str = Header("", alias="X-Payment"),
) -> SignupResponse:
    """Create a player and mint their MCP JWT.

    Returns everything the player's MCP client needs to start playing:
    the JWT for auth, the player_id for reference, the starting location
    and room map for orientation, and an ``mcp_setup`` block with the
    exact ``.mcp.json`` snippet the player should paste into their client.
    """
    from gateway.rate_limit import session_limiter
    client_ip = request.client.host if request.client else "unknown"
    session_limiter.check(client_ip)

    if _x402_required() and not x_payment:
        # Return the x402 challenge. The actual facilitator integration
        # (delve's CDP service) is wired in a follow-up task.
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "accepts": ["x402"],
                "message": "Player signup requires an x402 payment in production. "
                           "See docs/mcp-player-setup.md for the payment flow.",
            },
        )

    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(
            sm.create_player,
            req.player_name,
            wallet_address=req.wallet_address,
            archetype=req.archetype,
        )
    except Exception as exc:
        logger.error("player signup failed in SessionManager", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "session_creation_failed", "message": str(exc)},
        )

    # Register the Matrix user + seed presence tracking so legacy WS
    # consumers still see the player.
    from gateway.app import bridge, ws_hub
    if bridge and bridge.connected:
        try:
            await bridge.register_player(req.player_name, result["player_id"])
        except Exception:
            logger.debug("bridge.register_player failed", exc_info=True)
    if ws_hub:
        ws_hub.player_names[result["player_id"]] = req.player_name

    # Mint the JWT — sub is the KG UUID, which _check_tool_access uses to
    # look up the player's labels (["Player"]) and resolve allowed tools.
    token = sign_jwt(
        result["player_id"],
        type="player",
        ttl_seconds=_PLAYER_JWT_TTL_SECONDS,
        extra_claims={"name": req.player_name},
    )

    gateway_url = os.getenv("MEMENTO_GATEWAY_URL", "http://localhost:8081")
    mcp_setup = {
        "mcp_url": f"{gateway_url}/mcp/mcp",
        "mcp_json_example": {
            "mcpServers": {
                "memento-engine": {
                    "type": "http",
                    "url": f"{gateway_url}/mcp/mcp",
                    "headers": {"Authorization": f"Bearer {token}"},
                },
            },
        },
    }

    return SignupResponse(
        jwt=token,
        player_id=result["player_id"],
        session_id=result["session_id"],
        location=result["location_name"],
        archetype=result.get("archetype", req.archetype),
        health=result.get("health", 100),
        max_health=result.get("max_health", 100),
        skills=result.get("skills", {}),
        inventory=result.get("inventory", []),
        room_map=result.get("room_map"),
        opening_narrative=result.get("opening_narrative", ""),
        expires_in_seconds=_PLAYER_JWT_TTL_SECONDS,
        mcp_setup=mcp_setup,
    )
