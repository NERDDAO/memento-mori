import pytest

from gateway.location_resolver import LocationResolver
from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    async def drive_turn(self, loc, msg, *, addressed_name=None):
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
        self._registry, self._driver = registry, driver

    async def activate(self, loc):
        self._registry[loc] = self._driver
        return {"scene_id": loc}


class _FakeHub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast_to_location(self, loc, msg):
        self.broadcasts.append((loc, msg))


def _coord(registry, repo, act, hub, cache):
    return SceneCoordinator(
        scene_registry=registry,
        cxn_repo=repo,
        ws_hub=hub,
        activation_service=act,
        location_resolver=LocationResolver(repo, cache),
    )


@pytest.mark.asyncio
async def test_npc_joined_emitted_once_on_fresh_activation():
    registry = {}
    repo = _FakeRepo(
        {"loc-1": [{"uuid": "npc-1", "kind": "character", "name": "Gareth"}]}
    )
    hub = _FakeHub()
    coord = _coord(
        registry, repo, _FakeActivation(registry, _FakeDriver()), hub, {"Gate": "loc-1"}
    )

    await coord.handle_player_message("p1", "Gate", "hi")
    joined = [m for _, m in hub.broadcasts if m["type"] == "npc_joined"]
    assert len(joined) == 1
    assert joined[0]["npc_name"] == "Gareth" and joined[0]["npc_id"] == "npc-1"

    # Second message: scene already registered -> no re-emit.
    hub.broadcasts.clear()
    await coord.handle_player_message("p1", "Gate", "still here?")
    assert [m for _, m in hub.broadcasts if m["type"] == "npc_joined"] == []


@pytest.mark.asyncio
async def test_no_npc_joined_when_no_scene_activates():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "x", "kind": "location"}]})  # no character
    hub = _FakeHub()
    coord = _coord(
        registry, repo, _FakeActivation(registry, _FakeDriver()), hub, {"Gate": "loc-1"}
    )
    assert await coord.handle_player_message("p1", "Gate", "hi") is False
    assert [m for _, m in hub.broadcasts if m["type"] == "npc_joined"] == []
