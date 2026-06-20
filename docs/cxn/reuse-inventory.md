# cxn Reuse Inventory

Back to: [docs/START-HERE.md](../START-HERE.md) | Forward: [docs/cxn/thread-sheet.md](thread-sheet.md)

This document records the **verified** signatures and consumption points for every
existing symbol the cxn construction control system reuses. Every `file:line`
below was confirmed by reading the source file directly. No signature is quoted
from the spec alone.

---

## 1. `engine/src/memento/tools/chain.py`

### 1.1 `record_death`

**Spec says (§6.3):** `ChainMirror.on_character_death` dispatches to
`record_death(character_uuid, cause, location, tick)` — **no `killer_id`**.

**Verified signature:**

```python
# engine/src/memento/tools/chain.py:136
def record_death(character_uuid: str, cause: str, location: str, tick: int) -> None:
```

`file:line` — `engine/src/memento/tools/chain.py:136`

Confirmed: takes **no `killer_id`** parameter. Fire-and-forget (`_send_tx` in a
daemon thread); errors are logged and never propagate. The function maps to the
`killCharacter` MUD system call.

**cxn consumption:** C4 `EffectExecutor` calls this indirectly via
`LiveChainMirror.on_character_death` (§6.3). It is the terminal step in the
ATTACK `chain_kill` primitive, firing only when `computed_hp <= 0` (the
`hp_depleted` condition). The executor never imports `chain.py` directly;
`ChainMirror` is the seam that allows `NoopChainMirror` in tests.

---

### 1.2 `transfer_item`

**Spec says (§6.3):** `chain_transfer` primitive dispatches to
`transfer_item(item_uuid=item_id, new_owner_uuid=new_owner_id)` — **arity 2**.

**Verified signature:**

```python
# engine/src/memento/tools/chain.py:169
def transfer_item(item_uuid: str, new_owner_uuid: str) -> None:
```

`file:line` — `engine/src/memento/tools/chain.py:169`

Confirmed: exactly **2 positional parameters** (plus implicit `self` absent —
this is a module-level function). Maps to the `transferItem` MUD system call.
Fire-and-forget like all `chain.py` public functions.

> **Spec vs code — unified signature alignment:** The spec §6.2 defines the
> `StateRepository.transfer_item` port method with a 4-parameter signature
> `(item_uuid, from_uuid, to_uuid, to_location_uuid=None)`. That is the
> *transactional-store* port, not this chain function. The chain `transfer_item`
> in `chain.py` remains a 2-parameter call `(item_uuid, new_owner_uuid)`. No
> mismatch — the spec correctly documents both as separate surfaces. The
> `mm_inventory_transfer` handler in `mcp_server.py:577` already calls
> `_chain.transfer_item(item_id, to_entity)` with arity 2, confirming the
> existing usage pattern that `LiveChainMirror` must replicate.

**cxn consumption:** C4 `EffectExecutor` via `LiveChainMirror.on_item_transferred`
(§6.3). Fires as the `chain_transfer` primitive in the TAKE construction when the
item doc carries `onchain == True`. Always the last step; never participates in
rollback.

---

### 1.3 `is_enabled`

**Spec says (§6.3):** `LiveChainMirror` wraps the two `chain.py` functions and
no-ops when `chain.is_enabled()` is false.

**Verified signature:**

```python
# engine/src/memento/tools/chain.py:187
def is_enabled() -> bool:
```

`file:line` — `engine/src/memento/tools/chain.py:187`

Reads `CHAIN_ENABLED` from `memento.config.chain`. Returns `False` in any
environment where `CHAIN_ENABLED` is not set (local dev / CI default).

**cxn consumption:** `LiveChainMirror` guards all chain writes behind
`chain.is_enabled()`. When false, `on_character_death` and `on_item_transferred`
are no-ops, letting the construction execute cleanly in chain-less environments.

---

## 2. `engine/src/memento/tools/mechanics.py` — DON'T REUSE

**Spec says (§3.5):** The executor **must not** call `tools/mechanics.py`.
`calculate_damage` and `roll_skill_check` are disqualified on three counts:
(1) `@tool`-decorated (CrewAI), (2) take string args and return prose, (3)
`roll_skill_check` uses `random.randint`. All arithmetic lives in
`engine/src/memento/cxn/arithmetic.py` instead.

