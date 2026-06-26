# Persona UI Integration — P2: Reachability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use `- [ ]` checkboxes. Spec: `bonfires-ai-core/docs/superpowers/specs/2026-06-26-persona-ui-integration-design.md` (this is **P2** of three phases; **P1 dialogue-loop is DONE/merged** into `opening/engine-core`; **P3 provisioning** gets its own plan later).

## Context

P1 wired the dialogue loop: a player `POST /api/action` message at a location with an **already-registered** persona scene routes to `RoomDriver.drive_turn` and broadcasts the NPC reply over the existing `tool_event/mm_npc_response` WS path (the client renders it unchanged). P1 **assumed a scene was already activated** (e.g. via `POST /api/scenes/{loc}/activate`) and that NPCs were already present.

**P2 makes personas reachable through normal play:** when a player's message lands at a location that has persona NPCs but **no scene yet**, the scene **auto-activates**; when the last player **leaves** a location, its scene **auto-closes**. Location identity (the `ws_hub` keys on the location *name*; scenes/`cxn_repo` key on `location_uuid`) is reconciled in **one** place. And — so the loop is testable locally without the full KG stack — a **minimal, flag-gated persona-NPC seed** is loaded into the in-memory `cxn_repo` at gateway bootstrap.

**Goal:** A player who moves to a location with persona NPCs gets a scene auto-activated (idempotently) and talks to the NPC; when they leave and no players remain, the scene closes. Reachable end-to-end locally via a minimal seed. No persona scene present → the existing `RoundManager`/Matrix path runs unchanged; a persona failure never 500s `/api/action`.

