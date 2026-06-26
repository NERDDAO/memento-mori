"""Tests for GET /api/opening/room/{room_uuid}/contents?player_id=…

Contract
--------
C1  After POST /api/opening/start, GET /api/opening/room/{location_id}/contents
    with the returned player_id → 200 and {"things": [...]} whose names include
    "a dying adventurer" (deterministically seeded canon character at LOC_DEEP_ROADS).

C2  GET /api/opening/room/{room_uuid}/contents?player_id=does-not-exist → 404.

Test setup mirrors test_opening_routes.py: all DI builder hooks monkeypatched to
fakes, opening_registry AND opening_repos cleared before each test.
"""

from __future__ import annotations

import pytest
import httpx


# ---------------------------------------------------------------------------
# Fake / stub helpers (mirrors test_opening_routes.py)
# ---------------------------------------------------------------------------


def _make_fake_comprehension() -> object:
    from memento.cxn.kernel_client import FakeComprehensionClient
    from memento.cxn.types import ComprehendedFrame

    return FakeComprehensionClient({})


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
    return "deadbeef00000000000000aa"


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
    """Ensure opening_registry AND opening_repos are empty before each test."""
    import gateway.routes.opening as opening_mod

    monkeypatch.setattr(opening_mod, "opening_registry", {})
    monkeypatch.setattr(opening_mod, "opening_repos", {})


@pytest.fixture()
def app_transport():
    """Return an ASGITransport wired to the gateway app."""
    from gateway.app import app
    return httpx.ASGITransport(app=app)


def make_client(transport):
    """Create a fresh AsyncClient — never reuse after close."""
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# C1 — room_contents returns seeded entities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_contents_returns_seeded_entities(app_transport):
    """POST /start then GET room contents → 200 with 'a dying adventurer' in names."""
    async with make_client(app_transport) as c:
        # Start a fresh opening session
        start_resp = await c.post(
            "/api/opening/start",
            json={
                "player_name": "TestHero",
                "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
                "archetype": "",
            },
        )
        assert start_resp.status_code == 200, start_resp.text
        start_data = start_resp.json()
        player_id = start_data["player_id"]
        location_id = start_data["location_id"]

        # Fetch room contents
        contents_resp = await c.get(
            f"/api/opening/room/{location_id}/contents",
            params={"player_id": player_id},
        )

    assert contents_resp.status_code == 200, contents_resp.text
    data = contents_resp.json()
    assert "things" in data, f"Expected 'things' key, got: {data}"
    assert isinstance(data["things"], list), "'things' must be a list"

    # "a dying adventurer" is the sole canon character seeded at LOC_DEEP_ROADS
    # by load_seed_room (canon=True, kind="character", name="a dying adventurer").
    # The player entity is also there (kind="character", name="TestHero").
    # Both appear via entities_at_location (non-item entities at location_uuid).
    # iron_blade and threat are non-canon → not seeded → not returned.
    names = [t["name"] for t in data["things"]]
    assert "a dying adventurer" in names, (
        f"Expected 'a dying adventurer' in things names, got: {names}"
    )


# ---------------------------------------------------------------------------
# C2 — unknown player_id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_contents_unknown_player_returns_404(app_transport):
    """GET room contents with unknown player_id → 404."""
    from memento.opening.deep_roads import LOC_DEEP_ROADS

    async with make_client(app_transport) as c:
        resp = await c.get(
            f"/api/opening/room/{LOC_DEEP_ROADS}/contents",
            params={"player_id": "does-not-exist"},
        )

    assert resp.status_code == 404, resp.text