**Verified — `calculate_damage`:**

```python
# engine/src/memento/tools/mechanics.py:22
@tool("Calculate Damage")
def calculate_damage(weapon_damage: str, attacker_strength: str, defender_armor: str) -> str:
```

`file:line` — `engine/src/memento/tools/mechanics.py:22`

Returns a prose string, e.g. `"Damage: 7 (weapon 5 + strength 4 = 9, minus armor 2)"`.

**Verified — `roll_skill_check`:**

```python
# engine/src/memento/tools/mechanics.py:8
@tool("Roll Skill Check")
def roll_skill_check(skill_level: str, difficulty: str, modifiers: str = "0") -> str:
```

`file:line` — `engine/src/memento/tools/mechanics.py:8`

Uses `random.randint(1, 20)` at line 13. Returns prose PASS/FAIL string.

> **DON'T REUSE — confirmed.** Both functions are `@tool`-decorated via
> `memento.core.tool`, accept only string arguments (no typed ints), and return
> human-readable prose. `roll_skill_check` is non-deterministic (`random.randint`).
> The construction control layer needs pure, typed, deterministic integers. Use
> `cxn/arithmetic.py` exclusively.

**Note:** `mcp_server.py` currently wraps these functions via `.func` attribute
(lines 213–215, 228–229) to strip the CrewAI decorator for the `mm_calculate_damage`
and `mm_evaluate_disposition` read tools. The cxn executor must **not** follow
this pattern — it must call `arithmetic.py` helpers directly.

---

## 3. `engine/src/memento/tools/tool_labels.py` — KITS tables

**Spec says (§7.5):** Add `mm_move`, `mm_attack`, `mm_take` to the `NPC` kit;
add `mm_move` and `mm_take` to the `Player` kit. Until this edit lands, `_check_tool_access`
raises `capability_missing:` for every NPC invoking a construction tool.

**Verified `KITS` dict:**

`file:line` — `engine/src/memento/tools/tool_labels.py:34`

```python
KITS: dict[str, set[str]] = {
    "NPC": {
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
        "mm_give_item",
        "mm_create_item",
        "mm_inventory",
        "mm_inventory_transfer",
        "mm_remember_event",
        "mm_update_entity",
        "mm_move_to",
        "mm_move_within",
        "mm_give_quest",
    },
    ...
    "Player": {
        "mm_inventory",
        "mm_move_to",
        "mm_check_plausibility",
        "mm_give_item",
    },
}
```

**`NPC` kit current legacy tools** (lines 37–49): `mm_resolve_combat`,
`mm_assess_combat`, `mm_check_plausibility`, `mm_give_item`, `mm_create_item`,
`mm_inventory`, `mm_inventory_transfer`, `mm_remember_event`, `mm_update_entity`,
`mm_move_to`, `mm_move_within`, `mm_give_quest`.

**`Player` kit current legacy tools** (lines 109–113): `mm_inventory`, `mm_move_to`,
`mm_check_plausibility`, `mm_give_item`.

**Required edit (§7.5, owned by C6 / McpToolBridge task):**
- Add `"mm_move"`, `"mm_attack"`, `"mm_take"` to `KITS["NPC"]`
- Add `"mm_move"`, `"mm_take"` to `KITS["Player"]` (deliberate omission of `mm_attack`)

**cxn consumption:** C6 `McpToolBridge` (`gateway/src/gateway/cxn_tools.py` +
`mcp_server.py`, §8.1). The `get_allowed_tools(labels)` function at line 147 is
called by `check_tool_access` in `gateway/engine_auth.py`, which `_check_tool_access`
(see §5 below) delegates to. No change to the function itself; only `KITS` entries
are edited.

---

## 4. `engine/src/memento/models/state_update.py` — `StateUpdate` and event models

**Spec says (§7.2):** The executor builds a `StateUpdate` from `get_actor_snapshot`,
decorates it with `CombatEvent` for ATTACK and `InventoryEvent` for TAKE, and returns
`update.model_dump(exclude_none=True)`. `schema_version` stays `1` — the skeleton
adds no fields and ships no client changes.

**Verified `StateUpdate`:**