**Architecture:** Extend the existing `SceneCoordinator` (gateway) with `ensure_scene` (auto-activate when NPCs present + not registered, idempotent) and `maybe_close` (close a departed, now-empty scene). A new small `LocationResolver` owns name↔uuid reconciliation with an **app-scoped** cache (each `/api/action` builds a fresh coordinator, so the cache must live on `app.state`). `maybe_close` is driven from the **action path** (spec decision #4 — no movement event bus exists). A gated bootstrap seed puts persona NPCs into the in-memory repo so auto-activation has something to find locally.

**Tech Stack:** Python 3.12 (memento-mori gateway + engine), FastAPI/Starlette, httpx. Tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **mmori branch:** `persona/ui-reachability`, off `opening/engine-core` (HEAD `6457ea7`, which carries P1).
- Use an **isolated worktree**: `git worktree add -b persona/ui-reachability <scratchpad>/mmori-reach-wt opening/engine-core`. Work from the worktree; read files from it (the main checkout is on a different branch — wrong-tree trap).

## Global Constraints

- Commit trailer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. PR targets this lineage's base, never main.
- No cross-service Python imports (plain dicts on the wire). No `Any` in new signatures **except** the `repo`/`state`/`scene_registry`/`ws_hub`/`activation_service`/cache app-state-namespace params (Protocol/app-state convention, matching the existing `RoomDriver(repo: Any)` / `SceneActivationService.from_app_state(state: Any)` / P1 `SceneCoordinator(... : Any)`).
- Services raise **domain exceptions, not `HTTPException`** — and **a persona failure must never break the action path** (auto-activation / close degrade to a logged no-op, never 500 `/api/action`).
- UUIDs for entity/scene identity; the location **name** string is only used as the `ws_hub` broadcast key and as a resolver cache key (resolution, not identity).
- `os.environ` reads are allowed in the **gateway** (memento-mori) — the existing `mcp_server._build_cxn_repo()` and `routes/codex.py` already read `os.environ`/`world.json` directly. (The bonfires-ai-core no-`os.getenv` rule is for that repo's `services/*/src/modules` — not here.)
- Ruff-format only the files each task touches (the base isn't ruff-clean).
- Never write test entities to the production KG. The local seed is **in-memory-repo only**, flag-gated.

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/engine-core` @ `6457ea7`

- **`SceneActivationService`** — `gateway/src/gateway/scene_activation.py`. Ctor kw-only `(*, repo: Any, agent_runtime_client, scene_registry: dict[str, RoomDriver], bonfire_id=BONFIRE_ID)`; `from_app_state(state)` reads `state.cxn_repo` / `state.agent_runtime_client` / `state.scene_registry`. `async activate(location_uuid) -> dict` **raises `SceneAlreadyOpen` if already registered** (NOT idempotent), builds a `RoomDriver`, `await driver.open_room(...)`, wraps `httpx.HTTPError`→`AgentRuntimeUnavailable`, registers `scene_registry[location_uuid] = driver` **only after** a successful open, returns `{"scene_id": location_uuid, **result}`. `async close(location_uuid) -> dict` raises `SceneNotOpen` if absent, `await driver.close_room(...)`, pops the registry after success. Exceptions subclass `SceneActivationError`.
- **`RoomDriver.open_room(location_uuid)`** — `gateway/src/gateway/room_driver.py`. NPC discovery is **exactly** `entities = await self._repo.get_entities_at_location(location_uuid)`, then keep `entity.get("kind") == "character"` and **not** `self._is_player(entity)` (player labels default `{"Player"}`). Caches `self._last_roster_uuids[location_uuid] = {uuids}`. `drive_turn(location_uuid, player_message, *, addressed_name=None) -> dict` returns `{**agent_runtime_json, "self_id": actor_uuid}` (P1).
- **`SceneCoordinator`** (P1) — `gateway/src/gateway/scene_coordinator.py`. Ctor `(*, scene_registry: Any, cxn_repo: Any, ws_hub: Any)`; `from_app_state(state)` tolerant `getattr(...)`; `async handle_player_message(player_id, location_name, message) -> bool` (resolves uuid via `_get_location_uuid`, `registry.get(uuid)`, `drive_turn`, broadcasts `tool_event/mm_npc_response` keyed on `location_name`, degrades to logged no-op returning True on `drive_turn` failure, suppresses broadcast on `should_respond=False`); `async _npc_name(self_id)` via `cxn_repo.get_entity`.
- **`StateRepository`** — `engine/src/memento/state/repository.py` (Protocol) + `in_memory.py` (`InMemoryStateRepository`, **sync** `seed_entity(doc)`) + `event_sourced.py` (`EventSourcedStateRepository`, **async** `seed_entity`). `async get_entities_at_location(location_uuid) -> list[EntityDoc]`; `async get_entity(uuid) -> EntityDoc | None`. `EntityDoc` TypedDict: `{uuid, name, kind, labels, location_uuid, attrs, is_dead}`.
- **`_get_location_uuid(player_id) -> str | None`** — `gateway/src/gateway/routes/codex.py` (module-level async; `ws_hub.player_locations[player_id]` name → KG `client.kg.search` → first `Location`-labelled uuid → `world.json` Threshold fallback). KG-only — returns `None` in a pure in-memory/local run. Monkeypatchable.
- **`WebSocketHub`** — `gateway/src/gateway/ws.py`. `player_locations: dict[str,str]` (player→location **name**); `async set_location(player_id, location)` overwrites `player_locations[player_id]` (capturing `old_location` internally, **not returned**); `players_at_location(name) -> int` (accurate count after a `set_location`); `broadcast_to_location(name, msg)`; `async disconnect(player_id)`.
- **`submit_action`** (P1) — `gateway/src/gateway/routes/action.py`. `async def submit_action(req: ActionRequest, request: Request)`: `await ws_hub.set_location(req.player_id, req.location)` → build `SceneCoordinator.from_app_state(request.app.state)` → `if await coordinator.handle_player_message(req.player_id, req.location, req.action): return ActionResponse(status="queued")` → else the `round_manager` path. Imports module globals `from gateway.app import round_manager, ws_hub`.
- **`app.py` lifespan** — `gateway/src/gateway/app.py`. Sets `app.state.ws_hub`, `app.state.cxn_repo` (`mcp_asgi.cxn_repo`, the `StateRepository`), `app.state.cxn_executor`, `app.state.agent_runtime_client = build_agent_runtime_client()`, `app.state.scene_registry = {}`. `_build_cxn_repo()` (`mcp_server.py`) returns `EventSourcedStateRepository` when `KERNEL_BASE_URL`+`GM_INTERNAL_TOKEN` are set, else `InMemoryStateRepository` (starts **empty**).
- **Test seed shape** — `gateway/tests/test_scene_activation_route.py`: `repo.seed_entity({"uuid":..,"kind":"character","name":"Guard","labels":["Character","NPC"],"location_uuid":loc,"attrs":{"hp":10,"max_hp":10,"inventory":[]},"is_dead":False})`. Location: `{"uuid":loc,"kind":"location","name":"Hall","labels":["Location"],"location_uuid":None,"attrs":{"exits":[],"item_ids":[]},"is_dead":False}`. (`InMemoryStateRepository.seed_entity` is sync.)

---

# Movement 1 — gateway: location identity in one place

## Task 1 — `LocationResolver` (name↔uuid + app-scoped cache)

**Files:**
- Create: `gateway/src/gateway/location_resolver.py`
- Test: `gateway/tests/test_location_resolver.py` (new)

**Interfaces:**
- Produces: `LocationResolver(cxn_repo, cache)`; `async uuid_for(player_id, location_name) -> str | None` (cache-first, then `_get_location_uuid`, records on success); `async name_for(location_uuid) -> str | None`; `record(name, uuid)`; `uuid_for_name(name) -> str | None`; `forget_name(name)`. The `cache` is a shared `dict[str, str]` (location name → uuid) owned by `app.state` so it survives across requests. Consumed by `SceneCoordinator` (Tasks 3 & 4).

- [ ] **Step 1 — write the resolver** (`gateway/src/gateway/location_resolver.py`):
```python
"""Reconciles the two location identities used by the gateway: ws_hub keys on a
location NAME, while scenes / cxn_repo key on a location_uuid. The name->uuid cache
is owned by app.state (passed in) so it survives across requests; it is populated
by the bootstrap persona seed and by KG-confirmed lookups, and read by maybe_close
to resolve a departed location whose player has already moved away.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)


class LocationResolver:
    def __init__(self, cxn_repo: Any, cache: Any) -> None:
        self._repo = cxn_repo
        self._cache = cache if cache is not None else {}

    async def uuid_for(self, player_id: str, location_name: str) -> str | None:
        # Cache first (local seed + previously KG-confirmed names): works without KG.
        cached = self._cache.get(location_name)
        if cached:
            return cached
        # Fall back to the KG-authoritative resolver for the real deployment.
        from gateway.routes.codex import _get_location_uuid

        uuid = await _get_location_uuid(player_id)
        if uuid and location_name:
            self._cache[location_name] = uuid
        return uuid

    async def name_for(self, location_uuid: str) -> str | None:
        if self._repo is None:
            return None
        try:
            entity = await self._repo.get_entity(location_uuid)
        except Exception:  # repo failure must not break the action path
            return None
        return entity.get("name") if entity else None

    def record(self, name: str, uuid: str) -> None:
        if name and uuid:
            self._cache[name] = uuid

    def uuid_for_name(self, name: str) -> str | None:
        return self._cache.get(name)

    def forget_name(self, name: str) -> None:
        self._cache.pop(name, None)
```

- [ ] **Step 2 — failing tests** (`gateway/tests/test_location_resolver.py`):
```python
import pytest

from gateway.location_resolver import LocationResolver


class _Repo:
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gatehouse"} if uuid == "loc-1" else None


def _patch_kg(monkeypatch, value):
    async def _fake(_pid):
        return value
    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _fake)


@pytest.mark.asyncio
async def test_uuid_for_hits_cache_without_kg(monkeypatch):
    calls = {"n": 0}

    async def _kg(_pid):
        calls["n"] += 1
        return None
    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _kg)
    cache = {"Gatehouse": "loc-1"}
    r = LocationResolver(_Repo(), cache)
    assert await r.uuid_for("p1", "Gatehouse") == "loc-1"
    assert calls["n"] == 0  # cache hit -> KG never consulted


@pytest.mark.asyncio
async def test_uuid_for_falls_back_to_kg_and_records(monkeypatch):
    _patch_kg(monkeypatch, "loc-9")
    cache: dict[str, str] = {}
    r = LocationResolver(_Repo(), cache)
    assert await r.uuid_for("p1", "North Gate") == "loc-9"
    assert cache["North Gate"] == "loc-9"          # recorded for later maybe_close


@pytest.mark.asyncio
async def test_uuid_for_returns_none_when_unresolved(monkeypatch):
    _patch_kg(monkeypatch, None)
    r = LocationResolver(_Repo(), {})
    assert await r.uuid_for("p1", "Nowhere") is None


@pytest.mark.asyncio
async def test_name_for_reads_repo():
    r = LocationResolver(_Repo(), {})
    assert await r.name_for("loc-1") == "Gatehouse"
    assert await r.name_for("missing") is None


def test_record_lookup_forget():
    cache: dict[str, str] = {}
    r = LocationResolver(_Repo(), cache)
    r.record("Gatehouse", "loc-1")
    assert r.uuid_for_name("Gatehouse") == "loc-1"
    r.forget_name("Gatehouse")
    assert r.uuid_for_name("Gatehouse") is None
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_location_resolver.py -q` → 5 passed. *(If `gateway.log.get_logger` is wrong, match the gateway convention — most modules use `gateway.log.get_logger`; confirm against `scene_coordinator.py`.)*
- [ ] **Step 4 — commit** (stage location_resolver.py + test) — `feat(gateway): LocationResolver reconciles location name<->uuid with an app-scoped cache`.

---

# Movement 2 — gateway: bootstrap (shared cache + local seed)

## Task 2 — `app.state.scene_locations` + gated local persona seed

**Files:**
- Create: `gateway/src/gateway/persona_seed.py`
- Modify: `gateway/src/gateway/app.py` (lifespan)
- Test: `gateway/tests/test_persona_seed.py` (new)

**Interfaces:**
- Produces: `async seed_local_personas(repo, cache) -> bool` — when `repo` is an `InMemoryStateRepository` (local/no-KG) it seeds one location + one NPC into the repo and records `name->uuid` in `cache`; returns True if it seeded. No-op (returns False) for KG-backed repos. Lifespan sets `app.state.scene_locations = {}` (the resolver cache, Task 1) and calls `seed_local_personas` when `PERSONA_LOCAL_SEED` is set.

- [ ] **Step 1 — write the seed helper** (`gateway/src/gateway/persona_seed.py`):
```python
"""Minimal, flag-gated persona-NPC seed for LOCAL play (in-memory cxn_repo only).
Lets a developer test the persona dialogue loop without standing up the KG stack.
KG-backed deployments seed NPCs through the world bootstrap / KG (P3 provisioning),
so this is a no-op there. Never writes to the production KG.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)

# Deterministic local-only uuids (clearly non-production).
_LOC_UUID = "local-threshold"
_LOC_NAME = "The Threshold"
_NPC_UUID = "local-gareth"


def _location_doc() -> dict[str, Any]:
    return {
        "uuid": _LOC_UUID,
        "kind": "location",
        "name": _LOC_NAME,
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {"exits": [], "item_ids": []},
        "is_dead": False,
    }


def _npc_doc() -> dict[str, Any]:
    return {
        "uuid": _NPC_UUID,
        "kind": "character",
        "name": "Gareth the Guard",
        "labels": ["Character", "NPC", "Guard"],
        "location_uuid": _LOC_UUID,
        "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
        "is_dead": False,
    }


async def seed_local_personas(repo: Any, cache: Any) -> bool:
    from memento.state.in_memory import InMemoryStateRepository

    if not isinstance(repo, InMemoryStateRepository):
        return False  # KG-backed deployment seeds via the world bootstrap (P3)
    repo.seed_entity(_location_doc())  # InMemoryStateRepository.seed_entity is sync
    repo.seed_entity(_npc_doc())
    if cache is not None:
        cache[_LOC_NAME] = _LOC_UUID  # so LocationResolver resolves it without KG
    logger.info("seeded local persona NPC %s at %s", _NPC_UUID, _LOC_NAME)
    return True
```

- [ ] **Step 2 — wire the lifespan** in `gateway/src/gateway/app.py`. Find where `app.state.scene_registry = {}` is set in the lifespan and, immediately after it, add the shared cache + the gated seed:
```python
    app.state.scene_locations = {}  # location name -> uuid cache (LocationResolver)
    import os

    if os.environ.get("PERSONA_LOCAL_SEED"):
        from gateway.persona_seed import seed_local_personas

        await seed_local_personas(app.state.cxn_repo, app.state.scene_locations)
```
  *(Place it after `cxn_repo` and `scene_registry` are on `app.state`. Match the surrounding lifespan style; if the lifespan already imports `os` at module top, drop the local `import os`.)*

- [ ] **Step 3 — failing tests** (`gateway/tests/test_persona_seed.py`):
```python
import pytest

from memento.state.in_memory import InMemoryStateRepository
from gateway.persona_seed import seed_local_personas, _LOC_UUID, _LOC_NAME, _NPC_UUID


@pytest.mark.asyncio
async def test_seeds_inmemory_repo_and_cache():
    repo = InMemoryStateRepository()
    cache: dict[str, str] = {}
    seeded = await seed_local_personas(repo, cache)
    assert seeded is True
    entities = await repo.get_entities_at_location(_LOC_UUID)
    npc_uuids = {e["uuid"] for e in entities if e.get("kind") == "character"}
    assert _NPC_UUID in npc_uuids                     # discoverable by ensure_scene
    assert cache[_LOC_NAME] == _LOC_UUID              # resolvable without KG


class _NotInMemory:
    def seed_entity(self, doc):  # would raise if called
        raise AssertionError("must not seed a KG-backed repo")


@pytest.mark.asyncio
async def test_noop_for_non_inmemory_repo():
    cache: dict[str, str] = {}
    assert await seed_local_personas(_NotInMemory(), cache) is False
    assert cache == {}
```

- [ ] **Step 4 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_seed.py -q` → 2 passed.
- [ ] **Step 5 — regression smoke** (the lifespan edit must not break app import/boot): `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_activation_route.py -q` → green (it imports the real `app` + drives the route).
- [ ] **Step 6 — commit** (stage persona_seed.py + app.py + test) — `feat(gateway): app-scoped scene_locations cache + gated local persona seed`.

---

# Movement 3 — gateway: auto-activation

## Task 3 — `SceneCoordinator.ensure_scene` + `handle_player_message` auto-activates

**Files:**
- Modify: `gateway/src/gateway/scene_coordinator.py`
- Test: `gateway/tests/test_scene_coordinator_reachability.py` (new)

**Interfaces:**
- Consumes: `LocationResolver` (Task 1), `app.state.scene_locations` (Task 2), `SceneActivationService` (`activate`, `SceneAlreadyOpen`, `SceneActivationError`), `repo.get_entities_at_location`.
- Produces: `async ensure_scene(location_uuid) -> Any | None` (returns the live driver; auto-activates iff NPCs present + not registered + an activation service is available; idempotent; never raises). `handle_player_message` now resolves via the `LocationResolver`, records the name↔uuid, and calls `ensure_scene`. New optional ctor kwargs `activation_service=None`, `location_resolver=None` (back-compat with P1 tests). Consumed by Task 4 (`maybe_close`).

- [ ] **Step 1 — extend the coordinator.** In `gateway/src/gateway/scene_coordinator.py`:
  - Add imports near the top:
```python
from gateway.location_resolver import LocationResolver
from gateway.scene_activation import (
    SceneActivationError,
    SceneActivationService,
    SceneAlreadyOpen,
)
```
  - Replace the ctor + `from_app_state` with:
```python
    def __init__(
        self,
        *,
        scene_registry: Any,
        cxn_repo: Any,
        ws_hub: Any,
        activation_service: Any = None,
        location_resolver: Any = None,
    ) -> None:
        self._registry = scene_registry
        self._repo = cxn_repo
        self._ws_hub = ws_hub
        self._activation = activation_service
        self._resolver = location_resolver or LocationResolver(cxn_repo, {})

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneCoordinator":
        registry = getattr(state, "scene_registry", None)
        repo = getattr(state, "cxn_repo", None)
        ws_hub = getattr(state, "ws_hub", None)
        cache = getattr(state, "scene_locations", None)
        activation = None
        if (
            registry is not None
            and repo is not None
            and getattr(state, "agent_runtime_client", None) is not None
        ):
            activation = SceneActivationService.from_app_state(state)
        return cls(
            scene_registry=registry,
            cxn_repo=repo,
            ws_hub=ws_hub,
            activation_service=activation,
            location_resolver=LocationResolver(repo, cache),
        )
```
  - Add `ensure_scene` and a private NPC-presence check:
```python
    async def ensure_scene(self, location_uuid: str) -> Any | None:
        if self._registry is None:
            return None
        driver = self._registry.get(location_uuid)
        if driver is not None:
            return driver  # already active (idempotent)
        if self._activation is None:
            return None  # no auto-activation capability (P1-style direct construction)
        if not await self._has_persona_npcs(location_uuid):
            return None  # nothing to talk to here -> caller falls through
        try:
            await self._activation.activate(location_uuid)
        except SceneAlreadyOpen:
            pass  # concurrent activation won the race
        except SceneActivationError as exc:  # incl. AgentRuntimeUnavailable
            logger.warning("scene_coordinator.activate_failed: %s", exc)
            return None
        return self._registry.get(location_uuid)

    async def _has_persona_npcs(self, location_uuid: str) -> bool:
        if self._repo is None:
            return False
        try:
            entities = await self._repo.get_entities_at_location(location_uuid)
        except Exception:  # repo failure must not break the action path
            return False
        return any(e.get("kind") == "character" for e in entities)
```
  - Rewrite `handle_player_message` to resolve via the resolver and auto-activate:
```python
    async def handle_player_message(
        self, player_id: str, location_name: str, message: str
    ) -> bool:
        if self._registry is None or self._ws_hub is None:
            return False
        location_uuid = await self._resolver.uuid_for(player_id, location_name)
        if not location_uuid:
            return False
        self._resolver.record(location_name, location_uuid)  # for maybe_close (Task 4)
        driver = await self.ensure_scene(location_uuid)
        if driver is None:
            return False
        try:
            turn = await driver.drive_turn(location_uuid, message)
        except Exception as exc:  # persona failure must NOT break the action path
            logger.warning("scene_coordinator.drive_turn_failed: %s", exc)
            return True
        if turn.get("should_respond", True):
            npc_name = await self._npc_name(turn.get("self_id"))
            msg = {
                "type": "tool_event",
                "tool": "mm_npc_response",
                "npc": npc_name,
                "summary": turn.get("response_text", ""),
                "data": {},
                "location": location_name,
                "channel": "narrative",
            }
            await self._ws_hub.broadcast_to_location(location_name, msg)
        return True
```
  *(`_npc_name` is unchanged from P1. `handle_player_message` no longer imports `_get_location_uuid` directly — the resolver owns that.)*

- [ ] **Step 2 — failing tests** (`gateway/tests/test_scene_coordinator_reachability.py`) — a fake activation service that registers a driver into the shared registry on `activate`:
```python
import pytest

from gateway.scene_activation import AgentRuntimeUnavailable
from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    def __init__(self): self.calls = []
    async def drive_turn(self, loc, msg, *, addressed_name=None):
        self.calls.append((loc, msg))
        return {"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}


class _FakeRepo:
    def __init__(self, entities): self._entities = entities
    async def get_entities_at_location(self, loc):
        return self._entities.get(loc, [])
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gareth"} if uuid == "npc-1" else None


class _FakeActivation:
    def __init__(self, registry, driver):
        self._registry, self._driver, self.activated = registry, driver, []
    async def activate(self, loc):
        self.activated.append(loc)
        self._registry[loc] = self._driver
        return {"scene_id": loc}


class _FakeHub:
    def __init__(self): self.broadcasts = []
    async def broadcast_to_location(self, loc, msg): self.broadcasts.append((loc, msg))


def _coord(registry, repo, activation, hub, cache):
    from gateway.location_resolver import LocationResolver
    return SceneCoordinator(
        scene_registry=registry, cxn_repo=repo, ws_hub=hub,
        activation_service=activation,
        location_resolver=LocationResolver(repo, cache),
    )


@pytest.mark.asyncio
async def test_ensure_scene_activates_when_npcs_present():
    registry = {}
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, driver)
    coord = _coord(registry, repo, act, _FakeHub(), {})
    got = await coord.ensure_scene("loc-1")
    assert got is driver
    assert act.activated == ["loc-1"]


@pytest.mark.asyncio
async def test_ensure_scene_idempotent_when_already_registered():
    driver = _FakeDriver()
    registry = {"loc-1": driver}
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, _FakeDriver())
    coord = _coord(registry, repo, act, _FakeHub(), {})
    got = await coord.ensure_scene("loc-1")
    assert got is driver           # the pre-registered driver, not a new one
    assert act.activated == []     # no re-activation


@pytest.mark.asyncio
async def test_ensure_scene_returns_none_without_npcs():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "x", "kind": "location"}]})  # no character
    act = _FakeActivation(registry, _FakeDriver())
    coord = _coord(registry, repo, act, _FakeHub(), {})
    assert await coord.ensure_scene("loc-1") is None
    assert act.activated == []


@pytest.mark.asyncio
async def test_ensure_scene_degrades_on_agent_runtime_unavailable():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})

    class _Boom(_FakeActivation):
        async def activate(self, loc):
            raise AgentRuntimeUnavailable("down")
    coord = _coord(registry, repo, _Boom(registry, _FakeDriver()), _FakeHub(), {})
    assert await coord.ensure_scene("loc-1") is None   # no raise


@pytest.mark.asyncio
async def test_handle_player_message_auto_activates_and_broadcasts():
    registry = {}
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    act = _FakeActivation(registry, driver)
    hub = _FakeHub()
    cache = {"North Gate": "loc-1"}                       # resolver cache hit (no KG)
    coord = _coord(registry, repo, act, hub, cache)
    handled = await coord.handle_player_message("p1", "North Gate", "Gareth?")
    assert handled is True
    assert act.activated == ["loc-1"]                    # auto-activated
    assert driver.calls == [("loc-1", "Gareth?")]
    assert len(hub.broadcasts) == 1
    loc, msg = hub.broadcasts[0]
    assert loc == "North Gate" and msg["npc"] == "Gareth" and msg["summary"] == "Halt!"


@pytest.mark.asyncio
async def test_handle_player_message_no_activation_service_is_p1_behavior():
    # No activation service (P1-style direct construction): only a pre-registered scene works.
    driver = _FakeDriver()
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character"}]})
    hub = _FakeHub()
    from gateway.location_resolver import LocationResolver
    coord = SceneCoordinator(
        scene_registry={}, cxn_repo=repo, ws_hub=hub,
        location_resolver=LocationResolver(repo, {"North Gate": "loc-1"}),
    )
    assert await coord.handle_player_message("p1", "North Gate", "hi") is False
    assert hub.broadcasts == []
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_coordinator_reachability.py -q` → 6 passed.
- [ ] **Step 4 — P1 regression:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_coordinator.py gateway/tests/test_action_persona_branch.py -q` → green. (P1's `test_scene_coordinator.py` constructs the coordinator directly with no `activation_service` and patches `_get_location_uuid`; `ensure_scene` returns `registry.get(...)` and the resolver's cache-miss path still calls the patched `_get_location_uuid` — behavior preserved.)
- [ ] **Step 5 — commit** (stage scene_coordinator.py + the new test) — `feat(gateway): SceneCoordinator auto-activates a persona scene when NPCs are present`.

---

# Movement 4 — gateway: auto-close on departure

## Task 4 — `maybe_close` + `submit_action` departure wiring

**Files:**
- Modify: `gateway/src/gateway/scene_coordinator.py` (add `maybe_close`)
- Modify: `gateway/src/gateway/routes/action.py` (capture old location, call `maybe_close`)
- Test: `gateway/tests/test_scene_close_on_leave.py` (new)

**Interfaces:**
- Consumes: `SceneActivationService.close` + `SceneNotOpen`, `ws_hub.players_at_location(name)`, the resolver cache (`uuid_for_name`).
- Produces: `async maybe_close(departed_location_name) -> None` (closes a registered scene at the departed location iff no players remain; resolves the uuid from the resolver cache so it works after the player has moved; degrades, never raises). `submit_action` captures the player's previous location before `set_location` and calls `maybe_close` when they moved away.

- [ ] **Step 1 — add `maybe_close`** to `gateway/src/gateway/scene_coordinator.py`. Add `SceneNotOpen` to the existing `scene_activation` import, then add the method:
```python
    async def maybe_close(self, departed_location_name: str) -> None:
        if not departed_location_name or self._ws_hub is None or self._activation is None:
            return
        location_uuid = self._resolver.uuid_for_name(departed_location_name)
        if not location_uuid or self._registry is None or location_uuid not in self._registry:
            return
        if self._ws_hub.players_at_location(departed_location_name) > 0:
            return  # someone is still here
        try:
            await self._activation.close(location_uuid)
        except SceneNotOpen:
            pass
        except SceneActivationError as exc:  # incl. AgentRuntimeUnavailable
            logger.warning("scene_coordinator.close_failed: %s", exc)
            return
        self._resolver.forget_name(departed_location_name)
```
  *(The import line becomes `from gateway.scene_activation import (SceneActivationError, SceneActivationService, SceneAlreadyOpen, SceneNotOpen)`.)*

- [ ] **Step 2 — wire `submit_action`** in `gateway/src/gateway/routes/action.py`. Capture the previous location BEFORE `set_location`, and call `maybe_close` after building the coordinator (the same coordinator instance shares the app-scoped resolver cache). The changed region becomes:
```python
    from gateway.app import round_manager, ws_hub

    previous_location = ""
    if ws_hub:
        previous_location = ws_hub.player_locations.get(req.player_id, "")
        await ws_hub.set_location(req.player_id, req.location)

    from gateway.scene_coordinator import SceneCoordinator

    coordinator = SceneCoordinator.from_app_state(request.app.state)
    handled = await coordinator.handle_player_message(req.player_id, req.location, req.action)
    if previous_location and previous_location != req.location:
        await coordinator.maybe_close(previous_location)
    if handled:
        return ActionResponse(status="queued")
```
  *(Keep the existing `round_manager` block below unchanged.)*

- [ ] **Step 3 — failing unit tests** (`gateway/tests/test_scene_close_on_leave.py`):
```python
import pytest

from gateway.scene_activation import SceneNotOpen
from gateway.scene_coordinator import SceneCoordinator


class _FakeActivation:
    def __init__(self, registry):
        self._registry, self.closed = registry, []
    async def close(self, loc):
        self.closed.append(loc)
        self._registry.pop(loc, None)
        return {"scene_id": loc}


class _Hub:
    def __init__(self, counts): self._counts = counts
    def players_at_location(self, name): return self._counts.get(name, 0)


def _coord(registry, activation, hub, cache):
    from gateway.location_resolver import LocationResolver
    return SceneCoordinator(
        scene_registry=registry, cxn_repo=None, ws_hub=hub,
        activation_service=activation,
        location_resolver=LocationResolver(None, cache),
    )


@pytest.mark.asyncio
async def test_closes_scene_when_last_player_leaves():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == ["loc-1"]
    assert "loc-1" not in registry


@pytest.mark.asyncio
async def test_keeps_scene_when_players_remain():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 1}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == []
    assert "loc-1" in registry


@pytest.mark.asyncio
async def test_noop_when_no_scene_registered():
    registry = {}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {"North Gate": "loc-1"})
    await coord.maybe_close("North Gate")
    assert act.closed == []


