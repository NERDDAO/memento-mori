# Inventory Management via Manifest Primitives

**Date:** 2026-04-04
**Status:** Design

## Context

Memento Mori has item models, generation crews, an inventory detector crew, and a read-only client panel — but no interactive inventory system. Players can't equip, drop, use, or trade items through the UI. The chain Items table exists but is write-only. This sprint builds the full inventory loop: chain as ownership truth, manifests as derived views, structured actions for instant feedback.

## Design Decisions

- **Chain = canonical owner.** The MUD Items table tracks who owns what and where items are. KG stores rich metadata (description, effects, lore). The inventory manifest merges both.
- **Manifest-first architecture.** `inventory_manifest.py` follows the proven `room_manifest.py` pattern — assembles a complete view from chain + KG.
- **Hybrid UX.** Structured REST endpoints for deterministic ops (equip/drop/use/pickup) give instant feedback. Trade goes through narrative crews for AI-validated negotiation.
- **Fixed equipment slots.** Weapon, Armor, Accessory, Ring — one item per slot. The `slot_type` field already exists on the Item model.
- **Consumable stacking.** Items marked `stackable: true` (consumables, scrolls, potions) merge into stacks with a quantity counter. Equipment never stacks.

## Data Model

### Chain Items Table (MUD)

Add two fields to the existing table:

```
Items: {
  id: bytes32,
  ownerId: bytes32,      // player UUID, or 0x0 if on ground
  locationId: bytes32,   // room UUID
  name: string,
  rarity: string,
  slotType: string,      // NEW: weapon/armor/accessory/ring/""
  quantity: uint32,       // NEW: stack count, default 1
}
```

### KG Item Entity (enrichment)

Stored on the Item entity in the KG (via summary JSON or direct attributes):

- `description: str` — flavor text
- `effects: list[str]` — mechanical effects for tooltip
- `is_consumable: bool` — enables "use" action
- `is_quest_item: bool` — prevents drop
- `stackable: bool` — derived from is_consumable, enables merge/split

### InventoryItemUpdate (state_update schema)

Expanded to support the new UI:

```python
class InventoryItemUpdate(BaseModel):
    id: str = ""              # item UUID (for structured actions)
    name: str = ""
    rarity: str = "common"
    slot_type: str = ""       # weapon/armor/accessory/ring/""
    equipped: bool = False
    is_consumable: bool = False
    is_quest_item: bool = False
    effects: list[str] = []
    quantity: int = 1         # stack count
```

## Inventory Manifest

New file: `engine/src/memento/inventory_manifest.py`

Follows `room_manifest.py` pattern:

```python
def get_inventory_manifest(player_uuid: str) -> dict:
    """Assemble complete inventory view from chain + KG.

    1. Query chain Items table: all items where ownerId == player_uuid
    2. For each item, enrich from KG entity (description, effects, slot_type)
    3. Return: {
         equipped: { weapon: item|null, armor: item|null, accessory: item|null, ring: item|null },
         backpack: [item, ...],
         capacity: 10,
         count: N,
         weight: N,
       }
    """
```

Consumers: gateway state route, inventory action endpoints, round controller post-turn, NPC agent tools.

## Temporal Edge Model (Chain-Anchored)

Graphiti edges support bi-temporal fields: `valid_at` (when a fact became true), `expired_at`/`invalid_at` (when it stopped being true), and `created_at` (when written). We use these to keep the KG canonical with chain state.

**Core principle**: Every CARRIES/LOCATED_IN edge gets `valid_at` from the chain transaction timestamp. On ownership transfer, the old edge gets `expired_at` and a new edge is created. The chain is the clock, the KG is the temporal history.

### Write Pattern

Every inventory action follows this sequence:

1. **Chain tx first** — update Items table, capture tx timestamp `T`
2. **Expire old KG edge** — set `expired_at=T` on the superseded CARRIES or LOCATED_IN edge
3. **Create new KG edge** — with `valid_at=T`

Examples:

**Drop item (Player A → Room X):**
```
Chain: Items.update(id=sword, ownerId=0x0, locationId=roomX) → T
KG:   (PlayerA)--[CARRIES {expired_at=T}]-->(Sword)         # expire
KG:   (Sword)--[LOCATED_IN {valid_at=T}]-->(RoomX)          # create
```

**Pickup item (Player B from Room X):**
```
Chain: Items.update(id=sword, ownerId=playerB) → T
KG:   (Sword)--[LOCATED_IN {expired_at=T}]-->(RoomX)        # expire
KG:   (PlayerB)--[CARRIES {valid_at=T}]-->(Sword)            # create
```

**Trade (Player A → NPC Grumlock):**
```
Chain: Items.update(id=dagger, ownerId=grumlockId) → T
KG:   (PlayerA)--[CARRIES {expired_at=T}]-->(Dagger)         # expire
KG:   (Grumlock)--[CARRIES {valid_at=T}]-->(Dagger)          # create
```

### Read Pattern

`inventory_manifest.py` queries only current (unexpired) edges:

