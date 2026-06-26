import pytest

from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    def __init__(self):
        self.calls = []

    async def drive_turn(self, loc, msg, *, addressed_name=None):
        self.calls.append((loc, msg))
        return {"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}


class _FakeRepo:
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gareth"} if uuid == "npc-1" else None


class _FakeHub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast_to_location(self, location, message):
        self.broadcasts.append((location, message))


def _patch_loc(monkeypatch, value):
    async def _fake(_pid):
        return value

    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _fake)


@pytest.mark.asyncio
async def test_handles_message_when_scene_active_and_broadcasts(monkeypatch):
    driver, hub = _FakeDriver(), _FakeHub()
    coord = SceneCoordinator(
        scene_registry={"loc-1": driver}, cxn_repo=_FakeRepo(), ws_hub=hub
    )
    _patch_loc(monkeypatch, "loc-1")
    handled = await coord.handle_player_message(
        "p1", "North Gate", "Gareth, may I pass?"
    )
    assert handled is True
    assert driver.calls == [("loc-1", "Gareth, may I pass?")]
    assert len(hub.broadcasts) == 1
    loc, msg = hub.broadcasts[0]
    assert loc == "North Gate"
    assert msg["type"] == "tool_event" and msg["tool"] == "mm_npc_response"
    assert msg["npc"] == "Gareth" and msg["summary"] == "Halt!"
    assert msg["location"] == "North Gate"


@pytest.mark.asyncio
async def test_no_scene_registered_returns_false(monkeypatch):
    hub = _FakeHub()
    coord = SceneCoordinator(scene_registry={}, cxn_repo=_FakeRepo(), ws_hub=hub)
    _patch_loc(monkeypatch, "loc-1")
    handled = await coord.handle_player_message("p1", "North Gate", "hi")
    assert handled is False
    assert hub.broadcasts == []


@pytest.mark.asyncio
async def test_unresolved_location_returns_false(monkeypatch):
    coord = SceneCoordinator(
        scene_registry={"loc-1": _FakeDriver()}, cxn_repo=_FakeRepo(), ws_hub=_FakeHub()
    )
    _patch_loc(monkeypatch, None)
    assert await coord.handle_player_message("p1", "Nowhere", "hi") is False


@pytest.mark.asyncio
async def test_should_respond_false_suppresses_broadcast(monkeypatch):
    class _Quiet(_FakeDriver):
        async def drive_turn(self, loc, msg, *, addressed_name=None):
            return {"response_text": "", "should_respond": False, "self_id": "npc-1"}

    hub = _FakeHub()
    coord = SceneCoordinator(
        scene_registry={"loc-1": _Quiet()}, cxn_repo=_FakeRepo(), ws_hub=hub
    )
    _patch_loc(monkeypatch, "loc-1")
    assert await coord.handle_player_message("p1", "North Gate", "hi") is True
    assert hub.broadcasts == []


@pytest.mark.asyncio
async def test_drive_turn_failure_degrades_without_raising(monkeypatch):
    class _Boom(_FakeDriver):
        async def drive_turn(self, loc, msg, *, addressed_name=None):
            raise RuntimeError("agent-runtime down")

    hub = _FakeHub()
    coord = SceneCoordinator(
        scene_registry={"loc-1": _Boom()}, cxn_repo=_FakeRepo(), ws_hub=hub
    )
    _patch_loc(monkeypatch, "loc-1")
    # claimed by the persona path (True) but no broadcast and no exception
    assert await coord.handle_player_message("p1", "North Gate", "hi") is True
    assert hub.broadcasts == []