@pytest.mark.asyncio
async def test_noop_when_location_uncached():
    registry = {"loc-1": object()}
    act = _FakeActivation(registry)
    coord = _coord(registry, act, _Hub({"North Gate": 0}), {})  # name not in cache
    await coord.maybe_close("North Gate")
    assert act.closed == []
```

- [ ] **Step 4 — integration test** (append to `gateway/tests/test_scene_close_on_leave.py`) — `/api/action` that moves a player away from a scene-active location closes it. Built on the P1 `test_action_persona_branch.py::_wire` pattern (real `app`, `httpx.ASGITransport`, monkeypatched `gateway.app.ws_hub`/`round_manager`, a stub agent-runtime serving `/turn`+`/close`, `_get_location_uuid` patched to the player's NEW location):
```python
import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.state.in_memory import InMemoryStateRepository
from gateway.room_driver import RoomDriver


def _stub(closed):
    async def _turn(request):
        return JSONResponse({"response_text": "ok", "should_respond": False})
    async def _close(request):
        closed.append(request.path_params["rid"])
        return JSONResponse({"closed": True})
    return Starlette(routes=[
        Route("/v1/scenes/{rid}/turn", _turn, methods=["POST"]),
        Route("/v1/scenes/{rid}/close", _close, methods=["POST"]),
    ])


