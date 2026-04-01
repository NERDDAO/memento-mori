"""Session routes — create and join game sessions."""

import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class CreateSessionRequest(BaseModel):
    player_name: str
    game_id: str = "default"


class CreateSessionResponse(BaseModel):
    player_id: str
    session_id: str
    location: str
    opening_narrative: str = ""


@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new game session — creates player in KG, generates opening narration."""
    try:
        from memento.session import SessionManager
        sm = SessionManager()
        # Run sync SessionManager in thread
        result = await asyncio.to_thread(sm.create_player, req.player_name)
        return CreateSessionResponse(
            player_id=result["player_id"],
            session_id=result["session_id"],
            location=result["location_name"],
            opening_narrative=result.get("opening_narrative", ""),
        )
    except Exception as e:
        # Fallback if engine not available
        import uuid
        return CreateSessionResponse(
            player_id=str(uuid.uuid4()),
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
