# Personas in the Typewriter UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-personas-in-typewriter-ui-design.md` (committed `c221ab5`).

**Goal:** Make an agent-runtime-backed persona NPC speak into the typewriter opening UI — its reply typed into the prose pane and its presence shown in the room map — by bridging the persona stack (P1/P2/P3, on `opening/engine-core`) to the typewriter client (on `ui/typewriter-kg-map`) over the existing WebSocket.

**Architecture:** Merge the two branches (conflict-free). Reuse the persona server stack **unchanged**: a gated seed puts a persona NPC into `app.state.cxn_repo` at the Deep Roads; a ~6-line best-effort hook in `act_opening` calls `SceneCoordinator.handle_player_message` after the player's turn; the typewriter client opens a WebSocket and a small adapter renders `mm_npc_response` as a gold NPC prose segment and `npc_joined` as a room-map glyph. Persona failures degrade to silence — the opening turn always returns.

**Tech Stack:** Python 3.12 (memento-mori gateway + engine), FastAPI/Starlette, httpx. Client: TypeScript, Bun (build + test). Server tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`. Client tests: `cd client && bun test <file>`.

## Branch & base

- **Branch:** `persona/typewriter-ui`, already cut off `opening/engine-core` (@ `8d54f7f`, carries P1+P2+P3) and currently holding only the spec commit (`c221ab5`).
- **Worktree:** work in the existing worktree `…/scratchpad/mmori-tw-spec` (already checked out on `persona/typewriter-ui`). Read **and** edit files from there — the main checkout (`~/Vaults/Bonfires/memento-mori`) is on `ui/typewriter-kg-map` (wrong-tree trap). The `client/` tree only exists in this worktree **after Task 1's merge**.
- **Merge on completion** via the arc's fast-forward pattern: `git branch -f opening/engine-core persona/typewriter-ui`. Never check out `opening/engine-core` in the main tree.

## Global Constraints

- Commit trailer (exact, every commit): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. Any PR targets this lineage's base (`opening/engine-core`), never `main`/`canon`.
- **A persona / agent-runtime / seed failure must never break the opening turn or crash gateway startup.** Every new server-side persona call site is wrapped `try/except → log` and degrades to a no-op. The opening remains fully playable with the persona path silent.
- **The persona server stack (P1/P2/P3) is reused unchanged.** No edits to `scene_coordinator.py`, `scene_activation.py`, `room_driver.py`, `cxn_tools.py`, or the engine. New server code is confined to `persona_seed.py` (additive helper), `app.py` (one gated lifespan call), and `routes/opening.py` (the hook).
- **Opening room identity (verbatim constants):** uuid `"507f1f77bcf86cd799439011"`, name `"the deep roads"` (from `engine/src/memento/opening/deep_roads.py`). The seed NPC's `location_uuid` and the resolver cache key use exactly these.
- The seed is **opt-in** (`PERSONA_OPENING_SEED`), writes the **intended game NPC** (not a test entity), no-ops on the wrong repo backend, and never writes to the production KG.
- No cross-service Python imports (plain dicts on the wire). `Any` is allowed only for the `repo`/`cache`/`state` app-state-namespace params (matching the existing `seed_local_personas(repo: Any, cache: Any)` convention).
- UUIDs are entity/scene identity; the location **name** (`"the deep roads"`) is only a `ws_hub` broadcast key and a resolver cache key.
- Python: ruff-format only the files each task touches (the base isn't ruff-clean). Client: follow the existing `client/src/**/*.test.ts` style.

## Key existing symbols (reuse, don't reinvent) — verbatim anchors

- **Opening room:** `engine/src/memento/opening/deep_roads.py` — `LOC_DEEP_ROADS = "507f1f77bcf86cd799439011"`, name `"the deep roads"`.
- **`persona_seed.py`** (`gateway/src/gateway/persona_seed.py`) — module-level `logger`; `_location_doc()`/`_npc_doc()` doc shape (`uuid`,`kind`,`name`,`labels`,`location_uuid`,`attrs`,`is_dead`); `seed_local_personas(repo, cache) -> bool` guards `isinstance(repo, InMemoryStateRepository)`, calls **sync** `repo.seed_entity(...)`, sets `cache[name]=uuid`, returns True. `provision_kg_personas` is the EventSourced counterpart. Add the opening helper here, parallel to these.
- **`InMemoryStateRepository`** (`engine/src/memento/state/in_memory.py`) — `seed_entity(doc) -> None` is **sync**; `get_entities_at_location(uuid)` is **async** and returns entities whose `location_uuid == uuid` and `kind != "item"`.
- **`app.py` lifespan** (`gateway/src/gateway/app.py`) — already `import os`, has module `logger`; sets `app.state.cxn_repo`, `app.state.scene_registry = {}`, `app.state.scene_locations = {}`, `app.state.bonfire_id`, then the gated `PERSONA_LOCAL_SEED` / `PERSONA_KG_SEED` seed blocks (each `try/except` non-fatal). Module global `ws_hub` and `app` are defined after the lifespan.
- **`routes/opening.py`** — `import os`, `import uuid as _uuid_mod`; `from fastapi import APIRouter, HTTPException`; `opening_registry: dict[str, object]`; `class ActRequest(BaseModel)` with `player_id: str` + `text: str`; `async def act_opening(req: ActRequest) -> dict` (line ~271) runs `turn_router.handle(req.text, req.player_id)`, pops the registry on win, returns `dict(outcome)`. **No `Request` param today.**
- **The persona-hook pattern** (`gateway/src/gateway/routes/action.py:80-99`) — the exact code to mirror:
  ```python
  from gateway.app import round_manager, ws_hub
  ...
  if ws_hub:
      previous_location = ws_hub.player_locations.get(req.player_id, "")
      await ws_hub.set_location(req.player_id, req.location)
  from gateway.scene_coordinator import SceneCoordinator
  coordinator = SceneCoordinator.from_app_state(request.app.state)
  handled = await coordinator.handle_player_message(req.player_id, req.location, req.action)
  ```
- **`WebSocketHub`** (`gateway/src/gateway/ws.py`) — `async set_location(player_id, location) -> None`; `player_locations: dict[str,str]`; `broadcast_to_location(name, msg)` reaches every player whose `player_locations[pid] == name`.
- **`SceneCoordinator.handle_player_message`** — on a fresh scene activation broadcasts `{"type":"npc_joined","npc_name":…,"npc_id":…}` then `{"type":"tool_event","tool":"mm_npc_response","npc":name,"summary":text,"location":location_name,"channel":"narrative"}`; swallows persona failures (logged no-op, never 500). Requires `app.state.agent_runtime_client` set and a `kind=="character"` NPC present.
- **Test substrate (server):** `gateway/tests/test_action_persona_branch.py` is the route-test pattern (real `app`, stub agent-runtime, fake WS). `EventSourcedStateRepository(InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror())` is a no-KG EventSourced repo (for the no-op assertion).
- **Client — `ProseLayer`** (`client/src/layers/prose-layer.ts`) — `Segment{ text; kind: "epigraph"|"location"|"description"|"narration"|"prompt" }`; `enqueue(seg)`; `render()` builds rows and colors **every** line `theme.colors.primary` at the `textRow(line, theme.colors.primary, cols)` call. `theme.colors.npc` exists (`#d4a574`, gold).
- **Client — NPC visual model** (`client/src/panels/narrative.ts:224-250`) — `npc-name` = `◆ <name>` in `theme.colors.npc`, bold; `npc-dialogue` = indented italic lines with a `│` accent bar in `theme.colors.npc`. The typewriter port reproduces the **colors** (gold name + gold dialogue); the elaborate per-cell accent-bar layout is the full-panel renderer's and is out of scope.
- **Client — WS plumbing** (`client/src/state/session.ts`) — `export const GATEWAY_URL`; **module-private** `const WS_URL = …:${GATEWAY_PORT}/ws`; `connectWebSocket()` does `ws = new WebSocket(\`${WS_URL}/${session.playerId}\`)` and dispatches `onMessage`. `setMessageHandler(handler)` sets `onMessage`. The opening flow never sets `session.playerId`, so the opening shell needs its own connect (Task 5 exports `WS_URL` and opens its own socket — it does **not** mutate the main-loop `session` singleton).
- **Client — `RoomViewportAdapter`** (`client/src/layers/room-viewport.ts`) — `setContents(roomUuid, things: {uuid,name}[])` (no-op if `roomUuid !== current room`); `currentThings(): Thing[]`. The opening shell holds `currentRoom` (= `location_id` = `"507f1f77bcf86cd799439011"`).
- **Client — boot** (`client/src/boot/opening-shell.ts`) — `start()` sets `playerId`/`currentRoom`, enqueues prose, `viewport.visitRoom(...)`. `act(text)` POSTs `/api/opening/act` and enqueues the narration. `redrawProse()` pushes the prose layer; `viewport.setContents(...)` self-blits.