```python
edges = client.kg.get_edges(player_uuid, direction="outgoing", edge_type="CARRIES")
current_items = [e for e in edges if not e.get("expired_at")]
```

### Divergence Detection

Safety net in `inventory_manifest.py` — after assembling from KG, cross-check against chain:

```python
chain_items = chain_client.fetch_items_by_owner(player_uuid)
kg_item_ids = {item["id"] for item in current_items}
chain_item_ids = {item["id"] for item in chain_items}

if kg_item_ids != chain_item_ids:
    logger.warning("KG/chain divergence for %s", player_uuid)
    # Chain wins — expire stale KG edges, create missing ones
    _reconcile_inventory(player_uuid, chain_items, current_items)
```

### Conflict Resolution

Reconciliation is lazy (runs on manifest read) and idempotent. Chain always wins.

**`_reconcile_inventory(player_uuid, chain_items, kg_items)`:**

```
For each item in chain but NOT in KG (chain has it, KG doesn't):
  → Create CARRIES edge with valid_at=now
  → Log: "Reconciled missing KG edge for item {id}"

For each item in KG but NOT in chain (KG has it, chain doesn't):
  → Expire the stale CARRIES edge with expired_at=now
  → Log: "Expired orphaned KG edge for item {id}"

For each item where chain.ownerId != KG edge source (wrong owner in KG):
  → Expire the stale CARRIES edge from wrong owner
  → Create new CARRIES edge from correct owner with valid_at=now
  → Log: "Corrected ownership for item {id}: {old_owner} → {new_owner}"

For each item where chain.locationId != KG LOCATED_IN target (wrong room):
  → Expire stale LOCATED_IN edge
  → Create new LOCATED_IN edge to correct room with valid_at=now
```

**When does divergence happen?**
- Gateway crash between chain tx and KG write
- Chain tx revert (gas, nonce collision)
- Manual chain interaction outside the game (direct contract call)
- Race condition in multiplayer (two pickups on same item)

**Guarantees:**
- Chain is always authoritative — KG self-heals to match
- Reconciliation only runs when manifest is read, not on every action (lazy)
- Each reconciliation is idempotent — running it twice produces the same result
- Expired edges are never deleted, preserving the audit trail
- Warnings are logged so divergence frequency can be monitored

### Benefits

- **Full ownership history** — expired edges form an audit trail (who had what, when)
- **Narrative enrichment** — narration crew can reference past ownership ("the sword once carried by the fallen warrior")
- **Permadeath memorials** — provable inventory at time of death from temporal edges
- **Consistency guarantee** — chain is always authoritative; KG self-heals on read

## Structured Action Endpoints

New route module: `gateway/src/gateway/routes/inventory.py`

```
POST /api/inventory/equip     { player_id, item_id, slot }
POST /api/inventory/unequip   { player_id, slot }
POST /api/inventory/drop      { player_id, item_id, quantity? }
POST /api/inventory/use       { player_id, item_id }
POST /api/inventory/pickup    { player_id, item_id }
GET  /api/inventory/{player_id}
```

### Action Flow

```
Client button click
  → Gateway REST endpoint
  → Engine inventory_actions.py (deterministic validation)
  → Chain tx first (Items table update, capture timestamp T)
  → KG edge writes (expire old edge at T, create new edge at T)
  → Broadcast state_update via WebSocket (inventory + room_map changes)
  → Return success/failure to client
```

Structured actions are instant — no round wait, no phase lock. They can happen during the `collecting` phase.

### Engine: inventory_actions.py

New file: `engine/src/memento/inventory_actions.py`

Deterministic validation functions:

- **equip(player_uuid, item_id, slot)**: Validate slot_type matches slot. If slot occupied, swap to backpack. Update KG: set equipped attribute on entity. No chain change (ownerId stays the same, equip state is KG-only).
- **unequip(player_uuid, slot)**: Move equipped item to backpack. Update KG: clear equipped attribute.
- **drop(player_uuid, item_id, quantity=None)**: Check not quest item. If stacked and partial drop → split: create new chain entity with split quantity, decrement original. Chain tx: `ownerId=0x0, locationId=room_uuid` → capture timestamp T. KG: expire CARRIES edge at T, create LOCATED_IN edge at T.
- **use(player_uuid, item_id)**: Check is_consumable. Apply effects via existing `mechanics.py` tools (e.g. heal → update player health in KG, buff → add status edge). Chain tx: decrement quantity (or delete at 0) → capture T. KG: expire CARRIES edge at T.
- **pickup(player_uuid, item_id)**: Check item is in player's current room. Check capacity. If stackable and player has matching item → merge: increment existing stack quantity on chain, delete ground entity. Otherwise: chain tx `ownerId=player_uuid` → capture T. KG: expire LOCATED_IN edge at T, create CARRIES edge at T.

### Validation Rules

- Can't drop quest items
- Can't equip wrong slot_type to slot
- Can't pickup if at capacity (5 weight per item, 50 capacity)
- Can't use non-consumable items
- Can't pickup items not in current room
- Can't act on items you don't own (except pickup from ground)

### Stacking Logic

