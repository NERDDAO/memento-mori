import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.in_memory import InMemoryStateRepository
from gateway.room_driver import RoomDriver


class _Hub:
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


class _RM:
    def __init__(self):
        self.submitted = []

    async def submit_action(self, *a):
        self.submitted.append(a)

    async def close_round(self, loc): ...


def _turn_stub(recorder):
    async def _turn(request: Request):
        recorder.append(await request.json())
        return JSONResponse(
            {"response_text": "Halt, traveler.", "should_respond": True}
        )

    return Starlette(routes=[Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"])])


async def _wire(monkeypatch, loc_uuid):
    from gateway.app import app

    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": "npc-1",
            "kind": "character",
            "name": "Gareth",
            "labels": ["Character", "NPC"],
            "location_uuid": loc_uuid,
            "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
            "is_dead": False,
        }
    )
    recorder = []
    ar_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_turn_stub(recorder)),
        base_url="http://ar-stub",
    )
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids[loc_uuid] = {"npc-1"}
    hub, rm = _Hub(), _RM()
    app.state.cxn_repo = repo
    app.state.ws_hub = hub
    app.state.scene_registry = {loc_uuid: driver}
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    monkeypatch.setattr("gateway.app.round_manager", rm)

    async def _loc(_pid):
        return loc_uuid

    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _loc)
    return app, repo, hub, rm, recorder, ar_client


@pytest.mark.asyncio
async def test_action_in_scene_drives_persona_and_broadcasts(monkeypatch):
    app, repo, hub, rm, recorder, ar_client = await _wire(monkeypatch, "loc-1")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(
                "/api/action",
                json={
                    "player_id": "p1",
                    "action": "Gareth, may I pass?",
                    "location": "North Gate",
                },
            )
            assert resp.status_code == 200
        assert (
            len(recorder) == 1 and recorder[0]["self_id"] == "npc-1"
        )  # agent-runtime got the turn
        assert rm.submitted == []  # round path skipped
        assert len(hub.broadcasts) == 1
        loc, msg = hub.broadcasts[0]
        assert loc == "North Gate" and msg["tool"] == "mm_npc_response"
        assert msg["npc"] == "Gareth" and msg["summary"] == "Halt, traveler."
    finally:
        await ar_client.aclose()


@pytest.mark.asyncio
async def test_action_without_scene_falls_through_to_round_path(monkeypatch):
    # location_uuid resolves but NO scene registered for it -> existing path runs
    app, repo, hub, rm, recorder, ar_client = await _wire(monkeypatch, "loc-1")
    app.state.scene_registry = {}  # no active scene
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(
                "/api/action",
                json={
                    "player_id": "p1",
                    "action": "look around",
                    "location": "North Gate",
                },
            )
            assert resp.status_code == 200
        assert recorder == []  # agent-runtime NOT called
        assert len(rm.submitted) == 1  # round path ran
        assert hub.broadcasts == []  # no persona broadcast
    finally:
        await ar_client.aclose()
