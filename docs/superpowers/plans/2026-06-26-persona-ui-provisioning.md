# Persona UI Integration — P3: Provisioning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Fresh implementer per task, per-task review, whole-branch opus review at the end. Steps use `- [ ]` checkboxes. Spec: `bonfires-ai-core/docs/superpowers/specs/2026-06-26-persona-ui-integration-design.md` (this is **P3 — the final phase**; **P1 dialogue-loop** and **P2 reachability** are DONE/merged into `opening/engine-core` @ `53cef2a`).

## Context

P1 wired the dialogue loop (a player message at a location with an already-registered persona scene routes to `RoomDriver.drive_turn` and renders over `tool_event/mm_npc_response`). P2 made personas **reachable through play**: auto-activate a scene when persona NPCs are present, auto-close when the last player leaves, reconciling location name↔uuid in `LocationResolver`. Both work today **only on the in-memory repo** (the `PERSONA_LOCAL_SEED` path) — they do **not** work against the real KG-backed deployment.

**P3 makes personas work on the real (KG-backed) stack** — the live bring-up. Three things block that today:

1. **The bonfire-id mismatch (the bring-up blocker).** Two identity systems never reconcile: the slug `"mm-world-v1"` (hardcoded in `routes/opening.py:68` and reached by `SceneActivationService` → `RoomDriver` → agent-runtime `/v1/scenes`, plus the cxn/comprehend/memory paths) versus the SDK's `BONFIRE_ID` env value (a Mongo **ObjectId**) used for every `client.kg.*` call. graph-memory coerces the `{bonfire_id}` path param to a `PydanticObjectId` and **404s anything that isn't a 24-hex ObjectId** (`bonfires_service.get`, `kg_service.ingest_episode`). `SceneActivationService.from_app_state` doesn't even pass `bonfire_id`, so it silently defaults to the slug → every KG-backed scene activation fails before touching data.

2. **No persona NPC exists in the KG.** `KgProjection.create()` already writes an entity + `LOCATED_IN` edge, but nothing seeds a persona NPC through the `EventSourcedStateRepository`; `persona_seed.py` deliberately no-ops on KG repos. Without a seeded `kind=="character"` NPC, `SceneCoordinator._has_persona_npcs` finds nothing and no scene ever activates.

3. **No UI surfacing of the persona NPC.** When a scene opens, the client never learns an NPC is present. The `npc_joined` WS event is fully handled client-side (`message-handler.ts`) but is only emitted by the Matrix bridge — never by the persona path.

Plus a robustness gap P2 left open: scenes only close on the **action path** (a player submitting a move). A player who closes the tab leaves the scene registered forever.

**Goal:** With the KG stack up and a flag set, a player at the seeded location sends a message, a persona scene auto-activates against graph-memory (correct bonfire ObjectId), the NPC replies, and the NPC appears in the client's NPC panel; when the player disconnects, the now-empty scene closes. No persona path ever 500s `/api/action`; the existing `RoundManager`/Matrix path stays the untouched default.

**Architecture:** (1) Resolve the world bonfire id **once** from the `BONFIRE_ID` env (the same value the SDK already uses), thread it through every wire path, slug only as the local fallback. (2) A gated `provision_kg_personas` helper seeds a location + persona NPC through the `EventSourcedStateRepository` (so `KgProjection.create()` writes the KG entity + `LOCATED_IN`) and primes the app-scoped resolver cache with name→engine-uuid. (3) `SceneCoordinator` emits `npc_joined` over the existing WS path on **fresh** scene activation. (4) The WS-disconnect handler drives `SceneCoordinator.maybe_close` for the departed location.

**Tech Stack:** Python 3.12 (memento-mori gateway + engine), FastAPI/Starlette, httpx. Tests: `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest <path> -q`.

## Branch & base

- **mmori branch:** `persona/ui-provisioning`, off `opening/engine-core` (HEAD `53cef2a`, which carries P1+P2).
- Use an **isolated worktree**: `git worktree add -b persona/ui-provisioning <scratchpad>/mmori-prov-wt opening/engine-core`. Work from the worktree; read files from it (the main checkout is on `ui/typewriter-kg-map` — wrong-tree trap).
- Merge on completion via the arc's clean fast-forward pattern: `git branch -f opening/engine-core persona/ui-provisioning` (branches are off its tip). Never check out `opening/engine-core` in the main tree.

## Global Constraints

