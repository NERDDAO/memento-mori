import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.scene_activation import (
    AgentRuntimeUnavailable,
    SceneActivationService,
    SceneAlreadyOpen,
    SceneNotOpen,
)


class _FakeRepo:
    """Minimal StateRepository slice RoomDriver.open_room/close_room touch."""
    def __init__(self, entities=None):
        self._entities = entities or []
    async def get_entities_at_location(self, loc):
        return self._entities


def _stub_app(open_status=200):
    async def _open(request: Request):
        await request.json()
        return JSONResponse({"source_episode_id": "ep-1"}, status_code=open_status)
    async def _close(request: Request):
        return JSONResponse({"task_id": "t-1", "snapshot_size": 0})
    return Starlette(routes=[
        Route("/v1/scenes/{loc}/open", _open, methods=["POST"]),
        Route("/v1/scenes/{loc}/close", _close, methods=["POST"]),
    ])


def _svc(registry, open_status=200):
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_stub_app(open_status)),
        base_url="http://agent-runtime-stub",
    )
    return SceneActivationService(
        repo=_FakeRepo(), agent_runtime_client=client, scene_registry=registry,
    ), client


@pytest.mark.asyncio
async def test_activate_registers_then_double_activate_raises():
    registry: dict = {}
    svc, client = _svc(registry)
    try:
        out = await svc.activate("loc-1")
        assert out["scene_id"] == "loc-1"
        assert "loc-1" in registry
        with pytest.raises(SceneAlreadyOpen):
            await svc.activate("loc-1")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_close_unopened_raises_then_close_deregisters():
    registry: dict = {}
    svc, client = _svc(registry)
    try:
        with pytest.raises(SceneNotOpen):
            await svc.close("loc-x")
        await svc.activate("loc-1")
        await svc.close("loc-1")
        assert "loc-1" not in registry
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_open_transport_error_wraps_and_does_not_register():
    registry: dict = {}
    svc, client = _svc(registry, open_status=500)  # raise_for_status -> httpx.HTTPStatusError
    try:
        with pytest.raises(AgentRuntimeUnavailable):
            await svc.activate("loc-1")
        assert "loc-1" not in registry
    finally:
        await client.aclose()
