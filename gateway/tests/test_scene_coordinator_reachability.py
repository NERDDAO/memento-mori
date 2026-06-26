import pytest

from gateway.scene_activation import AgentRuntimeUnavailable
from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    def __init__(self):
        self.calls = []

    async def drive_turn(self, loc, msg, *, addressed_name=None):
        self.calls.append((loc, msg))
        return {"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}


class _FakeRepo:
    def __init__(self, entities):
        self._entities = entities

    async def get_entities_at_location(self, loc):
        return self._entities.get(loc, [])

    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gareth"} if uuid == "npc-1" else None


class _FakeActivation:
    def __init__(self, registry, driver):
        self._registry, self._driver, self.activated = registry, driver, []

    async def activate(self, loc):
        self.activated.append(loc)
        self._registry[loc] = self._driver
        return {"scene_id": loc}


class _FakeHub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast_to_location(self, loc, msg):
        self.broadcasts.append((loc, msg))


def _coord(registry, repo, activation, hub, cache):
    from gateway.location_resolver import LocationResolver

    return SceneCoordinator(
        scene_registry=registry,
        cxn_repo=repo,
        ws_hub=hub,
        activation_service=activation,
        location_resolver=LocationResolver(repo, cache),
    )


@pytest.mark.asyncio
async def test_ensure_scene_activates_when_npcs_present():
    registry = {}
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, driver)
    coord = _coord(registry, repo, act, _FakeHub(), {})
    got = await coord.ensure_scene("loc-1")
    assert got is driver
    assert act.activated == ["loc-1"]


@pytest.mark.asyncio
async def test_ensure_scene_idempotent_when_already_registered():
    driver = _FakeDriver()
    registry = {"loc-1": driver}
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, _FakeDriver())
    coord = _coord(registry, repo, act, _FakeHub(), {})
    got = await coord.ensure_scene("loc-1")
    assert got is driver  # the pre-registered driver, not a new one
    assert act.activated == []  # no re-activation


@pytest.mark.asyncio
async def test_ensure_scene_returns_none_without_npcs():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "x", "kind": "location"}]})  # no character
    act = _FakeActivation(registry, _FakeDriver())
    coord = _coord(registry, repo, act, _FakeHub(), {})
    assert await coord.ensure_scene("loc-1") is None
    assert act.activated == []


@pytest.mark.asyncio
async def test_ensure_scene_degrades_on_agent_runtime_unavailable():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})

    class _Boom(_FakeActivation):
        async def activate(self, loc):
            raise AgentRuntimeUnavailable("down")

    coord = _coord(registry, repo, _Boom(registry, _FakeDriver()), _FakeHub(), {})
    assert await coord.ensure_scene("loc-1") is None  # no raise


@pytest.mark.asyncio
async def test_handle_player_message_auto_activates_and_broadcasts():
    registry = {}
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, driver)
    hub = _FakeHub()
    cache = {"North Gate": "loc-1"}  # resolver cache hit (no KG)
    coord = _coord(registry, repo, act, hub, cache)
    handled = await coord.handle_player_message("p1", "North Gate", "Gareth?")
    assert handled is True
    assert act.activated == ["loc-1"]  # auto-activated
    assert driver.calls == [("loc-1", "Gareth?")]
    assert len(hub.broadcasts) == 1
    loc, msg = hub.broadcasts[0]
    assert loc == "North Gate" and msg["npc"] == "Gareth" and msg["summary"] == "Halt!"


@pytest.mark.asyncio
async def test_handle_player_message_no_activation_service_is_p1_behavior():
    # No activation service (P1-style direct construction): only a pre-registered scene works.
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    hub = _FakeHub()
    from gateway.location_resolver import LocationResolver

    coord = SceneCoordinator(
        scene_registry={},
        cxn_repo=repo,
        ws_hub=hub,
        location_resolver=LocationResolver(repo, {"North Gate": "loc-1"}),
    )
    assert await coord.handle_player_message("p1", "North Gate", "hi") is False
    assert hub.broadcasts == []
