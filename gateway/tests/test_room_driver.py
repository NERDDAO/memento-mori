"""Tests for RoomDriver — room→location roster build, trivial who-acts, agent-runtime calls.

TDD contract:
  T1  open_room POSTs /open with both NPC self specs; embodiment_agent_id = entity UUIDs (NOT names)
  T2  open_room gm_self has a deterministic id and embodiment_agent_id
  T3  drive_turn(addressed_name="goblin") POSTs /turn with self_id = goblin's uuid
  T4  drive_turn with no address and single NPC picks that NPC
  T5  close_room POSTs /close
  T6  internal-token header is present on every call (open, turn, close)
  T7  drive_turn with addressed_name not in registry falls back to the single NPC
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# ---------------------------------------------------------------------------
# Stub agent-runtime app that records calls
# ---------------------------------------------------------------------------


class _Recorder:
    """Accumulates (method, url, headers, body) for every request received."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, method: str, url: str, headers: dict, body: Any) -> None:
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "body": body}
        )


recorder = _Recorder()


async def _handle_open(request: Request) -> JSONResponse:
    body = await request.json()
    recorder.record("POST", str(request.url), dict(request.headers), body)
    return JSONResponse({"source_episode_id": "ep-test-001"})


async def _handle_turn(request: Request) -> JSONResponse:
    body = await request.json()
    recorder.record("POST", str(request.url), dict(request.headers), body)
    return JSONResponse({"response_text": "The goblin grunts."})


async def _handle_close(request: Request) -> JSONResponse:
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    recorder.record("POST", str(request.url), dict(request.headers), body)
    return JSONResponse({"task_id": "task-close-001", "snapshot_size": 0})


_stub_app = Starlette(
    routes=[
        Route("/v1/rooms/{room_id}/open", _handle_open, methods=["POST"]),
        Route("/v1/rooms/{room_id}/turn", _handle_turn, methods=["POST"]),
        Route("/v1/rooms/{room_id}/close", _handle_close, methods=["POST"]),
    ]
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_INTERNAL_TOKEN = "test-internal-token-abc123"
_BONFIRE_ID = "bonfire-test-001"

# stable UUIDs for the test world
_LOC_UUID = str(_uuid.uuid4())
_GOBLIN_UUID = str(_uuid.uuid4())
_TROLL_UUID = str(_uuid.uuid4())
_PLAYER_UUID = str(_uuid.uuid4())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_recorder():
    """Clear recorded calls before each test."""
    recorder.calls.clear()


@pytest.fixture()
def repo():
    """Seeded InMemoryStateRepository: 1 location + 2 character NPCs + 1 player."""
    from memento.state.in_memory import InMemoryStateRepository

    r = InMemoryStateRepository()

    r.seed_entity(
        {
            "uuid": _LOC_UUID,
            "name": "The Dungeon",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"description": "A dank dungeon.", "exits": []},
            "is_dead": False,
        }
    )
    r.seed_entity(
        {
            "uuid": _GOBLIN_UUID,
            "name": "goblin",
            "kind": "character",
            "labels": ["Character", "NPC"],
            "location_uuid": _LOC_UUID,
            "attrs": {"hp": 10, "max_hp": 10},
            "is_dead": False,
        }
    )
    r.seed_entity(
        {
            "uuid": _TROLL_UUID,
            "name": "troll",
            "kind": "character",
            "labels": ["Character", "NPC"],
            "location_uuid": _LOC_UUID,
            "attrs": {"hp": 30, "max_hp": 30},
            "is_dead": False,
        }
    )
    # Player also at the location — must NOT appear in NPC roster
    r.seed_entity(
        {
            "uuid": _PLAYER_UUID,
            "name": "hero",
            "kind": "character",
            "labels": ["Character", "Player"],
            "location_uuid": _LOC_UUID,
            "attrs": {"hp": 50, "max_hp": 50},
            "is_dead": False,
        }
    )
    return r


@pytest.fixture()
def repo_single():
    """Repo with only one character NPC (goblin)."""
    from memento.state.in_memory import InMemoryStateRepository

    r = InMemoryStateRepository()
    r.seed_entity(
        {
            "uuid": _LOC_UUID,
            "name": "The Dungeon",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"description": "A dank dungeon.", "exits": []},
            "is_dead": False,
        }
    )
    r.seed_entity(
        {
            "uuid": _GOBLIN_UUID,
            "name": "goblin",
            "kind": "character",
            "labels": ["Character", "NPC"],
            "location_uuid": _LOC_UUID,
            "attrs": {"hp": 10, "max_hp": 10},
            "is_dead": False,
        }
    )
    return r


@pytest.fixture()
def npc_registry_seeded():
    """Seed the npc_registry module with goblin and troll so name→uuid resolution works."""
    from gateway import npc_registry

    npc_registry._registry.clear()
    npc_registry.register_npc(
        agent_id="agent-goblin",
        name="goblin",
        location=_LOC_UUID,
        kg_uuid=_GOBLIN_UUID,
    )
    npc_registry.register_npc(
        agent_id="agent-troll",
        name="troll",
        location=_LOC_UUID,
        kg_uuid=_TROLL_UUID,
    )
    yield
    npc_registry._registry.clear()