@pytest.mark.asyncio
async def test_action_moving_away_closes_previous_scene(monkeypatch):
    from gateway.app import app

    repo = InMemoryStateRepository()
    repo.seed_entity({"uuid": "npc-A", "kind": "character", "name": "Gareth",
                      "labels": ["Character", "NPC"], "location_uuid": "loc-A",
                      "attrs": {"hp": 10, "max_hp": 10, "inventory": []}, "is_dead": False})
    closed: list[str] = []
    ar_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_stub(closed)),
                                  base_url="http://ar")
    driver = RoomDriver(repo=repo, agent_runtime_client=ar_client, bonfire_id="b1")
    driver._last_roster_uuids["loc-A"] = {"npc-A"}

    class _Hub:
        def __init__(self): self.locs = {"p1": "Hall A"}; self.broadcasts = []
        async def set_location(self, pid, loc): self.locs[pid] = loc
        async def broadcast_to_location(self, loc, msg): self.broadcasts.append((loc, msg))
        def players_at_location(self, loc): return sum(1 for v in self.locs.values() if v == loc)

    class _RM:
        async def submit_action(self, *a): ...
        async def close_round(self, loc): ...

    hub = _Hub()
    app.state.cxn_repo = repo
    app.state.ws_hub = hub
    app.state.scene_registry = {"loc-A": driver}
    app.state.scene_locations = {"Hall A": "loc-A"}
    monkeypatch.setattr("gateway.app.ws_hub", hub)
    monkeypatch.setattr("gateway.app.round_manager", _RM())

    async def _loc(_pid): return "loc-B"  # NEW location resolves to loc-B (no scene/NPCs)
    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _loc)

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as gw:
            resp = await gw.post("/api/action",
                                 json={"player_id": "p1", "action": "leave", "location": "Hall B"})
            assert resp.status_code == 200
        assert closed == ["loc-A"]                       # previous scene closed
        assert "loc-A" not in app.state.scene_registry
        assert hub.players_at_location("Hall A") == 0
    finally:
        await ar_client.aclose()
