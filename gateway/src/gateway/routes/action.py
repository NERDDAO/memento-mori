"""Action route — player submits a game action."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter()


class PositionSyncRequest(BaseModel):
    player_id: str
    x: int
    y: int


@router.post("/position/sync")
async def sync_position(req: PositionSyncRequest):
    """Sync player position to chain. Called on interaction, not every move.

    Client moves optimistically (WASD is instant). Position is synced to chain
    on interaction (talk, pickup, use exit) to confirm the player's actual location.
    If chain rejects (invalid tile), client should snap back.
    """
    try:
        from gateway.routes.codex import _get_location_uuid

        location_uuid = await _get_location_uuid(req.player_id)

        if not location_uuid:
            return {"success": True}  # Can't resolve, but don't block player

        from gateway.chain_client import write_position

        success = await write_position(req.player_id, location_uuid, req.x, req.y)

        return {"success": success}
    except Exception:
        import logging

        logging.getLogger(__name__).debug("Position sync failed", exc_info=True)
        return {"success": True}  # Don't block player on chain errors


class ActionRequest(BaseModel):
    player_id: str = Field(
        ..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    action: str = Field(..., min_length=1, max_length=500)
    location: str = Field("", max_length=200)

    @field_validator("action")
    @classmethod
    def normalize_whitespace(cls, v: str) -> str:
        return " ".join(v.split())


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
        await ws_hub.broadcast_death(
            req.player_name, req.level, req.cause, req.location
        )
    return {"status": "broadcast"}


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest, request: Request):
    """Submit a player action. Batched by location via RoundManager."""
    from gateway.rate_limit import action_limiter

    action_limiter.check(req.player_id)

    from gateway.app import round_manager, ws_hub

    previous_location = ""
    if ws_hub:
        previous_location = ws_hub.player_locations.get(req.player_id, "")
        await ws_hub.set_location(req.player_id, req.location)

    from gateway.scene_coordinator import SceneCoordinator

    coordinator = SceneCoordinator.from_app_state(request.app.state)
    handled = await coordinator.handle_player_message(
        req.player_id, req.location, req.action
    )
    if previous_location and previous_location != req.location:
        await coordinator.maybe_close(previous_location)
    if handled:
        return ActionResponse(status="queued")

    if round_manager:
        await round_manager.submit_action(
            req.player_id, req.player_id, req.location, req.action
        )
        # Solo fast-path: if only 1 player at location, close round immediately
        if ws_hub and ws_hub.players_at_location(req.location) <= 1:
            await round_manager.close_round(req.location)

    return ActionResponse(status="queued")
