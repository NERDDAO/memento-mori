# Persona Scene Activation — First Production RoomDriver Call Site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use `- [ ]` checkboxes. Spec: `bonfires-ai-core/docs/superpowers/specs/2026-06-26-persona-scene-activation-design.md`.

## Context

`RoomDriver` carries the entire persona capability chain (roster → `capabilities` + KG-uuid `embodiment_agent_id` → POST `/v1/scenes/{loc}/open` to the agent-runtime), but it has **no production call site** — it is referenced only in its own module and tests. The live turn path (`routes/opening.py`, `/api/opening/*`) uses `TurnRouter`, which has no NPCs, no personas, no capabilities, and never calls the agent-runtime. So the proven capability chain is inert when the app runs. This slice gives the gateway a real **scene-activation path**: an explicit route constructs a `RoomDriver` against the shared world store and opens/closes a scene, proven at the integration level against a **stubbed** agent-runtime. Driving turns and standing up the real agent-runtime are the next slice.

**Goal:** A mounted gateway route (`POST /api/scenes/{loc}/activate` + `.../close`) constructs a real `RoomDriver` from `app.state` deps and opens/closes a scene; the roster the agent-runtime receives carries `capabilities` + KG-uuid `embodiment_agent_id`; proven against a recording stub.

**Architecture:** (1) expose the repo's projection via a read-only property so `RoomDriver` gets KG-uuid embodiment; (2) a `SceneActivationService` constructs the `RoomDriver`, opens/closes, registers the live driver, and raises domain exceptions; (3) two thin routes map those exceptions to HTTP, plus an app-scoped agent-runtime client + scene registry built in the lifespan.

**Tech Stack:** Python 3.12 (memento-mori engine + gateway), FastAPI/Starlette, httpx. Tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q` (engine-only suites use `PYTHONPATH=engine/src`).

## Branch & base

- **mmori branch:** `persona/scene-activation`, off `opening/engine-core` (dc155af).
- Use an **isolated worktree**: `git worktree add -b persona/scene-activation <scratchpad>/mmori-scene-act-wt opening/engine-core`. Work from the worktree (the main repo checkout is on a different branch and must stay untouched).
- **Read files from the worktree**, not the main repo (the main checkout lacks this lineage — a known wrong-tree trap).

## Global Constraints

- Commit trailer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. PR targets this lineage's base, never main.
- No cross-service Python imports (plain dicts on the wire). No `Any` in new service signatures **except** the `repo` param, which is a `StateRepository` Protocol impl typed `Any` to match the pre-existing `RoomDriver.__init__(repo: Any)` convention — do not invent a tighter type.
- Services raise **domain exceptions, not `HTTPException`** — only the route layer maps them. Env reads only at the wiring boundary (the lifespan / the existing `build_agent_runtime_client()` factory) — the service reads no env.
- UUIDs, not names. Never write test entities to the production KG.
- Ruff-format only the files each task touches (not the whole tree — the base isn't ruff-clean).
- Identity-uuid mode in tests (KG uuid == engine uuid via `KgProjectionFake`), consistent with the arc-integration proof.

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/engine-core`

