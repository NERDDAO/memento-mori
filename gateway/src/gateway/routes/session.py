"""Session routes — create and join game sessions."""

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


@router.post("/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new game session for a player."""
    # Phase 8 will wire this to the engine's session manager
    # For now, return placeholder
    import uuid
    player_id = str(uuid.uuid4())
    return CreateSessionResponse(
        player_id=player_id,
        session_id=f"session-{player_id[:8]}",
        location="Starting Location",
    )


class JoinSessionRequest(BaseModel):
    player_id: str
    game_id: str = "default"


@router.post("/session/join")
async def join_session(req: JoinSessionRequest):
    """Join an existing game session."""
    return {"status": "joined", "player_id": req.player_id}
