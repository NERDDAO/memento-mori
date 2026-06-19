# Memento Mori — Construction-Based Control System (Walking Skeleton)

**Goal.** Replace memento-mori's archived Bonfires-KG (Graphiti-on-Neo4j via the Delve HTTP API) integration and its LLM classification/event-detection/consequence crews with a deterministic, construction-based control system, delivered first as a thin vertical slice over three actions: MOVE, ATTACK, TAKE.

**Architecture summary.** Game state is split across three substrates — a transactional/authoritative store (MongoDB behind a `StateRepository` port), a memory/knowledge substrate (the graph-memory kernel HTTP service), and the orthogonal onchain MUD/Redstone mirror. Between agent input and state sits one new control layer: an *effectful constructicon*. A construction is a form→meaning→effect triple; an effect template composed of typed state primitives executes deterministically with no LLM in the effect path. Constructions surface to agents as MCP tools — the constructicon *is* the agent tool palette.

**The Day-1 cut line (read this first).** The walking skeleton is **UUID-args-only**: agents/NPCs invoke each construction as an MCP tool passing entity **UUIDs** as typed arguments, and a construction is matched directly by its `predicate` from those args. There is **NO text comprehension on Day 1** — no `kernel/comprehend`, no `EntityResolver`, no surface-string→UUID resolution, no FCG round-trip. The full hybrid-comprehension path (the kernel's FCG turning raw text into a role-bound semantic frame) is the documented **next milestone (Milestone 2 — comprehension, §5)**, fully specified but explicitly out of the Day-1 build. The Day-1 skeleton depends on **zero new graph-memory endpoints**.

**Success criterion — maximum expressiveness at minimum inference cost.** The construction layer is a deterministic, entrenching cache over agent expressiveness: in the full system inference is paid only at the genuine novelty frontier (one comprehension call per turn, shared across all action categories), not per action and not per action volume. MOVE/ATTACK/TAKE cost 8–12 LLM calls each in the legacy crew pipeline. On Day 1 they cost **zero** LLM calls (deterministic match on UUID args); at Milestone 2 they cost **one** shared comprehension call regardless of how many event types a turn implies.

---

## 1. Problem & thesis

### 1.1 What we are replacing

Memento-mori's old integration treated the Bonfires "KG" stack — Graphiti-on-Neo4j fronted by the Delve HTTP API — as its primary world-state authority. That stack is being **archived**. Keeping it would mean maintaining a Graphiti fork, a Neo4j instance, the Delve FastAPI process, the Bonfires Python SDK, and roughly 30 call-sites across `tools/kg.py`, `round_controller.py`, and crew files that all spoke the Delve response schema (`entities`, `nodes`, `edges`, `uuid`, `fact`). World-state read and write both flowed through an external HTTP service whose latency and availability the engine could not control.

The more expensive problem is the **control pipeline**. Every player action passes through a chain of LLM crew calls before the engine knows what happened or what to do about it:

1. `ContextCrew` — retrieves world context (LLM call)
2. Plausibility check — open-ended LLM gate (LLM call)
3. `EventDetectionFlow` — `ClassificationCrew`, then one or more of `CombatDetectorCrew`, `InventoryDetectorCrew`, `QuestDetectorCrew`, `WorldChangeDetectorCrew`, `EventMergeCrew` (2–6 LLM calls)
4. Per-category resolution — `CombatFlow` chains `CombatAssessmentCrew` → `AttackResolutionCrew` (or `AbilityResolutionCrew`) → `ConsequenceCrew`, the last of which writes outcomes to the KG as free text interpreted by an LLM (3 LLM calls for combat alone)
5. `QuestFlow`, `ReputationCrew` — additional chains for other categories
6. `NarrationCrew` — prose generation
7. `EpisodicMemoryFlow` — `MemoryConsolidationCrew` + N × `NpcMemoryCrew` (N+1 LLM calls)

A single MOVE or ATTACK for one player can cost **8–12 LLM calls** before narration, with outcomes written to the KG as unstructured strings matched by `"dead" in result.raw.lower()`. The crew budget scales with **action volume, not action novelty**: every "pick up the torch" costs the same as discovering a hidden conspiracy.

### 1.2 The thesis

A **construction** is a form→meaning→effect triple. The old pipeline routes *every* action through LLM classification and LLM consequence-writing regardless of novelty. Construction-based control inverts this: comprehension produces a semantic frame once per turn; the constructicon matches the frame to an action deterministically; and a typed effect template executes against the substrates with no LLM in the path.

| Cost source | Old pipeline | Construction system |
|---|---|---|
| Action classification | 1 LLM call / turn | 0 — frame match is deterministic |
| Event detection (combat) | classification + detector + merge = 3 calls | 0 — construction matched by frame |
| Combat resolution | assessment + resolution = 2 calls | 0 — damage formula is a state primitive |
| Consequence application | consequence crew = 1 call + free-text KG writes | 0 — effect template executed deterministically |
| Inventory detection | inventory detector = 1 call | 0 — TAKE matches directly |
| Movement detection | classification = 1 call | 0 — MOVE matches by frame |
| Memory consolidation | consolidation + N × NPC memory | 1 HTTP call to `kernel/index` (async, post-turn) |
| **Total for MOVE/ATTACK/TAKE** | **8–12 LLM calls** | **0 LLM calls (Day 1, UUID args)** / **1 LLM call (Milestone 2, comprehension, shared across all constructions)** |

On Day 1 the construction column is **zero** LLM calls: agents pass UUID args and the matched construction's effect template runs deterministically. At Milestone 2 the single remaining inference call is **comprehension** — the kernel's FCG turning raw input into a general semantic frame, paid once per turn (not once per category): a turn with three detectable event types costs the same one comprehension call as a turn with one.

**Entrenchment is amortization at the grammar level.** A high-entrenchment construction has been comprehended, matched, and executed many times; the kernel's grammar recognizes its form pattern fast and confidently, so inference cost falls as the construction becomes familiar. Novel actions the constructicon cannot match are the only ones that escalate to an LLM crew. Inference scales with genuine novelty.

**Declarative effects are correct by construction.** `set_attr(entity, "hp", new_hp)` is a typed operation against the `StateRepository` port; its outcome is checked by a unit test, not by reading LLM output for the word "dead."

---

## 2. Architecture

### 2.1 Three substrates, one control layer, one transport

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    PLAYER / NPC AGENT                            │
  │   (MCP client — calls constructions as MCP tools via /mcp)      │
  └────────────────────────────┬────────────────────────────────────┘
                               │  MCP tool call:
                               │  mm_attack({patient, instrument})
                               ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │              CONSTRUCTION CONTROL LAYER  (engine/src)            │
  │                                                                  │
  │  DAY 1: MCP tool args ARE the frame (UUID roles, no NLP).        │
  │  MILESTONE 2 adds step 0 (kernel/comprehend) — see §5.          │
  │                                                                  │
  │  1. MATCH  ──────────────────────► Constructicon                │
  │     cxn = constructicon.match(frame)   (deterministic,          │
  │     frame.predicate from tool name      O(constructions))       │
  │                                                                  │
  │  2. FILL   ──────────────────────► RoleBinding                  │
  │     bindings from UUID args            (type-checked by         │
  │                                         selection restrictions) │
  │                                                                  │
  │  3. EXECUTE  ────────────────────► StateRepository (Mongo)      │
  │     EffectExecutor.execute(cxn,        set_attr, move_entity,   │
  │       caller_id, bindings)             transfer_item, link …    │
  │              ──────────────────────► ChainMirror (gated)        │
  │                                                                  │
  │  4. REMEMBER ────────────────────► kernel/index                 │
  │     ingest_episode(text)               (post-commit,            │
  │                                         non-fatal on failure)   │
  └─────────────────────────────────────────────────────────────────┘
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
  ┌──────────────────┐ ┌────────────────┐ ┌──────────────┐
  │  SUBSTRATE (a)   │ │  SUBSTRATE (b) │ │ SUBSTRATE(c) │
  │  TRANSACTIONAL   │ │  MEMORY /      │ │  CHAIN       │
  │                  │ │  KNOWLEDGE     │ │              │
  │  MongoDB         │ │  graph-memory  │ │  onchain MUD │
  │  document-per-   │ │  kernel HTTP   │ │  / Redstone  │
  │  entity          │ │  service       │ │              │
  │  StateRepository │ │                │ │ tools/chain  │
  │  port            │ │  kernel/index  │ │  + ChainMirror│
  │                  │ │  kernel/search │ │  (existing   │
  │  HP, position,   │ │  (Day 1)       │ │   seam,      │
  │  inventory,      │ │  kernel/       │ │   unchanged) │
  │  room topology,  │ │   comprehend   │ │              │
  │                  │ │  (Milestone 2) │ │              │
  │  quest stage,    │ │  episodes,     │ │  death,      │
  │  death           │ │  world-context,│ │  ownership,  │
  │                  │ │  lore, NPC mem │ │  position    │
  └──────────────────┘ └────────────────┘ └──────────────┘
```

- **Substrate (a) — Transactional.** MongoDB, document-per-entity, exposed exclusively through the `StateRepository` port. Authoritative for all game-mechanical truth: HP, position, inventory/equipped, room exits, quest stage, death flag. The onchain dual-write for the permadeath-critical subset (death, item ownership, position) routes through `tools/chain.py` via a `ChainMirror` façade exactly as today — orthogonal and unchanged. See §6.

- **Substrate (b) — Memory/Knowledge.** The graph-memory kernel HTTP service. On Day 1 the engine uses only the two existing routes — `POST /v1/bonfires/{bonfire_id}/kernel/search` and `POST /v1/bonfires/{bonfire_id}/kernel/index`. The `kernel/comprehend` route is a Milestone-2 dependency that does **not** exist yet (see §5). The engine is a thin HTTP client — no `torch`, `spaCy`, FCG-Go, or Neo4j in the engine image.

- **Substrate (c) — Chain.** Unchanged. `tools/chain.py` and `gateway/chain_client` remain the only chain seam, fronted by `ChainMirror`. See §6.3.

- **The construction control layer** owns the match → fill → execute → remember loop (Day 1) — with a comprehend step prepended at Milestone 2 — and is the only component that touches all three substrates in a turn.

### 2.2 The agent loop

The control layer is **not** a crew or flow graph — it is a synchronous async function. **On Day 1 there is no fork and no router.** An agent calls a construction's MCP tool with UUID args; the handler builds a `MatchedCxn` directly (predicate from the tool name, roles from the args), runs the executor, and returns the `StateUpdate`:

```
DAY 1 — UUID-args-only
agent MCP tool call  mm_attack(patient=<uuid>, instrument=<uuid>?)
     │   agent = caller JWT `sub`;  predicate = "attack" (from tool name)
     ▼
[ MatchedCxn built directly — roles bound from UUID args, no NLP, no kernel call ]
     │
     ▼
[ EffectExecutor.execute(cxn, caller_id, bindings) ]   ← zero LLM calls
     │   validate restrictions/guards → transactional phase → memory + chain phase
     ▼
StateUpdate delivered immediately; narration may fire async, non-blocking
```

```
MILESTONE 2 (comprehension, §5) — adds free-form text via a thin TurnRouter
player_action (raw text)
     │
     ▼
[ comprehend(text, actor_id, bonfire_id) ]   ← one kernel/comprehend HTTP call
     │  SemanticFrame { predicate, roles→UUIDs, confidence }
     │
     ├─ confidence ≥ THRESHOLD and cxn matched → EffectExecutor.execute (same as Day 1)
     │
     └─ confidence < THRESHOLD or no match → legacy RoundController.run()  (unchanged fallback)
```

The Day-1 build contains none of the Milestone-2 box: no `comprehend`, no `TurnRouter`, no confidence threshold, no legacy fork. NPC/agent callers already hold the UUIDs they need from `mm_get_state` / `mm_room_manifest`, so they invoke the construction tools directly. Milestone 2 is fully specified in §5 so the Day-1 interfaces (the `SemanticFrame` shape, the executor signature) are forward-compatible with it.

---

## 3. State primitives

State primitives are the atomic, typed operations effect templates compose from. They are **not** exposed to agents directly — agents fire constructions; constructions declare an ordered list of primitives; the `EffectExecutor` runs them. The executor processes the list in order and aborts the transactional phase on the first failure, rolling back transactional writes applied so far in the same template run.

### 3.1 Canonical primitive set

The six primitive `op` codes used by effect templates, across the three substrates:

| `op` | Substrate | StateRepository / client method | Purpose |
|---|---|---|---|
| `set_attr` | transactional | `set_attr(uuid, field, value)` | Set a scalar field (incl. arithmetic results) on an entity doc |
| `move_entity` | transactional | `move_entity(uuid, to_location_uuid)` | Relocate a character/NPC; maintain location/contents denormalization |
| `transfer_item` | transactional | `transfer_item(item_uuid, from_uuid, to_uuid, to_location_uuid=None)` | Move an item between holder/floor; maintain ownership + contents (one signature everywhere, §6.2) |
| `link` | transactional | `link(from_uuid, to_uuid, rel)` | Append to a list field / add a relation (e.g. status effect, `DIED_IN`) |
| `unlink` | transactional | `unlink(from_uuid, to_uuid, rel)` | Inverse of `link` |
| `ingest_episode` | memory | `MemoryClient.ingest_episode(...)` | Persist the turn's outcome as a kernel episode (post-commit) |

Chain effects are expressed as primitives with `substrate="chain"` (`chain_kill`, `chain_transfer`) but dispatch through the `ChainMirror` façade (§6.3), never `chain.py` directly. Chain primitives are always the **last** steps in a template, fire-and-forget, and never roll back transactional state.

> **Naming note (unification).** Earlier drafts used `incr_attr`/`SetAttr`/`MoveEntity`/`TransferItem` dataclasses and a `clamp_hp`/`roll_damage` `Computed` mechanism. The canonical model is the `StatePrimitive` TypedDict below with the six `op` codes above. Arithmetic (damage, HP clamping) is computed by the executor in-line via the **pure helper in §3.5** and written through `set_attr` — there is no separate `incr_attr` op and no `Computed` value type. The executor is the single place where deterministic arithmetic lives.

### 3.5 Deterministic arithmetic (no CrewAI tools, no RNG)

The executor **must not** call `tools/mechanics.py`. Those functions (`calculate_damage`, `roll_skill_check`) are CrewAI `@tool`-decorated, take string args, return prose (`"Damage: 7 (weapon 5 + strength 4 = 9, minus armor 2)"`), and `roll_skill_check` uses `random.randint` — all three properties are disqualifying in a deterministic effect path. Instead, the executor calls pure integer helpers it owns at `engine/src/memento/cxn/arithmetic.py`:

```python
# engine/src/memento/cxn/arithmetic.py
def damage(weapon: int, strength: int, armor: int) -> int:
    """ATTACK damage. No random roll on Day 1. Pure, total, int-only."""
    return max(0, weapon + strength - armor)

def clamp_hp(current: int, dmg: int) -> int:
    return max(0, current - dmg)
```

**ATTACK has NO random roll on Day 1** — damage is exactly `max(0, weapon + strength − armor)` (all ints; `weapon` = instrument's `attrs["damage"]`, `strength` = agent's `attrs["strength"]`, `armor` = patient's `attrs["armor"]`, each defaulting to 0 if absent). Determinism is a **hard guarantee**: the smoke tests assert exact `StateDelta` values (e.g. str 3 + weapon 8 − armor 2 ⇒ `damage == 9`, `hp 9 → 0`), which is only possible because no RNG is in the path. A future damage variance roll, if ever wanted, is a Milestone-2+ change behind its own flag and is out of scope here.

### 3.2 Types

```python
# engine/src/memento/cxn/types.py
from __future__ import annotations
from typing import Any, Literal, TypedDict

class StatePrimitive(TypedDict):
    substrate: Literal["transactional", "memory", "chain"]
    op: Literal["set_attr", "move_entity", "transfer_item",
                "link", "unlink", "ingest_episode",
                "chain_kill", "chain_transfer"]
    args: dict[str, Any]          # "$role" / "$computed_hp" refs, "@episode_template", or literals (§4.4)
    if_condition: str | None      # None, or a key into the closed CONDITIONS dict (§4.4).
                                  # NO expression parser, NO eval, NO LLM.
```

### 3.3 Return contract and rollback

Each transactional primitive returns a `StateDelta` (`op`, `target_uuid`, `field`, `before`, `after`) that the executor collects for the response payload and for compensation. Primitives **never raise** for domain failures (entity not found, precondition violated, holder mismatch) — they surface a typed failure the executor converts into a `ConstructionError`. They raise only for programming errors (bad argument types).

The executor opens a transactional context before the first transactional primitive and, on the first transactional failure, rolls back via the inverse-op (compensation) table. **Rollback prerequisite (state it plainly):**

- **Day-1 default path is the `InMemoryStateRepository`.** It needs no transactions — the executor simply runs the recorded inverse operations (the compensation table below) in reverse order over the in-memory dicts. This is the path the integration test exercises.
- **The Mongo path requires a replica set** for `start_transaction()` (multi-document transactions). A standalone `mongod` cannot do multi-doc transactions; there the executor falls back to the same reverse-order compensation, with a logged warning (acceptable because chain is the authoritative conflict resolver for the permadeath subset).
- **`mongomock-motor` does NOT support transactions.** Therefore the integration test does **not** rely on mongomock for transactional integrity — it uses `InMemoryStateRepository` (default) or a real replica set. Do not claim mongomock gives transactional rollback.

Memory and chain primitives do not participate in rollback: `ingest_episode` is never reached if an earlier step fails, and chain writes are always the final fire-and-forget steps.

Compensation table:

| `op` | Compensation |
|---|---|
| `set_attr` | `set_attr(uuid, field, before_value)` |
| `move_entity` | `move_entity(uuid, previous_location_uuid)` |
| `transfer_item` | `transfer_item(item_uuid, from_uuid=to_uuid, to_uuid=from_uuid, to_location_uuid=original_location_uuid)` — restores the item to its original holder/floor location (see §6.2 for the unified signature) |
| `link` | `unlink(from_uuid, to_uuid, rel)` |
| `unlink` | `link(from_uuid, to_uuid, rel)` |

### 3.4 Per-construction primitive composition

| Step | MOVE | ATTACK | TAKE |
|------|------|--------|------|
| 1 | `move_entity(agent, destination)` | `set_attr(patient, "hp", computed_hp)` | `transfer_item(item, location, agent)` |
| 2 | `ingest_episode(...)` | `[if hp≤0] link(patient, location, "DIED_IN")` | `[if onchain] chain_transfer(item, agent)` |
| 3 | — | `[if hp≤0] set_attr(patient, "is_dead", True)` | `ingest_episode(...)` |
| 4 | — | `[if hp_depleted] chain_kill(patient)` | — |
| 5 | — | `ingest_episode(...)` | — |

ATTACK steps 2–4 fire only when the executor evaluates the `hp_depleted` condition (`computed_hp <= 0`) after step 1. `computed_hp` is `clamp_hp(patient.hp, damage(...))` from §3.5 — pure ints, no RNG, no LLM. The `chain_kill` primitive dispatches through `ChainMirror.on_character_death(character_id, cause, location_id, tick)` (§6.3); it carries **no `killer_id`** (the real `chain.py` `record_death` takes none). TAKE step 2 (`chain_transfer`) fires only when the item doc carries `onchain == True`.

> **Dropped-item story (resolved):** the Day-1 skeleton does **not** auto-drop a slain character's inventory. `ChainMirror.on_item_dropped` is therefore **cut from skeleton scope** — death is a `set_attr(is_dead)` + `link(DIED_IN)` + `chain_kill` only. Inventory-drop-on-death is a future construction (a DROP/LOOT cxn) and is listed in the forward map (§9.2).

---

## 4. Effectful constructicon + the 3 cxns

### 4.1 Core data model

A construction is a `CxnDef`: a name, the semantic roles it binds, selection restrictions (guard predicates), an ordered effect template, and a deterministic episode template. The **constructicon** is a static registry that matches a `SemanticFrame` to a `MatchedCxn`.

```python
# engine/src/memento/cxn/types.py  (continued)

RoleTag = Literal["agent", "patient", "instrument", "location"]

class SemanticFrame(TypedDict):
    predicate: str                 # from kernel comprehension: "move" | "attack" | "take"
    roles: dict[str, str]          # role label → entity UUID (resolved)
    confidence: float              # 0.0–1.0
    raw_text: str

class SelectionRestriction(TypedDict):
    role: str
    required_labels: list[str]     # entity must carry ALL of these
    forbidden_labels: list[str]    # entity must carry NONE of these

class CxnDef(TypedDict):
    name: str                      # "MOVE" | "ATTACK" | "TAKE"
    predicate: str                 # frame predicate this cxn matches
    mcp_tool_name: str             # "mm_move" | "mm_attack" | "mm_take"
    description: str               # MCP tool docstring (agent-facing)
    semantic_roles: list[str]      # ordered roles → MCP tool params
    restrictions: list[SelectionRestriction]
    guards: list[str]              # named runtime predicates (e.g. "exit_exists")
    chain_mirror: bool             # whether the cxn fires chain primitives
    effect_template: list[StatePrimitive]
    episode_template: str          # f-string over role labels + computed values

class MatchedCxn(TypedDict):
    cxn: CxnDef
    bound_roles: dict[str, str]    # role label → UUID, fully resolved

class Constructicon(Protocol):
    def match(self, frame: SemanticFrame) -> MatchedCxn | None: ...
    def all_cxns(self) -> list[CxnDef]: ...
```

`match()` is O(n) over registered constructions (three in the skeleton): it selects the cxn whose `predicate` equals `frame.predicate` and populates `bound_roles` from `frame.roles`. Selection restrictions and named guards are checked later, by the executor, before any state mutation (§7.2 Phase 1).

**Standard guard predicates** (deterministic, read-only, no LLM):

| Guard | Meaning |
|---|---|
| `exit_exists` | the agent's current location has a named exit to `destination` |
| `agent_armed` | the agent has a weapon equipped (or a bound `instrument` labelled `Weapon` and carried) |
| `target_damageable` | the patient has an `hp` attr and is not `Dead` |
| `same_room` | the patient/item's `location_uuid` matches the agent's |
| `item_carryable` | the item's `carryable` attr is not `False` |
| `capacity_ok` | the agent's inventory count is below `DEFAULT_CAPACITY` (20) |

### 4.2 The three constructions

#### CXN.MOVE

```python
CxnDef(
    name="MOVE", predicate="move", mcp_tool_name="mm_move",
    description="Move the agent character to an adjacent room (by destination UUID).",
    semantic_roles=["agent", "location"],   # location = destination room
    restrictions=[
        SelectionRestriction(role="agent", required_labels=["Character"], forbidden_labels=["Dead"]),
        SelectionRestriction(role="location", required_labels=["Location"], forbidden_labels=[]),
    ],
    guards=["exit_exists"],
    chain_mirror=False,
    effect_template=[
        StatePrimitive(substrate="transactional", op="move_entity",
            args={"uuid": "$agent", "to_location_uuid": "$location"}, if_condition=None),
        StatePrimitive(substrate="memory", op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"}, if_condition=None),
    ],
    episode_template="{agent_name} moved to {location_name}.",
)
```

No chain step — position is not permadeath-critical. Worked example: Kael (`a1b2`) in The Threshold (`r001`, exit `north → r002`) sends `go north` → frame `{predicate:"move", roles:{agent:a1b2, location:r002}}` → guards pass → `move_entity(a1b2, r002)` → `ingest_episode("Kael moved to The Ash Market.")`. **0 LLM calls** (legacy: ≥1).

#### CXN.ATTACK

```python
CxnDef(
    name="ATTACK", predicate="attack", mcp_tool_name="mm_attack",
    description="Agent attacks a target, applying damage; instrument is the weapon "
                "(defaults to equipped main-hand if omitted).",
    semantic_roles=["agent", "patient", "instrument", "location"],
    restrictions=[
        SelectionRestriction(role="agent", required_labels=["Character"], forbidden_labels=["Dead"]),
        SelectionRestriction(role="patient", required_labels=["Character"], forbidden_labels=["Dead"]),
        SelectionRestriction(role="instrument", required_labels=["Weapon"], forbidden_labels=[]),
    ],
    guards=["agent_armed", "target_damageable", "same_room"],
    chain_mirror=True,   # death = permadeath-critical
    effect_template=[
        StatePrimitive(substrate="transactional", op="set_attr",
            args={"uuid": "$patient", "field": "hp", "value": "$computed_hp"}, if_condition=None),
        StatePrimitive(substrate="transactional", op="link",
            args={"from_uuid": "$patient", "to_uuid": "$location", "rel": "DIED_IN"},
            if_condition="hp_depleted"),
        StatePrimitive(substrate="transactional", op="set_attr",
            args={"uuid": "$patient", "field": "is_dead", "value": True},
            if_condition="hp_depleted"),
        # chain death → ChainMirror.on_character_death(character_id, cause, location_id, tick)
        # NOTE: no killer_id — the real chain.py record_death does not take one.
        StatePrimitive(substrate="chain", op="chain_kill",
            args={"character_id": "$patient", "cause": "combat", "location_id": "$location"},
            if_condition="hp_depleted"),
        StatePrimitive(substrate="memory", op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"},
            if_condition=None),
    ],
    episode_template="{agent_name} attacked {patient_name} with {instrument_name} for {damage} damage{death_suffix}.",
)
```

The executor populates three transients before episode assembly (§7.2 / §4.4): `computed_hp = clamp_hp(patient.hp, damage)`, `damage = damage(instrument.attrs["damage"], agent.attrs["strength"], patient.attrs["armor"])` (the pure §3.5 helper — no RNG), and `death_suffix = " — {patient_name} has died."` when `hp_depleted` else `""`.

Worked example (death sub-case): Kael (str 3, Iron Sword dmg 8) attacks Goblin (hp 9, armor 2) → `damage = max(0, 8+3−2) = 9` → `clamp_hp(9, 9) = 0` → `set_attr(goblin, "hp", 0)` → `link(goblin, r002, "DIED_IN")` → `set_attr(goblin, "is_dead", True)` → `chain_kill(goblin, cause="combat", location_id=r002)` → episode `"Kael attacked Goblin Scout with Iron Sword for 9 damage — Goblin Scout has died."`. **0 LLM calls** (legacy: 4 sequential crew calls plus free-text dead-check). Determinism is asserted on the exact `damage == 9` / `hp == 0` deltas.

#### CXN.TAKE

```python
CxnDef(
    name="TAKE", predicate="take", mcp_tool_name="mm_take",
    description="Agent picks up an item from the current room into their inventory.",
    semantic_roles=["agent", "patient", "location"],   # patient = item
    restrictions=[
        SelectionRestriction(role="agent", required_labels=["Character"], forbidden_labels=["Dead"]),
        SelectionRestriction(role="patient", required_labels=["Item"], forbidden_labels=[]),
        SelectionRestriction(role="location", required_labels=["Location"], forbidden_labels=[]),
    ],
    guards=["item_carryable", "same_room", "capacity_ok"],
    chain_mirror=True,   # ownership change → chain transfer
    effect_template=[
        # item moves from the floor (location) to the agent; from_location captured for compensation.
        StatePrimitive(substrate="transactional", op="transfer_item",
            args={"item_uuid": "$patient", "from_uuid": "$location",
                  "to_uuid": "$agent", "to_location_uuid": None},
            if_condition=None),
        StatePrimitive(substrate="chain", op="chain_transfer",
            args={"item_id": "$patient", "new_owner_id": "$agent"},
            if_condition="patient_onchain"),
        StatePrimitive(substrate="memory", op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"}, if_condition=None),
    ],
    episode_template="{agent_name} picked up {patient_name} from {location_name}.",
)
```

Worked example: Kael takes Tattered Scroll (`i044`, `carryable`, `onchain=False`) from The Ash Market → `transfer_item(i044, from_uuid=r002, to_uuid=a1b2)` → chain step skipped (`patient_onchain` false) → episode. Onchain sub-case (Iron Sword, `onchain=True`): step 2 fires `chain_transfer` via `ChainMirror.on_item_transferred(w001, a1b2)`. **0 LLM calls** (legacy: consequence + narration crews). If TAKE is compensated, the restore is `transfer_item(item_uuid=i044, from_uuid=a1b2, to_uuid=None, to_location_uuid=r002)` — back to the original floor location (§3.3, §6.2).

### 4.3 Registration

All three constructions are registered at engine startup, before the MCP server mounts. Definitions live as literals in `engine/src/memento/cxn/definitions.py`; the registry (`engine/src/memento/cxn/constructicon.py`) loads them into `CONSTRUCTION_REGISTRY: dict[str, CxnDef]`. The MCP server reads the registry to know which tools to register; tool names come from each cxn's `mcp_tool_name`, directly replacing the legacy `mm_move_to` / `mm_resolve_combat` / `mm_inventory_transfer` surface.

### 4.4 Substitution syntax and the closed condition evaluator

Three distinct, non-overlapping substitution forms appear in effect/episode templates. Each has a fixed, documented meaning — there is **no expression parser and no `eval`** anywhere.

| Form | Where | Resolves to | Resolved by |
|---|---|---|---|
| `$role` | primitive `args` values | the **bound UUID** for that role (`$agent`, `$patient`, `$instrument`, `$location`) | role binding (Day 1: from MCP args) |
| `$computed_hp` | primitive `args` values | an executor **transient** | executor, before Phase 2 (see below) |
| `@episode_template` | `ingest_episode` `text` arg | the cxn's `episode_template` string (then run through `{}` resolution) | executor, Phase 3 |
| `{name}` | `episode_template` only | a **resolved entity name** or a computed transient value | executor, Phase 3, via one doc read per entity |

**Why two sigils.** `$` substitutes into *machine* positions (UUIDs and numeric transients that become `StateRepository` arguments); `{}` substitutes into *human-readable* episode prose (names, formatted numbers). Keeping them distinct means the executor never has to guess whether a `{patient_name}` in episode text is meant to become a UUID. `@episode_template` is a single fixed indirection so the episode sentence is authored once.

**The three computed transients** (enumerated — the executor populates exactly these before episode assembly, all derived from §3.5 pure helpers, none from an LLM):

| Transient | Value | Used by |
|---|---|---|
| `computed_hp` | `clamp_hp(patient.attrs["hp"], damage)` | ATTACK step 1 (`$computed_hp`) |
| `damage` | `damage(instrument.attrs["damage"], agent.attrs["strength"], patient.attrs["armor"])` | ATTACK episode (`{damage}`) |
| `death_suffix` | `" — {patient_name} has died."` if `hp_depleted` else `""` | ATTACK episode (`{death_suffix}`) |

**The closed `if_condition` evaluator.** `if_condition` is **not** an expression — it is a key into a fixed, hand-written dict of named, read-only predicates. Anything not in this dict is a registration-time error. The complete Day-1 set:

```python
# engine/src/memento/cxn/conditions.py
CONDITIONS: dict[str, Callable[[ExecutionContext], bool]] = {
    "hp_depleted":     lambda ctx: ctx.transients["computed_hp"] <= 0,
    "patient_onchain": lambda ctx: bool(ctx.entity("patient").get("attrs", {}).get("onchain")),
}
```

`if_condition=None` always fires. There are exactly **two** named conditions on Day 1 (`hp_depleted`, `patient_onchain`); a primitive's `if_condition` must be `None` or one of these keys. No arithmetic, comparison, or attribute-path strings are ever parsed.

---

## 5. graph-memory integration (Day-1 memory writes) + Milestone 2 (comprehension)

The engine is a thin HTTP client. It embeds no NLP stack, no FCG-Go process, no Neo4j driver. Every kernel operation is a JSON/HTTP call to the graph-memory service.

> **Day-1 dependency callout.** The Day-1 walking skeleton depends on **ZERO new graph-memory endpoints.** It uses only the two routes that already exist — `POST /v1/bonfires/{bonfire_id}/kernel/index` (episode write) and, optionally, `POST /v1/bonfires/{bonfire_id}/kernel/search` (world-context read) — both verified present in `services/graph-memory/src/modules/kernel/kernel_routes.py`. Everything under "Milestone 2" below (comprehension) is forward-looking and is **not** required to ship Day 1.

§5.1 (auth/namespace) and §5.3-index/search apply to Day 1. **§5.2, §5.3-comprehend, §5.4-ComprehensionClient, and §5.5/§5.6 are Milestone 2 (comprehension)** — fully specified so the team can build them next, but explicitly outside the Day-1 build.

### 5.1 Namespace mapping and auth

| memento-mori concept | graph-memory concept | example |
|---|---|---|
| game world | `bonfire_id` | `"mm-world-v1"` (fixed at deploy) |
| player / NPC | `actor_id` | `"player:7f3a…"` / `"npc:goblin-sentinel-42"` |
| turn event | episode | one `kernel/index` call per resolved action |

All calls carry a shared internal token — `Authorization: Bearer <GM_INTERNAL_TOKEN>` — validated by graph-memory's `InternalAuthMiddleware` (verified wired in `src/app/server.py`, gated on `auth_mode == "internal"` against `cfg.internal_token`). No per-player tokens; every call runs under the engine's identity (same pattern as platform-api → graph-memory). Bonfire/actor registration uses graph-memory's existing onboarding routes; confirm exact paths against the running service before wiring (they are not on the Day-1 critical path — `kernel/index` is the only required call).

### 5.2 The pipeline — MILESTONE 2 (comprehension)

The free-text comprehension pipeline below is **not built on Day 1**. On Day 1 there is no `kernel/search`, no `EntityResolver`, no `kernel/comprehend`; the agent supplies role UUIDs directly as MCP args and `Constructicon.match` runs on those (steps 4–6 only, with step 6 the existing `kernel/index`).

```
MILESTONE 2 ONLY
player input (raw text)
        │
1. kernel/search   ── world-context fetch ──►  EntityCandidate[]   (existing route)
        │
2. EntityResolver  (in-engine, deterministic) ──►  role→entity hints   (Milestone 2)
        │
3. kernel/comprehend  ── UNVERIFIED, to be built ──►  SemanticFrame {predicate, roles, confidence}
        │
4. Constructicon.match (in-engine)  ──►  MatchedCxn | None
        │
5. EffectExecutor.execute (in-engine)  ──►  StateUpdate           ← the ONLY Day-1 steps are 4–6
        │
6. kernel/index   ── episode write (post-commit, non-fatal)       (existing route)
```

`EntityResolver` (surface-string → UUID resolution) and the `kernel/comprehend` round-trip are Milestone-2 components. On Day 1 the `SemanticFrame` (or, equivalently, the `MatchedCxn`) is constructed in-process from the MCP tool name (predicate) and UUID args (roles) — no kernel round-trip, no NLP.

### 5.3 Endpoints

**`POST /v1/bonfires/{bonfire_id}/kernel/search`** — *exists (verified).* Optional Day-1 world-context fetch; **required only for Milestone 2** entity resolution. Request `KernelSearchRequest{ "query": "<raw input>", "top_k": 10 }` (top_k 1–100); response `KernelSearchResponse{ bonfire_id, query, hits }` where each `KernelSearchHit` has `uuid`, `score`, `text`, `family`, `metadata`, `episode_ids`. On timeout/5xx the engine proceeds with empty context (non-fatal).

**`POST /v1/bonfires/{bonfire_id}/kernel/comprehend`** — **UNVERIFIED — DOES NOT EXIST; to be built by the graph-memory team (Milestone 2).** Verified against `services/graph-memory`: a repo-wide grep for `comprehend` returns **zero hits**. The kernel module (`kernel_service.py` / `kernel_controller.py` / `kernel_routes.py`) exposes exactly `index`, `search`, and `state` — there is **no** comprehend route, no comprehend method, and **no** bridge sidecar exposing `/v1/comprehend` or `/v1/comprehend-scoped` (also zero hits). The only `FCGBridgeClient` reference is an external-library startup health-check (`from memory_kernel.construction.fcg.bridge import FCGBridgeClient`) used in `_validate_fcg_startup` — it has no HTTP comprehend surface. The DTOs and adapter sketch below are a **proposed contract for the graph-memory team to implement**, not a description of anything that exists. The Day-1 skeleton does not call it.

```python
class KernelComprehendRequest(BaseModel):
    actor_id: str
    utterance: str = Field(..., min_length=1, max_length=1024)
    entity_hints: list[str] = Field(default_factory=list)        # → FCGActivationScope.selected_topic_ids
    allowed_construct_ids: list[str] = Field(default_factory=list)  # restrict activation (the 3 skeleton cxns)

class BoundRole(BaseModel):
    role: str               # "agent" | "patient" | "instrument" | "location"
    filler: str             # surface span or entity_id
    entity_id: str | None   # resolved UUID if matched

class SemanticFrameDTO(BaseModel):
    predicate: str
    confidence: float
    roles: list[BoundRole]
    applied_cxn_ids: list[str]
    matched: bool
    raw_meaning: list[dict]

class KernelComprehendResponse(BaseModel):
    bonfire_id: str
    actor_id: str
    utterance: str
    frame: SemanticFrameDTO | None    # None when matched=False
    diagnostics: dict[str, Any] = Field(default_factory=dict)
```

Proposed graph-memory work to ship this (Milestone 2): `KernelComprehendRequest`/`Response` DTOs in `kernel_dto.py`; `KernelService.comprehend()`; a `KernelBackendProtocol.comprehend()` extension on the kernel adapter that drives FCG comprehension (e.g. via the `memory_kernel` FCG construction layer) with an activation scope built from `allowed_construct_ids` + `entity_hints`; the route in `kernel_routes.py`; and frame extraction that maps PropBank-style bound slots (`V`, `ARG0`, `ARG1`, `ARGM-LOC`) to canonical role names, reading `predicate` from the `V` slot. The engine implements its client stub against this contract; the kernel team owns the implementation. **None of this is on the Day-1 critical path.**

**`POST /v1/bonfires/{bonfire_id}/kernel/index`** — *exists (verified).* Episode write after the executor commits — **the one graph-memory call Day 1 makes.** Request `KernelIndexRequest(actor_id, mode="upsert", message_batches=[[{content, speaker, timestamp, metadata}]], metadata={...})`; `content` is the deterministic episode sentence assembled from `episode_template` (no LLM). Response `KernelIndexResponse` carrying `episode_uuids: list[str]`; the engine stores the first UUID against the turn record. Index is awaited but **non-fatal**: a 5xx is logged and retried next turn; the player action still succeeds.

### 5.4 In-engine clients

**Day 1 — `MemoryClient` only.** A thin async HTTP wrapper over `httpx.AsyncClient` with `KERNEL_BASE_URL` and `GM_INTERNAL_TOKEN` from env, calling the existing `kernel/index` (and optionally `kernel/search`).

```python
class MemoryClient(Protocol):
    async def ingest_episode(self, episode: EpisodeIn) -> str | None: ...    # returns episode_uuid
    async def search_context(self, query: str, bonfire_id: str, actor_id: str,
                             k: int = 5) -> list[WorldContext]: ...           # optional Day 1

class EpisodeIn(TypedDict):
    bonfire_id: str
    actor_id: str
    content: str
    metadata: dict          # action_type, effect_summary, location_uuid, …
```

Day-1 stubs: `NullMemoryClient` (ingest no-op, search `[]`) and `CapturingMemoryClient` (records ingests for assertions). These are the **only** memory doubles the skeleton needs.

**Milestone 2 — `ComprehensionClient`.** Added when `kernel/comprehend` is built. Not part of the Day-1 build; there is **no** `PatternComprehensionClient` and **no** regex stub on Day 1 (the executor is tested against a directly-constructed `MatchedCxn`, see §8.4).

```python
# MILESTONE 2
class ComprehensionClient(Protocol):
    async def comprehend(self, text: str, bonfire_id: str, actor_id: str) -> SemanticFrame: ...
```

### 5.5 Failure-mode contract

Day-1 rows in **bold**; the rest are Milestone 2.

| Scenario | graph-memory | engine behavior |
|---|---|---|
| **`kernel/index` 5xx** | — | **logged, retried next turn; player action still succeeds** |
| **`kernel/index` ok but `episode_uuids=[]`** | 200 | **warning logged; no UUID stored; non-fatal** |
| `kernel/search` timeout/5xx (M2) | — | empty context; resolution proceeds with empty hints |
| `kernel/comprehend` `matched=False` (M2) | 200 | no-match; clarification response, no state touched |
| `kernel/comprehend` 4xx (M2, grammar not loaded) | 400/404 | `ComprehendError`; "I don't understand that action" |

### 5.6 What graph-memory already provides vs. must add

| Capability | Status |
|---|---|
| `kernel/index`, `kernel/search`, `kernel/state` (under `/v1/bonfires/{bonfire_id}/kernel/`) | **EXISTS (verified)** — Day 1 uses `index` (+ optional `search`) |
| FCG comprehend route / method / DTOs | **DOES NOT EXIST** (0 grep hits) — Milestone-2 build, owned by graph-memory team |
| Bridge sidecar `/v1/comprehend(-scoped)` | **DOES NOT EXIST** (0 grep hits) — `FCGBridgeClient` is an external-lib startup health-check only |
| `InternalAuthMiddleware` / internal-token auth | **EXISTS** (wired in `src/app/server.py`) |

---

## 6. Transactional substrate (store + StateRepository + chain mirror)

S0 is the authoritative, synchronous source of truth for all mutable game state. It is a MongoDB database owned exclusively by the memento-mori engine — nothing outside this service writes to it, and the construction executor reaches it only through the `StateRepository` port.

### 6.1 Document model

All entity types live in a single `mm_entities` collection, discriminated by `kind`. Every document's `_id` is the entity UUID string — the canonical identifier everywhere. Names are display-only and **never** used for lookups. Mutable fields are marked; everything else changes only via world-authoring tools, not the executor.

Each entity doc carries the shared shape the rest of the spec references:

```python
class EntityDoc(TypedDict):       # characters / NPCs / locations
    uuid: str                     # == Mongo _id
    name: str                     # display-only
    kind: str                     # "character" | "location" | "item" | "region" | "faction" | "quest"
    labels: list[str]             # e.g. ["Character","NPC"], ["Location"], ["Item","Weapon"]
    location_uuid: str | None     # MUTABLE — which Location this entity is in
    attrs: dict[str, Any]         # MUTABLE — hp, max_hp, level, xp, equipped, status_effects,
                                  #           exits[], item_ids[], strength, armor, …
    is_dead: bool                 # MUTABLE — permadeath flag

class ItemDoc(TypedDict):
    uuid: str
    name: str
    kind: str                     # "item"
    labels: list[str]
    owner_uuid: str | None        # MUTABLE — holder; None = on the floor
    location_uuid: str | None     # MUTABLE — room when on the floor
    attrs: dict[str, Any]         # slot_type, damage, defense, weight, quantity, carryable, onchain, …
```

Key denormalizations: a character's `attrs["equipped"]` map (slot→item UUID) and inventory list stay consistent with item `owner_uuid`; a location's `attrs["item_ids"]` caches floor items (authoritative record is `item.location_uuid`) so a room manifest is a single-document read; a location's `attrs["exits"]` is a list of `{direction, target_uuid, locked, key_item_id}`. Characters/NPCs record position only on `location_uuid` (no x/y in the authoritative store; tile coords are display-only hints on the room).

Compound indexes (declared in `ensure_indexes()`): `kind`; `(kind, location_uuid)`; `(kind, owner_uuid)`; `(is_dead, kind)`. (A `(kind, assignee_id)` index is forward-looking for a future quest/assignment field and is **not** created Day 1 — no Day-1 document carries `assignee_id`.)

### 6.2 StateRepository port

`StateRepository` is a `Protocol` at `engine/src/memento/state/repository.py`. The executor imports only this protocol; the Mongo implementation is injected at startup. Identifiers are always UUID strings; names are never used for lookup.

```python
class StateRepository(Protocol):
    # reads
    async def get_entity(self, uuid: str) -> EntityDoc | None: ...
    async def get_labels(self, uuid: str) -> list[str]: ...
    async def get_entities_at_location(self, location_uuid: str) -> list[EntityDoc]: ...
    async def get_items_at_location(self, location_uuid: str) -> list[ItemDoc]: ...
    async def get_exits(self, location_uuid: str) -> list[ExitRecord]: ...
    async def get_actor_snapshot(self, uuid: str) -> dict[str, Any]: ...   # health, location, inventory, exits…
    async def room_manifest(self, location_uuid: str) -> RoomManifest: ...

    # transactional writes (return post-write snapshot / delta)
    async def set_attr(self, uuid: str, field: str, value: Any) -> EntityDoc: ...
    async def move_entity(self, uuid: str, to_location_uuid: str) -> EntityDoc: ...
    async def transfer_item(self, item_uuid: str, from_uuid: str | None,
                            to_uuid: str | None, to_location_uuid: str | None = None) -> ItemDoc: ...
    async def link(self, from_uuid: str, to_uuid: str, rel: str) -> None: ...
    async def unlink(self, from_uuid: str, to_uuid: str, rel: str) -> None: ...

    # lifecycle / utility
    async def ensure_indexes(self) -> None: ...   # idempotent; called once at startup
```

> **No `record_death` on the repository.** There is **no** `StateRepository.record_death` — death in the transactional store is expressed by the construction template as `set_attr(patient, "is_dead", True)` + `link(patient, location, "DIED_IN")` (§3.4 / §4.2). The *chain* death write goes through `ChainMirror.on_character_death` (§6.3), which wraps `chain.py`'s own `record_death`. Keeping a separate repo method named `record_death` would collide in meaning with the chain function; the name is deliberately removed from the port.

`transfer_item` uses **one signature everywhere**: `transfer_item(item_uuid, from_uuid, to_uuid, to_location_uuid=None)` — pickup is `(item, from_uuid=location, to_uuid=agent)`; the compensating restore is `(item, from_uuid=agent, to_uuid=None, to_location_uuid=original_location)`.

Contracts: every write does `$set` of the patched fields plus `updated_at = utcnow()`. `move_entity` and `transfer_item` maintain the location/contents and owner/inventory denormalizations atomically (single Mongo `ClientSession` with `start_transaction()` on a **replica set**; on a standalone dev instance, or under `InMemoryStateRepository`, ordered sequential writes with a logged warning — acceptable because chain is the authoritative conflict resolver for the permadeath subset). `get_entity` returns `None` only for the executor's existence checks; the executor surfaces a typed `ConstructionError` rather than letting `None` propagate.

Companion types:

```python
@dataclass
class ExitRecord:
    direction: str
    target_id: str
    locked: bool = False
    key_item_id: str | None = None

@dataclass
class RoomManifest:
    location_id: str
    name: str
    description: str
    exits: list[ExitRecord]
    npcs: list[dict[str, Any]]    # characters with matching location_uuid
    items: list[dict[str, Any]]   # floor items (location_uuid matches, owner_uuid None)
    room_map: dict[str, Any]      # display hint only
```

Implementations: `MongoStateRepository` (`engine/src/memento/state/mongo_repository.py`, `motor`-backed); `InMemoryStateRepository` (dict-backed test/dev double satisfying the same Protocol — the only store dependency of construction unit tests). No component outside `state/` imports the concrete classes by name.

### 6.3 Chain mirror seam

The chain mirror is a fire-and-forget write-through side-channel for a strictly bounded permadeath-critical subset; it never blocks the effect path. The existing `tools/chain.py` surface is reused unchanged; the executor calls a `ChainMirror` façade (never `chain.py` directly) so it can be disabled in tests without monkeypatching.

```python
class ChainMirror(Protocol):
    """Non-blocking. Implementations must not raise — errors are logged; gameplay continues."""
    def on_character_death(self, character_id: str, cause: str, location_id: str, tick: int) -> None: ...
    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None: ...
```

**Primitive → ChainMirror method → real `tools/chain.py` function (verified signatures).** The skeleton fires exactly two chain primitives; their full dispatch path is fixed:

| Chain primitive | ChainMirror method | Real `chain.py` call (exact args) |
|---|---|---|
| `chain_kill` (ATTACK, `if hp_depleted`) | `on_character_death(character_id, cause, location_id, tick)` | `record_death(character_uuid=character_id, cause=cause, location=location_id, tick=tick)` — **no `killer_id`** (the function takes none) |
| `chain_transfer` (TAKE, `if patient_onchain`) | `on_item_transferred(item_id, new_owner_id)` | `transfer_item(item_uuid=item_id, new_owner_uuid=new_owner_id)` — **arity 2** |

`LiveChainMirror` wraps these two `chain.py` functions and no-ops when `chain.is_enabled()` is false; `NoopChainMirror` is the test double.

> **`tick` source.** `chain.py`'s `record_death` requires a `tick: int`. The Day-1 engine maintains a single monotonically increasing `world_tick` counter (incremented once per resolved action; held on the engine's session state, started at 0 at boot). `LiveChainMirror.on_character_death` reads the current `world_tick`. If wiring a turn counter is deemed out of scope for the skeleton, **drop `tick` from the Day-1 chain mirror** and pass a constant `0` — the on-chain death event still records correctly; `tick` is a sequencing nicety, not a correctness requirement. (Recommendation: a simple boot-time counter; pick one and state it in the build.)

> **`on_item_dropped` is cut from skeleton scope.** No Day-1 construction drops items (death does not auto-loot — §3.4), so the `drop_item` path and an `on_item_dropped` method are deliberately **not** part of the skeleton `ChainMirror`. They return when a DROP/LOOT construction is authored (§9.2).

**What is mirrored:** character death (after the `is_dead` `set_attr` + `DIED_IN` `link` commit) and item ownership change on TAKE (after `transfer_item` commits, when the item is `onchain`). Character/item *registration* happens in the world-gen pipeline, not the executor.

**Conflict invariant:** chain is canonical for item ownership and permadeath. On a Mongo-succeeds/chain-fails split, Mongo is authoritative for the current session; the next session start reconciles via `chain_client.fetch_items(owner_uuid)` against `item.owner_uuid` (chain wins; the reconciler updates Mongo, not chain). This lazy reconcile lives in an `S0Reconciler` called at session startup, never by the executor.

### 6.4 Wiring

```python
db = MongoClient(settings.MONGO_URI)[settings.MONGO_DB]
repo = MongoStateRepository(db); await repo.ensure_indexes()
mirror = LiveChainMirror()
state_repo: StateRepository = repo       # injected, never a global import
chain_mirror: ChainMirror = mirror
```

The executor is fully testable with `InMemoryStateRepository` + `NoopChainMirror` — no web3, no network, no Mongo.

---

## 7. Cxns-as-MCP-tools + the effect executor

### 7.1 Construction → MCP tool registration

The constructicon **is** the agent tool palette. Each `CxnDef` is registered as one MCP tool on the existing `FastMCP("memento-engine")` instance built by `build_mcp_app`. A new `_register_construction_tools(mcp, ...)` helper (or the equivalent `register_cxn_tools` in `gateway/cxn_tools.py`) is called from `build_mcp_app` alongside the existing registration helpers; it iterates `CONSTRUCTION_REGISTRY` and registers each cxn under its `mcp_tool_name`.

**Exact MCP tool signatures (Day 1 — UUID args only).** `agent` is **never** a tool parameter: it comes from the caller's JWT `sub` claim (the acting entity's UUID), read from `_current_identity` exactly as `_check_tool_access` does today. Every other role is a UUID argument.

```python
@mcp.tool
async def mm_move(destination: str) -> dict: ...
    # destination: room UUID. agent = JWT sub. location role = agent's current room (read).

@mcp.tool
async def mm_attack(patient: str, instrument: str | None = None) -> dict: ...
    # patient: target character UUID. instrument: weapon UUID, optional (defaults to the
    # agent's equipped main-hand weapon UUID, resolved BEFORE the Weapon restriction check).
    # agent = JWT sub. location role = agent's current room (read).

@mcp.tool
async def mm_take(patient: str) -> dict: ...
    # patient: item UUID. agent = JWT sub. location role = agent's current room (read).
```

| Construction | MCP tool | Params (UUIDs; `agent` = JWT `sub`, not a param) |
|---|---|---|
| MOVE | `mm_move` | `destination: str` (room UUID) |
| ATTACK | `mm_attack` | `patient: str`, `instrument: str \| None = None` |
| TAKE | `mm_take` | `patient: str` (item UUID) |

- **`agent` from JWT** (I2): consistent with the existing `_check_tool_access` identity model. This **differs from the legacy `mm_move_to(entity_name, destination=name)`**, which took the actor and destination as **name strings**; the new tools take UUIDs and derive the actor from the token.
- **`location` defaults to the agent's room** (M1): the `location` role for all three cxns is the agent's current `location_uuid` (one read of the agent doc), never a tool arg. It scopes `same_room` / `exit_exists` and is the `DIED_IN` target.
- **`instrument` defaults from equipped, BEFORE the restriction check** (M2): when `mm_attack` omits `instrument`, the executor resolves the agent's equipped main-hand weapon UUID **first**, then the `instrument` `required_labels=["Weapon"]` restriction and `agent_armed` guard run against the resolved UUID. (If nothing is equipped and none is passed, `agent_armed` fails cleanly.)

The existing `_check_tool_access(tool_name)` capability gate applies unchanged, keyed on the construction's MCP name (see §8.5 for the required kit edit) — per-construction capability gating with no new infrastructure. Each handler builds the `MatchedCxn` directly from the JWT agent + UUID args (no comprehend on Day 1), runs `EffectExecutor.execute`, returns the `StateUpdate` dict, and calls `broadcast_tool_event(...)` to keep the live WebSocket feed intact.

### 7.2 The EffectExecutor

`engine/src/memento/cxn/executor.py`. Single entry point: `execute(cxn, caller_id, bindings) -> StateUpdate dict`. Three strictly ordered phases, **no LLM in any phase**:

**Phase 1 — Selection-restriction + guard validation (reads only).** For each restriction, load the bound entity's labels (`StateRepository.get_labels`) and assert all `required_labels` present and no `forbidden_labels` present. Then run the cxn's named guards (`exit_exists`, `agent_armed`, `target_damageable`, `same_room`, `item_carryable`, `capacity_ok`). On any failure, raise `ConstructionError(reason="selection_restriction" | "<guard>")` before touching any store. This replaces the legacy open-ended LLM plausibility gate for the three actions.

**Phase 1.5 — Compute transients (pure, no LLM, no RNG).** Before any write, the executor populates the three transients (§4.4): `damage`, `computed_hp`, `death_suffix`, using the pure integer helpers in `engine/src/memento/cxn/arithmetic.py` (§3.5). It does **not** call `tools/mechanics.py` (those are CrewAI `@tool`s — prose-returning, str-arg, RNG-using).

**Phase 2 — Transactional primitives (all-or-nothing).** Open the transactional context; for each `substrate == "transactional"` primitive whose `if_condition` evaluates `True` (closed `CONDITIONS` dict, §4.4), resolve `$role` and `$computed_*` references, call the mapped `StateRepository` method, and record a `StateDelta`. On any failure, run the compensation table (§3.3) in reverse and raise `ConstructionError(reason="transactional_failed")`.

**Phase 3 — Cross-substrate commit (memory + optional chain).** After the transactional phase commits, resolve `@episode_template` + its `{}` substitutions and fire `memory` primitives (`ingest_episode` — best-effort, isolated error handling, non-fatal); then, when `cxn.chain_mirror` and chain enabled, the `chain` primitives through `ChainMirror` in a worker thread. Neither rolls back transactional state.

The executor then builds a `StateUpdate` (the existing `memento/models/state_update.py` model — **`schema_version` stays `1`**; this skeleton makes no v2 change, adds no fields to the model, and ships no new client owner) from `get_actor_snapshot`, decorating it with the cxn-specific event fields the v1 model already carries (`CombatEvent` for ATTACK, `InventoryEvent` for TAKE), and returns `update.model_dump(exclude_none=True)`.

### 7.3 Turn flow

**Day 1 — no TurnRouter, no fork.** Agents (players-as-agents and NPCs) call `mm_move` / `mm_attack` / `mm_take` directly as MCP tools with UUIDs they already hold from `mm_get_state` / `mm_room_manifest`. The MCP handler builds the `MatchedCxn` directly and runs `EffectExecutor.execute` — that is the entire Day-1 turn path. On `ConstructionError` the handler returns `{status:"rejected", cause}` with no state change. Narration may be fired async/non-blocking after the `StateUpdate` is returned, but it never re-decides outcomes (state is authoritative and immediate; narration *describes what the StateUpdate already records*).

**Milestone 2 — `TurnRouter` for free-form text.** `engine/src/memento/cxn/turn_router.py` is added at Milestone 2 as the per-turn entry point for **raw-text** player actions (called from `matrix_listener`). It comprehends input into a `SemanticFrame`, and:

- If a cxn matches and `confidence ≥ CXN_CONFIDENCE_THRESHOLD` (default `0.80`, env `CXN_CONFIDENCE_THRESHOLD`): run `EffectExecutor.execute` (the same executor as Day 1), deliver the `StateUpdate`, fire narration async.
- Otherwise: fall back to the unchanged legacy `RoundController.run()` via `asyncio.to_thread`.

The `TurnRouter`, the confidence threshold, and the legacy fork are **not** part of the Day-1 build — they exist only once comprehension (§5, Milestone 2) lands. The Day-1 executor signature is unchanged by their later arrival.

### 7.4 Error contract

Stable string-prefixed errors, consistent with the existing MCP surface (`_check_tool_access` already raises `capability_missing:` / `identity_missing:`):

| Prefix | Meaning | HTTP analogue |
|---|---|---|
| `selection_restriction:` | binding/guard failed | 422 |
| `construction_not_found:` | `cxn_id` not in registry | 404 |
| `transactional_failed:` | Phase 2 rolled back; store unchanged | 500 |
| `capability_missing:` | existing gate; entity lacks permission | 403 |
| `identity_missing:` | existing gate; no JWT context | 401 |

### 7.5 Required capability-kit edit (do not skip)

The three new tool names must be registered in the capability tables at `engine/src/memento/tools/tool_labels.py`, or `_check_tool_access` → `check_tool_access` → `get_allowed_tools` will raise `capability_missing:` for **every** NPC that calls them (only `INNATE_TOOLS` and kit/label tools pass the gate).

**Concrete edit:** add `mm_move`, `mm_attack`, `mm_take` to the `NPC` kit in `KITS` (the legacy `mm_move_to` / `mm_resolve_combat` / `mm_inventory_transfer` live there today). Add `mm_move` and `mm_take` to the `Player` kit as well (the `Player` kit deliberately excludes combat — keep `mm_attack` out of it unless players are meant to initiate combat). Until this edit lands, NPCs cannot invoke any construction tool. (No change to `_check_tool_access` itself is needed — it is keyed on tool name and already reads identity from the JWT.)

---

## 8. Component boundaries, interfaces, one-day plan, test strategy

### 8.1 Components

Five Day-1 components, each independently buildable and stubable from Day-1 morning. No component imports another's internal module — only `cxn/types.py` and the other's `Protocol`. This is the hard seam enabling parallel work.

| # | Component | File(s) | Responsibility | Depends on | Dev | Stub |
|---|---|---|---|---|---|---|
| C1 | StateRepository | `engine/src/memento/state/` | Authoritative transactional store + port + MCP tool registration glue | MongoDB (`motor`) | A | `InMemoryStateRepository` |
| C2 | MemoryClient | `engine/src/memento/memory/` | Thin kernel HTTP client (`ingest_episode`; optional `search_context`) | `httpx`, `KERNEL_BASE_URL` | B | `NullMemoryClient`, `CapturingMemoryClient` |
| C3 | Constructicon | `engine/src/memento/cxn/constructicon.py`, `definitions.py`, `arithmetic.py`, `conditions.py` | Static registry; `match(frame) → MatchedCxn`; pure damage helper; closed condition dict | nothing (pure data) | C | (definitions written directly) |
| C4 | EffectExecutor | `engine/src/memento/cxn/executor.py` | 3-phase deterministic execution + transient compute + `StateUpdate` build | C1, C2, C3, ChainMirror | C | — |
| C6 | McpToolBridge | `gateway/src/gateway/cxn_tools.py` + `mcp_server.py` | Register one MCP tool per cxn (UUID args); JWT-agent; **kit edit (§7.5)** | C1–C4, `FastMCP` | A | — |

**Milestone 2 (not Day 1):** C5 `ComprehensionClient` (`engine/src/memento/cxn/kernel_client.py`, the `kernel/comprehend` HTTP client) and `TurnRouter` (`engine/src/memento/cxn/turn_router.py`, free-text orchestrator). Neither is built or stubbed in the Day-1 slice. There is **no** `PatternComprehensionClient` / regex stub on Day 1.

### 8.2 Shared DTO module

All cross-component DTOs live in `engine/src/memento/cxn/types.py`: `SemanticFrame`, `StatePrimitive`, `SelectionRestriction`, `CxnDef`, `MatchedCxn`, `StateDelta`, `EpisodeIn`, `ExecutionContext`, `ConstructionError`. (`ExecutionContext` carries the bound roles, loaded entity docs, the three computed transients, and the `world_tick` — it is what `CONDITIONS` predicates and `$`/`{}` substitution read.) `EffectResult`, `WorldContext` are Milestone-2 additions (search/comprehend plumbing) and are not required Day 1. Every dev imports DTOs from this one place; stubs are type-safe against it.

### 8.3 One-day build plan

**Morning — scaffold + interfaces + stubs (~3h, parallel).** First deliverable (15 min, any dev, merged before the rest): `cxn/types.py`. Then:
- **Dev A** — `StateRepository` Protocol + `InMemoryStateRepository` (full CRUD, the Day-1 default store); scaffold `gateway/cxn_tools.py`. (`MongoStateRepository` is a stretch — see §8.6.)
- **Dev B** — `MemoryClient` Protocol + `NullMemoryClient`/`CapturingMemoryClient` (the Day-1 default); scaffold the `httpx`-backed `KernelMemoryClient` against the existing `kernel/index`. (No comprehension client — Milestone 2.)
- **Dev C** — `cxn/definitions.py` (the three `CxnDef` literals, fully specified); `cxn/arithmetic.py` (§3.5 pure helpers); `cxn/conditions.py` (closed `CONDITIONS` dict, §4.4); `Constructicon.match`; scaffold `EffectExecutor` with an empty-pass guard registry.
- **All** — agree fixture UUIDs/shapes in `tests/fixtures.py`.

**Midday — implement against interfaces (~3h).** Dev A: `register_cxn_tools` (build `MatchedCxn` from JWT agent + UUID args → `match` → `execute`); the §7.5 kit edit. Dev B: real `httpx` `ingest_episode` against `kernel/index`, unit-tested against `CapturingMemoryClient` shape. Dev C: guards (`exit_exists`, `agent_armed`, `target_damageable`, `same_room`, `item_carryable`, `capacity_ok`) + `EffectExecutor.execute` (1.5/2/3 phases, transient compute, compensation, episode ingest), unit-tested with `InMemoryStateRepository` + `NullMemoryClient`.

**Afternoon — wire the vertical slice (~2.5h).** Wire C1/C2/C3/C4/C6 in gateway startup with `InMemoryStateRepository` + `NoopChainMirror` + `CapturingMemoryClient`; issue three manual MCP calls (`mm_move`, `mm_attack`, `mm_take`) with fixture UUIDs; confirm exact `state_deltas` in responses and captured episode text.

**End of day — smoke test (~30 min).** `pytest tests/integration/test_vertical_slice.py`.

### 8.4 Test strategy

**Principle: no LLM and no NLP in any test.** Because Day 1 is UUID-args-only, there is nothing to comprehend — tests drive the executor with a **directly-constructed `MatchedCxn`** (the cxn def + a `bound_roles` dict of fixture UUIDs), not a regex over text. State → `InMemoryStateRepository`; memory → `NullMemoryClient` / `CapturingMemoryClient`; chain → `NoopChainMirror`.

Constructing a filled construction for a test (no parsing, no `PatternComprehensionClient`):
```python
matched = MatchedCxn(
    cxn=CONSTRUCTION_REGISTRY["ATTACK"],
    bound_roles={"agent": KAEL, "patient": GOBLIN, "instrument": IRON_SWORD, "location": ASH_MARKET},
)
update = await executor.execute(matched.cxn, caller_id=KAEL, bindings=matched.bound_roles)
```

Test layers:
- **Arithmetic unit tests** — `damage(8, 3, 2) == 9`, `damage(1, 0, 50) == 0`, `clamp_hp(9, 9) == 0` (pure, exact, no RNG).
- **One unit test per `StateRepository` write** (`set_attr`, `move_entity`, `transfer_item`, `link`/`unlink`) over exact field values, against `InMemoryStateRepository`.
- **One smoke test per construction**, asserting exact `StateDelta`s + captured episode text: MOVE → `move_entity` delta + 1 ingest; ATTACK → `hp` delta `9 → 0` (exact) + death sub-case sets `is_dead=True`, links `DIED_IN`, and fires `chain_kill` (captured via a recording `ChainMirror`); TAKE → `transfer_item` delta to agent.
- **Guard-failure tests** — e.g. ATTACK with an unarmed agent raises `ConstructionError(reason="agent_armed")` before any write; the store is untouched.

**Integration / rollback test:** uses `InMemoryStateRepository` (default) or a real Mongo **replica set**. It does **not** use `mongomock-motor` for transactional assertions — `mongomock-motor` does not support transactions (§3.3), so it cannot exercise multi-doc rollback.

**CI gate:** `pytest tests/unit tests/integration/test_vertical_slice.py` — all assertions over exact `StateDelta` values, zero LLM calls, zero NLP.

### 8.5 Day-1 definition of done (realistic slice) vs. stretch

**Day-1 "done" (the committed slice):**
- `cxn/types.py`, `definitions.py` (3 cxns), `arithmetic.py`, `conditions.py`, `constructicon.py`, `executor.py`.
- `StateRepository` Protocol + **`InMemoryStateRepository`** as the wired default store.
- `MemoryClient` Protocol + **`CapturingMemoryClient`** as the wired default; `NoopChainMirror`.
- C6: `mm_move` / `mm_attack` / `mm_take` registered as MCP tools (UUID args, JWT agent) + the §7.5 kit edit.
- The full test suite of §8.4 green, including the three deterministic-cxn smoke tests over exact `StateDelta`s.
- **No comprehension, no Mongo, no real chain, no real `kernel/index` round-trip required** to call the slice done.

**Stretch (nice-to-have on Day 1, not required):**
- `MongoStateRepository` (`motor`) + a replica-set integration run.
- Real `httpx` `KernelMemoryClient` posting to a live `kernel/index`.
- `LiveChainMirror` against `tools/chain.py` with `CHAIN_ENABLED=true`.

**Milestone 2 (separate):** `kernel/comprehend` (graph-memory team), `ComprehensionClient`, `EntityResolver`, `TurnRouter`, free-text player path.

---

## 9. Out of scope / forward map

### 9.1 Replaced in this skeleton (MOVE / ATTACK / TAKE only)

`ClassificationCrew`, `CombatDetectorCrew`, `InventoryDetectorCrew`, `EventMergeCrew`, `CombatAssessmentCrew`, `AttackResolutionCrew`, `ConsequenceCrew`, `EventDetectionFlow`, `CombatFlow`, `MemoryConsolidationCrew`, `NpcMemoryCrew`, `EpisodicMemoryFlow`, `RoundController.detect_events()/resolve_events()`, the `mm_check_plausibility` LLM gate (for these three actions), the legacy `mm_move_to`/`mm_resolve_combat`/`mm_inventory_transfer` tools, and the ~30 `tools/kg.py` Delve call-sites — all eliminated for the three skeleton actions by the construction system. The legacy `RoundController` and its tools are **not deleted**; on Day 1 they simply stay in place (the construction tools are additive — agents call them directly). They become a *fallback* only at Milestone 2, when the free-text `TurnRouter` (§7.3) forks low-confidence input back to `RoundController.run()` until every action category is covered.

### 9.2 Left alone (unchanged, out of scope)

Generation crews (`world_gen/*`, `npc_gen/*`, `item_gen/*`, `loot_designer`, `cartographer`, `portraitist`, `ascii_art`) — genuinely generative, correct to keep their inference cost. `NarrationCrew` / `mm_narrate` / `mm_npc_response` — inference at the novelty frontier, now post-state and non-blocking. `mm_heartbeat`/`HeartbeatRunner`. `tools/chain.py` + `gateway/chain_client` (fronted by `ChainMirror`). `gateway/mcp_server.py` infra (JWT auth, `_BearerAuthMiddleware`, `broadcast_tool_event`) — new tools register via the same factory. `agent_controller.py` / `agent_spawner.py`. `WorldChangeDetectorCrew`, `QuestDetectorCrew`, `QuestFlow`, `ReputationCrew` and all other Delve call-sites (quest/faction/lore/codex) — candidate future constructions (QUEST-ACCEPT, REPUTATION-SHIFT, COMPLETE-QUEST), not redesigned here. **Item-drop / loot-on-death** (the cut `on_item_dropped` path + `chain.py drop_item`) is likewise a future DROP/LOOT construction, not in the skeleton. The permadeath chain write and room-topology authoring remain orthogonal.

### 9.3 Forward map — S3: Generative Composition and Entrenchment (a later spec)

Out of scope here, established but not exercised by the skeleton:

- **Generative composition** — agents minting new constructions from primitives under the kernel grammar's constraints; valid new cxns registering as MCP tools. The `Constructicon` registry is static here; `all_cxns()` returns exactly the three authored definitions.
- **Entrenchment** — usage-frequency weighting, construction promotion/demotion, write-back from execution frequency into the constructicon or kernel grammar. No entrenchment counters or weights in this spec.
- **Registration-time validation** — the kernel grammar's type system checking that a new `CxnDef`'s effect template composes valid primitives and that roles bind under selection restrictions (the **constraint authority**). Hand-authored cxns don't need it yet.
- **Full FCG grammar authoring** — memento-mori authors only effect templates; the kernel grammar (and the `kernel/comprehend` implementation) is the kernel team's concern.
- **Other Delve call-sites, quest/faction transitions, the NPC autonomous turn loop** (initiative/scheduling/targeting AI upstream of the tools).

The walking skeleton establishes the `EffectExecutor`, the state primitives, the `StateRepository`/`MemoryClient`/`ChainMirror` ports, and the static `Constructicon` that S3 extends. Nothing in the skeleton precludes S3 — the construction model already carries the role schema, selection restrictions, and effect template that generative composition and entrenchment will build on.
