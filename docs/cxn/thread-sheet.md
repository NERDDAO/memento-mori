# cxn Thread / Ownership Sheet

Back to: [docs/START-HERE.md](../START-HERE.md)

This is the page a lead walks the team through. One card per thread — each dev knows
exactly which component is theirs, what to stub first, and where to start reading.

Cards map to spec §8.1 (five Day-1 components) plus C5/Milestone-2 Comprehension and
Track C (graph-memory comprehend route). Reuse pointers link into
[docs/cxn/reuse-inventory.md](reuse-inventory.md).

---

## C1 — StateRepository

**Owner:** TBD (Dev A)

**Files:**
- `engine/src/memento/state/` (new directory)
  - `repository.py` — `StateRepository` Protocol
  - `in_memory.py` — `InMemoryStateRepository` (Day-1 default, no external deps)
  - `mongo_repository.py` — `MongoStateRepository` (stretch; `motor` + replica set)

**Depends on:** `engine/src/memento/cxn/types.py` (must land first — shared DTOs)

**Stub:**
```python
class InMemoryStateRepository:
    """Full CRUD over an in-process dict. The wired Day-1 default."""
    async def set_attr(self, entity_uuid: str, attr: str, value: Any) -> StateDelta: ...
    async def move_entity(self, entity_uuid: str, to_room_uuid: str) -> StateDelta: ...
    async def transfer_item(self, item_uuid: str, from_uuid: str, to_uuid: str,
                            to_location_uuid: str | None = None) -> StateDelta: ...
    async def link(self, source_uuid: str, rel: str, target_uuid: str) -> StateDelta: ...
    async def unlink(self, source_uuid: str, rel: str, target_uuid: str) -> StateDelta: ...
    async def get_actor_snapshot(self, entity_uuid: str) -> dict[str, Any]: ...
```

**Acceptance test (Day 1):**
- One unit test per write method asserting exact before/after field values
  against `InMemoryStateRepository`.
- `schema_version=1` on every returned `StateUpdate` — no new fields added.
- `mongomock-motor` may NOT be used for transactional assertions (it does not
  support transactions); use `InMemoryStateRepository` or a real Mongo replica set.

**First step:** `engine/src/memento/state/repository.py` — write the `StateRepository`
Protocol typing, import it into `types.py`.

