"""E1 — GM-Room loop end-to-end: deterministic stitched proof.

What this test proves
---------------------
The full GM-Room game loop from RoomDriver.open_room through a per-self JWT
POST /v1/tools/mm_move to the real EffectExecutor and back:

  RoomDriver (real) → per-self JWT harness (faithful stand-in for agent-runtime)
    → gateway /v1/tools/mm_move (real) → EffectExecutor (real)
    → NPC location_uuid == room_B (read back from InMemoryStateRepository)
    → episode ingested by CapturingMemoryClient (actor_id == npc_uuid)

Design
------
- Runs entirely in the gateway venv (no agent-runtime import required).
- Uses the REAL RoomDriver (D1) and REAL EffectExecutor / InMemoryStateRepository.
- Stitches the cross-venv boundary with a "per-self JWT harness": on a turn,
  the harness mints sign_jwt(sub=<npc_uuid>, type="npc") — exactly what the
  real agent-runtime CxnGatewayClient does — and POSTs to the real gateway
  via httpx ASGITransport loopback.
- The agent-runtime room route (open/turn/close) is replaced by a minimal
  Starlette stub that captures requests and drives the JWT-POST on "turn".
- The only stubbed element is the ReAct LLM decision to call mm_move;
  the mechanical part (JWT → gateway → executor → state) is fully real.

Per-self identity assertion
---------------------------
- The JWT minted per turn has sub = npc_uuid.
- The executor reads the JWT sub as the agent.
- The state mutation (location_uuid change) applies to npc_uuid.
- The episode actor_id == npc_uuid.
Together these prove "sub=X drove X's move."

Assertions
----------
E1-A: HTTP 200 from /v1/tools/mm_move.
E1-B: npc.location_uuid == room_b_id (read back via repo.get_entity).
E1-C: CapturingMemoryClient.ingested has exactly one episode.
E1-D: episode.actor_id == npc_id  (per-self identity drove it).
E1-E: episode.content contains "moved to" (MOVE episode_template rendered).
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

_TEST_JWT_SECRET = "e1-gm-room-loop-secret"

# ---------------------------------------------------------------------------
# Fixtures — world seeding (reuses the same pattern as test_tools_http_route.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module runs with a stable JWT_SECRET."""
    monkeypatch.setenv("JWT_SECRET", _TEST_JWT_SECRET)


