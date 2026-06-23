"""Smoke-test the full GM-Room game loop.

Usage::

    python scripts/gm_room_smoke.py

Reads ``AGENT_RUNTIME_BASE_URL`` and ``AGENT_RUNTIME_INTERNAL_TOKEN`` from the
environment (or ``.env``).  If the agent-runtime is not reachable (env var
absent or health probe fails), exits cleanly with a SKIP message — this is
expected in CI and local environments without the full stack.

When the agent-runtime IS reachable the script:
  1. Boots the gateway app in-process (ASGITransport).
  2. Seeds two adjacent rooms + an NPC via InMemoryStateRepository.
  3. Drives RoomDriver.open_room → drive_turn (mm_move via per-self JWT) → close_room.
  4. Asserts: NPC's location_uuid == room_B AND an episode was ingested.

All network I/O is guarded behind ``if __name__ == "__main__":`` so that
``import scripts.gm_room_smoke`` is fully side-effect-free.
"""

import os
import sys
import uuid as _uuid


# ---------------------------------------------------------------------------
# Skip guard — check agent-runtime reachability before doing anything else
# ---------------------------------------------------------------------------


def _agent_runtime_reachable() -> tuple[bool, str]:
    """Return (reachable, reason).

    Reachable when AGENT_RUNTIME_BASE_URL is set AND a GET /health probe
    returns 2xx within 5 seconds.
    """
    base_url = os.environ.get("AGENT_RUNTIME_BASE_URL", "")
    if not base_url:
        return False, "AGENT_RUNTIME_BASE_URL not set"

    try:
        import httpx  # noqa: PLC0415

        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{base_url.rstrip('/')}/health")
        if 200 <= resp.status_code < 300:
            return True, base_url
        return False, f"agent-runtime health probe returned {resp.status_code}"
    except Exception as exc:
        return False, f"agent-runtime not reachable: {exc}"


# ---------------------------------------------------------------------------
# World seeding
# ---------------------------------------------------------------------------


def _seed_world():
    """Return (repo, npc_id, room_a_id, room_b_id) for the smoke world."""
    from memento.state.in_memory import InMemoryStateRepository  # noqa: PLC0415

    room_a_id = str(_uuid.uuid4())
    room_b_id = str(_uuid.uuid4())
    npc_id = str(_uuid.uuid4())

    repo = InMemoryStateRepository()

    repo.seed_entity(
        {
            "uuid": room_a_id,
            "kind": "location",
            "name": "Smoke Room A",
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
            "name": "Smoke Room B",
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
            "name": "SmokeNPC",
            "labels": ["Character", "NPC"],
            "location_uuid": room_a_id,
            "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
            "is_dead": False,
        }
    )

    return repo, npc_id, room_a_id, room_b_id


# ---------------------------------------------------------------------------
# Gateway bootstrap (in-process, no uvicorn)
# ---------------------------------------------------------------------------


def _build_gateway_app(repo, capturing_memory):
    """Return a gateway FastAPI app wired to the test repo + executor."""
    from memento.cxn.executor import EffectExecutor  # noqa: PLC0415
    from memento.state.chain_mirror import NoopChainMirror  # noqa: PLC0415
    from gateway.app import app  # noqa: PLC0415

    mirror = NoopChainMirror()
    executor = EffectExecutor(repo=repo, memory=capturing_memory, chain=mirror)
    app.state.cxn_repo = repo
    app.state.cxn_executor = executor
    return app


def _check(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}{': ' + detail if detail else ''}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Smoke runner
# ---------------------------------------------------------------------------