**Reuse pointer:** [reuse-inventory.md §4 — `StateUpdate` / `CombatEvent` / `InventoryEvent`](reuse-inventory.md#4-enginesrcmementomodelsstate_updatepy--stateupdate-and-event-models).
The executor populates `events.combat` and `events.inventory_changes`; `schema_version`
stays `1`; no new fields.

---

## C2 — MemoryClient

**Owner:** TBD (Dev B)

**Files:**
- `engine/src/memento/memory/` (new directory)
  - `client.py` — `MemoryClient` Protocol
  - `null_client.py` — `NullMemoryClient` (ingest no-op, search returns `[]`)
  - `capturing_client.py` — `CapturingMemoryClient` (records ingests for assertions)
  - `kernel_client.py` — `KernelMemoryClient` (`httpx` against `kernel/index`; stretch)

**Depends on:** `engine/src/memento/cxn/types.py` (`EpisodeIn`)

**Stub:**
```python
class NullMemoryClient:
    """Ingest is a no-op; search returns []. Wired as Day-1 default."""
    async def ingest_episode(self, episode: EpisodeIn) -> str | None: return None
    async def search_context(self, query: str, bonfire_id: str,
                             actor_id: str, k: int = 5) -> list[WorldContext]: return []

class CapturingMemoryClient:
    """Records every ingest call for unit-test assertions."""
    ingested: list[EpisodeIn]
    async def ingest_episode(self, episode: EpisodeIn) -> str | None: ...
```

**Acceptance test (Day 1):**
- `CapturingMemoryClient` captures episode text after each construction execution;
  content matches the deterministic `episode_template` string (no LLM calls).
- `KernelMemoryClient.ingest_episode` posts correct JSON to `kernel/index`; tested
  against a mock `httpx` transport (no live kernel required for Day 1).

**First step:** Write `client.py` Protocol + `NullMemoryClient`; wire as default in
gateway startup.

**Graph-memory endpoints used on Day 1:**
- `POST /v1/bonfires/{bonfire_id}/kernel/index` — the one required call. Non-fatal:
  5xx is logged and retried; the player action still succeeds.
- `POST /v1/bonfires/{bonfire_id}/kernel/search` — optional world-context fetch;
  used in Milestone 2 entity resolution. Day 1: `NullMemoryClient` returns `[]`.

**Reuse pointer:** No existing codebase symbol — this is new infrastructure. For the
HTTP auth pattern (`Authorization: Bearer <GM_INTERNAL_TOKEN>`) and endpoint shapes,
see [docs/cxn/gm-contract.md](gm-contract.md) (Track C contract section) and spec §5.1/§5.3.

---

## C3 — Constructicon

**Owner:** TBD (Dev C)

**Files:**
- `engine/src/memento/cxn/`
  - `constructicon.py` — `Constructicon` class: `match(frame) → MatchedCxn | None`
  - `definitions.py` — the three `CxnDef` literals (`MOVE`, `ATTACK`, `TAKE`)
  - `arithmetic.py` — pure damage/clamp helpers (spec §3.5)
  - `conditions.py` — closed `CONDITIONS` dict of typed guard predicates (spec §4.4)

**Depends on:** `engine/src/memento/cxn/types.py` (pure data — no other component deps)

**Stub:**
```python
# definitions.py
MOVE_CXN = CxnDef(
    name="MOVE",
    predicate="move",
    roles={"agent": SelectionRestriction(entity_type="character"),
           "destination": SelectionRestriction(entity_type="room")},
    guards=["exit_exists", "same_room"],
    effect_template=[StatePrimitive(op="move_entity", ...)],
    episode_template="<agent> moves to <destination>.",
)
# ATTACK_CXN, TAKE_CXN analogously
```

**Acceptance test (Day 1):**
- Arithmetic unit tests: `damage(8, 3, 2) == 9`, `damage(1, 0, 50) == 0`,
  `clamp_hp(9, 9) == 0` (pure, exact, no RNG).
- `Constructicon.match` returns correct `MatchedCxn` for each of the three
  construction names; returns `None` for an unknown predicate.

**First step:** `definitions.py` — write all three `CxnDef` literals against spec §4;
arithmetic helpers go in parallel.

**Reuse pointer:** [reuse-inventory.md §2 — `mechanics.py` DON'T REUSE](reuse-inventory.md#2-enginesrcmementotoolsmechanicspy--dont-reuse).
`calculate_damage` and `roll_skill_check` are `@tool`-decorated, return prose, and
use `random.randint`. All arithmetic lives in `cxn/arithmetic.py` instead.

---

## C4 — EffectExecutor

**Owner:** TBD (Dev C, same as C3)

**Files:**
- `engine/src/memento/cxn/executor.py` — `EffectExecutor` class

**Depends on:** C1 (`StateRepository`), C2 (`MemoryClient`), C3 (`Constructicon`),
`ChainMirror` protocol, `engine/src/memento/cxn/types.py`

**Stub:**
```python
class EffectExecutor:
    def __init__(self, repo: StateRepository, memory: MemoryClient,
                 chain: ChainMirror) -> None: ...
    async def execute(self, cxn: CxnDef, caller_id: str,
                      bindings: dict[str, str]) -> StateUpdate: ...
```

The executor runs three phases deterministically: (1) validate guards, (2) apply
effect template against `StateRepository`, (3) ingest episode via `MemoryClient`.
Compensation logic on step-2 failure (undo writes already applied). On guard failure:
returns `StateUpdate(status="rejected", cause=<reason>)` with no writes.

**Acceptance test (Day 1):**
- One smoke test per construction: MOVE → `move_entity` delta + 1 ingest;
  ATTACK → hp delta `9 → 0` (exact) + death sub-case sets `is_dead=True`, links
  `DIED_IN`, fires `chain_kill` captured via `RecordingChainMirror`; TAKE →
  `transfer_item` delta to agent.
- Guard-failure test: ATTACK with unarmed agent raises
  `ConstructionError(reason="agent_armed")` before any write.
- Integration test with `InMemoryStateRepository + NoopChainMirror + CapturingMemoryClient`.

**First step:** Wire `EffectExecutor.__init__` and an empty `execute` that raises
`NotImplementedError`; then implement guards one at a time with tests.

**Reuse pointer:**
- [reuse-inventory.md §1 — `chain.record_death` / `transfer_item` / `is_enabled`](reuse-inventory.md#1-enginesrcmementotoolschainpy):
  `LiveChainMirror` wraps these; executor calls via the mirror, never `chain.py` directly.
- [reuse-inventory.md §4 — `StateUpdate` / `CombatEvent` / `InventoryEvent` / `EventSummary`](reuse-inventory.md#4-enginesrcmementomodelsstate_updatepy--stateupdate-and-event-models):
  Executor returns `StateUpdate.model_dump(exclude_none=True)`; `schema_version` stays `1`.

---

## C6 — McpToolBridge

**Owner:** TBD (Dev A, same as C1)

**Files:**
- `gateway/src/gateway/cxn_tools.py` (new file) — `register_cxn_tools(mcp, ws_hub, repo, mirror)`
- `engine/src/memento/tools/tool_labels.py` — **kit edit only**: add `mm_move`,
  `mm_attack`, `mm_take` to `KITS["NPC"]`; add `mm_move`, `mm_take` to
  `KITS["Player"]` (no `mm_attack` for players)
- `gateway/src/gateway/mcp_server.py` — add one `register_cxn_tools` call inside
  `build_mcp_app`; no other changes to that function

**Depends on:** C1–C4, `FastMCP`, JWT auth middleware

**Stub:**
```python
# cxn_tools.py
def register_cxn_tools(
    mcp: FastMCP,
    ws_hub: WebSocketHub,
    repo: StateRepository,
    mirror: ChainMirror,
) -> None:
    @mcp.tool("mm_move")
    async def mm_move(destination_uuid: str, ...) -> dict:
        entity_id = await _check_tool_access("mm_move")   # JWT gate — unchanged
        matched = MatchedCxn(cxn=MOVE_CXN, bound_roles={"agent": entity_id, ...})
        update = await executor.execute(matched.cxn, entity_id, matched.bound_roles)
        await broadcast_tool_event(ws_hub, tool="mm_move", npc_id=entity_id, ...)
        return update
    # mm_attack, mm_take analogously
```

**Acceptance test (Day 1):**
- After the kit edit, `_check_tool_access("mm_move")` passes for an NPC identity
  that previously would have raised `capability_missing:`.
- Vertical-slice integration: three manual MCP calls with fixture UUIDs confirm
  exact `state_deltas` in responses.

**First step:** `gateway/src/gateway/cxn_tools.py` scaffold + the kit edit in
`tool_labels.py` (two-line change, blocks every NPC invocation until it lands).

**Reuse pointer:**
- [reuse-inventory.md §3 — `KITS["NPC"]` / `KITS["Player"]` at `tool_labels.py:34`](reuse-inventory.md#3-enginesrcmementotoolstool_labelspy--kits-tables):
  required edit documented; `NPC` needs `mm_move`/`mm_attack`/`mm_take`; `Player`
  needs `mm_move`/`mm_take`.
- [reuse-inventory.md §5.1 — `_check_tool_access` at `mcp_server.py:46`](reuse-inventory.md#51-_check_tool_access):
  call unchanged; new tool names just need to be in KITS.
- [reuse-inventory.md §5.2 — `broadcast_tool_event` at `engine_events.py:14`](reuse-inventory.md#52-broadcast_tool_event):
  call signature unchanged; `data` kwarg is optional.
- [reuse-inventory.md §5.3 — `build_mcp_app` at `mcp_server.py:1064`](reuse-inventory.md#53-fastmcp--build_mcp_app-registration-factory):
  add exactly one `register_cxn_tools(mcp, ws_hub, repo, mirror)` call inside.

---

## C5 / Milestone-2 — Comprehension (ComprehensionClient + TurnRouter)

**Owner:** TBD (Milestone-2 sprint, after Day-1 slice ships)

**Files (Milestone 2 — not built on Day 1):**
- `engine/src/memento/cxn/kernel_client.py` — `ComprehensionClient` (HTTP adapter
  against `kernel/comprehend`)
- `engine/src/memento/cxn/turn_router.py` — `TurnRouter` (free-text orchestrator:
  `kernel/search` → `EntityResolver` → `kernel/comprehend` → `Constructicon.match`
  → `EffectExecutor.execute`)
- `engine/src/memento/cxn/entity_resolver.py` — `EntityResolver` (deterministic
  surface-string → UUID from search hits; Milestone 2)

**EXPOSE the existing capability — not build from scratch.** The comprehension
function already exists and is exercised live inside `memory_kernel`:
`FCGBridgeClient.comprehend(grammar_ref, utterance)` and
`.comprehend_scoped(grammar_ref, utterance, activation_scope)` (POSTing
`/v1/comprehend` and `/v1/comprehend-scoped`); the in-process path
`_comprehend_loaded_grammar(grammar, utterance, ...)` drives `PyFCGBackend`
with no sidecar. `runtime/kernel.py` search ALREADY comprehends queries
internally — `fcg_comprehend` / `comprehend_attempts` diagnostics carry
`activated_cxns`. Milestone 2 = add a thin `kernel/comprehend` HTTP route
that wraps and exposes this; the engine client stub (`ComprehensionClient`)
calls it. Game-grammar authoring (the substantive effort) is separate.

**Depends on:** C1–C4 (Day-1 slice must ship first); the `kernel/comprehend`
HTTP route (Track C).

**Day-1 state:** No stub exists on Day 1 — spec §8.1 is explicit: "There is **no**
`PatternComprehensionClient` / regex stub on Day 1." `TurnRouter` is not scaffolded.

**First step (when sprint opens):** Confirm the live `kernel/comprehend` route from
Track C is deployed; then write `ComprehensionClient` against the DTO contract
in spec §5.3; then wire `TurnRouter` as the top-of-funnel for free-text turns.

**Reuse pointer / contract:** See [docs/cxn/gm-contract.md](gm-contract.md) for the
Track C contract — `FCGBridgeClient.comprehend_scoped` / `_comprehend_loaded_grammar`
entry points, DTO shapes (`KernelComprehendRequest` / `SemanticFrameDTO`), and the
`kernel/comprehend` route plan. The engine client is written against that contract.

---

## Track C — graph-memory comprehend route

**Owner:** TBD (graph-memory team, separate repo/PR)
**Repo:** `bonfires-ai-core`, `services/graph-memory/`
**Branch:** separate PR to `staging` — NOT this memento-mori branch

**EXPOSE the existing capability — not build from scratch.** The comprehend function
is live in `memory_kernel/src/memory_kernel/construction/fcg/bridge.py`:
`FCGBridgeClient.comprehend(grammar_ref, utterance)` and
`FCGBridgeClient.comprehend_scoped(grammar_ref, utterance, activation_scope)`.
The in-process path is `_comprehend_loaded_grammar(grammar, utterance, grammar_ref=,
activation_scope=)` driving `PyFCGBackend._comprehend_query` with no sidecar.
`runtime/kernel.py` already uses comprehension internally and emits
`fcg_comprehend` / `comprehend_attempts` diagnostics with `activated_cxns`.
This route wraps what exists.

**Files to touch in `services/graph-memory/`:**
- `kernel_dto.py` — add `KernelComprehendRequest` / `KernelComprehendResponse` /
  `SemanticFrameDTO` (spec §5.3)
- `kernel_service.py` — add `comprehend()` delegating to the backend protocol
- `kernel_controller.py` — DTO mapping for the new route
- `kernel_routes.py` — `@router.post("/comprehend")` mirroring `/index`/`/search`
- `src/adapters/memory_kernel/client.py` — `comprehend()`: local mode →
  `_comprehend_loaded_grammar(...)`; remote mode → `FCGBridgeClient.comprehend_scoped(...)`;
  map `(meanings, diagnostics.activated_cxns)` → `SemanticFrameDTO`

**Acceptance (Track C smoke):**
- Live `comprehend("attack the goblin")` returns a frame with `predicate` populated
  and at least one entry in `applied_cxn_ids` / `activated_cxns`.
- Game-grammar authoring (binding `move`/`attack`/`take` game roles) is the
  substantive Milestone-2 effort; Track C's prep scope ends at "route exists and
  returns a frame from the existing capability."

**First step:** Read `memory_kernel/src/memory_kernel/construction/fcg/bridge.py` to
confirm live signatures; add DTOs to `kernel_dto.py`; wire `kernel_routes.py`.

**Contract pointer:** [docs/cxn/gm-contract.md](gm-contract.md) — this doc is the
authoritative record of `kernel/index`, `kernel/search`, and (once Track C ships)
`kernel/comprehend` endpoint shapes, auth scheme, and error contracts.

---

## Merge order

```
1. engine/src/memento/cxn/types.py         ← any dev, first (unblocks C1/C2/C3 in parallel)
2. C1 InMemoryStateRepository              │
   C2 NullMemoryClient + CapturingMemoryClient  │  parallel
   C3 Constructicon + definitions + arithmetic  │
3. C4 EffectExecutor                       ← needs C1/C2/C3 green
4. C6 McpToolBridge (cxn_tools.py + kit edit)  ← needs C1–C4; final wire
5. C5 + Track C                            ← Milestone 2 sprint (separate PRs)
```
