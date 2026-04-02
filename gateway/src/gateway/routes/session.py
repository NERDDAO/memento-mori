"""Session routes — create and join game sessions."""

import asyncio
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30, pattern=r'^[a-zA-Z0-9_ -]+$')
    game_id: str = Field("default", max_length=64)
    wallet_address: str = Field(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')
    archetype: str = Field("", max_length=20, pattern=r'^[a-zA-Z]*$')


class CreateSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    opening_narrative: str = ""
    archetype: str = ""
    health: int = 100
    max_health: int = 100
    skills: dict = {}
    inventory: list[str] = []
    session_token: str = ""


@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest, request: Request):
    """Create a new game session. Requires x402 payment when enabled."""
    from gateway.rate_limit import session_limiter
    client_ip = request.client.host if request.client else "unknown"
    session_limiter.check(client_ip)

    # x402 payment check
    from gateway.x402 import check_payment_receipt, verify_payment_receipt, payment_required_response
    tx_hash = check_payment_receipt(request, req.wallet_address)
    if tx_hash is None:
        return payment_required_response()
    if tx_hash != "disabled":
        verified = await verify_payment_receipt(tx_hash, req.wallet_address)
        if not verified:
            return payment_required_response()

    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(
            sm.create_player, req.player_name,
            wallet_address=req.wallet_address,
            archetype=req.archetype,
        )

        # Register a Matrix user for this player
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(req.player_name, result["player_id"])

        # Create session token
        from gateway.session_store import create_session as _create_session_token
        token = _create_session_token(result["player_id"], req.wallet_address)

        return CreateSessionResponse(
            player_id=result["player_id"],
            session_id=result["session_id"],
            location=result["location_name"],
            opening_narrative=result.get("opening_narrative", ""),
            archetype=result.get("archetype", ""),
            health=result.get("health", 100),
            max_health=result.get("max_health", 100),
            skills=result.get("skills", {}),
            inventory=result.get("inventory", []),
            session_token=token,
        )
    except Exception:
        logger.error("Session creation via KG failed, using fallback", exc_info=True)
        import uuid
        player_id = str(uuid.uuid4())

        # Still try to register Matrix user in fallback
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(req.player_name, player_id)

        return CreateSessionResponse(
            player_id=player_id,
            session_id="fallback",
            location="The Threshold",
            opening_narrative=f"Welcome, {req.player_name}. Your journey begins.",
        )


@router.get("/players")
async def get_players(wallet: str = Query(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')):
    """Get all characters belonging to a wallet address."""
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        players = await asyncio.to_thread(sm.get_players_by_wallet, wallet)
        return players
    except Exception:
        logger.error("Failed to query players by wallet", exc_info=True)
        return []


class ResumeSessionRequest(BaseModel):
    player_id: str = Field(..., min_length=1, max_length=64)
    wallet_address: str = Field(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')
    signature: str = Field("", max_length=200)
    sign_message: str = Field("", max_length=200)


@router.post("/session/resume")
async def resume_session(req: ResumeSessionRequest, request: Request):
    """Resume an existing character session. Requires wallet signature (not payment).

    Living characters can be resumed for free by proving wallet ownership.
    Dead characters cannot be resumed — the client should show them as grayed out.
    """
    from gateway.x402 import X402_ENABLED
    from gateway.session_store import verify_wallet_signature

    # Verify wallet ownership via signature (when x402 is enabled)
    if X402_ENABLED:
        if not req.signature or not req.sign_message:
            return JSONResponse(
                status_code=401,
                content={"error": "signature_required", "message": "Sign a message to prove wallet ownership"},
            )
        if not verify_wallet_signature(req.wallet_address, req.sign_message, req.signature):
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_signature", "message": "Wallet signature verification failed"},
            )

    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(sm.resume_player, req.player_id)

        # Register Matrix user for reconnection
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(result.get("player_name", "player"), req.player_id)

        # Create session token
        from gateway.session_store import create_session as _create_session_token
        token = _create_session_token(result["player_id"], req.wallet_address)

        # Fetch recent room history for context
        recent_history: list[dict] = []
        from gateway.app import bridge
        if bridge and bridge.connected:
            recent_history = await bridge.get_room_history(result["location_name"], limit=20)

        return {
            "player_id": result["player_id"],
            "session_id": f"session-{result['player_id'][:8]}",
            "location": result["location_name"],
            "player_name": result["player_name"],
            "archetype": result.get("archetype", ""),
            "health": result.get("health", 100),
            "max_health": result.get("max_health", 100),
            "skills": result.get("skills", {}),
            "inventory": result.get("inventory", []),
            "session_token": token,
            "recent_history": recent_history,
        }
    except Exception:
        logger.error("Session resume failed", exc_info=True)
        return {"error": "Failed to resume session"}


@router.get("/archetypes")
async def list_archetypes():
    """List available character archetypes."""
    from memento.config.archetypes import list_archetypes as _list
    archetypes = _list()
    # Strip starting_items details for the preview (keep names only)
    result = []
    for arch in archetypes:
        result.append({
            "name": arch["name"],
            "description": arch.get("description", ""),
            "stats": arch.get("stats", {}),
            "skills": arch.get("skills", {}),
            "starting_items": [i["name"] for i in arch.get("starting_items", [])],
        })
    return result


class JoinSessionRequest(BaseModel):
    player_id: str
    game_id: str = "default"


@router.post("/session/join")
async def join_session(req: JoinSessionRequest):
    """Join an existing game session."""
    return {"status": "joined", "player_id": req.player_id}
