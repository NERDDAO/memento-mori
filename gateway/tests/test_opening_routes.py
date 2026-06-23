"""Tests for POST /api/opening/start and POST /api/opening/act.

Contract
--------
T1  POST /api/opening/start returns 200 with player_id and seeded room info;
    opening_registry holds a TurnRouter for that player_id.
T2  POST /api/opening/act with text canned to LOOK → 200, status=="narrated",
    non-empty narration.
T3  POST /api/opening/act with off-script text → 200, status=="clarify"
    (never a 4xx).
T4  POST /api/opening/act with text canned to winning MOVE → 200,
    won==True AND a subsequent /act returns 404 (registry entry dropped).
T5  POST /api/opening/act with unknown player_id → 404.

All builder hooks are monkeypatched to fakes so the test is pure in-process:
no network, no KG, no LLM.
"""

from __future__ import annotations

import pytest
import httpx

# ---------------------------------------------------------------------------
# Fake / stub helpers
# ---------------------------------------------------------------------------

_FIXED_PLAYER_UUID = "deadbeef00000000000000aa"


def _make_fake_comprehension() -> object:
    """Return a FakeComprehensionClient canned for the three opening beats."""
    from memento.cxn.kernel_client import FakeComprehensionClient
    from memento.cxn.types import ComprehendedFrame, FrameRole

    canned = {
        "look around": ComprehendedFrame(
            predicate="look",
            roles=[],
            matched=True,
            raw_text="look around",
        ),
        "go on": ComprehendedFrame(
            predicate="move",
            roles=[FrameRole(role="location", filler="on")],
            matched=True,
            raw_text="go on",
        ),
    }
    return FakeComprehensionClient(canned)


def _make_fake_memory() -> object:
    from memento.memory.null_client import NullMemoryClient
    return NullMemoryClient()


def _make_fake_mirror() -> object:
    from memento.state.chain_mirror import NoopChainMirror
    return NoopChainMirror()


def _make_fake_projection() -> object:
    from memento.state.kg_projection import KgProjectionFake
    return KgProjectionFake()


async def _fake_create_player(
    player_name: str, wallet_address: str, archetype: str
) -> str:
    return _FIXED_PLAYER_UUID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_opening_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace all DI builder hooks on the opening module with fakes."""
    import gateway.routes.opening as opening_mod

    monkeypatch.setattr(opening_mod, "build_comprehension", _make_fake_comprehension)
    monkeypatch.setattr(opening_mod, "build_memory", _make_fake_memory)
    monkeypatch.setattr(opening_mod, "build_mirror", _make_fake_mirror)
    monkeypatch.setattr(opening_mod, "build_projection", _make_fake_projection)
    monkeypatch.setattr(opening_mod, "create_player", _fake_create_player)


@pytest.fixture(autouse=True)
def _clear_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure opening_registry is empty before each test."""
    import gateway.routes.opening as opening_mod
    monkeypatch.setattr(opening_mod, "opening_registry", {})


@pytest.fixture()
def app_transport():
    """Return an ASGITransport wired to the gateway app."""
    from gateway.app import app
    return httpx.ASGITransport(app=app)


def make_client(transport):
    """Create a fresh AsyncClient — never reuse after close."""
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# T1 — /start returns player_id and seeded room
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_returns_player_id_and_room(app_transport):
    async with make_client(app_transport) as c:
        resp = await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
                "archetype": "",
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "player_id" in data
    assert data["player_id"] == _FIXED_PLAYER_UUID

    # Epigraph (the game's opening quote) is surfaced at start
    from memento.opening.deep_roads import OPENING_EPIGRAPH

    assert data["epigraph"] == OPENING_EPIGRAPH
    assert "time of monsters" in data["epigraph"]

    # Registry should hold the router now
    import gateway.routes.opening as opening_mod
    assert _FIXED_PLAYER_UUID in opening_mod.opening_registry


# ---------------------------------------------------------------------------
# T2 — /act with LOOK → narrated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_act_look_returns_narrated(app_transport):
    async with make_client(app_transport) as c:
        # Start first
        await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
                "archetype": "",
            },
        )
        resp = await c.post(
            "/api/opening/act",
            json={"player_id": _FIXED_PLAYER_UUID, "text": "look around"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "narrated", f"Expected narrated, got: {data}"
    assert data.get("narration"), "Expected non-empty narration"


# ---------------------------------------------------------------------------
# T3 — /act with off-script text → clarify (200, not 4xx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_act_offscript_returns_clarify(app_transport):
    async with make_client(app_transport) as c:
        await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
                "archetype": "",
            },
        )
        resp = await c.post(
            "/api/opening/act",
            json={"player_id": _FIXED_PLAYER_UUID, "text": "xyzzy no match"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "clarify"


# ---------------------------------------------------------------------------
# T4 — winning MOVE → won==True; subsequent /act → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_act_winning_move_drops_registry(app_transport):
    async with make_client(app_transport) as c:
        await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
                "archetype": "",
            },
        )
        # We must look first so the dead-adventurer beat fires (FORCED_FIRST
        # beat blocks subsequent turns until surfaced).
        await c.post(
            "/api/opening/act",
            json={"player_id": _FIXED_PLAYER_UUID, "text": "look around"},
        )
        # Now cross the exit (the player is seeded at LOC_DEEP_ROADS, NEXT_ROOM
        # is seeded by start).
        go = await c.post(
            "/api/opening/act",
            json={"player_id": _FIXED_PLAYER_UUID, "text": "go on"},
        )
        assert go.status_code == 200, go.text
        assert go.json().get("won") is True, f"Expected won=True, got: {go.json()}"

        # Registry entry must be gone
        import gateway.routes.opening as opening_mod
        assert _FIXED_PLAYER_UUID not in opening_mod.opening_registry

        # Subsequent /act → 404 (same client, still open)
        second = await c.post(
            "/api/opening/act",
            json={"player_id": _FIXED_PLAYER_UUID, "text": "go on"},
        )
        assert second.status_code == 404


# ---------------------------------------------------------------------------
# T5 — unknown player_id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_act_unknown_player_returns_404(app_transport):
    async with make_client(app_transport) as c:
        resp = await c.post(
            "/api/opening/act",
            json={"player_id": "does-not-exist", "text": "go on"},
        )
    assert resp.status_code == 404