def _make_driver(repo_instance, monkeypatch):
    """Build a RoomDriver wired to the ASGI stub."""
    monkeypatch.setenv("AGENT_RUNTIME_BASE_URL", "http://agent-runtime")
    monkeypatch.setenv("AGENT_RUNTIME_INTERNAL_TOKEN", _INTERNAL_TOKEN)

    from gateway.room_driver import RoomDriver

    transport = httpx.ASGITransport(app=_stub_app)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, base_url="http://agent-runtime")

    return RoomDriver(
        repo=repo_instance,
        agent_runtime_client=client,
        bonfire_id=_BONFIRE_ID,
        internal_token=_INTERNAL_TOKEN,
        player_labels={"Player"},
    ), client


@pytest.fixture()
def driver_and_client(repo, npc_registry_seeded, monkeypatch):
    drv, client = _make_driver(repo, monkeypatch)
    return drv, client


@pytest.fixture()
def driver_single_and_client(repo_single, npc_registry_seeded, monkeypatch):
    drv, client = _make_driver(repo_single, monkeypatch)
    return drv, client


# ---------------------------------------------------------------------------
# T1 — open_room sends both NPC self specs with entity UUIDs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_room_roster_has_npc_uuids(driver_and_client):
    drv, client = driver_and_client
    try:
        await drv.open_room(_LOC_UUID)
    finally:
        await client.aclose()

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert "/open" in call["url"]

    body = call["body"]
    roster = body["roster"]
    # Must have exactly 2 NPCs (goblin + troll; player excluded)
    assert len(roster) == 2

    embodiment_ids = {spec["embodiment_agent_id"] for spec in roster}
    assert _GOBLIN_UUID in embodiment_ids, (
        "goblin UUID must be in roster embodiment_agent_ids"
    )
    assert _TROLL_UUID in embodiment_ids, (
        "troll UUID must be in roster embodiment_agent_ids"
    )

    # Names must NOT appear as embodiment_agent_id
    assert "goblin" not in embodiment_ids
    assert "troll" not in embodiment_ids

    # Each spec must carry seat="LLM"
    for spec in roster:
        assert spec["seat"] == "LLM"


# ---------------------------------------------------------------------------
# T2 — open_room gm_self is deterministic and carries embodiment_agent_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_room_gm_self(driver_and_client):
    drv, client = driver_and_client
    try:
        await drv.open_room(_LOC_UUID)
    finally:
        await client.aclose()

    body = recorder.calls[0]["body"]
    gm_self = body["gm_self"]
    assert gm_self["id"] == f"gm:{_LOC_UUID}"
    assert gm_self["embodiment_agent_id"] == f"gm:{_LOC_UUID}"
    assert isinstance(gm_self["names"], list)
    assert len(gm_self["names"]) > 0


# ---------------------------------------------------------------------------
# T3 — drive_turn with addressed_name resolves to that NPC's uuid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drive_turn_addressed_name(driver_and_client):
    drv, client = driver_and_client
    try:
        await drv.open_room(_LOC_UUID)
        recorder.calls.clear()

        await drv.drive_turn(_LOC_UUID, "I attack the goblin!", addressed_name="goblin")
    finally:
        await client.aclose()

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert "/turn" in call["url"]
    assert call["body"]["self_id"] == _GOBLIN_UUID
    assert call["body"]["message"] == "I attack the goblin!"


# ---------------------------------------------------------------------------
# T4 — drive_turn with no address + single NPC picks that NPC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drive_turn_single_npc_no_address(driver_single_and_client):
    drv, client = driver_single_and_client
    try:
        await drv.open_room(_LOC_UUID)
        recorder.calls.clear()

        await drv.drive_turn(_LOC_UUID, "Hello?")
    finally:
        await client.aclose()

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["body"]["self_id"] == _GOBLIN_UUID


# ---------------------------------------------------------------------------
# T5 — close_room POSTs /close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_room(driver_and_client):
    drv, client = driver_and_client
    try:
        await drv.open_room(_LOC_UUID)
        recorder.calls.clear()

        await drv.close_room(_LOC_UUID)
    finally:
        await client.aclose()

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert "/close" in call["url"]


# ---------------------------------------------------------------------------
# T6 — internal-token header on every call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_token_header_on_all_calls(driver_and_client):
    drv, client = driver_and_client
    try:
        await drv.open_room(_LOC_UUID)
        await drv.drive_turn(_LOC_UUID, "hi", addressed_name="goblin")
        await drv.close_room(_LOC_UUID)
    finally:
        await client.aclose()

    assert len(recorder.calls) == 3
    for call in recorder.calls:
        assert call["headers"].get("x-internal-token") == _INTERNAL_TOKEN, (
            f"Expected X-Internal-Token header on {call['url']}"
        )


# ---------------------------------------------------------------------------
# T7 — drive_turn with unknown addressed_name falls back to the single NPC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drive_turn_unknown_name_falls_back(driver_single_and_client):
    drv, client = driver_single_and_client
    try:
        await drv.open_room(_LOC_UUID)
        recorder.calls.clear()

        # "wizard" is not in npc_registry — fall back to the only NPC
        await drv.drive_turn(_LOC_UUID, "Where is the wizard?", addressed_name="wizard")
    finally:
        await client.aclose()

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["body"]["self_id"] == _GOBLIN_UUID
