# Gateway `mm_look` Tool + Room-ECS Boot Seed — Implementation Plan (Slice 1, Plan 2 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-agent-driven-opening-cxn-catch-design.md` (Components C + H, "Phase 2" gateway slice). Builds on **Plan 1** (`reveal_or_deepen` / `seed_room_ecs` / `RevealDelta` already shipped in `engine/src/memento/opening/reveal.py`). This is **Plan 2 of the slice** — the gateway-hosted `mm_look` MCP tool + the gated room-ECS boot seed, all single-repo (memento-mori, gateway) and headless-testable. Plan 3 (cross-repo bonfires-ai-core: player-`SelfDto` + agent-runtime manifest/kit + `cxn_fired` observability) and Plan 4 (cinematic intro + client `room_draw` glyph rendering) come after.

**Goal:** Expose Plan 1's reveal/deepen state machine as a gateway MCP tool `mm_look` that the persona ReAct loop can call — it resolves the caller's room, advances its reveal-state in `app.state.cxn_repo`, broadcasts an *incremental* `room_draw` WS delta, and returns a narration summary — plus a gated boot seed that loads the pre-authored Deep Roads room into the cxn repo as reveal-tracked ECS entities.

**Architecture:** A new `gateway/src/gateway/look_tool.py` registers `mm_look` on the shared `FastMCP("memento-engine")` (alongside the MOVE/ATTACK/TAKE registration), closing over the injected `repo` + `ws_hub` exactly like `register_cxn_tools`. `mm_look` takes **no args**: it reads the actor identity from the JWT ContextVar (`_check_tool_access`), resolves the actor's `location_uuid` from the repo, calls `reveal_or_deepen(repo, location)`, broadcasts the delta as a new `room_draw` event, and returns a plain dict (`kind`/`entity`/`depth`/`summary`) into the ReAct trajectory. It is a standalone tool — it produces **no** `StateUpdate`, so it never touches the `mm_act` `assert update is not None` branch. A gated `OPENING_ROOM_SEED` lifespan block seeds the room via a thin `seed_opening_room(repo)` helper.

**Tech Stack:** Python 3.12, FastAPI/Starlette gateway, `FastMCP`, `pytest` + `pytest-asyncio` (gateway tests use the **explicit `@pytest.mark.asyncio` decorator** — match the sibling gateway tests, unlike the engine suite). Test command: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **Branch:** `opening/cxn-catch` (HEAD `3091e7c` after Plan 1). Work in the existing worktree `…/scratchpad/mmori-cxn-catch`.
- Single repo (memento-mori), gateway + (read-only) engine imports. No cross-service / bonfires-ai-core changes in this plan.

## Global Constraints

