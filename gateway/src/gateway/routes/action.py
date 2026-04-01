"""Action route — player submits a game action."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ActionRequest(BaseModel):
    player_id: str
    action: str
    location: str = ""


class ActionResponse(BaseModel):
    status: str = "queued"


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest):
    """Submit a player action. The engine processes it asynchronously via Matrix."""
    from gateway.app import bridge, ws_hub

    if bridge and bridge.connected:
        room_id = await bridge.get_or_create_room(req.location)
        await bridge.send_action(room_id, req.player_id, req.action)

    # Also send "thinking" indicator to client
    if ws_hub:
        await ws_hub.send_to_player(req.player_id, {
            "type": "thinking",
            "action": req.action,
        })

    return ActionResponse(status="queued")
