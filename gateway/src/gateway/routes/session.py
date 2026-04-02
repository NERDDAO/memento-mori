"""Session routes — create and join game sessions."""

import asyncio
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30, pattern=r'^[a-zA-Z0-9_ -]+$')
    game_id: str = Field("default", max_length=64)
    wallet_address: str = Field(..., min_length=42, max_length=42, pattern=r'^0x[a-fA-F0-9]{40}$')


class CreateSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    opening_narrative: str = ""


@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest, request: Request):
    """Create a new game session — creates player in KG, registers Matrix user, generates opening narration."""
    from gateway.rate_limit import session_limiter
    client_ip = request.client.host if request.client else "unknown"
    session_limiter.check(client_ip)

    try:
        from memento.session import SessionManager
        sm = SessionManager()
        result = await asyncio.to_thread(sm.create_player, req.player_name, wallet_address=req.wallet_address)

        # Register a Matrix user for this player
        from gateway.app import bridge
        if bridge and bridge.connected:
            await bridge.register_player(req.player_name, result["player_id"])

        return CreateSessionResponse(
            player_id=result["player_id"],
            session_id=result["session_id"],
            location=result["location_name"],
            opening_narrative=result.get("opening_narrative", ""),
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


class JoinSessionRequest(BaseModel):
    player_id: str
    game_id: str = "default"


@router.post("/session/join")
async def join_session(req: JoinSessionRequest):
    """Join an existing game session."""
    return {"status": "joined", "player_id": req.player_id}
