import pytest

import gateway.app as gw_app


class _Hub:
    def __init__(self):
        self.player_locations = {"p1": "Gate"}
        self.disconnected = []

    async def disconnect(self, pid):
        self.disconnected.append(pid)
        self.player_locations.pop(pid, None)


class _Coord:
    closed: list[str] = []

    async def maybe_close(self, name):
        type(self).closed.append(name)


@pytest.mark.asyncio
async def test_disconnect_closes_departed_scene(monkeypatch):
    hub = _Hub()
    monkeypatch.setattr(gw_app, "ws_hub", hub)
    _Coord.closed = []
    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state",
        classmethod(lambda cls, state: _Coord()),
    )
    await gw_app._evict_scene_on_disconnect("p1")
    assert hub.disconnected == ["p1"]  # still disconnects
    assert _Coord.closed == ["Gate"]  # closes the location the player left


@pytest.mark.asyncio
async def test_disconnect_without_location_is_safe(monkeypatch):
    hub = _Hub()
    hub.player_locations = {}
    monkeypatch.setattr(gw_app, "ws_hub", hub)
    _Coord.closed = []
    await gw_app._evict_scene_on_disconnect("p1")
    assert hub.disconnected == ["p1"]
    assert _Coord.closed == []  # nothing to close


@pytest.mark.asyncio
async def test_eviction_failure_never_raises(monkeypatch):
    hub = _Hub()
    monkeypatch.setattr(gw_app, "ws_hub", hub)

    def _boom(cls, state):
        raise RuntimeError("down")

    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state", classmethod(_boom)
    )
    await gw_app._evict_scene_on_disconnect("p1")  # must not raise
    assert hub.disconnected == ["p1"]  # disconnect still happened