- Commit trailer (exact, every commit): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches.
- `mm_look` resolves identity via `_check_tool_access("mm_look")` (the established pattern — identity from the JWT ContextVar, capability gate runs). It takes **no MCP parameters** (the agent "looks around here"); the room is the actor's current `location_uuid`, read from the repo, never a tool arg.
- `mm_look` MUST NOT build a `MatchedCxn` / run the `EffectExecutor` / return a `StateUpdate`. It returns its own plain dict, so the `mm_act` `assert update is not None` branch (`cxn_tools.py:236`) is never reached.
- Reveal-state mutation goes ONLY through `reveal_or_deepen` (Plan 1) on the closed-over `repo` — never reach into repo internals. The reveal is monotonic, so a retried look is safe (advances at most one step, never resets).
- **Failure isolation:** a missing actor / missing location / `ws_hub is None` / broadcast failure must degrade to a logged-or-silent no-op and still return a narration dict — `mm_look` must never raise into the ReAct turn (mirrors the spec's error-handling contract). The boot seed is opt-in (`OPENING_ROOM_SEED`) and wrapped non-fatal so a seed failure never crashes startup.
- The `room_draw` WS event is **new** (no draw/map WS event exists today — the client populates the viewport via an HTTP fetch). Plan 2 only *emits* it gateway-side; the client case that renders it is Plan 4. Do not add a client handler here.
- Ruff-format only the files each task touches (the base isn't ruff-clean): `python3.12 -m ruff format <files>`.

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/cxn-catch` @ `3091e7c`

- **Plan 1 engine API** — `engine/src/memento/opening/reveal.py`: `async reveal_or_deepen(repo, location_uuid, *, max_depth=DEFAULT_MAX_DEPTH=3) -> RevealDelta`; `RevealDelta(kind: str, entity: dict|None, depth: int)` (`kind ∈ {"revealed","deepened","exhausted"}`, `entity` = `{uuid,name,kind,labels}` or None); `async seed_room_ecs(repo, room: SeedRoom) -> None`. `DEFAULT_MAX_DEPTH` is importable.
- **Deep Roads seed** — `engine/src/memento/opening/deep_roads.py`: `LOC_DEEP_ROADS = "507f1f77bcf86cd799439011"`; `deep_roads_seed() -> SeedRoom` (3 facts: `a dying adventurer` salience 1_000_000 / `something in the dark` salience 100 / `an iron blade` salience 50, an item). Feed `deep_roads_seed()` straight to `seed_room_ecs`.
- **`register_cxn_tools`** — `gateway/src/gateway/cxn_tools.py:59-66` — signature `(mcp, ws_hub, repo, mirror, memory, bonfire_id=DEFAULT_BONFIRE_ID)`. Tools close over `repo`/`ws_hub`/`executor`; the handler shape is `@mcp.tool(name=...)` `async def …(…) -> dict`, with `agent_id = await _check_tool_access(tool_name)` first. `_check_tool_access` is late-imported `from gateway.mcp_server import _check_tool_access` (line 80). Follow this exact pattern.
- **`_check_tool_access`** — `gateway/src/gateway/mcp_server.py:48-75`. Reads `_current_identity` ContextVar (raises `RuntimeError("identity_missing: …")` if unset), then `await check_tool_access(entity_id, tool_name)` (raises `RuntimeError("capability_missing: …")` on `HTTPException`). Returns the entity id. The capability gate `check_tool_access` lives in `gateway/src/gateway/engine_auth.py:115`; tests patch `gateway.mcp_server.check_tool_access` to pass.
- **WS broadcast** — `WebSocketHub.broadcast_to_location(location: str, message: dict) -> None` (`gateway/src/gateway/ws.py:88`). Used directly for the `room_draw` event (the actor's location is resolved from the repo, NOT via `broadcast_tool_event`/`npc_registry`). There is **no** existing `room_draw`/`draw`/`map` event — this plan defines it.
- **`build_mcp_app` wiring** — `gateway/src/gateway/mcp_server.py`: import line `1269: from gateway.cxn_tools import register_cxn_tools, register_mm_act`; `cxn_repo = _build_cxn_repo()` (1285); `register_cxn_tools(mcp, ws_hub, cxn_repo, cxn_mirror, memory, bonfire_id=bonfire_id)` (1288-1295); `register_mm_act(...)` (1311-1319). `ws_hub` is the `build_mcp_app` param. A `register_look_tool(mcp, ws_hub, cxn_repo)` call slots in right after line 1295 (same `cxn_repo`/`ws_hub`).
- **Lifespan seeding** — `gateway/src/gateway/app.py`: `app.state.cxn_repo = mcp_asgi.cxn_repo` (set, in scope), `app.state.scene_locations = {}`, then gated `PERSONA_LOCAL_SEED` / `PERSONA_KG_SEED` / `PERSONA_OPENING_SEED` blocks (each `await`ed; `KG`/`OPENING` wrapped in non-fatal `try/except … logger.warning(..., exc_info=True)`). `import os` and `logger` are present. The new `OPENING_ROOM_SEED` block copies the `PERSONA_OPENING_SEED` try/except shape and is inserted right after it (before the `# Seed NPC registry` comment).
- **Test substrate** — `gateway/tests/test_mcp_server.py`: `_with_identity(entity_id)` context manager (sets `_current_identity`); `_extract_result(call_tool_result)` (`call_tool_result[0].text` → `json.loads`); tools driven via `await mcp.call_tool("name", {})` under `patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock), _with_identity(uuid)`. `mock_ws_hub` = `AsyncMock()` with `broadcast_to_location = AsyncMock()`. `InMemoryStateRepository` (`memento.state.in_memory`) is the headless repo; its `seed_entity` is **sync**, `get_entity`/`get_entities_at_location`/`set_attr` are **async**.

## File Structure

- `gateway/src/gateway/look_tool.py` (**new**) — `register_look_tool(mcp, ws_hub, repo, *, max_depth)` + the `mm_look` handler + `_broadcast_room_draw` + `_summarize` (Task 1); `seed_opening_room(repo)` (Task 2). One file: "the look tool + its room seed".
- `gateway/src/gateway/mcp_server.py` (**modify**) — import + wire `register_look_tool` in `build_mcp_app` (Task 1).
- `gateway/src/gateway/app.py` (**modify**) — gated `OPENING_ROOM_SEED` lifespan block (Task 2).
- `gateway/tests/test_look_tool.py` (**new**) — the gateway tests (both tasks).

---

# Task 1 — the `mm_look` gateway MCP tool

**Files:**
- Create: `gateway/src/gateway/look_tool.py`
- Modify: `gateway/src/gateway/mcp_server.py` (import + wire)
- Test: `gateway/tests/test_look_tool.py` (new)

**Interfaces:**
- Produces: `register_look_tool(mcp, ws_hub, repo, *, max_depth=DEFAULT_MAX_DEPTH) -> None` — registers the `mm_look` MCP tool. `mm_look()` (no args) returns `{"kind","entity","depth","summary"}`. Emits a `room_draw` WS event `{"type":"room_draw","kind","entity","depth","location"}` on `revealed`/`deepened` (not `exhausted`). Consumed by Task 2's integration test and by Plan 3's agent-runtime manifest (the tool name `mm_look`).

- [ ] **Step 1 — write `look_tool.py`** (`gateway/src/gateway/look_tool.py`):
```python
"""Gateway-hosted ``mm_look`` MCP tool — the first "expressive ECS" effect.

``mm_look`` is the persona ReAct loop's accretive look: it resolves the caller's
current room, advances that room's reveal-state via Plan 1's
``reveal_or_deepen`` (reveal the next salient thing, else deepen the shallowest
seen thing, else exhausted), broadcasts an *incremental* ``room_draw`` WS delta
(the client ADDS the new glyph — no redraw), and returns a narration summary
into the agent's trajectory so the same turn narrates it.

Unlike the MOVE/ATTACK/TAKE tools (``cxn_tools.py``), ``mm_look`` does NOT run
the ``EffectExecutor`` and produces NO ``StateUpdate`` — it returns its own
plain dict, so it never reaches the ``mm_act`` ``assert update is not None``
branch.  Identity comes from the JWT ContextVar (``_check_tool_access``); the
tool takes no parameters (you "look around HERE").  Every failure mode degrades
to a narration dict — ``mm_look`` never raises into the ReAct turn.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from memento.opening.reveal import DEFAULT_MAX_DEPTH, RevealDelta, reveal_or_deepen

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.fastmcp import FastMCP

    from memento.state.repository import StateRepository
    from gateway.ws import WebSocketHub

logger = logging.getLogger(__name__)


def _summarize(delta: RevealDelta) -> str:
    """A short narration hint for the ReAct trajectory (the LLM rewrites it)."""
    name = delta.entity["name"] if delta.entity else None
    if delta.kind == "revealed":
        return f"You notice {name}."
    if delta.kind == "deepened":
        return f"You look more closely at {name}."
    return "You have taken in all there is to see here."


async def _broadcast_room_draw(
    ws_hub: "WebSocketHub | None", location_uuid: str, delta: RevealDelta
) -> None:
    """Push the incremental ``room_draw`` delta to players in the room.

    On ``revealed`` the client ADDS the new glyph; on ``deepened`` no glyph
    changes (depth-only). ``exhausted`` draws nothing. Best-effort — a hub
    failure is logged and swallowed so the look still returns its narration.
    """
    if ws_hub is None or delta.kind == "exhausted":
        return
    try:
        await ws_hub.broadcast_to_location(
            location_uuid,
            {
                "type": "room_draw",
                "kind": delta.kind,
                "entity": delta.entity,
                "depth": delta.depth,
                "location": location_uuid,
            },
        )
    except Exception:  # surfacing is best-effort, never breaks the turn
        logger.warning("room_draw broadcast failed for %s", location_uuid, exc_info=True)


def register_look_tool(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> None:
    """Register the ``mm_look`` MCP tool on ``mcp``.

    Closes over ``repo`` (the room ECS) and ``ws_hub`` (the draw channel), the
    same injection pattern as ``register_cxn_tools``.
    """
    from gateway.mcp_server import _check_tool_access  # late import (auth surface)

    @mcp.tool(name="mm_look")
    async def mm_look() -> dict[str, Any]:
        """Look around the current room. Reveals the next notable thing, or —
        once everything is surfaced — looks more closely at something already
        seen. Re-looking adds detail; it never starts over."""
        actor_id = await _check_tool_access("mm_look")
        actor = await repo.get_entity(actor_id)
        location_uuid = actor.get("location_uuid") if actor else None
        if not location_uuid:
            # No room to look at — degrade, never raise into the turn.
            return {
                "kind": "exhausted",
                "entity": None,
                "depth": 0,
                "summary": "There is nothing here to see.",
            }
        delta = await reveal_or_deepen(repo, location_uuid, max_depth=max_depth)
        await _broadcast_room_draw(ws_hub, location_uuid, delta)
        return {
            "kind": delta.kind,
            "entity": delta.entity,
            "depth": delta.depth,
            "summary": _summarize(delta),
        }
```

- [ ] **Step 2 — wire `build_mcp_app`** (`gateway/src/gateway/mcp_server.py`). Extend the cxn-tools import (line 1269) and add the registration call right after the `register_cxn_tools(...)` block (after line 1295):
```python
from gateway.cxn_tools import register_cxn_tools, register_mm_act
from gateway.look_tool import register_look_tool
```
  and, immediately after the `cxn_executor = register_cxn_tools(...)` call closes (after line 1295):
```python
    register_look_tool(mcp, ws_hub, cxn_repo)
```
  *(Same `mcp`/`ws_hub`/`cxn_repo` as the MOVE/ATTACK/TAKE tools — one shared room ECS.)*

- [ ] **Step 3 — write the failing tests** (`gateway/tests/test_look_tool.py`):
```python
"""Tests for the gateway-hosted mm_look MCP tool (Plan 2, Task 1)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from memento.opening.deep_roads import LOC_DEEP_ROADS, deep_roads_seed
from memento.opening.reveal import seed_room_ecs
from memento.state.in_memory import InMemoryStateRepository

from gateway.look_tool import register_look_tool

_ACTOR = "player-uuid-1"


def _fastmcp():
    from mcp.server.fastmcp import FastMCP

    return FastMCP("memento-engine")


@contextmanager
def _with_identity(entity_id=_ACTOR):
    from gateway.mcp_server import _current_identity

    token = _current_identity.set(entity_id)
    try:
        yield
    finally:
        _current_identity.reset(token)


def _extract(call_result) -> dict:
    return json.loads(call_result[0].text)


def _hub():
    hub = AsyncMock()
    hub.broadcast_to_location = AsyncMock()
    return hub


async def _seed_room_and_actor(repo, *, location=LOC_DEEP_ROADS):
    await seed_room_ecs(repo, deep_roads_seed())
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": location,
            "attrs": {},  # no reveal_level -> the actor is not itself a candidate
            "is_dead": False,
        }
    )


async def _call_look(mcp):
    with patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock), _with_identity():
        return _extract(await mcp.call_tool("mm_look", {}))


@pytest.mark.asyncio
async def test_mm_look_reveals_in_salience_order_and_broadcasts():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    names = []
    for _ in range(3):
        res = await _call_look(mcp)
        assert res["kind"] == "revealed"
        names.append(res["entity"]["name"])
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]

    # one room_draw per reveal, to the actor's location, carrying the entity
    assert hub.broadcast_to_location.await_count == 3
    loc, msg = hub.broadcast_to_location.await_args.args
    assert loc == LOC_DEEP_ROADS
    assert msg["type"] == "room_draw" and msg["kind"] == "revealed"
    assert msg["entity"]["name"] == "an iron blade" and msg["location"] == LOC_DEEP_ROADS


@pytest.mark.asyncio
async def test_mm_look_deepens_after_all_revealed():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)  # default max_depth=3

    for _ in range(3):
        await _call_look(mcp)  # reveal all three
    res = await _call_look(mcp)  # 4th -> deepen the most salient
    assert res["kind"] == "deepened"
    assert res["entity"]["name"] == "a dying adventurer" and res["depth"] == 2
    assert hub.broadcast_to_location.await_args.args[1]["kind"] == "deepened"


@pytest.mark.asyncio
async def test_mm_look_exhausts_and_does_not_broadcast():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo, max_depth=1)  # no deepening: reveal-only

    for _ in range(3):
        await _call_look(mcp)  # reveal all three
    hub.broadcast_to_location.reset_mock()
    res = await _call_look(mcp)  # 4th -> exhausted
    assert res["kind"] == "exhausted" and res["entity"] is None
    assert hub.broadcast_to_location.await_count == 0  # nothing to draw


@pytest.mark.asyncio
async def test_mm_look_degrades_when_actor_has_no_location():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": None,  # no room
            "attrs": {},
            "is_dead": False,
        }
    )
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    res = await _call_look(mcp)  # must not raise
    assert res["kind"] == "exhausted" and res["entity"] is None
    assert hub.broadcast_to_location.await_count == 0
```

- [ ] **Step 4 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_look_tool.py -q
```
Expected: 4 passed. *(If FastMCP's `call_tool` returns a `(content, raw)` tuple in this version rather than a content list, mirror however `test_mcp_server.py::_extract_result` unwraps it — they use the same FastMCP. If `mm_look()` with no params trips a schema issue, confirm the other no-arg tool `mm_get_world_time` in `mcp_server.py` and match its decoration.)*

- [ ] **Step 5 — regression smoke** (the new tool/import doesn't break the MCP build or the existing tool suite):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_mcp_server.py -q
```
Expected: green (note `test_tool_registration_count` asserts a tool count — if it pins an exact number, `mm_look` adds one; update that test's expected count by +1 in the SAME commit and say so in the report).

- [ ] **Step 6 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/look_tool.py gateway/src/gateway/mcp_server.py gateway/tests/test_look_tool.py
git add gateway/src/gateway/look_tool.py gateway/src/gateway/mcp_server.py gateway/tests/test_look_tool.py
# include gateway/tests/test_mcp_server.py in the add ONLY if Step 5 required the count bump
git commit -m "feat(gateway): mm_look MCP tool — accretive reveal/deepen + room_draw WS delta

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 2 — gated room-ECS boot seed

**Files:**
- Modify: `gateway/src/gateway/look_tool.py` (add `seed_opening_room`)
- Modify: `gateway/src/gateway/app.py` (gated `OPENING_ROOM_SEED` lifespan block)
- Test: `gateway/tests/test_look_tool.py` (append the seed + integration tests)

**Interfaces:**
- Consumes: `seed_room_ecs` + `deep_roads_seed` (Plan 1 + existing); `register_look_tool` / `mm_look` (Task 1).
- Produces: `async seed_opening_room(repo) -> None` — seeds the Deep Roads room into `repo` as reveal-tracked ECS entities. The lifespan calls it behind `OPENING_ROOM_SEED`, wrapped non-fatal.

- [ ] **Step 1 — add `seed_opening_room`** to `gateway/src/gateway/look_tool.py` (append below `register_look_tool`):
```python
async def seed_opening_room(repo: Any) -> None:
    """Seed the pre-authored Deep Roads room into the cxn repo as reveal-tracked
    ECS entities (``reveal_level=0`` + ``salience``), so the gateway-hosted
    ``mm_look`` has a room to read and advance. Gated on ``OPENING_ROOM_SEED``
    and wrapped non-fatal by the caller — a seed failure must not crash boot.
    """
    from memento.opening.deep_roads import deep_roads_seed

    from memento.opening.reveal import seed_room_ecs

    await seed_room_ecs(repo, deep_roads_seed())
    logger.info("seeded opening room ECS (Deep Roads) into the cxn repo")
```

- [ ] **Step 2 — wire the lifespan** (`gateway/src/gateway/app.py`). Immediately after the existing `PERSONA_OPENING_SEED` block (the one calling `seed_opening_persona`), before the `# Seed NPC registry` comment, add:
```python
    if os.environ.get("OPENING_ROOM_SEED"):
        from gateway.look_tool import seed_opening_room

        try:
            await seed_opening_room(app.state.cxn_repo)
        except Exception:
            logger.warning("opening room ECS seed failed (non-fatal)", exc_info=True)
```
  *(Same gated, `await`ed, non-fatal shape as `PERSONA_OPENING_SEED`; `app.state.cxn_repo`, `os`, and `logger` are all in scope.)*

- [ ] **Step 3 — append the failing tests** (`gateway/tests/test_look_tool.py`):
```python
from gateway.look_tool import seed_opening_room


@pytest.mark.asyncio
async def test_seed_opening_room_seeds_latent_reveal_tracked_facts():
    repo = InMemoryStateRepository()
    await seed_opening_room(repo)
    ents = await repo.get_entities_at_location(LOC_DEEP_ROADS)
    items = await repo.get_items_at_location(LOC_DEEP_ROADS)
    by_name = {t["name"]: t for t in (list(ents) + list(items))}
    assert by_name["a dying adventurer"]["attrs"]["reveal_level"] == 0
    assert by_name["a dying adventurer"]["attrs"]["salience"] == 1_000_000
    assert by_name["something in the dark"]["attrs"]["reveal_level"] == 0
    assert by_name["an iron blade"]["kind"] == "item"  # item arm
    assert by_name["an iron blade"]["attrs"]["reveal_level"] == 0


@pytest.mark.asyncio
async def test_seeded_room_drives_mm_look_in_authored_order():
    repo = InMemoryStateRepository()
    await seed_opening_room(repo)  # boot-seed path (no manual seed_room_ecs)
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC_DEEP_ROADS,
            "attrs": {},
            "is_dead": False,
        }
    )
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    names = [(await _call_look(mcp))["entity"]["name"] for _ in range(3)]
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]
```

- [ ] **Step 4 — run, verify pass:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_look_tool.py -q
```
Expected: 6 passed (4 from Task 1 + 2 here).

- [ ] **Step 5 — lifespan-boot smoke** (the new gated block doesn't break app import/boot wiring):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_kg_seed.py gateway/tests/test_mcp_server.py -q
```
Expected: green. *(These exercise the lifespan-seeder pattern and the MCP build the new block sits beside.)*

- [ ] **Step 6 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/look_tool.py gateway/src/gateway/app.py gateway/tests/test_look_tool.py
git add gateway/src/gateway/look_tool.py gateway/src/gateway/app.py gateway/tests/test_look_tool.py
git commit -m "feat(gateway): gated OPENING_ROOM_SEED boot seed for the Deep Roads room ECS

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Verification (end-to-end)

1. **`mm_look` tool (Task 1):** reveals the room's things in descending salience order (adventurer → threat → blade), emits one incremental `room_draw` WS event per reveal (to the actor's location, carrying the entity), deepens after all are revealed (default `max_depth=3`), exhausts with no broadcast, and degrades to a narration dict when the actor has no location — never raising into the turn. It returns a plain dict (no `StateUpdate`), so the `mm_act` assert branch is untouched. 4 tests + MCP-build regression.
2. **Room-ECS boot seed (Task 2):** `seed_opening_room` seeds the Deep Roads facts (incl. the iron-blade item) as reveal-tracked ECS entities at `reveal_level=0`; the gated `OPENING_ROOM_SEED` lifespan block calls it non-fatally; a seeded room drives `mm_look` through the authored reveal order end-to-end via `call_tool`. 2 tests + lifespan/MCP smoke.
3. **No regression:** `test_mcp_server.py` stays green (tool-count test bumped by +1 if it pins an exact count).
4. **Backend-agnostic carry-through:** `mm_look` calls only `repo.get_entity` + `reveal_or_deepen` (which itself is protocol-only), so it runs unchanged against the EventSourced/KG `cxn_repo` a live deployment builds.

## What this plan deliberately does NOT do (later plans)

- **Plan 3 (cross-repo, bonfires-ai-core):** the player-as-persona `SelfDto` creation at `/v1/scenes/{deep_roads}/open`; `mm_look` in the agent-runtime `MEMENTO_MANIFEST` + a `get_allowed_tools` kit/label so the player-persona is *allowed* to call it; `SceneTurnResponse.fired_cxns`; and the `cxn_fired` observability (gateway log + WS event + the "◇ caught: LOOK" client beat).
- **Plan 4:** the client `room_draw` handler that ADDS the new glyph to the map viewport (incremental, no redraw); the cinematic intro (epigraph fade + name box); retiring the legacy overlay; rendering the look narration attributed to the player-self.
- **Kernel LOOK grammar authoring (Component E)** at boot — folded into Plan 3's bring-up (the Phase-0 spike already proved the grammar; wiring the author-grammar call belongs with the agent-runtime comprehension path).