- Commit trailer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Never `git add -A`** — stage only the files each task touches. PR (if any) targets this lineage's base (`opening/engine-core`), never main.
- No cross-service Python imports (plain dicts on the wire). No `Any` in new signatures **except** the `repo`/`state`/`scene_registry`/`ws_hub`/`activation_service`/cache app-state-namespace params (Protocol/app-state convention, matching existing `RoomDriver(repo: Any)` / `SceneCoordinator(... : Any)`).
- Services raise **domain exceptions, not `HTTPException`** — and **a persona/provisioning failure must never break the action path or crash gateway startup** (degrade to a logged no-op).
- **The bonfire id is one resolved value, from one resolver.** The resolved value is `os.environ.get("BONFIRE_ID") or "mm-world-v1"`; the slug `"mm-world-v1"` is the **local fallback only**. Thread it; do not re-introduce the literal at any wire site.
- UUIDs for entity/scene identity; the location **name** is only a `ws_hub` broadcast key and a resolver cache key.
- `os.environ` reads are allowed in the **gateway** (existing `mcp_server._build_cxn_repo()` / `routes/codex.py` pattern). Keep env reads in the gateway; thread the resolved id into engine objects via their existing `bonfire_id=` params (do not scatter env reads into `engine/`).
- The KG seed is **opt-in (flag-gated)** and writes the **intended game NPC** (not a test entity); it must be a logged no-op on the in-memory repo and wrapped so a KG outage at boot does not crash startup.
- Ruff-format only the files each task touches (the base isn't ruff-clean).

## Key existing symbols (reuse, don't reinvent) — verbatim anchors on `opening/engine-core` @ `53cef2a`

- **`BONFIRE_ID`** — `gateway/src/gateway/routes/opening.py:68` = `"mm-world-v1"`. `opening.py` already `import os` (line 46). Imported by `scene_activation.py:10`.
- **`SceneActivationService`** — `gateway/src/gateway/scene_activation.py`. Ctor `(*, repo, agent_runtime_client, scene_registry, bonfire_id=BONFIRE_ID)` stores `self._bonfire_id`; `_build_driver` passes it to `RoomDriver(bonfire_id=self._bonfire_id)`. **`from_app_state(state)` (lines 51-56) omits `bonfire_id`** → always defaults to the slug. This is the threading hole.
- **`build_mcp_app`** — `gateway/src/gateway/mcp_server.py` (~1240-1340). Already `import os` inside. Constructs: `register_cxn_tools(mcp, ws_hub, cxn_repo, cxn_mirror, memory)` (no bonfire_id); `HttpComprehensionClient()` (no bonfire_id → default); `register_mm_act(mcp, ws_hub, cxn_repo, cxn_mirror, memory, comprehension)` (no bonfire_id → default).
- **`register_cxn_tools`** — `gateway/src/gateway/cxn_tools.py:59-65`, builds `executor = EffectExecutor(repo=repo, memory=memory, chain=mirror)` at line 81 (→ `DEFAULT_BONFIRE_ID`), `return executor` at 163. **No `bonfire_id` param today.**
- **`register_mm_act`** — `gateway/src/gateway/cxn_tools.py:167`, already has `bonfire_id: str = "mm-world-v1"` (line 173) and threads it into its own `EffectExecutor(...)`.
- **`EffectExecutor`** — `engine/src/memento/cxn/executor.py`, ctor `(repo, memory, chain, bonfire_id=DEFAULT_BONFIRE_ID)` (`DEFAULT_BONFIRE_ID="mm-world-v1"` at line 52), stamps `self._bonfire_id` onto every `EpisodeIn` (→ `KernelMemoryClient` ingest URL).
- **`HttpComprehensionClient`** — `engine/src/memento/cxn/kernel_client.py`, ctor `(base_url=None, token=None, bonfire_id="mm-world-v1", client=None)` → builds `…/v1/bonfires/{bonfire_id}/kernel/comprehend`.
- **`app.py` lifespan** — `gateway/src/gateway/app.py`. Already `import os`. Sets (in order) `app.state.cxn_repo`, `app.state.cxn_executor`, `app.state.agent_runtime_client`, `app.state.scene_registry = {}`, `app.state.scene_locations = {}`, then `if os.environ.get("PERSONA_LOCAL_SEED"): await seed_local_personas(app.state.cxn_repo, app.state.scene_locations)`. Module global `app` is defined after the lifespan; `_seed_ontology()` shows the non-fatal `try/except` boot pattern.
- **`persona_seed.py`** — `gateway/src/gateway/persona_seed.py`. `seed_local_personas(repo, cache) -> bool` guards `if not isinstance(repo, InMemoryStateRepository): return False`; `_location_doc()`/`_npc_doc()` return the canonical docs (NPC: `kind:"character"`, `labels:["Character","NPC","Guard"]`). `InMemoryStateRepository.seed_entity` is **sync**.
- **`EventSourcedStateRepository`** — `engine/src/memento/state/event_sourced.py`, ctor `(tx_log, activation_log, projection, chain)`. **`seed_entity` is async** and flows through `projection.create()` → KG entity + `LOCATED_IN`. `get_entities_at_location(loc)` delegates to the projection. Built by `mcp_server._build_cxn_repo()` when `KERNEL_BASE_URL`+`GM_INTERNAL_TOKEN` are set (else `InMemoryStateRepository`).
- **Test substrate (no live KG):** `KgProjectionFake` (`engine/src/memento/state/kg_projection.py`, honours `doc["uuid"]`), `InMemoryTxLog`/`InMemoryActivationLog` (`engine/src/memento/state/tx_log.py`), `NoopChainMirror` (`engine/src/memento/state/chain_mirror.py`). `EventSourcedStateRepository(InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror())` is a fully in-memory EventSourced repo.
- **`SceneCoordinator`** — `gateway/src/gateway/scene_coordinator.py`. `ensure_scene(location_uuid)` (idempotent; returns the live driver or None); `handle_player_message(player_id, location_name, message)` resolves via `self._resolver`, records name↔uuid, calls `ensure_scene`, drives + broadcasts `mcp` `tool_event/mm_npc_response`; `maybe_close(name)`; `_has_persona_npcs` (`kind=="character"`). Has `self._ws_hub`, `self._repo`, `self._registry`.
- **`WebSocketHub`** — `gateway/src/gateway/ws.py`. `disconnect(player_id)` reads `location = self.player_locations.get(player_id, "")` **before** popping, then broadcasts `player_left`. `players_at_location(name) -> int` (accurate after the pop). `broadcast_to_location(name, msg)`.
- **WS endpoint** — `gateway/src/gateway/app.py` (~205-220): `websocket_endpoint` — `WebSocketDisconnect` and generic `except` both call `await ws_hub.disconnect(player_id)`. Uses the module global `ws_hub`; the module global `app` (and thus `app.state`) is in scope.
- **`npc_joined` (client, already wired)** — `client/src/types/ws-messages.ts` `NpcJoinedMessage {type:'npc_joined'; npc_name; npc_id?}`; handler `client/src/message-handler.ts` `case 'npc_joined'` dedups by name, pushes `{name,id,role:''}` into `gameState.location.npcs`, re-renders. Sole server emitter today: `gateway/src/gateway/matrix_bridge.py` (`ensure_npcs_in_room`). **No client change needed.**
- **`room_manifest` NPC labels** — `engine/src/memento/room_manifest.py:21` `NPC_LABELS` includes `"NPC"`, `"Guard"`, etc. (the seed NPC's labels satisfy this for any later codex surfacing — not required for P3, see Out of scope).

---

# Movement 1 — gateway: one resolved bonfire id, threaded

## Task 1 — resolve the bonfire id from env and thread it through every wire path

**Files:**
- Create: `gateway/src/gateway/world_identity.py`
- Modify: `gateway/src/gateway/routes/opening.py` (BONFIRE_ID), `gateway/src/gateway/scene_activation.py` (`from_app_state`), `gateway/src/gateway/app.py` (lifespan: set `app.state.bonfire_id`), `gateway/src/gateway/mcp_server.py` (`build_mcp_app`: resolve + thread), `gateway/src/gateway/cxn_tools.py` (`register_cxn_tools`: accept + thread `bonfire_id`)
- Test: `gateway/tests/test_world_identity.py` (new), `gateway/tests/test_bonfire_id_threading.py` (new)

**Interfaces:**
- Produces: `resolve_bonfire_id() -> str` (env `BONFIRE_ID` else `"mm-world-v1"`). `app.state.bonfire_id` (resolved). `SceneActivationService.from_app_state` now threads `state.bonfire_id`. `register_cxn_tools(..., bonfire_id=DEFAULT_BONFIRE_ID)` new trailing kwarg. Consumed by Tasks 2-4 only indirectly (they rely on the threaded id being correct in a KG deployment).

- [ ] **Step 1 — write the resolver** (`gateway/src/gateway/world_identity.py`):
```python
"""Single source of truth for the world's bonfire id.

graph-memory coerces the {bonfire_id} URL path param to a Mongo ObjectId and
404s anything that isn't one. The SDK already reads BONFIRE_ID (the ObjectId)
from the environment for every client.kg.* call; the scene / cxn / comprehend /
memory paths historically hardcoded the slug "mm-world-v1" and so never agreed
with the KG. This resolver makes them agree: read BONFIRE_ID from the env (the
same value the SDK uses), falling back to the slug only for local / no-KG play.
"""

from __future__ import annotations

import os

_SLUG_FALLBACK = "mm-world-v1"


def resolve_bonfire_id() -> str:
    return os.environ.get("BONFIRE_ID") or _SLUG_FALLBACK
```

- [ ] **Step 2 — failing tests** (`gateway/tests/test_world_identity.py`):
```python
from gateway.world_identity import resolve_bonfire_id


def test_resolve_prefers_env(monkeypatch):
    monkeypatch.setenv("BONFIRE_ID", "6650000000000000000000f1")
    assert resolve_bonfire_id() == "6650000000000000000000f1"


def test_resolve_falls_back_to_slug(monkeypatch):
    monkeypatch.delenv("BONFIRE_ID", raising=False)
    assert resolve_bonfire_id() == "mm-world-v1"


def test_resolve_falls_back_when_env_blank(monkeypatch):
    monkeypatch.setenv("BONFIRE_ID", "")
    assert resolve_bonfire_id() == "mm-world-v1"
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_world_identity.py -q` → 3 passed.

- [ ] **Step 4 — wire `routes/opening.py`.** Replace the literal at line 68 so the module-level default also honours the env:
```python
from gateway.world_identity import resolve_bonfire_id  # add near the other gateway imports

BONFIRE_ID = resolve_bonfire_id()
```

- [ ] **Step 5 — set `app.state.bonfire_id` in the lifespan** (`gateway/src/gateway/app.py`). Immediately after `app.state.scene_registry = {}` / `app.state.scene_locations = {}` (before the `PERSONA_LOCAL_SEED` block), add:
```python
    from gateway.world_identity import resolve_bonfire_id

    app.state.bonfire_id = resolve_bonfire_id()
```

- [ ] **Step 6 — thread it in `SceneActivationService.from_app_state`** (`gateway/src/gateway/scene_activation.py`). The classmethod becomes:
```python
    @classmethod
    def from_app_state(cls, state: Any) -> "SceneActivationService":
        return cls(
            repo=state.cxn_repo,
            agent_runtime_client=state.agent_runtime_client,
            scene_registry=state.scene_registry,
            bonfire_id=getattr(state, "bonfire_id", BONFIRE_ID),
        )
```
  *(`BONFIRE_ID` is already imported at the top of this module.)*

- [ ] **Step 7 — add `bonfire_id` to `register_cxn_tools`** (`gateway/src/gateway/cxn_tools.py`). Import the engine default and add the trailing kwarg + thread it into the executor. The signature (lines 59-65) becomes:
```python
from memento.cxn.executor import DEFAULT_BONFIRE_ID, EffectExecutor  # extend the existing import

def register_cxn_tools(
    mcp: "FastMCP",
    ws_hub: "WebSocketHub | None",
    repo: "StateRepository",
    mirror: "ChainMirror",
    memory: "MemoryClient",
    bonfire_id: str = DEFAULT_BONFIRE_ID,
) -> "EffectExecutor":
```
  And the executor construction (line 81) becomes:
```python
    executor = EffectExecutor(repo=repo, memory=memory, chain=mirror, bonfire_id=bonfire_id)
```
  *(`register_cxn_tools` has exactly one caller — `build_mcp_app` — updated in Step 8. The kwarg is defaulted, so the change is backward-compatible.)*

- [ ] **Step 8 — resolve once and thread in `build_mcp_app`** (`gateway/src/gateway/mcp_server.py`). `import os` is already present inside the function; add the resolve and pass it to the three construction sites:
```python
    from gateway.world_identity import resolve_bonfire_id

    bonfire_id = resolve_bonfire_id()
    ...
    cxn_executor = register_cxn_tools(
        mcp,
        ws_hub,
        cxn_repo,
        cxn_mirror,
        memory,
        bonfire_id=bonfire_id,
    )
    ...
    comprehension = HttpComprehensionClient(bonfire_id=bonfire_id)  # the KERNEL/GM branch only
    ...
    register_mm_act(
        mcp,
        ws_hub,
        cxn_repo,
        cxn_mirror,
        memory,
        comprehension,
        bonfire_id=bonfire_id,
    )
```
  *(Only the `HttpComprehensionClient(...)` inside the `if KERNEL_BASE_URL and GM_INTERNAL_TOKEN:` branch gains the kwarg; `NullComprehensionClient()` is unchanged. The engine literals in `executor.py`/`kernel_client.py` stay as local fallback defaults — they are now always overridden by these threaded values.)*

- [ ] **Step 9 — failing tests** (`gateway/tests/test_bonfire_id_threading.py`):
```python
import pytest

from gateway.scene_activation import SceneActivationService


class _State:
    def __init__(self, bonfire_id=None):
        self.cxn_repo = object()
        self.agent_runtime_client = object()
        self.scene_registry = {}
        if bonfire_id is not None:
            self.bonfire_id = bonfire_id


def test_from_app_state_threads_bonfire_id():
    svc = SceneActivationService.from_app_state(_State(bonfire_id="6650000000000000000000f1"))
    assert svc._bonfire_id == "6650000000000000000000f1"


def test_from_app_state_falls_back_to_slug_when_absent():
    svc = SceneActivationService.from_app_state(_State())  # no bonfire_id attr
    assert svc._bonfire_id == "mm-world-v1"


def test_register_cxn_tools_threads_bonfire_id_into_executor():
    from fastmcp import FastMCP

    from gateway.cxn_tools import register_cxn_tools
    from memento.memory.null_client import NullMemoryClient
    from memento.state.chain_mirror import NoopChainMirror
    from memento.state.in_memory import InMemoryStateRepository

    executor = register_cxn_tools(
        FastMCP("t"), None, InMemoryStateRepository(), NoopChainMirror(),
        NullMemoryClient(), bonfire_id="6650000000000000000000f1",
    )
    assert executor._bonfire_id == "6650000000000000000000f1"
```
  *(If `FastMCP`'s import path differs, match the import used at the top of `mcp_server.py` / `cxn_tools.py`. The third test exercises the real `register_cxn_tools` against in-memory ports — no KG.)*

- [ ] **Step 10 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_bonfire_id_threading.py -q` → 3 passed.

- [ ] **Step 11 — regression smoke** (the threading must not break app boot or the cxn tools): `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_activation_route.py gateway/tests/test_action_persona_branch.py -q` → green.

- [ ] **Step 12 — commit** (stage `world_identity.py`, `routes/opening.py`, `scene_activation.py`, `app.py`, `mcp_server.py`, `cxn_tools.py`, both new tests) — `feat(gateway): resolve world bonfire id from env and thread it through every wire path`.

---

# Movement 2 — gateway: provision a persona NPC into the KG

## Task 2 — `provision_kg_personas` (gated EventSourced seed)

**Files:**
- Modify: `gateway/src/gateway/persona_seed.py` (add the KG-branch helper, reusing `_location_doc`/`_npc_doc`)
- Modify: `gateway/src/gateway/app.py` (lifespan: gated, non-fatal call)
- Test: `gateway/tests/test_persona_kg_seed.py` (new)

**Interfaces:**
- Consumes: `EventSourcedStateRepository.seed_entity` (async, writes KG entity + `LOCATED_IN`), the canonical `_location_doc()`/`_npc_doc()` (Task is additive — they already exist).
- Produces: `async provision_kg_personas(repo, cache) -> bool` — seeds the location then the NPC through the EventSourced repo and primes `cache[name] = location_engine_uuid`; returns True if it seeded, False (no-op) for a non-EventSourced repo. Lifespan calls it behind `PERSONA_KG_SEED`, wrapped non-fatal.

- [ ] **Step 1 — add the helper** to `gateway/src/gateway/persona_seed.py` (append below `seed_local_personas`; reuse the existing `_location_doc`/`_npc_doc`/`_LOC_UUID`/`_LOC_NAME`):
```python
async def provision_kg_personas(repo: Any, cache: Any) -> bool:
    """Seed the persona location + NPC into a KG-backed (EventSourced) repo so a
    real deployment has a reachable persona scene. Each seed flows through
    KgProjection.create() -> a KG entity + a LOCATED_IN edge. No-op (returns
    False) on the in-memory repo (that path uses seed_local_personas).

    Order matters: the location is seeded first so its engine->kg uuid is mapped
    before the NPC's LOCATED_IN edge resolves. The name->engine-uuid cache entry
    lets LocationResolver resolve the location without a KG search, keeping the
    cxn path on the engine-uuid identity the EventSourced repo expects.
    """
    from memento.state.event_sourced import EventSourcedStateRepository

    if not isinstance(repo, EventSourcedStateRepository):
        return False  # in-memory play uses seed_local_personas
    await repo.seed_entity(_location_doc())  # EventSourcedStateRepository.seed_entity is async
    await repo.seed_entity(_npc_doc())
    if cache is not None:
        cache[_LOC_NAME] = _LOC_UUID  # resolve without a KG search -> engine-uuid identity
    logger.info("provisioned KG persona NPC %s at %s", _NPC_UUID, _LOC_NAME)
    return True
```

- [ ] **Step 2 — wire the lifespan** (`gateway/src/gateway/app.py`). Immediately after the existing `PERSONA_LOCAL_SEED` block, add the gated, non-fatal KG seed:
```python
    if os.environ.get("PERSONA_KG_SEED"):
        from gateway.persona_seed import provision_kg_personas

        try:
            await provision_kg_personas(app.state.cxn_repo, app.state.scene_locations)
        except Exception:
            logger.warning("KG persona provisioning failed (non-fatal)", exc_info=True)
```
  *(Non-fatal: a graph-memory outage at boot must not crash gateway startup — mirrors the `_seed_ontology()` try/except boot pattern.)*

- [ ] **Step 3 — failing tests** (`gateway/tests/test_persona_kg_seed.py`) — a real EventSourced repo backed by the in-memory fake projection (no live KG):
```python
import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

from gateway.persona_seed import provision_kg_personas, _LOC_UUID, _LOC_NAME, _NPC_UUID


def _event_sourced_repo():
    return EventSourcedStateRepository(
        InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror()
    )


@pytest.mark.asyncio
async def test_provisions_kg_repo_with_located_npc_and_cache():
    repo = _event_sourced_repo()
    cache: dict[str, str] = {}
    seeded = await provision_kg_personas(repo, cache)
    assert seeded is True
    entities = await repo.get_entities_at_location(_LOC_UUID)
    npc = next((e for e in entities if e.get("kind") == "character"), None)
    assert npc is not None and npc["uuid"] == _NPC_UUID   # LOCATED_IN resolved
    assert "NPC" in npc["labels"]                          # satisfies room_manifest too
    assert cache[_LOC_NAME] == _LOC_UUID                   # resolvable without a KG search


@pytest.mark.asyncio
async def test_noop_for_in_memory_repo():
    cache: dict[str, str] = {}
    assert await provision_kg_personas(InMemoryStateRepository(), cache) is False
    assert cache == {}
```

- [ ] **Step 4 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_kg_seed.py -q` → 2 passed. *(If `KgProjectionFake` does not return `kind`/`labels` round-tripped on `get_entities_at_location`, inspect `_from_kg_entity` in `kg_projection.py` and assert on the fields it does reconstruct — `uuid` + `kind` are the load-bearing ones; adjust the `labels` assertion to match the fake's round-trip.)*

- [ ] **Step 5 — regression smoke** (lifespan still boots; the local-seed path is untouched): `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_persona_seed.py gateway/tests/test_scene_activation_route.py -q` → green.

- [ ] **Step 6 — commit** (stage `persona_seed.py` + `app.py` + the new test) — `feat(gateway): provision a persona NPC into the KG via the EventSourced repo (gated)`.

---

# Movement 3 — gateway: surface the persona NPC in the UI

## Task 3 — emit `npc_joined` on fresh scene activation

**Files:**
- Modify: `gateway/src/gateway/scene_coordinator.py` (`handle_player_message` emits `npc_joined` on fresh activation; new private `_broadcast_npcs_joined`)
- Test: `gateway/tests/test_scene_npc_joined.py` (new)

**Interfaces:**
- Consumes: `self._repo.get_entities_at_location`, `self._ws_hub.broadcast_to_location`, the existing client `npc_joined` handler (no client change).
- Produces: on the **first** activation of a scene (registry miss → driver), `handle_player_message` broadcasts one `npc_joined` per `kind=="character"` NPC to the location name. Idempotent across subsequent messages (no re-emit while the scene stays registered).

- [ ] **Step 1 — edit `handle_player_message`** in `gateway/src/gateway/scene_coordinator.py`. Capture whether the scene was already registered *before* `ensure_scene`, and emit after a fresh activation. The region around `ensure_scene` becomes:
```python
        self._resolver.record(location_name, location_uuid)  # for maybe_close
        was_registered = location_uuid in self._registry
        driver = await self.ensure_scene(location_uuid)
        if driver is None:
            return False
        if not was_registered:  # scene just opened -> surface its NPCs once
            await self._broadcast_npcs_joined(location_uuid, location_name)
```
  *(Everything from `try: turn = await driver.drive_turn(...)` onward is unchanged.)*

- [ ] **Step 2 — add the private emitter** (place beside `_has_persona_npcs`):
```python
    async def _broadcast_npcs_joined(self, location_uuid: str, location_name: str) -> None:
        if self._ws_hub is None or self._repo is None:
            return
        try:
            entities = await self._repo.get_entities_at_location(location_uuid)
        except Exception:  # surfacing is best-effort, never breaks the turn
            return
        for entity in entities:
            if entity.get("kind") != "character":
                continue
            await self._ws_hub.broadcast_to_location(
                location_name,
                {
                    "type": "npc_joined",
                    "npc_name": entity.get("name", ""),
                    "npc_id": entity.get("uuid", ""),
                },
            )
```

- [ ] **Step 3 — failing tests** (`gateway/tests/test_scene_npc_joined.py`) — reuse the P2-style fakes; assert `npc_joined` fires once on first message and not on the second:
```python
import pytest

from gateway.location_resolver import LocationResolver
from gateway.scene_coordinator import SceneCoordinator


class _FakeDriver:
    async def drive_turn(self, loc, msg, *, addressed_name=None):
        return {"response_text": "Halt!", "should_respond": True, "self_id": "npc-1"}


class _FakeRepo:
    def __init__(self, entities): self._entities = entities
    async def get_entities_at_location(self, loc): return self._entities.get(loc, [])
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gareth"} if uuid == "npc-1" else None


class _FakeActivation:
    def __init__(self, registry, driver): self._registry, self._driver = registry, driver
    async def activate(self, loc): self._registry[loc] = self._driver; return {"scene_id": loc}


class _FakeHub:
    def __init__(self): self.broadcasts = []
    async def broadcast_to_location(self, loc, msg): self.broadcasts.append((loc, msg))


def _coord(registry, repo, act, hub, cache):
    return SceneCoordinator(
        scene_registry=registry, cxn_repo=repo, ws_hub=hub,
        activation_service=act, location_resolver=LocationResolver(repo, cache),
    )


@pytest.mark.asyncio
async def test_npc_joined_emitted_once_on_fresh_activation():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "npc-1", "kind": "character", "name": "Gareth"}]})
    hub = _FakeHub()
    coord = _coord(registry, repo, _FakeActivation(registry, _FakeDriver()), hub, {"Gate": "loc-1"})

    await coord.handle_player_message("p1", "Gate", "hi")
    joined = [m for _, m in hub.broadcasts if m["type"] == "npc_joined"]
    assert len(joined) == 1
    assert joined[0]["npc_name"] == "Gareth" and joined[0]["npc_id"] == "npc-1"

    # Second message: scene already registered -> no re-emit.
    hub.broadcasts.clear()
    await coord.handle_player_message("p1", "Gate", "still here?")
    assert [m for _, m in hub.broadcasts if m["type"] == "npc_joined"] == []


@pytest.mark.asyncio
async def test_no_npc_joined_when_no_scene_activates():
    registry = {}
    repo = _FakeRepo({"loc-1": [{"uuid": "x", "kind": "location"}]})  # no character
    hub = _FakeHub()
    coord = _coord(registry, repo, _FakeActivation(registry, _FakeDriver()), hub, {"Gate": "loc-1"})
    assert await coord.handle_player_message("p1", "Gate", "hi") is False
    assert [m for _, m in hub.broadcasts if m["type"] == "npc_joined"] == []
```

- [ ] **Step 4 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_npc_joined.py -q` → 2 passed.

- [ ] **Step 5 — P2/P1 regression:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_coordinator_reachability.py gateway/tests/test_scene_coordinator.py gateway/tests/test_action_persona_branch.py -q` → green. *(The `mm_npc_response` broadcast assertions still hold — `npc_joined` is an additional message, not a replacement; tests that count only `mm_npc_response` are unaffected, but if any test asserts an exact total broadcast count it must be updated to expect the extra `npc_joined`.)*

- [ ] **Step 6 — commit** (stage `scene_coordinator.py` + the new test) — `feat(gateway): broadcast npc_joined when a persona scene first activates`.

---

# Movement 4 — gateway: close scenes on disconnect

## Task 4 — drive `maybe_close` from the WS-disconnect path

**Files:**
- Modify: `gateway/src/gateway/app.py` (WS endpoint: capture departed location, call `maybe_close` after disconnect)
- Test: `gateway/tests/test_scene_close_on_disconnect.py` (new)

**Interfaces:**
- Consumes: `ws_hub.player_locations` (read the departed name before disconnect pops it), `ws_hub.disconnect`, `SceneCoordinator.from_app_state(app.state).maybe_close(name)` (resolves uuid from the app-scoped cache; no-ops if no scene / players remain / no activation service).
- Produces: a `_evict_scene_on_disconnect(player_id)` module-level helper used by both `websocket_endpoint` disconnect branches.

- [ ] **Step 1 — add the helper + use it** in `gateway/src/gateway/app.py`. Add the helper just above `websocket_endpoint`:
```python
async def _evict_scene_on_disconnect(player_id: str) -> None:
    """On WS disconnect, close the player's scene if they were the last one there.
    Best-effort: never raises into the WS teardown path."""
    if ws_hub is None:
        return
    departed = ws_hub.player_locations.get(player_id, "")  # read before disconnect pops it
    await ws_hub.disconnect(player_id)
    if not departed:
        return
    try:
        from gateway.scene_coordinator import SceneCoordinator

        coordinator = SceneCoordinator.from_app_state(app.state)
        await coordinator.maybe_close(departed)
    except Exception:
        logger.warning("scene eviction on disconnect failed for %s", player_id, exc_info=True)
```
  Then replace **both** `await ws_hub.disconnect(player_id)` calls in `websocket_endpoint` with `await _evict_scene_on_disconnect(player_id)`:
```python
    await ws_hub.connect(player_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await _evict_scene_on_disconnect(player_id)
    except Exception:
        logger.warning(
            "WebSocket error for %s, disconnecting", player_id, exc_info=True
        )
        await _evict_scene_on_disconnect(player_id)
```
  *(`maybe_close` already guards `players_at_location > 0` — and `disconnect` has already removed this player from the count — so the scene closes only when truly empty. In local/no-KG, `from_app_state` builds no activation service → `maybe_close` no-ops. The name→uuid is in `app.state.scene_locations` because `handle_player_message` recorded it during the player's earlier actions; an uncached name no-ops safely.)*

- [ ] **Step 2 — failing test** (`gateway/tests/test_scene_close_on_disconnect.py`) — unit-test the helper with a monkeypatched app.state, asserting the departed location is read pre-disconnect and `maybe_close` is invoked with it:
```python
import pytest

import gateway.app as gw_app


class _Hub:
    def __init__(self):
        self.player_locations = {"p1": "Gate"}
        self.disconnected = []
    async def disconnect(self, pid):
        self.disconnected.append(pid)
        self.player_locations.pop(pid, None)


class _Coord:
    closed: list[str] = []
    async def maybe_close(self, name): type(self).closed.append(name)


@pytest.mark.asyncio
async def test_disconnect_closes_departed_scene(monkeypatch):
    hub = _Hub()
    monkeypatch.setattr(gw_app, "ws_hub", hub)
    _Coord.closed = []
    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state",
        classmethod(lambda cls, state: _Coord()),
    )
    await gw_app._evict_scene_on_disconnect("p1")
    assert hub.disconnected == ["p1"]      # still disconnects
    assert _Coord.closed == ["Gate"]       # closes the location the player left


@pytest.mark.asyncio
async def test_disconnect_without_location_is_safe(monkeypatch):
    hub = _Hub(); hub.player_locations = {}
    monkeypatch.setattr(gw_app, "ws_hub", hub)
    _Coord.closed = []
    await gw_app._evict_scene_on_disconnect("p1")
    assert hub.disconnected == ["p1"]
    assert _Coord.closed == []             # nothing to close


@pytest.mark.asyncio
async def test_eviction_failure_never_raises(monkeypatch):
    hub = _Hub()
    monkeypatch.setattr(gw_app, "ws_hub", hub)
    def _boom(cls, state): raise RuntimeError("down")
    monkeypatch.setattr(
        "gateway.scene_coordinator.SceneCoordinator.from_app_state", classmethod(_boom)
    )
    await gw_app._evict_scene_on_disconnect("p1")  # must not raise
    assert hub.disconnected == ["p1"]              # disconnect still happened
```

- [ ] **Step 3 — run, verify pass:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests/test_scene_close_on_disconnect.py -q` → 3 passed.

- [ ] **Step 4 — regression smoke:** `PYTHONPATH=engine/src:gateway/src python3.12 -m pytest gateway/tests -q` → green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix` (confirm it's the only failure and unchanged).

- [ ] **Step 5 — commit** (stage `app.py` + the new test) — `feat(gateway): close an empty persona scene when its last player disconnects`.

---

## Verification (end-to-end)

1. **Bonfire id (Task 1):** `resolve_bonfire_id` prefers env, falls back to slug; `SceneActivationService.from_app_state` threads `state.bonfire_id`; `register_cxn_tools` threads it into the executor. 6 tests + app-boot/cxn smoke. The slug literal no longer reaches any KG wire path when `BONFIRE_ID` is set.
2. **KG provisioning (Task 2):** `provision_kg_personas` seeds location+NPC through a real `EventSourcedStateRepository` (fake projection), the NPC is retrievable via its `LOCATED_IN` edge, the cache is primed, and it no-ops on the in-memory repo. 2 tests + lifespan smoke.
3. **UI surfacing (Task 3):** `npc_joined` fires exactly once on fresh activation (per `kind=="character"` NPC), not on subsequent messages, and not when no scene activates; `mm_npc_response` is unaffected. 2 tests + P1/P2 regression.
4. **Disconnect eviction (Task 4):** `_evict_scene_on_disconnect` reads the departed location before disconnect, disconnects, and drives `maybe_close`; safe with no location; never raises. 3 tests + full-suite smoke.
5. **No regression:** the full gateway suite is green except the pre-existing unrelated `test_round_callback.py::test_send_batch_to_matrix`.
6. **Whole-branch opus review:** the branch is additive — the bonfire id is one resolved value from one resolver (no re-introduced literal at any wire site); the KG seed is opt-in, non-fatal, and a no-op on the in-memory repo; `npc_joined` reuses the existing client path with no client change; disconnect eviction degrades to a logged no-op and the existing `RoundManager`/Matrix path is untouched; a persona/provisioning failure never 500s `/api/action` or crashes startup; no `Any` beyond the app-state-namespace conventions.
7. **Live demo (manual, bring-up):** with the KG stack up, `BONFIRE_ID=<real ObjectId>` and `PERSONA_KG_SEED=1` set, boot the gateway against the running agent-runtime; at the seeded location send `/api/action {location:"The Threshold", action:"Gareth, may I pass?"}` → the scene auto-activates against graph-memory (correct bonfire id), the NPC reply renders, and the NPC appears in the client's NPC panel (the `npc_joined`); then close the tab and confirm the scene closes.

## Out of scope (P4 / later)

- **Multi-NPC who-acts** — `RoomDriver._resolve_actor_uuid` already does addressed-name matching, but `handle_player_message` calls `drive_turn` without `addressed_name`, and `_last_roster_uuids` is an unordered `set` (arbitrary single-NPC pick). Threading the addressed name + an ordered roster is P4.
- **TTL / background scene eviction** — the gateway has no periodic sweeper. A player who neither moves nor disconnects keeps a scene registered. Needs `opened_at`/`last_activity` on registry entries + a lifespan asyncio sweep task. Deferred.
- **`npc_left` surfacing** — P3's only close paths (last-player-leaves, last-player-disconnects) fire when the location is **empty**, so a `broadcast_to_location(name, npc_left)` would have **no recipients** (the departing client has already swapped to its new room's panel). Emitting it would be dead code. `npc_left` belongs with **TTL eviction** (close-while-players-present), so it ships in P4 alongside the sweeper.
- **Codex / `room_manifest` surfacing of the persona NPC** — the codex reads the legacy world identity (`world.json` threshold uuid + KG search by name), a different uuid than the cxn/projection engine uuid. Reconciling those so the persona NPC also appears in the codex browser (not just the live NPC panel) is a separate provisioning concern. The seed NPC's labels (`["Character","NPC","Guard"]`) already satisfy `room_manifest.NPC_LABELS` for when that reconciliation lands.
- **Bonfire document creation** — P3 resolves the bonfire **id** from env; it does not create the graph-memory `Bonfire` document. First-time provisioning (an operator setting `BONFIRE_ID` to a real ObjectId, or a one-shot `upsert_by_name` script) is an ops step, not gateway-boot code.
- **Idempotency across restarts** — `provision_kg_personas` is opt-in and creates a fresh NPC each boot (a per-process `KgProjection` has no cross-restart memory; `KgProjection.create` does not dedup). For the controlled bring-up, set `PERSONA_KG_SEED` once. World.json-style caching to make it restart-idempotent is a follow-up.
- **The standing "one PR"** promoting the whole persona stack (P1+P2+P3) to mmori `canon` / bonfires-ai-core `main` — still all on feature branches.

## On approval

Execute via superpowers:subagent-driven-development on a worktree branch `persona/ui-provisioning` off `opening/engine-core` (`53cef2a`), T1→T4. Copy this plan to `memento-mori/docs/superpowers/plans/2026-06-26-persona-ui-provisioning.md` and commit (in the worktree) before dispatching Task 1.
