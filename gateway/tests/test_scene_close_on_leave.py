import pytest

from gateway.scene_activation import SceneNotOpen
from gateway.scene_coordinator import SceneCoordinator


class _FakeActivation:
    def __init__(self, registry):
        self._registry, self.closed = registry, []

    async def close(self, loc):
        self.closed.append(loc)
        self._registry.pop(loc, None)
        return {"scene_id": loc}


class _Hub:
    def __init__(self, counts):
        self._counts = counts

    def players_at_location(self, name):
        return self._counts.get(name, 0)


def _coord(registry, activation, hub, cache):
    from gateway.location_resolver import LocationResolver

    return SceneCoordinator(
        scene_registry=registry,
        cxn_repo=None,
        ws_hub=hub,
        activation_service=activation,
        location_resolver=LocationResolver(None, cache),
    )


@pytest.mark.asyncio
async def test_closes_scene_when_last_player_leaves():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == ["loc-1"]
    assert "loc-1" not in registry


@pytest.mark.asyncio
async def test_keeps_scene_when_players_remain():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 1}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == []
    assert "loc-1" in registry


@pytest.mark.asyncio
async def test_noop_when_no_scene_registered():
    registry = {}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == []


@pytest.mark.asyncio
async def test_noop_when_location_uncached():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {})  # name not in cache
    await coord.maybe_close("North Gate")
    assert act.closed == []


import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.in_memory import InMemoryStateRepository
from gateway.room_driver import RoomDriver


def _stub(closed):
    async def _turn(request):
        return JSONResponse({"response_text": "ok", "should_respond": False})

    async def _close(request):
        closed.append(request.path_params["rid"])
        return JSONResponse({"closed": True})

    return Starlette(
        routes=[
            Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"]),
            Route("/v1/scenes/{rid}/close", _close, methods=["POST"]),
        ]
    )


@pytest.mark.asyncio
async def test_action_moving_away_closes_previous_scene(monkeypatch):
    from gateway.app import app

    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": "npc-A",
            "kind": "character",
            "name": "Gareth",
            "labels": ["Character", "NPC"],
            "location_uuid": "loc-A",
            "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
            "is_dead": False,
        }
    )
    closed: list[str] = []
    ar_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_stub(closed)), base_url="http://ar"
    )
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids["loc-A"] = {"npc-A"}

    class _Hub:
        def __init__(self):
            self.locs = {"p1": "Hall A"}
            self.broadcasts = []

        async def set_location(self, pid, loc):
            self.locs[pid] = loc

        async def broadcast_to_location(self, loc, msg):
            self.broadcasts.append((loc, msg))

        def players_at_location(self, loc):
            return sum(1 for v in self.locs.values() if v == loc)

        @property
        def player_locations(self):
            return self.locs

    class _RM:
        async def submit_action(self, *a): ...

        async def close_round(self, loc): ...

    hub = _Hub()
    app.state.cxn_repo = repo
    app.state.ws_hub = hub
    app.state.agent_runtime_client = ar_client
    app.state.scene_registry = {"loc-A": driver}
    app.state.scene_locations = {"Hall A": "loc-A"}
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    monkeypatch.setattr("gateway.app.round_manager", _RM())

    async def _loc(_pid):
        return "loc-B"  # NEW location resolves to loc-B (no scene/NPCs)

    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _loc)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(
                "/api/action",
                json={"player_id": "p1", "action": "leave", "location": "Hall B"},
            )
            assert resp.status_code == 200
        assert closed == ["loc-A"]  # previous scene closed
        assert "loc-A" not in app.state.scene_registry
        assert hub.players_at_location("Hall A") == 0
    finally:
        await ar_client.aclose()
        # Clean up test-scoped state so later tests don't inherit a closed client.
        app.state.agent_runtime_client = None
        app.state.scene_registry = {}
        app.state.scene_locations = {}