@pytest.fixture()
def world():
    """Return UUIDs + a pre-seeded InMemoryStateRepository.

    Two adjacent location rooms (A→B exit via direction "north")
    + a Character NPC in room A.
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
            "attrs": {"exits": [], "item_ids": []},
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


# ---------------------------------------------------------------------------
# Gateway app fixture — real EffectExecutor + CapturingMemoryClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def capturing_memory():
    """Return a CapturingMemoryClient for episode assertions."""
    from memento.memory.capturing_client import CapturingMemoryClient

    return CapturingMemoryClient()


@pytest.fixture()
def gateway_app(world: dict, capturing_memory):
    """Real gateway app wired to the test repo + executor + capturing memory.

    Bypasses the full lifespan (which requires Matrix/Mongo) by directly
    injecting app.state.cxn_repo and app.state.cxn_executor — the same
    pattern used in test_tools_http_route.py.
    """
    from memento.cxn.executor import EffectExecutor
    from memento.state.chain_mirror import NoopChainMirror
    from gateway.app import app

    repo = world["repo"]
    mirror = NoopChainMirror()
    executor = EffectExecutor(repo=repo, memory=capturing_memory, chain=mirror)

    app.state.cxn_repo = repo
    app.state.cxn_executor = executor

    return app


# ---------------------------------------------------------------------------
# Per-self JWT harness — faithful stand-in for agent-runtime CxnGatewayClient
# ---------------------------------------------------------------------------


def _build_agent_runtime_stub(
    gateway_asgi,
    npc_id: str,
    room_b_id: str,
) -> tuple[Any, list[dict]]:
    """Build a minimal Starlette stub for /v1/scenes/{room_id}/{open,turn,close}.

    On `open`:  returns a stub source_episode_id.
    On `turn`:  mints a per-self JWT (sub=npc_id) and POSTs /v1/tools/mm_move
                with destination=room_b_id to the real gateway via ASGITransport.
                Records the response.
    On `close`: returns a stub task_id.

    This is EXACTLY what the real agent-runtime room route + backend contract
    guarantees on a turn: mint sub=<acting_npc_uuid> JWT + POST mm_move.
    """
    turn_responses: list[dict] = []

    async def _handle_open(request: Request) -> JSONResponse:
        return JSONResponse({"source_episode_id": "stub-ep-001"})

    async def _handle_turn(request: Request) -> JSONResponse:
        from gateway.engine_auth import sign_jwt

        # Per-self JWT: sub = npc UUID (the entity whose turn it is)
        token = sign_jwt(npc_id, type="npc", ttl_seconds=3600)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway_asgi),
            base_url="http://testserver",
        ) as gw_client:
            from unittest.mock import AsyncMock, patch

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
                resp = await gw_client.post(
                    "/v1/tools/mm_move",
                    json={"destination": room_b_id},
                    headers={"Authorization": f"Bearer {token}"},
                )

        turn_responses.append({"status_code": resp.status_code, "body": resp.json()})
        return JSONResponse(
            {"response_text": "NPC moved.", "tool_response": resp.json()}
        )

    async def _handle_close(request: Request) -> JSONResponse:
        return JSONResponse({"task_id": "stub-close-001", "snapshot_size": 0})

    stub_app = Starlette(
        routes=[
            Route("/v1/scenes/{room_id}/open", _handle_open, methods=["POST"]),
            Route("/v1/scenes/{room_id}/turn", _handle_turn, methods=["POST"]),
            Route("/v1/scenes/{room_id}/close", _handle_close, methods=["POST"]),
        ]
    )
    return stub_app, turn_responses


# ---------------------------------------------------------------------------
# E1 — Full GM-Room loop: open → turn (mm_move via per-self JWT) → close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gm_room_loop_move_and_episode(
    world: dict, capturing_memory, gateway_app
):
    """E1 capstone: open room, drive one turn (mm_move), close room.

    Asserts:
      E1-A: /v1/tools/mm_move returned HTTP 200.
      E1-B: NPC location_uuid == room_b_id (read back from repo).
      E1-C: Exactly one episode was ingested.
      E1-D: episode.actor_id == npc_id (per-self identity drove the move).
      E1-E: episode.content mentions "moved to" (MOVE template rendered).
    """
    npc_id = world["npc_id"]
    room_a_id = world["room_a_id"]
    room_b_id = world["room_b_id"]
    repo = world["repo"]

    stub_app, turn_responses = _build_agent_runtime_stub(gateway_app, npc_id, room_b_id)

    # Wire RoomDriver to the stub agent-runtime
    from gateway.room_driver import RoomDriver

    stub_transport = httpx.ASGITransport(app=stub_app)  # type: ignore[arg-type]
    ar_client = httpx.AsyncClient(
        transport=stub_transport, base_url="http://agent-runtime-stub"
    )
    driver = RoomDriver(
        repo=repo,
        agent_runtime_client=ar_client,
        bonfire_id="e1-test-bonfire",
        internal_token="e1-internal-token",
    )

    try:
        # Phase 1: open room — builds roster from repo, POSTs /open to stub
        open_resp = await driver.open_room(room_a_id)
        assert "source_episode_id" in open_resp

        # Phase 2: drive turn — stub mints per-self JWT + POSTs mm_move to
        #          real gateway → real EffectExecutor executes the move
        await driver.drive_turn(room_a_id, "Go north.", addressed_name=None)

        # Phase 3: close room
        close_resp = await driver.close_room(room_a_id)
        assert "task_id" in close_resp

    finally:
        await ar_client.aclose()

    # -----------------------------------------------------------------------
    # E1-A: The turn stub's gateway POST returned 200
    # -----------------------------------------------------------------------
    assert len(turn_responses) == 1, (
        f"Expected 1 turn response, got {len(turn_responses)}"
    )
    assert turn_responses[0]["status_code"] == 200, (
        f"Expected HTTP 200 from /v1/tools/mm_move, got {turn_responses[0]['status_code']}: "
        f"{turn_responses[0]['body']}"
    )

    # -----------------------------------------------------------------------
    # E1-B: NPC's location_uuid was durably mutated to room_b_id
    # -----------------------------------------------------------------------
    npc_doc = await repo.get_entity(npc_id)
    assert npc_doc is not None, "NPC entity not found in repo after move"
    assert npc_doc["location_uuid"] == room_b_id, (
        f"Expected NPC location_uuid == room_b_id ({room_b_id!r}), "
        f"got {npc_doc['location_uuid']!r}"
    )

    # -----------------------------------------------------------------------
    # E1-C: Exactly one episode was produced by Phase-3 ingest_episode
    # -----------------------------------------------------------------------
    assert len(capturing_memory.ingested) == 1, (
        f"Expected exactly 1 ingested episode, got {len(capturing_memory.ingested)}: "
        f"{capturing_memory.ingested}"
    )

    episode = capturing_memory.ingested[0]

    # -----------------------------------------------------------------------
    # E1-D: episode.actor_id == npc_id (per-self identity drove the move)
    # -----------------------------------------------------------------------
    assert episode["actor_id"] == npc_id, (
        f"Expected episode.actor_id == npc_id ({npc_id!r}), got {episode['actor_id']!r}"
    )

    # -----------------------------------------------------------------------
    # E1-E: Episode text matches the MOVE template ("{agent_name} moved to {location_name}.")
    # -----------------------------------------------------------------------
    assert "moved to" in episode["content"].lower(), (
        f"Expected 'moved to' in episode content, got: {episode['content']!r}"
    )


# ---------------------------------------------------------------------------
# E1b — per-self identity contract: NPC X's JWT drives X's move (not Y's)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_self_identity_only_moves_acting_npc(
    world: dict, capturing_memory, gateway_app
):
    """Confirm sub=X in the JWT causes X (not Y) to move.

    Seeds a second NPC in room A; the turn JWT has sub=npc_id (NPC-1).
    After the turn: NPC-1 is in room B; NPC-2 remains in room A.
    """
    from memento.cxn.executor import EffectExecutor
    from memento.state.chain_mirror import NoopChainMirror
    from gateway.engine_auth import sign_jwt

    npc_id = world["npc_id"]
    room_a_id = world["room_a_id"]
    room_b_id = world["room_b_id"]
    repo = world["repo"]

    # Seed a second NPC in room A (must NOT move)
    npc2_id = str(_uuid.uuid4())
    repo.seed_entity(
        {
            "uuid": npc2_id,
            "kind": "character",
            "name": "Bystander",
            "labels": ["Character", "NPC"],
            "location_uuid": room_a_id,
            "attrs": {"hp": 5, "max_hp": 5, "inventory": []},
            "is_dead": False,
        }
    )

    # Directly call the gateway: mint JWT for npc_id (not npc2_id), POST mm_move
    token = sign_jwt(npc_id, type="npc", ttl_seconds=3600)

    from unittest.mock import AsyncMock, patch

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
            transport=httpx.ASGITransport(app=gateway_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/tools/mm_move",
                json={"destination": room_b_id},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200, resp.text

    # NPC-1 (the JWT sub) is now in room B
    npc1_doc = await repo.get_entity(npc_id)
    assert npc1_doc is not None
    assert npc1_doc["location_uuid"] == room_b_id, (
        f"NPC-1 should be in room B, got {npc1_doc['location_uuid']!r}"
    )

    # NPC-2 (the bystander) remains in room A
    npc2_doc = await repo.get_entity(npc2_id)
    assert npc2_doc is not None
    assert npc2_doc["location_uuid"] == room_a_id, (
        f"NPC-2 should still be in room A, got {npc2_doc['location_uuid']!r}"
    )

    # Episode actor_id == npc_id (not npc2_id)
    assert len(capturing_memory.ingested) == 1
    assert capturing_memory.ingested[0]["actor_id"] == npc_id


# ---------------------------------------------------------------------------
# E2 — Arc-integration proof: capability-chain enforced over one label store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_chain_enforced_over_one_store(world, capturing_memory):
    """Arc-integration proof: labels -> roster capabilities + KG-uuid embodiment ->
    per-self JWT -> the real check_tool_access reading the SAME label store -> enforcement.

    Identity-uuid: KG uuid == engine uuid (one id behind gate AND executor), so a real
    mm_move reaches 200 and a label revocation in the one store flips allow (200) -> deny (403).
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    import httpx
    import memento.bonfires_client as bonfires_client
    from gateway.app import app
    from gateway.engine_auth import sign_jwt
    from gateway.room_driver import RoomDriver
    from memento.cxn.executor import EffectExecutor
    from memento.state.chain_mirror import NoopChainMirror

    repo = world["repo"]
    npc_id = world["npc_id"]
    room_a_id = world["room_a_id"]
    room_b_id = world["room_b_id"]

    kg_uuid = npc_id  # identity-uuid: KG uuid coincides with engine uuid

    # --- THE ONE STORE: a single mutable label-bearing entity dict, read by BOTH
    #     the roster spec-builder AND the gate.
    label_store: dict[str, dict] = {
        kg_uuid: {"uuid": kg_uuid, "name": "Guard", "labels": ["Character", "NPC"]}
    }

    class _IdentityProjection:
        """KG uuid == engine uuid (identity map), matching #4-B-A's live shape in identity mode."""
        def kg_uuid_for(self, engine_uuid: str) -> str | None:
            return kg_uuid if engine_uuid == npc_id else None

    class _GateKg:
        """The slice of the KG client check_tool_access uses, pointed at the one store."""
        def get_entity(self, uuid: str) -> dict | None:
            return label_store.get(uuid)

    # --- ROSTER HALF: capabilities + KG-uuid embodiment, sourced from the one store ---
    ar_client = httpx.AsyncClient(base_url="http://unused")  # _npc_self_spec never calls it
    try:
        driver = RoomDriver(
            repo=repo,
            agent_runtime_client=ar_client,
            bonfire_id="arc-test-bonfire",
            projection=_IdentityProjection(),
        )
        spec = driver._npc_self_spec(label_store[kg_uuid])
        assert spec["embodiment_agent_id"] == kg_uuid          # KG-uuid embodiment
        assert "mm_move" in spec["capabilities"]               # granted by NPC kit
        assert "mm_attack" in spec["capabilities"]
    finally:
        await ar_client.aclose()

    # --- GATE HALF: real check_tool_access over the SAME store; executor over InMemory world ---
    app.state.cxn_repo = repo
    app.state.cxn_executor = EffectExecutor(
        repo=repo, memory=capturing_memory, chain=NoopChainMirror()
    )
    token = sign_jwt(kg_uuid, type="npc", ttl_seconds=3600)
    auth = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    gw = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        with (
            patch.object(bonfires_client, "get_client",
                         lambda: SimpleNamespace(kg=_GateKg())),
            patch("gateway.routes.tools_http.broadcast_tool_event", new_callable=AsyncMock),
        ):
            # ALLOWED: gate reads ["Character","NPC"] -> mm_move allowed -> real move -> 200
            resp = await gw.post(
                "/v1/tools/mm_move", json={"destination": room_b_id}, headers=auth
            )
            assert resp.status_code == 200, resp.text
            moved = await repo.get_entity(npc_id)
            assert moved["location_uuid"] == room_b_id          # real state change

            # REVOKE the NPC kit in the ONE store -> roster source AND gate both lose mm_move
            label_store[kg_uuid]["labels"] = ["Character"]
            assert "mm_move" not in driver._npc_self_spec(label_store[kg_uuid])["capabilities"]

            # DENIED: gate now reads ["Character"] -> mm_move not allowed -> 403 (before executor)
            resp2 = await gw.post(
                "/v1/tools/mm_move", json={"destination": room_a_id}, headers=auth
            )
            assert resp2.status_code == 403
            assert resp2.json()["detail"]["error"] == "capability_missing"

        # IDENTIFIER INVARIANT: the JWT sub == the KG uuid the gate resolved == embodiment id
        assert kg_uuid == npc_id == spec["embodiment_agent_id"]
    finally:
        await gw.aclose()