```

- [ ] **Step 5 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_close_on_leave.py -q` → 5 passed. Run twice (the integration test mutates the shared `app`/`gateway.app` globals) to confirm determinism.
- [ ] **Step 6 — regression smoke:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q` → green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix` (confirm it's the only failure and unchanged).
- [ ] **Step 7 — commit** (stage scene_coordinator.py + routes/action.py + the test) — `feat(gateway): close a persona scene when the last player leaves the location`.

---

## Verification (end-to-end)

1. **LocationResolver (Task 1):** cache-first resolution works with no KG; KG fallback records the name↔uuid; `name_for`/`record`/`forget` behave. 5 tests.
2. **Bootstrap (Task 2):** `app.state.scene_locations` exists; the gated local seed puts an NPC into the in-memory repo + records its location in the cache; no-op for KG-backed repos; the app still boots. 2 tests + smoke.
3. **Auto-activation (Task 3):** `ensure_scene` activates exactly once when NPCs are present, is idempotent when a scene exists, returns `None` with no NPCs / no activation service, degrades on `AgentRuntimeUnavailable`; `handle_player_message` auto-activates then drives + broadcasts; P1 direct-construction behavior preserved. 6 tests + P1 regression.
4. **Auto-close (Task 4):** `maybe_close` closes a registered scene when the last player leaves (cache-resolved uuid), keeps it when players remain, no-ops when unregistered/uncached; `/api/action` moving a player away closes the previous scene. 5 tests (twice) + full-suite smoke.
5. **No regression:** the full gateway suite is green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix`; P1's `test_scene_coordinator.py` + `test_action_persona_branch.py` stay green.
6. **Whole-branch opus review:** the branch is additive — auto-activation only fires where persona NPCs exist; the existing `RoundManager`/Matrix path is the default fallback; a persona failure (activate/close/drive) never 500s `/api/action`; location identity is reconciled only in `LocationResolver`; no `Any` beyond the app-state-namespace conventions; the local seed is in-memory-only + flag-gated and never touches the production KG.
7. **Live demo (manual, optional):** local — set `PERSONA_LOCAL_SEED=1`, run the gateway against a stubbed/real agent-runtime, send `/api/action {location:"The Threshold", action:"Gareth, may I pass?"}` and watch the scene auto-activate and the NPC reply render in the client; then move away and confirm the scene closes. Bring-up stack — same against the KG-seeded Threshold NPCs.

## Out of scope (P3 / later)

- **Provisioning (P3):** gateway world bonfire-id resolution (graph-memory ObjectId) replacing the hardcoded `"mm-world-v1"`; KG-backed `cxn_repo` wiring as the production default; net-new persona-NPC creation into the KG with `LOCATED_IN` edges; codex/`npc_joined` UI surfacing of auto-activated NPCs (the codex already reads `LOCATED_IN` from the KG, so KG-seeded NPCs surface once the repo is KG-backed).
- **Multi-NPC who-acts** beyond `drive_turn`'s addressed-name + single-NPC fallback (needs `npc_registry` populated for addressed-name; P3).
- **Disconnect-driven / TTL scene eviction** — P2 closes on action-path departure only; a player who closes the tab leaves the scene registered until a later visit (the scene-activation slice's standing "no eviction beyond explicit close" forward note).
- **Matrix cutover**, persona narration/gossip/combat dialogue, client UX for targeting NPCs — later.

## On approval

Execute via superpowers:subagent-driven-development on a worktree branch `persona/ui-reachability` off `opening/engine-core` (`6457ea7`), T1→T4. Copy this plan to `memento-mori/docs/superpowers/plans/2026-06-26-persona-ui-reachability.md` and commit (in the worktree) before dispatching Task 1.
