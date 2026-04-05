# Coordinates + Movement System Design

## Context

Memento Mori has tile-based rooms with ASCII maps, entity positions, and client-side movement — but none of it is onchain. Entity positions are ephemeral (KG + client memory), terrain lives only in the KG, and there's no spatial validation. This design adds onchain coordinates using the MUD framework's two-table spatial pattern, enabling verifiable movement, proximity-gated interactions, NPC movement via MCP tools, and onchain room creation.

## MUD Tables

### Existing tables (unchanged)
- `Characters` — player/NPC identity, level, alive status
- `Items` — ownership, location, rarity
- `Deaths` — permadeath records
- `Epochs` — state commitments

### New tables

**Terrain** — static tile grid per room, packed as bytes.

```typescript
Terrain: {
  key: ["locationId"],
  schema: {
    locationId: "bytes32",
    width: "uint32",
    height: "uint32",
    terrain: "bytes",  // width*height packed uint8 tile types
  },
},
```

Tile type mapping (uint8):
- 0 = void/impassable
- 1 = floor (`.`)
- 2 = wall (`#`)
- 3 = exit (`+`)
- 4 = water (`~`)
- 5 = table/furniture (`T`, `B`)
- 6+ = reserved for future terrain types

**Position** — forward index: entity → location + coordinates.

```typescript
Position: {
  key: ["id"],
  schema: {
    id: "bytes32",
    locationId: "bytes32",
    x: "int32",
    y: "int32",
  },
},
```

**EntitiesAtPosition** — reverse spatial index: tile → entity list.

```typescript
EntitiesAtPosition: {
  key: ["locationId", "x", "y"],
  schema: {
    locationId: "bytes32",
    x: "int32",
    y: "int32",
    entities: "bytes32[]",
  },
},
```

## System Contracts

### TerrainSystem.sol

- `setTerrain(bytes32 locationId, uint32 width, uint32 height, bytes terrain)` — write terrain for a room. Called on room creation.
- `getTileType(bytes32 locationId, int32 x, int32 y) → uint8` — read single tile.
- `isWalkable(bytes32 locationId, int32 x, int32 y) → bool` — returns true for floor, exit, water; false for wall, void.

### PositionSystem.sol

Implements the Sky Strife two-table sync pattern:

- `setPosition(bytes32 entityId, bytes32 locationId, int32 x, int32 y)` — place entity at position. Atomic: pop from old tile, set forward index, push to new tile.
- `moveEntity(bytes32 entityId, int32 newX, int32 newY)` — move within same room. Validates: tile is walkable, entity exists at current position.
- `removePosition(bytes32 entityId)` — remove entity from spatial index (death, pickup).

Internal `_popFromOldTile` and `_pushToNewTile` helpers keep both tables in sync atomically.

### Movement validation (onchain)

`moveEntity` checks:
1. Entity has a current Position
2. Target tile is within the same locationId
3. Target tile is walkable (via TerrainSystem)
4. Target tile coordinates are within terrain bounds

Movement range is NOT enforced onchain (engine handles that) — the contract just validates walkability.

## Engine Integration

### Room creation flow

When a new room is generated (world gen or runtime):
1. Location architect crew generates tile grid (existing)
2. Engine packs tiles into bytes array using the tile type mapping
3. Engine calls `TerrainSystem.setTerrain()` via the gateway
4. Terrain is now onchain and queryable via indexer

### Entity position sync

On room load / entity placement:
1. `room_manifest.py` reads entity positions from KG (existing)
2. Engine writes each entity's position via `PositionSystem.setPosition()`
3. Indexer indexes the writes
4. Client queries positions from indexer OR receives via WS

### Player movement

Client-side movement (WASD) remains client-local for responsiveness. Position is synced to chain periodically or on interaction:

1. Player presses WASD → client moves locally (existing `movement.ts`)
2. On interaction (talk, pickup, use exit) → client sends current position to gateway
3. Gateway writes `PositionSystem.moveEntity()` onchain
4. Gateway broadcasts `position_update` WS message to all clients at location

This is the optimistic rendering pattern from MUD — client moves immediately, chain confirms asynchronously.

### NPC movement via MCP tool

New MCP tool `mm_move`:

```python
@tool
def mm_move(target_x: int, target_y: int) -> str:
    """Move to a target tile in the current room.
    
    Args:
        target_x: Target x coordinate
        target_y: Target y coordinate
    
    Returns:
        Success message or error if tile is blocked/out of range.
    """
```

Engine validation:
- Target tile is walkable (check KG room_map, or query TerrainSystem)
- Distance from current position ≤ 5 tiles (Manhattan)
- Write new position via PositionSystem onchain
- Send `position_update` WS message
- Update KG room_map NPC position