```python
# engine/src/memento/models/state_update.py:102
class StateUpdate(BaseModel):
    schema_version: int = 1
    location: str | None = None
    health: int | None = None
    max_health: int | None = None
    level: int | None = None
    xp: int | None = None
    exits: list[ExitUpdate] | None = None
    npcs: list[EntityRefUpdate] | None = None
    items: list[EntityRefUpdate] | None = None
    inventory: list[InventoryItemUpdate] | None = None
    room_map: RoomMapUpdate | None = None
    world_time: WorldTimeDisplay | None = None
    skills: dict[str, int] | None = None
    events: EventSummary | None = None
    active_quests: list[QuestSummary] | None = None
    factions: list[FactionStanding] | None = None
    status: str | None = None
    cause: str | None = None
    subsystem_warnings: list[str] = []
    warning_details: dict[str, str] | None = None
```

`file:line` — `engine/src/memento/models/state_update.py:102`

**Verified `CombatEvent`** (consumed by `events: EventSummary | None`):

```python
# engine/src/memento/models/state_update.py:61
class CombatEvent(BaseModel):
    action_type: str = ""
    target_name: str = ""
    damage_dealt: int | None = None
    target_dead: bool = False
    xp_gained: int = 0
```

`file:line` — `engine/src/memento/models/state_update.py:61`

**Verified `InventoryEvent`:**

```python
# engine/src/memento/models/state_update.py:69
class InventoryEvent(BaseModel):
    event_type: str = ""   # PICKUP/DROP/USE/EQUIP/TRADE
    item_name: str = ""
```

`file:line` — `engine/src/memento/models/state_update.py:69`

**Verified `EventSummary`** (the `events` field on `StateUpdate`):

```python
# engine/src/memento/models/state_update.py:76
class EventSummary(BaseModel):
    categories: list[str] = []
    combat: CombatEvent | None = None
    inventory_changes: list[InventoryEvent] = []
    quest_update: str = ""
    reputation_changes: dict[str, float] = {}
```

`file:line` — `engine/src/memento/models/state_update.py:76`

**cxn consumption:** C4 `EffectExecutor` (§7.2) returns
`StateUpdate.model_dump(exclude_none=True)`. For ATTACK outcomes the executor
populates `events.combat` (`CombatEvent`). For TAKE outcomes it populates
`events.inventory_changes` (`InventoryEvent`). `schema_version` must remain `1`;
no new fields are added to this model in the Day-1 skeleton.

---

## 5. `gateway/src/gateway/mcp_server.py` — gateway seam

### 5.1 `_check_tool_access`

**Spec says (§7.1, §7.5):** The existing `_check_tool_access(tool_name)` capability
gate applies unchanged, keyed on the construction's MCP tool name.

**Verified signature:**

```python
# gateway/src/gateway/mcp_server.py:46
async def _check_tool_access(tool_name: str) -> str:
```

`file:line` — `gateway/src/gateway/mcp_server.py:46`

Resolves caller identity from `_current_identity` ContextVar (set by `_BearerAuthMiddleware`
after JWT decode) and delegates to `gateway.engine_auth.check_tool_access(entity_id, tool_name)`.
Returns the resolved `entity_id` string.

Stable error contract (load-bearing for tests and bonfires-ai):
- `RuntimeError("identity_missing: ...")` — no JWT context
- `RuntimeError("capability_missing: ...")` — entity lacks permission

**cxn consumption:** C6 `McpToolBridge` (`gateway/cxn_tools.py`). Every cxn
MCP tool handler calls `await _check_tool_access(tool_name)` as its first step,
exactly as all existing mutation handlers do. No change to this function's
signature or contract; the new tool names (`mm_move`, `mm_attack`, `mm_take`)
must be present in the `KITS` tables (§3 above) for the gate to pass.

---

### 5.2 `broadcast_tool_event`

**Spec says (§7.2):** After the `StateUpdate` is returned, the MCP handler calls
`broadcast_tool_event(...)` to keep the live WebSocket feed intact.

**Verified signature** (imported from `gateway.engine_events`):

```python
# gateway/src/gateway/engine_events.py:14
async def broadcast_tool_event(
    ws_hub,
    tool: str,
    npc_id: str,
    summary: str,
    data: dict | None = None,
) -> None:
```

`file:line` — `gateway/src/gateway/engine_events.py:14`

No-op when `ws_hub is None` (line 28). Resolves the NPC's display name and
current location from `gateway.npc_registry` internally; callers pass the raw
entity id.