---

# Task 1 — Integration branch: merge the typewriter client + verify both suites build/pass

**Files:**
- Merge: `ui/typewriter-kg-map` into `persona/typewriter-ui` (brings in `client/**` and the typewriter additions to `routes/opening.py`).
- Build artifact: `client/app.js` (from `bun run build`).
- No source edits in this task.

**Interfaces:**
- Produces: a single branch whose `gateway/` carries the persona stack (P1/P2/P3) and whose `client/` is the typewriter UI; `client/` builds; both test suites are green. Tasks 2-5 build on this tree.

- [ ] **Step 1 — confirm the merge is clean (no working-tree changes yet):**

Run (in the worktree):
```bash
git merge-tree $(git merge-base HEAD ui/typewriter-kg-map) HEAD ui/typewriter-kg-map | head -5
```
Expected: no `<<<<<<<`/`changed in both` conflict markers (the spec verified 0 conflicts; this is the pre-flight re-check).

- [ ] **Step 2 — merge:**
```bash
git merge --no-edit ui/typewriter-kg-map
```
Expected: a merge commit (or clean fast-forward of disjoint hunks); `client/` now present. If a trailer is needed on the merge commit, amend with the exact `Co-Authored-By` trailer above.

- [ ] **Step 3 — install + build the client:**
```bash
cd client && bun install && bun run build && cd ..
```
Expected: `bun run build` (targets `src/boot/opening-shell.ts`) writes `client/app.js` with no errors.

- [ ] **Step 4 — client test suite:**
```bash
cd client && bun test && cd ..
```
Expected: existing client tests pass (the merge added no client logic of ours yet — this is the baseline).