## Proximity-Gated Interactions

### Rules

- Interaction radius: **3 tiles** (Manhattan distance)
- Applies to: talk to NPC, pick up item, examine, trade
- Does NOT apply to: look (can see anything in room), go (exits are special)

### Implementation

**Engine side** (`round_controller.py` or action processing):
1. Parse action to extract target entity name
2. Look up player position and target position (from Position table via indexer)
3. Compute Manhattan distance: `abs(px - tx) + abs(py - ty)`
4. If distance > 3: reject action with "You're too far away. Move closer."
5. If distance ≤ 3: process normally

**Client side** (`movement.ts`):
- Already has proximity detection for entity highlighting
- Extend to show interaction prompts only within 3-tile radius
- Dim or gray out entities beyond interaction range in the Present panel

## WS Message Types

### position_update (new)

```typescript
interface PositionUpdateMessage {
  type: 'position_update';
  entity_id: string;
  entity_name: string;
  x: number;
  y: number;
  location_id: string;
}
```

Sent when any entity moves (player or NPC). Client updates the entity's position on the map canvas.

## Chain Client Updates

### gateway/chain_client.py

Add to `ALLOWED_TABLES`: `"Position"`, `"EntitiesAtPosition"`, `"Terrain"`

New functions:
- `fetch_position(entity_id: str) → dict` — get entity's current position
- `fetch_entities_at(location_id: str, x: int, y: int) → list[str]` — reverse lookup
- `fetch_terrain(location_id: str) → dict` — get room terrain data
- `set_position(entity_id: str, location_id: str, x: int, y: int)` — write position onchain
- `set_terrain(location_id: str, width: int, height: int, terrain: bytes)` — write terrain onchain

### Tile packing/unpacking

```python
TILE_CHAR_TO_TYPE = {
    ' ': 0, '#': 2, '.': 1, '+': 3, '~': 4,
    'T': 5, 'B': 5, '@': 1, '*': 1,
}

def pack_terrain(tiles: list[str], width: int, height: int) -> bytes:
    """Pack ASCII tile grid into bytes for onchain storage."""
    data = bytearray(width * height)
    for i, ch in enumerate(tiles):
        data[i] = TILE_CHAR_TO_TYPE.get(ch, 1)
    return bytes(data)

def unpack_terrain(data: bytes, width: int, height: int) -> list[str]:
    """Unpack onchain terrain bytes to ASCII tile characters."""
    TYPE_TO_CHAR = {0: ' ', 1: '.', 2: '#', 3: '+', 4: '~', 5: 'T'}
    return [TYPE_TO_CHAR.get(b, '.') for b in data]
```

## Files to Create/Modify

### New files
| File | Purpose |
|------|---------|
| `contracts/.../src/systems/PositionSystem.sol` | Position + spatial index management |
| `contracts/.../src/systems/TerrainSystem.sol` | Terrain storage + walkability checks |
| `contracts/.../src/libraries/LibPosition.sol` | Two-table sync helpers |
| `engine/src/memento/tools/movement.py` | `mm_move` MCP tool for NPCs |

### Modified files
| File | Change |
|------|--------|
| `contracts/.../mud.config.ts` | Add Position, EntitiesAtPosition, Terrain tables |
| `gateway/src/gateway/chain_client.py` | Add position/terrain fetch+write functions |
| `engine/src/memento/round_controller.py` | Add proximity check before action processing |
| `engine/src/memento/room_manifest.py` | Merge onchain positions with KG data |
| `engine/src/memento/flows/world_gen.py` | Write terrain onchain on room creation |
| `engine/src/memento/seed.py` | Seed Threshold terrain onchain |
| `client/src/map/movement.ts` | Sync position to chain on interaction |
| `client/src/app.ts` | Handle position_update WS messages |
| `client/src/panels/present.ts` | Gray out entities beyond interaction range |

## Verification

1. **Terrain onchain**: Deploy contracts, seed Threshold. Query indexer for Terrain table — should return packed tile data matching the ASCII map.
2. **Position onchain**: Join game, verify player position in Position table. Move around, verify updates.
3. **NPC movement**: Trigger an NPC action. NPC should call mm_move, position should update onchain and on client map.
4. **Proximity gate**: Move player far from an NPC, try to talk → rejected. Move within 3 tiles → allowed.
5. **Spatial index**: Query EntitiesAtPosition for a tile with multiple entities → returns all entity IDs.
6. **New room creation**: Generate a new location via world gen → terrain should be written onchain automatically.