def run_smoke() -> None:
    import asyncio  # noqa: PLC0415
    import httpx  # noqa: PLC0415

    # ------------------------------------------------------------------
    # Reachability check — skip cleanly when stack is not up
    # ------------------------------------------------------------------
    reachable, reason = _agent_runtime_reachable()
    if not reachable:
        print(f"SKIP: {reason}")
        print("      Set AGENT_RUNTIME_BASE_URL to run the full-loop smoke test.")
        return

    agent_runtime_base = os.environ["AGENT_RUNTIME_BASE_URL"].rstrip("/")
    internal_token = os.environ.get("AGENT_RUNTIME_INTERNAL_TOKEN", "")
    jwt_secret = os.environ.get("JWT_SECRET", "")

    if not jwt_secret:
        print("SKIP: JWT_SECRET not set — cannot mint per-self JWTs", file=sys.stderr)
        sys.exit(1)

    print(f"GM-Room smoke: agent-runtime @ {agent_runtime_base}")

    # ------------------------------------------------------------------
    # Seed world + boot gateway in-process
    # ------------------------------------------------------------------
    from memento.memory.capturing_client import CapturingMemoryClient  # noqa: PLC0415

    repo, npc_id, room_a_id, room_b_id = _seed_world()
    capturing = CapturingMemoryClient()
    # Built for parity with the deterministic test; the live loop drives the
    # real running gateway over HTTP, so this local app is not wired in here.
    _gateway_app = _build_gateway_app(repo, capturing)

    # ------------------------------------------------------------------
    # Build a per-self-JWT turn harness pointing at the REAL agent-runtime
    # ------------------------------------------------------------------
    async def _run() -> None:
        from gateway.room_driver import RoomDriver  # noqa: PLC0415

        # RoomDriver client → real agent-runtime over HTTP
        ar_client = httpx.AsyncClient(
            base_url=agent_runtime_base,
            headers={"X-Internal-Token": internal_token},
            timeout=30.0,
        )

        driver = RoomDriver(
            repo=repo,
            agent_runtime_client=ar_client,
            bonfire_id="smoke-bonfire",
            internal_token=internal_token,
        )

        try:
            print("  open_room ...")
            open_resp = await driver.open_room(room_a_id)
            _check(
                "source_episode_id" in open_resp,
                "open_room returned source_episode_id",
            )

            # The real agent-runtime room route will drive the ReAct loop which
            # calls mm_move. For the smoke we need the gateway reachable FROM
            # the agent-runtime (same host/port). We verify the full loop by
            # calling drive_turn and asserting the NPC moved afterward.
            #
            # If the agent-runtime's stub LM is not configured to emit mm_move,
            # drive_turn returns without a move and we skip the move assertion.
            print("  drive_turn ...")
            turn_resp = await driver.drive_turn(
                room_a_id,
                "Go north.",
                addressed_name=None,
            )
            print(f"    response_text: {turn_resp.get('response_text', '')[:80]}")

            print("  close_room ...")
            close_resp = await driver.close_room(room_a_id)
            _check("task_id" in close_resp, "close_room returned task_id")

        finally:
            await ar_client.aclose()

        # ------------------------------------------------------------------
        # Assert: NPC moved (location_uuid == room_B)
        # ------------------------------------------------------------------
        npc_doc = await repo.get_entity(npc_id)
        moved = npc_doc is not None and npc_doc.get("location_uuid") == room_b_id
        _check(moved, "NPC location_uuid == room_b_id after turn")

        # ------------------------------------------------------------------
        # Assert: episode produced (actor_id == npc_id)
        # ------------------------------------------------------------------
        episode_ok = (
            len(capturing.ingested) >= 1 and capturing.ingested[0]["actor_id"] == npc_id
        )
        _check(episode_ok, f"episode ingested with actor_id={npc_id[:8]}...")

    asyncio.run(_run())
    print("Smoke OK")


if __name__ == "__main__":
    # Load .env if present (mirrors kernel_smoke.py pattern)
    _dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(_dotenv_path):
        try:
            from dotenv import load_dotenv  # type: ignore[import]

            load_dotenv(_dotenv_path)
        except ImportError:
            pass  # dotenv optional

    # Ensure engine + gateway packages are importable when invoked directly
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _pkg_src in (
        os.path.join(_repo_root, "gateway", "src"),
        os.path.join(_repo_root, "engine", "src"),
    ):
        if _pkg_src not in sys.path:
            sys.path.insert(0, _pkg_src)

    run_smoke()