- [ ] **Step 5 — gateway test suite (persona stack intact post-merge):**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q
```
Expected: green except any pre-existing unrelated failure (`test_round_callback.py::test_send_batch_to_matrix` was the lone known one on this lineage — confirm it's the only failure and unchanged; if other failures appear, the merge is the cause → STOP and report).

- [ ] **Step 6 — commit** (the merge commit from Step 2 is the deliverable; if `bun install` updated a lockfile, stage only `client/bun.lockb`/`client/package-lock.json` and `client/app.js`):
```bash
git add client/app.js client/bun.lockb 2>/dev/null; git status --short
git commit -m "build(persona-tw): merge typewriter client into the persona lineage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(If the merge already committed and nothing else changed, this step is a no-op — note that in the report.)

---

# Task 2 — `seed_opening_persona`: a gated persona NPC at the Deep Roads (server)

**Files:**
- Modify: `gateway/src/gateway/persona_seed.py` (append the opening helper + its docs/constants; reuse the module `logger`)
- Modify: `gateway/src/gateway/app.py` (lifespan: gated, non-fatal call)
- Test: `gateway/tests/test_persona_opening_seed.py` (new)

**Interfaces:**
- Consumes: `InMemoryStateRepository.seed_entity` (**sync**) / `get_entities_at_location` (**async**).
- Produces: `async seed_opening_persona(repo: Any, cache: Any) -> bool` and module constants `_OPENING_LOC_UUID = "507f1f77bcf86cd799439011"`, `_OPENING_LOC_NAME = "the deep roads"`, `_OPENING_NPC_UUID = "opening-wanderer"`. Seeds a location + persona NPC into the in-memory repo and sets `cache["the deep roads"] = "507f1f77bcf86cd799439011"`; returns True on the in-memory repo, False (no-op) otherwise. Task 3 relies on this NPC being present at that uuid and the cache being primed.

- [ ] **Step 1 — write the failing test** (`gateway/tests/test_persona_opening_seed.py`):
```python
import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

from gateway.persona_seed import (
    seed_opening_persona,
    _OPENING_LOC_UUID,
    _OPENING_LOC_NAME,
    _OPENING_NPC_UUID,
)


@pytest.mark.asyncio
async def test_seeds_opening_npc_at_deep_roads_and_primes_cache():
    repo = InMemoryStateRepository()
    cache: dict[str, str] = {}
    assert await seed_opening_persona(repo, cache) is True
    entities = await repo.get_entities_at_location(_OPENING_LOC_UUID)
    npc = next((e for e in entities if e.get("kind") == "character"), None)
    assert npc is not None and npc["uuid"] == _OPENING_NPC_UUID
    assert "NPC" in npc["labels"]
    assert cache[_OPENING_LOC_NAME] == _OPENING_LOC_UUID
    assert _OPENING_LOC_UUID == "507f1f77bcf86cd799439011"
    assert _OPENING_LOC_NAME == "the deep roads"


@pytest.mark.asyncio
async def test_noop_on_non_in_memory_repo():
    repo = EventSourcedStateRepository(
        InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror()
    )
    cache: dict[str, str] = {}
    assert await seed_opening_persona(repo, cache) is False
    assert cache == {}
```

- [ ] **Step 2 — run, verify it fails:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_opening_seed.py -q
```
Expected: FAIL with `ImportError: cannot import name 'seed_opening_persona'`.

- [ ] **Step 3 — implement the helper.** Append to `gateway/src/gateway/persona_seed.py` (below `provision_kg_personas`):
```python
# --- Opening-arc persona (typewriter UI) ------------------------------------
# The Deep Roads opening room (engine/src/memento/opening/deep_roads.py).
_OPENING_LOC_UUID = "507f1f77bcf86cd799439011"
_OPENING_LOC_NAME = "the deep roads"
_OPENING_NPC_UUID = "opening-wanderer"


def _opening_location_doc() -> dict[str, Any]:
    return {
        "uuid": _OPENING_LOC_UUID,
        "kind": "location",
        "name": _OPENING_LOC_NAME,
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {"exits": [], "item_ids": []},
        "is_dead": False,
    }


def _opening_npc_doc() -> dict[str, Any]:
    return {
        "uuid": _OPENING_NPC_UUID,
        "kind": "character",
        "name": "a dying adventurer",
        "labels": ["Character", "NPC"],
        "location_uuid": _OPENING_LOC_UUID,
        "attrs": {"hp": 3, "max_hp": 10, "inventory": []},
        "is_dead": False,
    }


async def seed_opening_persona(repo: Any, cache: Any) -> bool:
    """Seed a persona NPC at the Deep Roads opening room into the in-memory
    ``app.state.cxn_repo`` so the typewriter opening UI can reach a live
    agent-runtime NPC. Gated by ``PERSONA_OPENING_SEED``. A no-op (returns
    False) on any non-in-memory repo — the opening demo path runs the in-memory
    cxn_repo. Writes only to ``app.state.cxn_repo`` (never the opening's own
    per-player repo, never the production KG). The cache entry lets
    LocationResolver resolve "the deep roads" without a KG search.
    """
    from memento.state.in_memory import InMemoryStateRepository

    if not isinstance(repo, InMemoryStateRepository):
        return False
    repo.seed_entity(_opening_location_doc())  # InMemoryStateRepository.seed_entity is sync
    repo.seed_entity(_opening_npc_doc())
    if cache is not None:
        cache[_OPENING_LOC_NAME] = _OPENING_LOC_UUID
    logger.info(
        "seeded opening persona NPC %s at %s", _OPENING_NPC_UUID, _OPENING_LOC_NAME
    )
    return True
