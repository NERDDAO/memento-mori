"""Tests for POST /v1/tools/{tool} and POST /v1/agents/{id}/activation.

G1 contract:
  - POST /v1/tools/mm_move + valid Bearer(sub=npc_uuid) → 200; NPC location_uuid == B.
  - Missing/expired/garbage Bearer → 401.
  - Forbidden verb / capability miss → 403.
  - POST /v1/agents/{npc}/activation {"cxn_ids":[]} + valid Bearer → 200 {"unlocked":[...]}.
  - Existing /mcp tests stay green (executor reused, not forked).

Test fixture strategy: inject a real seeded InMemoryStateRepository via
app.state so the HTTP route dispatches through the same executor/repo
instance. The check_tool_access KG call is mocked — we test the HTTP
boundary, not KG availability.
"""

from __future__ import annotations

import uuid as _uuid

import httpx
import pytest

_TEST_JWT_SECRET = "unit-test-http-route-secret"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with a stable JWT_SECRET."""
    monkeypatch.setenv("JWT_SECRET", _TEST_JWT_SECRET)


@pytest.fixture()
def world():
    """Return UUIDs + a pre-seeded InMemoryStateRepository.

    Two adjacent location rooms (A→B exit) + a Character NPC in room A.
    """
    from memento.state.in_memory import InMemoryStateRepository

    room_a_id = str(_uuid.uuid4())
    room_b_id = str(_uuid.uuid4())
    npc_id = str(_uuid.uuid4())

    repo = InMemoryStateRepository()

    repo.seed_entity(
        {
            "uuid": room_a_id,
            "kind": "location",
            "name": "Room A",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "exits": [
                    {"direction": "north", "target_uuid": room_b_id, "locked": False}
                ],
                "item_ids": [],
            },
            "is_dead": False,
        }
    )
    repo.seed_entity(
        {
            "uuid": room_b_id,
            "kind": "location",
            "name": "Room B",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "exits": [],
                "item_ids": [],
            },
            "is_dead": False,
        }
    )
    repo.seed_entity(
        {
            "uuid": npc_id,
            "kind": "character",
            "name": "TestNPC",
            "labels": ["Character", "NPC"],
            "location_uuid": room_a_id,
            "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
            "is_dead": False,
        }
    )

    return {
        "repo": repo,
        "room_a_id": room_a_id,
        "room_b_id": room_b_id,
        "npc_id": npc_id,
    }


@pytest.fixture()
def npc_jwt(world: dict) -> str:
    """Mint a valid JWT for the NPC entity."""
    from gateway.engine_auth import sign_jwt

    return sign_jwt(world["npc_id"], type="npc", ttl_seconds=3600)


@pytest.fixture()
def app_with_world(world: dict, monkeypatch: pytest.MonkeyPatch):
    """Return the gateway FastAPI app with app.state wired to the test repo+executor.

    We bypass the full lifespan (which tries to connect to Matrix/Mongo/etc.)
    and directly inject the cxn_repo and a matching executor into app.state.
    """
    from memento.cxn.executor import EffectExecutor
    from memento.state.chain_mirror import NoopChainMirror
    from memento.memory.null_client import NullMemoryClient

    repo = world["repo"]
    mirror = NoopChainMirror()
    memory = NullMemoryClient()
    executor = EffectExecutor(repo=repo, memory=memory, chain=mirror)

    # Import the app — it executes the module-level include_router calls
    # but does NOT run lifespan. We must set app.state manually.
    from gateway.app import app

    app.state.cxn_repo = repo
    app.state.cxn_executor = executor

    return app


# ---------------------------------------------------------------------------
# H1 — mm_move: 200 + location_uuid mutated to room B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mm_move_success(world: dict, npc_jwt: str, app_with_world):
    """POST /v1/tools/mm_move with valid Bearer → 200; NPC ends up in room B."""
    from unittest.mock import AsyncMock, patch

    npc_id = world["npc_id"]
    room_b_id = world["room_b_id"]
    repo = world["repo"]

    # Patch check_tool_access so the KG is not hit in tests
    with (
        patch(
            "gateway.routes.tools_http.check_tool_access",
            new_callable=AsyncMock,
        ),
        patch(
            "gateway.routes.tools_http.broadcast_tool_event",
            new_callable=AsyncMock,
        ),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_world),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/tools/mm_move",
                json={"destination": room_b_id},
                headers={"Authorization": f"Bearer {npc_jwt}"},
            )

    assert resp.status_code == 200, resp.text

    # THE core game-mechanic assertion: state was actually mutated
    npc_doc = await repo.get_entity(npc_id)
    assert npc_doc is not None
    assert npc_doc["location_uuid"] == room_b_id, (
        f"Expected NPC in room B ({room_b_id}), got {npc_doc['location_uuid']}"
    )


# ---------------------------------------------------------------------------
# H2 — missing Bearer → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_bearer_401(app_with_world):
    """POST /v1/tools/mm_move without Authorization header → 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_world),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/v1/tools/mm_move",
            json={"destination": "some-uuid"},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# H3 — invalid Bearer → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_bearer_401(app_with_world):
    """POST /v1/tools/mm_move with a garbage token → 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_world),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/v1/tools/mm_move",
            json={"destination": "some-uuid"},
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# H4 — capability miss → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_miss_403(world: dict, npc_jwt: str, app_with_world):
    """POST /v1/tools/mm_move when check_tool_access raises 403 → 403 response."""
    from unittest.mock import AsyncMock, patch
    from fastapi import HTTPException

    with patch(
        "gateway.routes.tools_http.check_tool_access",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="capability_missing"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_world),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/tools/mm_move",
                json={"destination": world["room_b_id"]},
                headers={"Authorization": f"Bearer {npc_jwt}"},
            )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# H5 — unknown tool → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_404(npc_jwt: str, app_with_world):
    """POST /v1/tools/mm_fly (not in registry) → 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_world),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/v1/tools/mm_fly",
            json={},
            headers={"Authorization": f"Bearer {npc_jwt}"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# H6 — activation route: 200 {"unlocked": [...]}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activation_200(world: dict, npc_jwt: str, app_with_world):
    """POST /v1/agents/{npc}/activation {"cxn_ids":[]} + valid Bearer → 200 {"unlocked":[...]}."""
    npc_id = world["npc_id"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_world),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            f"/v1/agents/{npc_id}/activation",
            json={"cxn_ids": []},
            headers={"Authorization": f"Bearer {npc_jwt}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "unlocked" in body
    assert isinstance(body["unlocked"], list)


# ---------------------------------------------------------------------------
# H7 — activation route: missing Bearer → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activation_missing_bearer_401(world: dict, app_with_world):
    """POST /v1/agents/{id}/activation without token → 401."""
    npc_id = world["npc_id"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_world),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            f"/v1/agents/{npc_id}/activation",
            json={"cxn_ids": []},
        )

    assert resp.status_code == 401