- **`build_agent_runtime_client() -> httpx.AsyncClient`** — `gateway/src/gateway/room_driver.py:45-58`. Reads `AGENT_RUNTIME_BASE_URL` / `AGENT_RUNTIME_INTERNAL_TOKEN`, sets `headers={"X-Internal-Token": token}`, `timeout=30.0`.
- **`RoomDriver.__init__`** — `room_driver.py:88-109`, keyword-only: `repo`, `agent_runtime_client`, `bonfire_id`, `internal_token=""` (env-falls-back internally), `player_labels=None`, `projection: "KgProjectionProtocol | None" = None`.
- **`RoomDriver.open_room(location_uuid) -> dict`** — `room_driver.py:189-239`. Builds the roster (filters `kind=="character"`, excludes players), POSTs `/v1/scenes/{loc}/open`, `resp.raise_for_status()`, returns `resp.json()` (shape `{"source_episode_id": ...}`). On transport failure OR non-2xx, raises an `httpx.HTTPError` subclass (re-raised after logging).
- **`RoomDriver.close_room(location_uuid) -> dict`** — `room_driver.py:286-305`. POSTs `/v1/scenes/{loc}/close`, `raise_for_status()`, returns `resp.json()` (shape `{"task_id": ..., "snapshot_size": 0}`); on success pops `_last_roster_uuids` + `gm_room_registry`; raises `httpx.HTTPError` on failure (cleanup skipped on failure).
- **`EventSourcedStateRepository`** — `engine/src/memento/state/event_sourced.py`: `__init__(tx_log, activation_log, projection, chain)` stores `self._projection = projection` (L85); `KgProjectionProtocol` imported at module top (L58, not TYPE_CHECKING); **no `@property` exists in the class** (this slice adds the first).
- **`KgProjectionFake`** — `memento/state/kg_projection.py`; identity map (`kg_uuid_for(uuid)` returns the uuid if present). `EventSourcedStateRepository.seed_entity` is **async** (`await repo.seed_entity({...})`).
- **`get_allowed_tools(labels)`** — `engine/src/memento/tools/tool_labels.py:155`. `["Character","NPC"]` grants `mm_move`, `mm_attack`, etc.
- **`BONFIRE_ID = "mm-world-v1"`** — `routes/opening.py:68` (the shared world bonfire id; import it).
- **Route/registry style** — `routes/opening.py`: `router = APIRouter()` (L56), handlers take a Pydantic/path arg, `raise HTTPException(status_code=404, detail="...")` on registry miss (L259-282). Path is WITHOUT the `/api` prefix (added in `app.py`).
- **App wiring** — `app.py`: lifespan sets `app.state.cxn_repo`/`cxn_executor` at L64-65 (startup, pre-`yield`); shutdown side after `yield` at L85-88 (`if bridge: await bridge.disconnect()`); router include block at L161-188 (`from gateway.routes import (...)` tuple + `app.include_router(<mod>.router, prefix="/api")`; mirror `opening`, which uses `prefix="/api"`).
- **Test patterns** — app-state fixture: `gateway/tests/test_tools_http_route.py:109-133` (`from gateway.app import app`; set `app.state.*`; drive via `httpx.ASGITransport(app=app)`). NPC seed shape: same file L81-91 (`{"uuid","kind":"character","name","labels":["Character","NPC"],"location_uuid","attrs":{...},"is_dead":False}`). EventSourced+KgProjectionFake pairing: `engine/tests/state/test_event_sourced_repository.py:145-158`. Recording agent-runtime stub: `gateway/tests/test_room_driver.py:33-76` (`_Recorder` + Starlette `Route`s returning `{"source_episode_id":...}` / `{"task_id":...}`); header keys are lowercased by httpx.

---

# Movement 1 — engine: expose the projection

## Task 1 — `EventSourcedStateRepository.projection` property

**Files:**
- Modify: `engine/src/memento/state/event_sourced.py`
- Test: `engine/tests/state/test_event_sourced_repository.py`

**Interfaces:**
- Produces: `EventSourcedStateRepository.projection` (read-only) `-> KgProjectionProtocol`, returning the injected projection. Task 2/3 consume it via `getattr(repo, "projection", None)`.

- [ ] **Step 1 — failing test** (add to `engine/tests/state/test_event_sourced_repository.py`, reusing its existing imports for `InMemoryTxLog`, `InMemoryActivationLog`, `KgProjectionFake`, and a `chain` — mirror the construction at L145-158):
```python
def test_projection_property_returns_injected_projection():
    proj = KgProjectionFake()
    repo = EventSourcedStateRepository(
        tx_log=InMemoryTxLog(),
        activation_log=InMemoryActivationLog(),
        projection=proj,
        chain=NoopChainMirror(),
    )
    assert repo.projection is proj
```
(Use the exact chain double the file already uses — if it imports `NoopChainMirror` from `memento.state.chain_mirror`, reuse that; otherwise reuse whatever chain stub the neighboring tests construct.)

- [ ] **Step 2 — run, verify fail:** `PYTHONPATH=engine/src python3.12 -m pytest engine/tests/state/test_event_sourced_repository.py -q -k projection_property` → FAIL (`AttributeError: ... 'projection'`).

- [ ] **Step 3 — implement** — add the property to `EventSourcedStateRepository` (just after `__init__`, ~L90):
```python
    @property
    def projection(self) -> KgProjectionProtocol:
        """The KgProjection backing this repo (lets callers resolve KG uuids)."""
        return self._projection
```