**cxn consumption:** C6 `McpToolBridge` cxn tool handlers call
`await broadcast_tool_event(ws_hub, tool=cxn_tool_name, npc_id=entity_id, summary=...)`.
`ws_hub` is captured from `build_mcp_app`'s argument, same pattern as
`_register_mutation_tools`. The `data` kwarg is optional and unused by the
three skeleton constructions; existing callers (e.g. `mm_npc_response` at line 808)
use it for emotion/target metadata.

---

### 5.3 `FastMCP` / `build_mcp_app` registration factory

**Spec says (§7.1, §8.1):** A new `_register_construction_tools(mcp, ...)` helper
(or `register_cxn_tools` in `gateway/cxn_tools.py`) is called from `build_mcp_app`
alongside the existing registration helpers.

**Verified `build_mcp_app` signature:**

```python
# gateway/src/gateway/mcp_server.py:1064
def build_mcp_app(
    ws_hub: "WebSocketHub",
    bridge: "MatrixBridge | None",
    narrator_registry: "dict[str, str]",
) -> "ASGIApp":
```

`file:line` — `gateway/src/gateway/mcp_server.py:1064`

Creates `FastMCP("memento-engine")`, calls the four existing registration helpers
(`_register_read_tools`, `_register_mutation_tools`, `_register_combat_narrative_tools`,
`_register_design_tools`), wraps in `_BearerAuthMiddleware`, exposes
`session_manager`, and returns the ASGI app.

**`FastMCP` import:**

```python
# gateway/src/gateway/mcp_server.py:22
from mcp.server.fastmcp import FastMCP
```

`file:line` — `gateway/src/gateway/mcp_server.py:22`

**cxn consumption:** C6 `McpToolBridge`. The Day-1 edit adds one call inside
`build_mcp_app`:

```python
from gateway.cxn_tools import register_cxn_tools
register_cxn_tools(mcp, ws_hub, repo, mirror)
```

No other changes to this function. `narrator_registry` is not needed by cxn tools
(no Matrix trigger in the three skeleton constructions).

---

## Summary table

| Symbol | `file:line` | cxn component | Spec section | Status |
|--------|-------------|---------------|--------------|--------|
| `chain.record_death(character_uuid, cause, location, tick)` | `chain.py:136` | C4 via `LiveChainMirror` | §6.3 | REUSE — no `killer_id`, confirmed |
| `chain.transfer_item(item_uuid, new_owner_uuid)` | `chain.py:169` | C4 via `LiveChainMirror` | §6.3 | REUSE — arity 2, confirmed |
| `chain.is_enabled()` | `chain.py:187` | C4 via `LiveChainMirror` | §6.3 | REUSE |
| `mechanics.calculate_damage(str, str, str) -> str` | `mechanics.py:22` | — | §3.5 | DON'T REUSE — `@tool`, prose, non-deterministic |
| `mechanics.roll_skill_check(str, str, str="0") -> str` | `mechanics.py:8` | — | §3.5 | DON'T REUSE — `@tool`, prose, `random.randint` |
| `KITS["NPC"]` / `KITS["Player"]` | `tool_labels.py:34` | C6 McpToolBridge | §7.5 | EDIT REQUIRED — add `mm_move`/`mm_attack`/`mm_take` |
| `StateUpdate` (Pydantic, v1) | `state_update.py:102` | C4 EffectExecutor | §7.2 | REUSE — `schema_version=1`, no new fields |
| `CombatEvent` | `state_update.py:61` | C4 EffectExecutor | §7.2 | REUSE |
| `InventoryEvent` | `state_update.py:69` | C4 EffectExecutor | §7.2 | REUSE |
| `EventSummary` | `state_update.py:76` | C4 EffectExecutor | §7.2 | REUSE |
| `_check_tool_access(tool_name) -> str` | `mcp_server.py:46` | C6 McpToolBridge | §7.1 | REUSE — unchanged; needs kit edit |
| `broadcast_tool_event(ws_hub, tool, npc_id, summary, data=None)` | `engine_events.py:14` | C6 McpToolBridge | §7.2 | REUSE |
| `build_mcp_app(ws_hub, bridge, narrator_registry)` | `mcp_server.py:1064` | C6 McpToolBridge | §7.1 | REUSE — add one `register_cxn_tools` call inside |
