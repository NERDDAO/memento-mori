"""Action route — player submits a game action."""

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

router = APIRouter()


class ActionRequest(BaseModel):
    player_id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    action: str = Field(..., min_length=1, max_length=500)
    location: str = Field("", max_length=200)

    @field_validator('action')
    @classmethod
    def normalize_whitespace(cls, v: str) -> str:
        return ' '.join(v.split())


class ActionResponse(BaseModel):
    status: str = "queued"


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest):
    """Submit a player action. The engine processes it asynchronously via Matrix."""
    from gateway.rate_limit import action_limiter
    action_limiter.check(req.player_id)

    from gateway.app import bridge, ws_hub

    if bridge and bridge.connected:
        room_id = await bridge.get_or_create_room(req.location)
        await bridge.send_action(room_id, req.player_id, req.action)

    # Track player location and send "thinking" indicator to client
    if ws_hub:
        ws_hub.set_location(req.player_id, req.location)
        await ws_hub.send_to_player(req.player_id, {
            "type": "thinking",
            "action": req.action,
        })

    return ActionResponse(status="queued")
