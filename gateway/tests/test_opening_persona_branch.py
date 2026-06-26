"""Task 3: POST /api/opening/act drives the persona scene (best-effort hook)."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.persona_seed import seed_opening_persona, _OPENING_LOC_UUID
from gateway.room_driver import RoomDriver
from memento.state.in_memory import InMemoryStateRepository

_DEEP_ROADS_NAME = "the deep roads"


class _Hub:  # mirrors test_action_persona_branch.py
    def __init__(self):
        self.broadcasts = []
        self.locs = {}

    async def set_location(self, pid, loc):
        self.locs[pid] = loc

    async def broadcast_to_location(self, loc, msg):
        self.broadcasts.append((loc, msg))

    def players_at_location(self, loc):
        return 1

    @property
    def player_locations(self):
        return self.locs


def _turn_stub(recorder):
    async def _turn(request: Request):
        recorder.append(await request.json())
        return JSONResponse(
            {"response_text": "You... made it this far?", "should_respond": True}
        )

    return Starlette(routes=[Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"])])


@pytest.fixture(autouse=True)
def _patch_opening_hooks(monkeypatch):
    """Fake DI builders so /opening/start is pure in-process (from test_opening_routes.py)."""
    import gateway.routes.opening as opening_mod
    from memento.cxn.kernel_client import FakeComprehensionClient
    from memento.cxn.types import ComprehendedFrame
    from memento.memory.null_client import NullMemoryClient
    from memento.state.chain_mirror import NoopChainMirror
    from memento.state.kg_projection import KgProjectionFake

    canned = {
        "look around": ComprehendedFrame(
            predicate="look", roles=[], matched=True, raw_text="look around"
        ),
    }
    monkeypatch.setattr(
        opening_mod, "build_comprehension", lambda: FakeComprehensionClient(canned)
    )
    monkeypatch.setattr(opening_mod, "build_memory", lambda: NullMemoryClient())
    monkeypatch.setattr(opening_mod, "build_mirror", lambda: NoopChainMirror())
    monkeypatch.setattr(opening_mod, "build_projection", lambda: KgProjectionFake())
    monkeypatch.setattr(opening_mod, "opening_registry", {})


async def _start(client):
    r = await client.post(
        "/api/opening/start",
        json={
            "player_name": "Tester",
            "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
            "archetype": "",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["player_id"]


async def _wire_persona_scene(monkeypatch):
    """Pre-register a persona scene at the Deep Roads on app.state, with a fake hub."""
    from gateway.app import app

    repo = InMemoryStateRepository()
    await seed_opening_persona(repo, None)  # seeds the NPC at _OPENING_LOC_UUID
    recorder: list = []
    ar_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_turn_stub(recorder)),
        base_url="http://ar-stub",
    )
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids[_OPENING_LOC_UUID] = {"opening-wanderer"}
    hub = _Hub()
    app.state.cxn_repo = repo
    app.state.agent_runtime_client = ar_client
    app.state.scene_registry = {_OPENING_LOC_UUID: driver}
    app.state.scene_locations = {_DEEP_ROADS_NAME: _OPENING_LOC_UUID}
    app.state.ws_hub = hub
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    return app, hub, recorder, ar_client


@pytest.mark.asyncio
async def test_opening_act_drives_persona_and_broadcasts(monkeypatch):
    app, hub, recorder, ar_client = await _wire_persona_scene(monkeypatch)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            player_id = await _start(gw)
            resp = await gw.post(
                "/api/opening/act",
                json={"player_id": player_id, "text": "look around"},
            )
            assert resp.status_code == 200, resp.text  # opening turn returns normally
        assert len(recorder) == 1  # the hook drove the registered scene's turn
        npc_msgs = [
            (loc, m) for loc, m in hub.broadcasts if m.get("tool") == "mm_npc_response"
        ]
        assert npc_msgs, hub.broadcasts
        loc, msg = npc_msgs[0]
        assert loc == _DEEP_ROADS_NAME
        assert msg["summary"] == "You... made it this far?"
    finally:
        await ar_client.aclose()


@pytest.mark.asyncio
async def test_opening_act_survives_persona_failure(monkeypatch):
    app, hub, recorder, ar_client = await _wire_persona_scene(monkeypatch)

    def _boom(cls, state):
        raise RuntimeError("scene coordinator down")

    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state", classmethod(_boom)
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            player_id = await _start(gw)
            resp = await gw.post(
                "/api/opening/act",
                json={"player_id": player_id, "text": "look around"},
            )
            # opening TurnOutcome is intact despite the persona-hook failure
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "narrated"
    finally:
        await ar_client.aclose()
