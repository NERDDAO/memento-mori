import uuid

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog


class _Recorder:
    def __init__(self): self.calls = []
    def record(self, url, body): self.calls.append({"url": url, "body": body})


def _make_stub(recorder, open_status=200):
    async def _open(request: Request):
        body = await request.json()
        recorder.record(str(request.url), body)
        return JSONResponse({"source_episode_id": "ep-1"}, status_code=open_status)
    async def _close(request: Request):
        recorder.record(str(request.url), {})
        return JSONResponse({"task_id": "t-1", "snapshot_size": 0})
    return Starlette(routes=[
        Route("/v1/scenes/{loc}/open", _open, methods=["POST"]),
        Route("/v1/scenes/{loc}/close", _close, methods=["POST"]),
    ])


async def _seed_world():
    proj = KgProjectionFake()
    repo = EventSourcedStateRepository(
        tx_log=InMemoryTxLog(), activation_log=InMemoryActivationLog(),
        projection=proj, chain=NoopChainMirror(),
    )
    loc = uuid.uuid4().hex
    npc = uuid.uuid4().hex
    await repo.seed_entity({"uuid": loc, "kind": "location", "name": "Hall",
                            "labels": ["Location"], "location_uuid": None,
                            "attrs": {"exits": [], "item_ids": []}, "is_dead": False})
    await repo.seed_entity({"uuid": npc, "kind": "character", "name": "Guard",
                            "labels": ["Character", "NPC"], "location_uuid": loc,
                            "attrs": {"hp": 10, "max_hp": 10, "inventory": []}, "is_dead": False})
    return repo, loc, npc


async def _wire_app(open_status=200):
    from gateway.app import app
    repo, loc, npc = await _seed_world()
    recorder = _Recorder()
    app.state.cxn_repo = repo
    app.state.scene_registry = {}
    app.state.agent_runtime_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_make_stub(recorder, open_status)),
        base_url="http://agent-runtime-stub",
    )
    return app, repo, loc, npc, recorder


@pytest.mark.asyncio
async def test_activate_ships_roster_with_capabilities_and_embodiment():
    app, repo, loc, npc, recorder = await _wire_app()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(f"/api/scenes/{loc}/activate")
            assert resp.status_code == 200, resp.text
            # the agent-runtime received an open with a capability-bearing roster
            open_call = next(c for c in recorder.calls if "/open" in c["url"])
            roster = open_call["body"]["roster"]
            assert len(roster) == 1
            spec = roster[0]
            assert "mm_move" in spec["capabilities"]            # NPC kit
            assert spec["embodiment_agent_id"] == npc            # identity-uuid via projection
            assert loc in app.state.scene_registry

            # double-activate -> 409
            assert (await gw.post(f"/api/scenes/{loc}/activate")).status_code == 409

            # close -> 200 + deregister
            close_resp = await gw.post(f"/api/scenes/{loc}/close")
            assert close_resp.status_code == 200, close_resp.text
            assert any("/close" in c["url"] for c in recorder.calls)
            assert loc not in app.state.scene_registry

            # close again -> 404
            assert (await gw.post(f"/api/scenes/{loc}/close")).status_code == 404
    finally:
        await app.state.agent_runtime_client.aclose()


@pytest.mark.asyncio
async def test_agent_runtime_error_maps_to_502():
    app, repo, loc, npc, recorder = await _wire_app(open_status=500)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(f"/api/scenes/{loc}/activate")
            assert resp.status_code == 502, resp.text
            assert loc not in app.state.scene_registry
    finally:
        await app.state.agent_runtime_client.aclose()
