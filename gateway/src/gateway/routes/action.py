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


class DeathBroadcast(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30)
    level: int = Field(1, ge=1)
    cause: str = Field("", max_length=200)
    location: str = Field("", max_length=200)


@router.post("/death/broadcast")
async def broadcast_death(req: DeathBroadcast):
    """Broadcast a permadeath announcement to all connected players."""
    from gateway.app import ws_hub
    if ws_hub:
        await ws_hub.broadcast_death(req.player_name, req.level, req.cause, req.location)
    return {"status": "broadcast"}


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest):
    """Submit a player action. Goes through the RoundManager for batching."""
    from gateway.rate_limit import action_limiter
    action_limiter.check(req.player_id)

    from gateway.app import round_manager

    if round_manager:
        accepted = await round_manager.submit_action(
            req.player_id,
            req.player_id,  # player_name — will be resolved from KG later
            req.location,
            req.action,
        )
        status = "queued" if accepted else "duplicate"
    else:
        # Fallback: direct send (no round manager)
        from gateway.app import bridge, ws_hub
        if bridge and bridge.connected:
            room_id = await bridge.get_or_create_room(req.location)
            await bridge.send_action(room_id, req.player_id, req.action)
        if ws_hub:
            ws_hub.set_location(req.player_id, req.location)
            await ws_hub.send_to_player(req.player_id, {
                "type": "thinking",
                "action": req.action,
            })
        status = "queued"

    return ActionResponse(status=status)