- [ ] **Step 4 — run, verify pass:** same `-k` command → PASS; then the whole file `PYTHONPATH=engine/src python3.12 -m pytest engine/tests/state/test_event_sourced_repository.py -q` → green.
- [ ] **Step 5 — commit** (stage the two files) — `feat(state): expose EventSourcedStateRepository.projection accessor`.

---

# Movement 2 — gateway: the scene-activation service

## Task 2 — `SceneActivationService` + domain exceptions

**Files:**
- Create: `gateway/src/gateway/scene_activation.py`
- Test: `gateway/tests/test_scene_activation_service.py` (new)

**Interfaces:**
- Consumes: `RoomDriver` (`gateway.room_driver`), `BONFIRE_ID` (`gateway.routes.opening`), `repo.projection` (Task 1, via `getattr`).
- Produces: `SceneActivationService` with `from_app_state(state)`, `async activate(location_uuid) -> dict`, `async close(location_uuid) -> dict`; exceptions `SceneActivationError`, `SceneAlreadyOpen`, `SceneNotOpen`, `AgentRuntimeUnavailable`. The `scene_registry` maps `location_uuid -> RoomDriver` (the live driver, reused for close).

- [ ] **Step 1 — write the service** (`gateway/src/gateway/scene_activation.py`):
```python
"""Scene activation: construct a RoomDriver and open/close a scene for a location."""

from __future__ import annotations

from typing import Any

import httpx

from gateway.room_driver import RoomDriver
from gateway.routes.opening import BONFIRE_ID


class SceneActivationError(Exception):
    """Base for scene-activation domain errors."""


class SceneAlreadyOpen(SceneActivationError):
    """A scene is already open for this location."""


class SceneNotOpen(SceneActivationError):
    """No scene is open for this location."""


class AgentRuntimeUnavailable(SceneActivationError):
    """The agent-runtime could not be reached or returned an error."""


class SceneActivationService:
    """Opens/closes a RoomDriver-backed scene for a location.

    Constructed per request from app.state; the open-scene registry persists
    on app.state (location_uuid -> live RoomDriver).
    """

    def __init__(
        self,
        *,
        repo: Any,  # StateRepository Protocol impl (matches RoomDriver(repo: Any))
        agent_runtime_client: httpx.AsyncClient,
        scene_registry: dict[str, RoomDriver],
        bonfire_id: str = BONFIRE_ID,
    ) -> None:
        self._repo = repo
        self._client = agent_runtime_client
        self._registry = scene_registry
        self._bonfire_id = bonfire_id

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneActivationService":
        return cls(
            repo=state.cxn_repo,
            agent_runtime_client=state.agent_runtime_client,
            scene_registry=state.scene_registry,
        )

    def _build_driver(self) -> RoomDriver:
        # KG-backed repos expose .projection (Task 1); InMemory repos do not
        # -> None -> RoomDriver falls back to the engine uuid for embodiment.
        projection = getattr(self._repo, "projection", None)
        return RoomDriver(
            repo=self._repo,
            agent_runtime_client=self._client,
            bonfire_id=self._bonfire_id,
            projection=projection,
        )

    async def activate(self, location_uuid: str) -> dict[str, Any]:
        if location_uuid in self._registry:
            raise SceneAlreadyOpen(location_uuid)
        driver = self._build_driver()
        try:
            result = await driver.open_room(location_uuid)
        except httpx.HTTPError as exc:
            raise AgentRuntimeUnavailable(str(exc)) from exc
        self._registry[location_uuid] = driver  # register only after a successful open
        return {"scene_id": location_uuid, **result}

    async def close(self, location_uuid: str) -> dict[str, Any]:
        driver = self._registry.get(location_uuid)
        if driver is None:
            raise SceneNotOpen(location_uuid)
        try:
            result = await driver.close_room(location_uuid)
        except httpx.HTTPError as exc:
            raise AgentRuntimeUnavailable(str(exc)) from exc
        self._registry.pop(location_uuid, None)  # deregister only after a successful close
        return {"scene_id": location_uuid, **result}
```