- **Merge on pickup**: Search player's inventory for item with same `name` + `rarity` + `stackable=true`. If found, increment quantity on existing stack and delete the ground entity.
- **Split on partial drop/trade**: Decrement original stack's quantity. Create new chain entity with the split-off quantity, placed on ground (or transferred to trade partner).
- **Use**: Decrement quantity. When quantity reaches 0, delete entity from chain + KG.
- Equipment (slot_type != "") never stacks regardless of other flags.

## Trade

Trade stays narrative — it needs AI judgment for NPC negotiation, price haggling, and willingness checks.

1. Player types "trade dagger to Grumlock" or "buy potion from merchant"
2. Normal turn flow → inventory detector crew detects TRADE event, validates
3. If approved → engine calls structured transfer functions (chain + KG update)
4. Narration crew describes the exchange

NPCs with the Merchant label show a "browse wares" option in the Present panel. Clicking opens a trade variant of the inventory modal showing NPC inventory alongside the player's. Actual transactions go through narrative.

## Client UI

### Sidebar Panel (always visible)

Replaces current read-only `inventory.ts` (36 LOC). Shows:

- **EQUIPPED** section: 4 slot rows with glyphs (⚔ weapon, 🛡 armor, ◇ accessory, ○ ring). Item name in rarity color, or "- empty -" in dim.
- **PACK** section: item list with rarity colors. Consumable stacks show ×N suffix. Count indicator (3/10).
- **"manage inventory"** button at bottom opens the modal.

### Inventory Modal (on click or `i` hotkey)

New file: `client/src/ui/inventory-modal.ts`

Two-column paperdoll layout using existing `dialog.ts` pattern:

- **Left column — EQUIPMENT SLOTS**: 4 bordered slot cards. Each shows slot label (WPN/ARM/ACC/RNG), item name in rarity color, effects summary, and "unequip" action link.
- **Right column — BACKPACK**: Item cards with name, type tag, effects, and context-aware action links (equip/use/drop). Consumable stacks show quantity.
- **Ground section** at bottom of backpack column: items in current room available for pickup.
- **Header**: title, weight/count summary, close button.

Actions are clickable text links (not drag-and-drop). Each fires a `fetch()` to the structured REST endpoint. Modal stays open after actions; inventory re-renders from the state_update broadcast.

### State Flow

```
Button click in modal
  → fetch('/api/inventory/equip', { player_id, item_id, slot })
  → Gateway validates, engine executes, dual-write
  → WebSocket broadcasts state_update { inventory: [...], room_map: {...} }
  → Client applies state_update → re-renders sidebar + modal
```

## Room Manifest Integration

When a player drops an item:
- Chain: `ownerId = 0x0`, `locationId = room_uuid`
- KG: remove CARRIES edge, add LOCATED_IN edge to room
- Room manifest now includes the item in `items[]`
- All players in room get `state_update` with updated `room_map.items`

Pickup is the reverse — item leaves room manifest, enters inventory manifest.

State updates for inventory actions include both `inventory` and `room_map` fields so the client can update both panels atomically.

## Files to Create/Modify

### New Files
- `engine/src/memento/inventory_manifest.py` — manifest assembler
- `engine/src/memento/inventory_actions.py` — deterministic action handlers
- `gateway/src/gateway/routes/inventory.py` — REST endpoints
- `client/src/ui/inventory-modal.ts` — modal component
- `engine/tests/test_inventory_actions.py` — unit tests
- `engine/tests/test_inventory_manifest.py` — unit tests

### Modified Files
- `contracts/packages/contracts/mud.config.ts` — add slotType, quantity to Items
- `engine/src/memento/models/state_update.py` — expand InventoryItemUpdate
- `engine/src/memento/models/items.py` — add stackable field
- `client/src/panels/inventory.ts` — rewrite sidebar panel
- `client/src/state/game-state.ts` — expand inventory state shape
- `client/src/app.ts` — wire modal, hotkey
- `gateway/src/gateway/app.py` — mount inventory routes
- `gateway/src/gateway/routes/state.py` — use inventory_manifest for inventory data
- `engine/src/memento/session.py` — use inventory_manifest for starting items
- `engine/src/memento/tools/chain.py` — update register_item for new fields

## Out of Scope

- Drag-and-drop (click actions only)
- Crafting or item modification
- Steal mechanic (detected by crew but not wired to structured actions)
- Equipment stacking (each piece is unique)
- Item durability or degradation

## Verification

1. **Unit tests**: inventory_actions.py — equip/unequip/drop/use/pickup with edge cases (wrong slot, quest item drop, capacity full, stack merge/split)
2. **Integration**: Start local dev (`./start.sh --dev`), create character, verify inventory manifest returns starting items
3. **E2E structured actions**: Click equip in modal → verify chain + KG + client all update
4. **E2E trade**: Type "buy potion from merchant" → verify crew detects → transfer executes → both inventories update
5. **Multiplayer**: Player A drops item → Player B sees it appear in room → Player B picks up → verify chain ownership transfer
6. **Stacking**: Pick up 2 health potions → verify they merge into ×2 stack → use one → verify ×1 → use last → verify deleted