```

- [ ] **Step 4 — run, verify it passes:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_opening_seed.py -q
```
Expected: 2 passed.

- [ ] **Step 5 — wire the lifespan.** In `gateway/src/gateway/app.py`, immediately after the existing `PERSONA_KG_SEED` block (or after `PERSONA_LOCAL_SEED` if `PERSONA_KG_SEED` isn't present on this lineage — place it adjacent to the other seed blocks), add:
```python
    if os.environ.get("PERSONA_OPENING_SEED"):
        from gateway.persona_seed import seed_opening_persona

        try:
            await seed_opening_persona(app.state.cxn_repo, app.state.scene_locations)
        except Exception:
            logger.warning("opening persona seed failed (non-fatal)", exc_info=True)
```

- [ ] **Step 6 — regression smoke** (lifespan still boots; existing seed paths untouched):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_seed.py gateway/tests/test_action_persona_branch.py -q
```
Expected: green.

- [ ] **Step 7 — ruff-format the touched files + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/persona_seed.py gateway/src/gateway/app.py gateway/tests/test_persona_opening_seed.py
git add gateway/src/gateway/persona_seed.py gateway/src/gateway/app.py gateway/tests/test_persona_opening_seed.py
git commit -m "feat(gateway): seed a persona NPC at the Deep Roads for the opening UI (gated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 3 — `act_opening` invokes the persona path (server, best-effort hook)

**Files:**
- Modify: `gateway/src/gateway/routes/opening.py` (`act_opening`: add `request: Request`, best-effort persona hook after the turn)
- Test: `gateway/tests/test_opening_persona_branch.py` (new)

**Interfaces:**
- Consumes: `ws_hub` (module global from `gateway.app`), `WebSocketHub.set_location` (async), `SceneCoordinator.from_app_state(request.app.state).handle_player_message(player_id, "the deep roads", text)`, the seed from Task 2 (NPC present at `507f1f77…`, cache primed).
- Produces: every `POST /api/opening/act` runs the player turn (HTTP response unchanged) **and** drives a persona turn; on a live scene the player's WS receives `npc_joined` + `tool_event/mm_npc_response`. A persona/agent-runtime failure leaves the `act_opening` response intact (no 500).

- [ ] **Step 1 — write the failing test** (`gateway/tests/test_opening_persona_branch.py`). This combines two proven patterns: the opening-route DI-hook fakes (autouse fixture, from `test_opening_routes.py`) and the persona-scene wiring (`_Hub` + ASGI `_turn_stub` + a **pre-registered** scene driver, from `test_action_persona_branch.py`). The scene is pre-registered so the hook drives a turn and broadcasts `mm_npc_response` to the fake hub at `"the deep roads"`; fresh-activation `npc_joined` is already covered by P3's `test_scene_npc_joined.py`, so this task asserts only what it adds — the **hook fires and reaches the WS**, and a persona failure leaves the opening response intact.
```python
"""Task 3: POST /api/opening/act drives the persona scene (best-effort hook)."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.persona_seed import seed_opening_persona, _OPENING_LOC_UUID
from gateway.room_driver import RoomDriver
from memento.state.in_memory import InMemoryStateRepository

_DEEP_ROADS_NAME = "the deep roads"


class _Hub:  # mirrors test_action_persona_branch.py
    def __init__(self):
        self.broadcasts = []
        self.locs = {}

    async def set_location(self, pid, loc):
        self.locs[pid] = loc

    async def broadcast_to_location(self, loc, msg):
        self.broadcasts.append((loc, msg))

    def players_at_location(self, loc):
        return 1

    @property
    def player_locations(self):
        return self.locs


def _turn_stub(recorder):
    async def _turn(request: Request):
        recorder.append(await request.json())
        return JSONResponse(
            {"response_text": "You... made it this far?", "should_respond": True}
        )

    return Starlette(routes=[Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"])])


@pytest.fixture(autouse=True)
def _patch_opening_hooks(monkeypatch):
    """Fake DI builders so /opening/start is pure in-process (from test_opening_routes.py)."""
    import gateway.routes.opening as opening_mod
    from memento.cxn.kernel_client import FakeComprehensionClient
    from memento.cxn.types import ComprehendedFrame
    from memento.memory.null_client import NullMemoryClient
    from memento.state.chain_mirror import NoopChainMirror
    from memento.state.kg_projection import KgProjectionFake

    canned = {
        "look around": ComprehendedFrame(
            predicate="look", roles=[], matched=True, raw_text="look around"
        ),
    }
    monkeypatch.setattr(
        opening_mod, "build_comprehension", lambda: FakeComprehensionClient(canned)
    )
    monkeypatch.setattr(opening_mod, "build_memory", lambda: NullMemoryClient())
    monkeypatch.setattr(opening_mod, "build_mirror", lambda: NoopChainMirror())
    monkeypatch.setattr(opening_mod, "build_projection", lambda: KgProjectionFake())
    monkeypatch.setattr(opening_mod, "opening_registry", {})


async def _start(client):
    r = await client.post(
        "/api/opening/start",
        json={
            "player_name": "Tester",
            "wallet_address": "0xabcdef1234567890abcdef1234567890abcdef12",
            "archetype": "",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["player_id"]


async def _wire_persona_scene(monkeypatch):
    """Pre-register a persona scene at the Deep Roads on app.state, with a fake hub."""
    from gateway.app import app

    repo = InMemoryStateRepository()
    await seed_opening_persona(repo, None)  # seeds the NPC at _OPENING_LOC_UUID
    recorder: list = []
    ar_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_turn_stub(recorder)),
        base_url="http://ar-stub",
    )
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids[_OPENING_LOC_UUID] = {"opening-wanderer"}
    hub = _Hub()
    app.state.cxn_repo = repo
    app.state.agent_runtime_client = ar_client
    app.state.scene_registry = {_OPENING_LOC_UUID: driver}
    app.state.scene_locations = {_DEEP_ROADS_NAME: _OPENING_LOC_UUID}
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    return app, hub, recorder, ar_client


@pytest.mark.asyncio
async def test_opening_act_drives_persona_and_broadcasts(monkeypatch):
    app, hub, recorder, ar_client = await _wire_persona_scene(monkeypatch)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            player_id = await _start(gw)
            resp = await gw.post(
                "/api/opening/act",
                json={"player_id": player_id, "text": "look around"},
            )
            assert resp.status_code == 200, resp.text  # opening turn returns normally
        assert len(recorder) == 1  # the hook drove the registered scene's turn
        npc_msgs = [
            (loc, m) for loc, m in hub.broadcasts if m.get("tool") == "mm_npc_response"
        ]
        assert npc_msgs, hub.broadcasts
        loc, msg = npc_msgs[0]
        assert loc == _DEEP_ROADS_NAME
        assert msg["summary"] == "You... made it this far?"
    finally:
        await ar_client.aclose()


@pytest.mark.asyncio
async def test_opening_act_survives_persona_failure(monkeypatch):
    app, hub, recorder, ar_client = await _wire_persona_scene(monkeypatch)

    def _boom(cls, state):
        raise RuntimeError("scene coordinator down")

    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state", classmethod(_boom)
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            player_id = await _start(gw)
            resp = await gw.post(
                "/api/opening/act",
                json={"player_id": player_id, "text": "look around"},
            )
            # opening TurnOutcome is intact despite the persona-hook failure
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "narrated"
    finally:
        await ar_client.aclose()
```
*(The wiring is copied from the two proven tests; if `SceneCoordinator.from_app_state` reads an `app.state` attr not set here, set it the way `test_action_persona_branch.py` does and keep the assertions. The load-bearing contract: (a) the hook drives the pre-registered scene → `mm_npc_response` reaches the hub at `"the deep roads"`; (b) a `from_app_state` failure yields HTTP 200 with the narrated `TurnOutcome`.)*

- [ ] **Step 2 — run, verify it fails:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_persona_branch.py -q
```
Expected: FAIL (no `npc_joined`/`mm_npc_response` delivered — the hook doesn't exist yet).

- [ ] **Step 3 — add `Request` to the import and signature** in `gateway/src/gateway/routes/opening.py`. Change the FastAPI import line:
```python
from fastapi import APIRouter, HTTPException, Request
```
and the `act_opening` signature:
```python
@router.post("/opening/act")
async def act_opening(req: ActRequest, request: Request) -> dict:
```

- [ ] **Step 4 — add the best-effort persona hook** in `act_opening`, immediately after `outcome = await turn_router.handle(req.text, req.player_id)` and **before** the win-pop/return. Mirror `routes/action.py`:
```python
    # Best-effort persona turn: give this opening player a presence entry at the
    # Deep Roads, then drive the persona scene. NPC content (npc_joined +
    # mm_npc_response) arrives asynchronously over the WS; the opening's own
    # TurnOutcome (below) is never affected by a persona/agent-runtime failure.
    try:
        from gateway.app import ws_hub

        if ws_hub is not None:
            await ws_hub.set_location(req.player_id, "the deep roads")
            from gateway.scene_coordinator import SceneCoordinator

            coordinator = SceneCoordinator.from_app_state(request.app.state)
            await coordinator.handle_player_message(
                req.player_id, "the deep roads", req.text
            )
    except Exception:
        logger.warning("opening persona hook failed (non-fatal)", exc_info=True)
```
*(`logger` is already defined at module top. `"the deep roads"` is the verbatim opening-room name and the resolver cache key primed by Task 2. `set_location` is idempotent. `SceneCoordinator.handle_player_message` itself swallows persona errors, but the `try/except` here also guards a missing `agent_runtime_client` / coordinator-construction failure.)*

- [ ] **Step 5 — run, verify it passes:**
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_persona_branch.py -q
```
Expected: 2 passed.

- [ ] **Step 6 — opening-arc regression** (the existing opening routes still work; the new `request` param doesn't break them):
```bash
PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_opening_route.py gateway/tests/test_opening_arc.py -q
```
Expected: green. *(If the opening route tests call `act_opening` directly rather than through the app, they must pass a `Request` — update those call sites to go through the app/test-client, or construct a minimal `Request`; the route is normally exercised via the app, like `submit_action`.)*

- [ ] **Step 7 — ruff-format + commit:**
```bash
python3.12 -m ruff format gateway/src/gateway/routes/opening.py gateway/tests/test_opening_persona_branch.py
git add gateway/src/gateway/routes/opening.py gateway/tests/test_opening_persona_branch.py
git commit -m "feat(gateway): drive the persona scene from the opening act (best-effort)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 4 — ProseLayer: NPC dialogue segment kinds (client)

**Files:**
- Modify: `client/src/layers/prose-layer.ts` (extend `Segment.kind`, optional `speaker`, color branch in `render()`)
- Test: `client/src/layers/prose-layer.test.ts` (new)

**Interfaces:**
- Produces: `Segment.kind` gains `"npc-name"` and `"npc-dialogue"`; `Segment` gains optional `speaker?: string`. `render()` colors `npc-name`/`npc-dialogue` lines with `theme.colors.npc` (all other kinds unchanged at `theme.colors.primary`). Task 5's adapter enqueues `{kind:"npc-dialogue", text, speaker}`.

- [ ] **Step 1 — write the failing test** (`client/src/layers/prose-layer.test.ts`). Assert an `npc-dialogue` segment renders in the NPC color and a `narration` segment stays primary. The renderer returns `{cells}` where each cell row carries per-character `fg`; assert the NPC line's foreground equals `theme.colors.npc`.
```ts
import { test, expect } from "bun:test";
import { ProseLayer } from "./prose-layer";
import { theme } from "../renderer/theme";

// Reveal everything so the typewriter prefix doesn't truncate the assertion.
function fullyRevealed(layer: ProseLayer): ProseLayer {
  layer.skip();
  return layer;
}

// Pull the fg color of the first non-space character in a rendered result.
function firstInkColor(cells: ReturnType<ProseLayer["render"]>["cells"]): string | undefined {
  for (const row of cells) {
    for (const cell of row.cells ?? []) {
      if (cell.char && cell.char !== " ") return cell.fg;
    }
  }
  return undefined;
}

test("npc-dialogue renders in the NPC color", () => {
  const layer = new ProseLayer();
  layer.enqueue({ text: "You may pass.", kind: "npc-dialogue", speaker: "a dying adventurer" });
  fullyRevealed(layer);
  const color = firstInkColor(layer.render(40, 10));
  expect(color).toBe(theme.colors.npc);
});

test("narration stays in the primary color", () => {
  const layer = new ProseLayer();
  layer.enqueue({ text: "The roads are dark.", kind: "narration" });
  fullyRevealed(layer);
  const color = firstInkColor(layer.render(40, 10));
  expect(color).toBe(theme.colors.primary);
});
```
*(Inspect `textRow`/`emptyRow` in `client/src/panels/panel-utils.ts` and `PanelResult`/cell shape in `client/src/canvas/types.ts` to confirm the exact field names — `cells[].cells[].fg`/`.char` above is the expected shape; adjust the two accessor helpers to the real field names if they differ. The two `expect(...).toBe(...)` assertions are the contract.)*

- [ ] **Step 2 — run, verify it fails:**
```bash
cd client && bun test src/layers/prose-layer.test.ts; cd ..
```
Expected: FAIL — both lines currently render `theme.colors.primary`, so the npc-dialogue assertion fails (and `"npc-dialogue"` isn't an allowed `kind`, a type error).

- [ ] **Step 3 — extend the type + color branch** in `client/src/layers/prose-layer.ts`. Update the `Segment` type:
```ts
export type Segment = {
  text: string;
  kind: "epigraph" | "location" | "description" | "narration" | "prompt" | "npc-name" | "npc-dialogue";
  speaker?: string;
};
```
The `render()` method colors per **segment**, not per line, so it must map revealed lines back to their source segment's kind. Replace the single-color render tail with a per-segment color walk. Change the `fullStream`-based reveal so render knows each line's kind — build the visible lines with their color:
```ts
  render(cols: number, rows: number): PanelResult {
    // Build (line, color) pairs segment by segment, honoring the reveal cursor.
    const lineColors: { line: string; color: string }[] = [];
    let consumed = 0;
    for (const seg of this.segments) {
      const segText = seg.text + "\n\n";
      const visibleChars = Math.max(0, Math.min(segText.length, this.revealed - consumed));
      consumed += segText.length;
      if (visibleChars === 0) continue;
      const shown = segText.slice(0, visibleChars).trimEnd();
      if (shown === "") continue;
      const color =
        seg.kind === "npc-name" || seg.kind === "npc-dialogue"
          ? theme.colors.npc
          : theme.colors.primary;
      for (const line of wordWrap(shown, cols)) {
        lineColors.push({ line, color });
      }
    }
    const visible = lineColors.slice(-rows);
    const cells: ReturnType<typeof textRow>[] = [];
    const padCount = rows - visible.length;
    for (let i = 0; i < padCount; i++) cells.push(emptyRow(cols));
    for (const { line, color } of visible) cells.push(textRow(line, color, cols));
    return { cells };
  }
```
*(This preserves the existing behavior for all current kinds — they map to `theme.colors.primary`, identical to today — and only diverges for the two NPC kinds. The `revealed`/`tick`/`skip`/`fullStream`/`enqueue` members and `wordWrap` are unchanged.)*

- [ ] **Step 4 — run, verify it passes:**
```bash
cd client && bun test src/layers/prose-layer.test.ts; cd ..
```
Expected: 2 pass.

- [ ] **Step 5 — full client suite (no regression in prose rendering):**
```bash
cd client && bun test; cd ..
```
Expected: green (same baseline as Task 1 Step 4, plus the 2 new tests).

- [ ] **Step 6 — build + commit:**
```bash
cd client && bun run build; cd ..
git add client/src/layers/prose-layer.ts client/src/layers/prose-layer.test.ts client/app.js
git commit -m "feat(client): NPC dialogue segment kinds in the prose layer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Task 5 — Opening WS adapter + boot wiring (client)

**Files:**
- Create: `client/src/state/opening-ws.ts` (pure message router + a thin socket connect)
- Test: `client/src/state/opening-ws.test.ts` (new)
- Modify: `client/src/state/session.ts` (export `WS_URL` so the opening shell can open its own socket)
- Modify: `client/src/boot/opening-shell.ts` (open the WS after `start()`, route messages to prose + viewport)

**Interfaces:**
- Consumes: `ProseLayer.enqueue({kind:"npc-dialogue", text, speaker})` (Task 4); `RoomViewportAdapter.setContents(roomUuid, things)` + `currentThings()`; the server's `tool_event/mm_npc_response`, `npc_joined`, `npc_left` messages (Task 3).
- Produces: `routeOpeningMessage(msg, surfaces): void` (pure, testable without a socket) and `connectOpeningWs(playerId, onMessage): WebSocket`. `surfaces` is `{ prose: {enqueue}, redrawProse: () => void, viewport: {setContents, currentThings}, roomUuid: () => string }`.

- [ ] **Step 1 — write the failing test** (`client/src/state/opening-ws.test.ts`) for the pure router:
```ts
import { test, expect } from "bun:test";
import { routeOpeningMessage } from "./opening-ws";

function makeSurfaces() {
  const enqueued: { kind: string; text: string; speaker?: string }[] = [];
  let things: { uuid: string; name: string }[] = [];
  let redraws = 0;
  return {
    surfaces: {
      prose: { enqueue: (s: { kind: string; text: string; speaker?: string }) => enqueued.push(s) },
      redrawProse: () => { redraws++; },
      viewport: {
        setContents: (_room: string, t: { uuid: string; name: string }[]) => { things = t; },
        currentThings: () => things,
      },
      roomUuid: () => "507f1f77bcf86cd799439011",
    },
    get enqueued() { return enqueued; },
    get things() { return things; },
    get redraws() { return redraws; },
  };
}

test("mm_npc_response becomes an npc-dialogue prose segment", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "tool_event", tool: "mm_npc_response", npc: "a dying adventurer", summary: "You may pass." }, s.surfaces);
  expect(s.enqueued).toEqual([{ kind: "npc-dialogue", text: "You may pass.", speaker: "a dying adventurer" }]);
  expect(s.redraws).toBe(1);
});

test("npc_joined adds the NPC as a room thing", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "npc_joined", npc_name: "a dying adventurer", npc_id: "opening-wanderer" }, s.surfaces);
  expect(s.things).toEqual([{ uuid: "opening-wanderer", name: "a dying adventurer" }]);
});

test("npc_left removes the NPC from room things", () => {
  const s = makeSurfaces();
  s.surfaces.viewport.setContents("507f1f77bcf86cd799439011", [{ uuid: "opening-wanderer", name: "a dying adventurer" }]);
  routeOpeningMessage({ type: "npc_left", npc_name: "a dying adventurer", npc_id: "opening-wanderer" }, s.surfaces);
  expect(s.things).toEqual([]);
});

test("a non-mm_npc_response tool_event is ignored", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "tool_event", tool: "mm_narrate", summary: "x" }, s.surfaces);
  expect(s.enqueued).toEqual([]);
});

test("presence and unknown messages are ignored", () => {
  const s = makeSurfaces();
  routeOpeningMessage({ type: "presence", players: [] }, s.surfaces);
  routeOpeningMessage({ type: "whatever" }, s.surfaces);
  expect(s.enqueued).toEqual([]);
  expect(s.things).toEqual([]);
});
```

- [ ] **Step 2 — run, verify it fails:**
```bash
cd client && bun test src/state/opening-ws.test.ts; cd ..
```
Expected: FAIL with `Cannot find module './opening-ws'`.

- [ ] **Step 3 — implement the adapter** (`client/src/state/opening-ws.ts`):
```ts
// Opening-arc WebSocket adapter: translate persona server messages onto the
// typewriter render surfaces. The router is pure (testable without a socket);
// connectOpeningWs is a thin wrapper that opens the player's WS and forwards
// parsed messages to it. The opening UI stays fully playable if the WS never
// connects — personas are additive.
import { WS_URL } from "./session";

export interface OpeningSurfaces {
  prose: { enqueue: (seg: { kind: string; text: string; speaker?: string }) => void };
  redrawProse: () => void;
  viewport: {
    setContents: (roomUuid: string, things: { uuid: string; name: string }[]) => void;
    currentThings: () => { uuid: string; name: string }[];
  };
  roomUuid: () => string;
}

export function routeOpeningMessage(msg: any, s: OpeningSurfaces): void {
  switch (msg?.type) {
    case "tool_event":
      if (msg.tool === "mm_npc_response" && msg.npc) {
        s.prose.enqueue({ kind: "npc-dialogue", text: msg.summary ?? "", speaker: msg.npc });
        s.redrawProse();
      }
      break;
    case "npc_joined": {
      if (!msg.npc_name) break;
      const things = s.viewport.currentThings();
      if (things.some((t) => t.uuid === msg.npc_id || t.name === msg.npc_name)) break;
      s.viewport.setContents(s.roomUuid(), [
        ...things,
        { uuid: msg.npc_id ?? "", name: msg.npc_name },
      ]);
      break;
    }
    case "npc_left": {
      const things = s.viewport.currentThings();
      s.viewport.setContents(
        s.roomUuid(),
        things.filter((t) => t.uuid !== msg.npc_id && t.name !== msg.npc_name),
      );
      break;
    }
    default:
      break; // presence / player_* / unknown → ignored
  }
}

export function connectOpeningWs(playerId: string, onMessage: (msg: any) => void): WebSocket {
  const ws = new WebSocket(`${WS_URL}/${playerId}`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // ignore unparseable frames
    }
  };
  return ws;
}
```
*(`any` is acceptable here for the on-the-wire message — it's an untyped JSON frame, matching `message-handler.ts`'s own `msg` handling. If the project's lint forbids `any`, type `msg` as `Record<string, unknown>` and narrow.)*

- [ ] **Step 4 — export `WS_URL`** from `client/src/state/session.ts`. Change:
```ts
const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:${GATEWAY_PORT}/ws`;
```
to:
```ts
export const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:${GATEWAY_PORT}/ws`;
```

- [ ] **Step 5 — run, verify the router test passes:**
```bash
cd client && bun test src/state/opening-ws.test.ts; cd ..
```
Expected: 5 pass.

- [ ] **Step 6 — wire the boot shell** (`client/src/boot/opening-shell.ts`). Add the import:
```ts
import { connectOpeningWs, routeOpeningMessage, type OpeningSurfaces } from "../state/opening-ws";
```
At the end of `start()` (after `await refreshContents();`), open the WS and route messages onto the existing `prose`/`viewport`/`redrawProse`/`currentRoom`:
```ts
    const surfaces: OpeningSurfaces = {
      prose,
      redrawProse,
      viewport,
      roomUuid: () => currentRoom,
    };
    connectOpeningWs(playerId, (msg) => routeOpeningMessage(msg, surfaces));
```
*(`prose.enqueue`, `viewport.setContents`, `viewport.currentThings`, and `redrawProse` already exist with the exact shapes `OpeningSurfaces` expects. `viewport.setContents` self-blits via its `onChange`; `redrawProse` repaints the prose region, and the typewriter `tick` reveals the new NPC segment character by character.)*

- [ ] **Step 7 — full client suite + build:**
```bash
cd client && bun test && bun run build; cd ..
```
Expected: green (baseline + the 5 new router tests); `app.js` rebuilt.

- [ ] **Step 8 — commit:**
```bash
git add client/src/state/opening-ws.ts client/src/state/opening-ws.test.ts client/src/state/session.ts client/src/boot/opening-shell.ts client/app.js
git commit -m "feat(client): WebSocket adapter renders persona NPC into the typewriter opening

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Verification (end-to-end)

1. **Merge (Task 1):** one branch carries the persona gateway + the typewriter client; `client/` builds; both suites green (modulo the known unrelated Matrix test).
2. **Seed (Task 2):** `seed_opening_persona` seeds a `kind=="character"` NPC at `507f1f77bcf86cd799439011`, primes `cache["the deep roads"]`, no-ops on a non-in-memory repo; gated + non-fatal at boot. 2 unit tests + lifespan smoke.
3. **Hook (Task 3):** `POST /api/opening/act` returns its `TurnOutcome` and drives the persona scene → `tool_event/mm_npc_response` reaches the opening player's WS at `"the deep roads"`; a persona failure leaves the HTTP response intact (no 500). 2 route tests + opening-arc regression. (Fresh-activation `npc_joined` is P3-tested in `test_scene_npc_joined.py` and exercised by the live demo.)
4. **Prose kinds (Task 4):** `npc-dialogue`/`npc-name` segments render in `theme.colors.npc`; all existing kinds unchanged. 2 client tests + full suite.
5. **Adapter (Task 5):** `routeOpeningMessage` maps `mm_npc_response`→prose, `npc_joined`/`npc_left`→viewport, ignores presence/unknown; the boot shell opens the WS and routes onto the live surfaces. 5 router tests + full suite + build.
6. **Whole-branch opus review:** the persona server stack is reused unchanged (no edits to scene/room/cxn/engine); every new server call site is `try/except → log` and degrades to a no-op; the seed is opt-in, backend-guarded, and never writes the production KG; the client WS is additive (opening fully playable without it); the opening turn's HTTP response is never altered by persona failure.
7. **Live browser demo (the goal):** with the backend stack up, `PERSONA_OPENING_SEED=1` + `agent_runtime_client` wired (the proven demo config — `BONFIRE_ID=<real ObjectId>`, `AGENT_RUNTIME_BASE_URL=http://localhost:8003`, `PERSONA_LOCAL_SEED` not required for this path), boot the merged gateway, open the typewriter UI, type a message → the dying adventurer's reply types into the prose pane (gold) and the NPC appears as a glyph in the room map.

## Out of scope (future work — from the spec)

- Opening→main-loop handoff to The Threshold (`/api/session` + `/api/action`).
- KG-backed opening repo (the opening stays in-process per-player; the persona NPC is seeded into `app.state.cxn_repo`).
- Multi-NPC who-acts (addressed-name targeting; `drive_turn` is called without `addressed_name`).
- Speech-gated / addressed-only triggering (chosen behavior is every-message).
- Turning the typewriter client into a full main-loop client.
- The standing "one PR" promoting the whole persona stack (P1+P2+P3+this) to mmori `canon` / bonfires-ai-core `main`.

## On completion

Merge via the arc's fast-forward pattern: `git branch -f opening/engine-core persona/typewriter-ui`. Then `superpowers:finishing-a-development-branch`.