- [ ] **Step 2 — failing unit test** (`gateway/tests/test_scene_activation_service.py`) — a minimal fake repo (empty roster is fine for the service's orchestration/error logic) + the recording-stub pattern from `test_room_driver.py:33-76`:
```python
import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.scene_activation import (
    AgentRuntimeUnavailable,
    SceneActivationService,
    SceneAlreadyOpen,
    SceneNotOpen,
)


class _FakeRepo:
    """Minimal StateRepository slice RoomDriver.open_room/close_room touch."""
    def __init__(self, entities=None):
        self._entities = entities or []
    async def get_entities_at_location(self, loc):
        return self._entities


def _stub_app(open_status=200):
    async def _open(request: Request):
        await request.json()
        return JSONResponse({"source_episode_id": "ep-1"}, status_code=open_status)
    async def _close(request: Request):
        return JSONResponse({"task_id": "t-1", "snapshot_size": 0})
    return Starlette(routes=[
        Route("/v1/scenes/{loc}/open", _open, methods=["POST"]),
        Route("/v1/scenes/{loc}/close", _close, methods=["POST"]),
    ])


def _svc(registry, open_status=200):
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_stub_app(open_status)),
        base_url="http://agent-runtime-stub",
    )
    return SceneActivationService(
        repo=_FakeRepo(), agent_runtime_client=client, scene_registry=registry,
    ), client


@pytest.mark.asyncio
async def test_activate_registers_then_double_activate_raises():
    registry: dict = {}
    svc, client = _svc(registry)
    try:
        out = await svc.activate("loc-1")
        assert out["scene_id"] == "loc-1"
        assert "loc-1" in registry
        with pytest.raises(SceneAlreadyOpen):
            await svc.activate("loc-1")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_close_unopened_raises_then_close_deregisters():
    registry: dict = {}
    svc, client = _svc(registry)
    try:
        with pytest.raises(SceneNotOpen):
            await svc.close("loc-x")
        await svc.activate("loc-1")
        await svc.close("loc-1")
        assert "loc-1" not in registry
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_open_transport_error_wraps_and_does_not_register():
    registry: dict = {}
    svc, client = _svc(registry, open_status=500)  # raise_for_status -> httpx.HTTPStatusError
    try:
        with pytest.raises(AgentRuntimeUnavailable):
            await svc.activate("loc-1")
        assert "loc-1" not in registry
    finally:
        await client.aclose()
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_activation_service.py -q` → 3 passed. (If `BONFIRE_ID` import from `gateway.routes.opening` triggers a heavy import chain, confirm it still imports cleanly; it is a module-level constant.)
- [ ] **Step 4 — commit** (stage scene_activation.py + the test) — `feat(gateway): SceneActivationService (open/close a RoomDriver scene + domain errors)`.

---

# Movement 3 — gateway: routes + app wiring + the proof

## Task 3 — `routes/scenes.py` + lifespan wiring + integration proof

**Files:**
- Create: `gateway/src/gateway/routes/scenes.py`
- Modify: `gateway/src/gateway/app.py`
- Test: `gateway/tests/test_scene_activation_route.py` (new)

**Interfaces:**
- Consumes: `SceneActivationService` (Task 2), `build_agent_runtime_client` (`gateway.room_driver`).
- Produces: `POST /api/scenes/{location_uuid}/activate` (200/409/502) and `POST /api/scenes/{location_uuid}/close` (200/404/502); `app.state.agent_runtime_client` + `app.state.scene_registry` set in the lifespan.

- [ ] **Step 1 — write the routes** (`gateway/src/gateway/routes/scenes.py`):
```python
"""Scene activation routes: open/close a RoomDriver-backed scene for a location."""

from fastapi import APIRouter, HTTPException, Request

from gateway.scene_activation import (
    AgentRuntimeUnavailable,
    SceneActivationService,
    SceneAlreadyOpen,
    SceneNotOpen,
)

router = APIRouter()


@router.post("/scenes/{location_uuid}/activate")
async def activate_scene(location_uuid: str, request: Request) -> dict:
    svc = SceneActivationService.from_app_state(request.app.state)
    try:
        return await svc.activate(location_uuid)
    except SceneAlreadyOpen:
        raise HTTPException(status_code=409, detail="Scene already open for this location.")
    except AgentRuntimeUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"Agent-runtime unavailable: {exc}")


@router.post("/scenes/{location_uuid}/close")
async def close_scene(location_uuid: str, request: Request) -> dict:
    svc = SceneActivationService.from_app_state(request.app.state)
    try:
        return await svc.close(location_uuid)
    except SceneNotOpen:
        raise HTTPException(status_code=404, detail="No scene open for this location.")
    except AgentRuntimeUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"Agent-runtime unavailable: {exc}")
```

- [ ] **Step 2 — wire the lifespan + router in `app.py`:**
  - Add an import near the other gateway imports (top of file): `from gateway.room_driver import build_agent_runtime_client`.
  - In `lifespan`, immediately AFTER `app.state.cxn_executor = mcp_asgi.cxn_executor` (L65), add:
```python
    app.state.agent_runtime_client = build_agent_runtime_client()
    app.state.scene_registry = {}
```
  - On the shutdown side (after `yield`, alongside the `if bridge:` block at L85-88), add (unconditional — the client is always built):
```python
    await app.state.agent_runtime_client.aclose()
```
  - Add `scenes` to the `from gateway.routes import (...)` tuple (L162-175) and, after the `opening` include (L188), add:
```python
app.include_router(scenes.router, prefix="/api")
```

- [ ] **Step 3 — integration test** (`gateway/tests/test_scene_activation_route.py`) — written after the route + wiring exist (the test imports `app`, which imports `scenes`, so it cannot be collected before Steps 1-2). It is non-vacuous regardless of order: the roster-capability/embodiment assertions and the 409/404/502 status checks cannot pass without the real route, service, and projection wiring. Real KG-backed repo (EventSourced over `KgProjectionFake`, identity-uuid) seeded with one NPC; agent-runtime client = recording stub; drive through the mounted route on the imported `app` singleton:
```python
import uuid

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog


class _Recorder:
    def __init__(self): self.calls = []
    def record(self, url, body): self.calls.append({"url": url, "body": body})


def _make_stub(recorder, open_status=200):
    async def _open(request: Request):
        body = await request.json()
        recorder.record(str(request.url), body)
        return JSONResponse({"source_episode_id": "ep-1"}, status_code=open_status)
    async def _close(request: Request):
        recorder.record(str(request.url), {})
        return JSONResponse({"task_id": "t-1", "snapshot_size": 0})
    return Starlette(routes=[
        Route("/v1/scenes/{loc}/open", _open, methods=["POST"]),
        Route("/v1/scenes/{loc}/close", _close, methods=["POST"]),
    ])


async def _seed_world():
    proj = KgProjectionFake()
    repo = EventSourcedStateRepository(
        tx_log=InMemoryTxLog(), activation_log=InMemoryActivationLog(),
        projection=proj, chain=NoopChainMirror(),
    )
    loc = uuid.uuid4().hex
    npc = uuid.uuid4().hex
    await repo.seed_entity({"uuid": loc, "kind": "location", "name": "Hall",
                            "labels": ["Location"], "location_uuid": None,
                            "attrs": {"exits": [], "item_ids": []}, "is_dead": False})
    await repo.seed_entity({"uuid": npc, "kind": "character", "name": "Guard",
                            "labels": ["Character", "NPC"], "location_uuid": loc,
                            "attrs": {"hp": 10, "max_hp": 10, "inventory": []}, "is_dead": False})
    return repo, loc, npc


async def _wire_app(open_status=200):
    from gateway.app import app
    repo, loc, npc = await _seed_world()
    recorder = _Recorder()
    app.state.cxn_repo = repo
    app.state.scene_registry = {}
    app.state.agent_runtime_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_make_stub(recorder, open_status)),
        base_url="http://agent-runtime-stub",
    )
    return app, repo, loc, npc, recorder


@pytest.mark.asyncio
async def test_activate_ships_roster_with_capabilities_and_embodiment():
    app, repo, loc, npc, recorder = await _wire_app()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(f"/api/scenes/{loc}/activate")
            assert resp.status_code == 200, resp.text
            # the agent-runtime received an open with a capability-bearing roster
            open_call = next(c for c in recorder.calls if "/open" in c["url"])
            roster = open_call["body"]["roster"]
            assert len(roster) == 1
            spec = roster[0]
            assert "mm_move" in spec["capabilities"]            # NPC kit
            assert spec["embodiment_agent_id"] == npc            # identity-uuid via projection
            assert loc in app.state.scene_registry

            # double-activate -> 409
            assert (await gw.post(f"/api/scenes/{loc}/activate")).status_code == 409

            # close -> 200 + deregister
            close_resp = await gw.post(f"/api/scenes/{loc}/close")
            assert close_resp.status_code == 200, close_resp.text
            assert any("/close" in c["url"] for c in recorder.calls)
            assert loc not in app.state.scene_registry

            # close again -> 404
            assert (await gw.post(f"/api/scenes/{loc}/close")).status_code == 404
    finally:
        await app.state.agent_runtime_client.aclose()


@pytest.mark.asyncio
async def test_agent_runtime_error_maps_to_502():
    app, repo, loc, npc, recorder = await _wire_app(open_status=500)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as gw:
            resp = await gw.post(f"/api/scenes/{loc}/activate")
            assert resp.status_code == 502, resp.text
            assert loc not in app.state.scene_registry
    finally:
        await app.state.agent_runtime_client.aclose()
```
  *(The two tests share the imported `app` singleton and both set `app.state` fresh at entry — mirror the existing `test_tools_http_route.py` / `test_gm_room_loop_e2e.py` pattern. If the seeded NPC does not appear in the roster, confirm `kind == "character"` and that `["Character","NPC"]` lacks `"Player"` — `open_room` filters by `kind` and excludes players.)*

- [ ] **Step 4 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_activation_route.py -q` → 2 passed. Run twice (the tests mutate the module-level `app.state`) to confirm determinism.
- [ ] **Step 5 — regression smoke:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q` → green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix` failure (confirm it is the only failure and unchanged).
- [ ] **Step 6 — commit** (stage scenes.py + app.py + the integration test) — `feat(gateway): scene-activation routes + lifespan wiring (first production RoomDriver call site)`.

---

## Verification (end-to-end)

1. **Engine accessor (Task 1):** `EventSourcedStateRepository.projection is <injected projection>`; engine state suite green.
2. **Service (Task 2):** `test_scene_activation_service.py` — activate registers + double-activate → `SceneAlreadyOpen`; close-unopened → `SceneNotOpen`, close deregisters; open transport/HTTP error → `AgentRuntimeUnavailable` and the scene is NOT registered.
3. **Route + wiring proof (Task 3):** `test_scene_activation_route.py` (deterministic, twice) — `POST /api/scenes/{loc}/activate` → 200, the agent-runtime stub received an `open` whose roster carries `capabilities` (∋ `mm_move`) and a KG-uuid `embodiment_agent_id` (== the seeded NPC uuid under identity-uuid), the scene is registered; `close` → 200 + deregistered + stub got a `close`; double-activate → 409; close-unopened → 404; agent-runtime 500 → 502 with no registration. `RoomDriver` is now constructed by a mounted production route.
4. **No regression:** full gateway suite green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix`.
5. **Whole-branch opus review:** `RoomDriver` has a genuine production call site; the projection seam is minimal and the InMemory fallback preserved; the service raises domain exceptions (route maps to HTTP); the lifespan builds/closes the agent-runtime client and inits the registry; no `Any` in new signatures beyond the `repo`-Protocol convention; no whole-tree ruff churn; identity-uuid scope honest.

## Out of scope (later slices)

- `drive_turn` route + the running agent-runtime that answers a real turn.
- Standing up / merging `bonfires-ai-core/persona/service-revision`; kernel/KG bring-up; `ws_hub` for broadcasts.
- The distinct-uuid executor gap (`kg_uuid→engine` resolution) — still deferred; this slice is identity-uuid.
- NPC content-seeding into the live world; auto-activation on player movement.
- #4-C role→param binding; #4-B remaining (Mongo, gate-reads-through-repo, opening-path repo unification, Approach A).

## On approval

Execute via superpowers:subagent-driven-development on a worktree branch `persona/scene-activation` off `opening/engine-core` (dc155af), T1→T3. Copy this plan to `memento-mori/docs/superpowers/plans/2026-06-26-persona-scene-activation.md` and commit (in the worktree) before dispatching Task 1.
