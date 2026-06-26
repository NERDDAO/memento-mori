"""Scene activation routes: open/close a RoomDriver-backed scene for a location."""

from fastapi import APIRouter, HTTPException, Request

from gateway.scene_activation import (
    AgentRuntimeUnavailable,
    SceneActivationService,
    SceneAlreadyOpen,
    SceneNotOpen,
)

router = APIRouter()


@router.post("/scenes/{location_uuid}/activate")
async def activate_scene(location_uuid: str, request: Request) -> dict:
    svc = SceneActivationService.from_app_state(request.app.state)
    try:
        return await svc.activate(location_uuid)
    except SceneAlreadyOpen:
        raise HTTPException(status_code=409, detail="Scene already open for this location.")
    except AgentRuntimeUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"Agent-runtime unavailable: {exc}")


@router.post("/scenes/{location_uuid}/close")
async def close_scene(location_uuid: str, request: Request) -> dict:
    svc = SceneActivationService.from_app_state(request.app.state)
    try:
        return await svc.close(location_uuid)
    except SceneNotOpen:
        raise HTTPException(status_code=404, detail="No scene open for this location.")
    except AgentRuntimeUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"Agent-runtime unavailable: {exc}")
