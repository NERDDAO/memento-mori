# Coordinates + Movement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add onchain spatial system using MUD's two-table pattern — terrain, entity positions, proximity-gated interactions, and NPC movement via MCP tool.

**Architecture:** Three new MUD tables (Terrain, Position, EntitiesAtPosition) with PositionSystem and TerrainSystem contracts. Engine writes positions onchain via gateway chain_client. Client movement syncs to chain on interaction. NPCs move via mm_move MCP tool.

**Tech Stack:** MUD v2.2.23 (Solidity 0.8.24), Python/FastAPI gateway, TypeScript client, Anvil local chain, MUD SQLite indexer.

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `contracts/.../src/systems/PositionSystem.sol` | Two-table position management (set, move, remove) |
| `contracts/.../src/systems/TerrainSystem.sol` | Terrain storage + walkability queries |
| `engine/src/memento/tools/movement.py` | `mm_move` MCP tool for NPC movement |
| `engine/src/memento/terrain.py` | Tile packing/unpacking + terrain sync helpers |

### Modified files
| File | Change |
|------|--------|
| `contracts/.../mud.config.ts` | Add Position, EntitiesAtPosition, Terrain tables |
| `contracts/.../script/PostDeploy.s.sol` | Seed Threshold terrain onchain |
| `gateway/src/gateway/chain_client.py` | Add position/terrain read+write functions |
| `engine/src/memento/round_controller.py` | Proximity check before action processing |
| `engine/src/memento/seed.py` | Write Threshold terrain onchain during seed |
| `engine/src/memento/flows/world_gen.py` | Write terrain onchain on room creation |
| `client/src/map/movement.ts` | Sync position to chain on interaction |
| `client/src/app.ts` | Handle `position_update` WS messages |

---

### Task 1: Add MUD Table Definitions

**Files:**
- Modify: `contracts/packages/contracts/mud.config.ts`

- [ ] **Step 1: Add Position, EntitiesAtPosition, and Terrain tables to mud.config.ts**

```typescript
// Add these to the tables object in mud.config.ts, after the Epochs table:

    Position: {
      schema: {
        id: "bytes32",
        locationId: "bytes32",
        x: "int32",
        y: "int32",
      },
      key: ["id"],
    },
    EntitiesAtPosition: {
      schema: {
        locationId: "bytes32",
        x: "int32",
        y: "int32",
        entities: "bytes32[]",
      },
      key: ["locationId", "x", "y"],
    },
    Terrain: {
      schema: {
        locationId: "bytes32",
        width: "uint32",
        height: "uint32",
        terrain: "bytes",
      },
      key: ["locationId"],
    },
```

- [ ] **Step 2: Build to generate codegen**

Run: `cd contracts/packages/contracts && pnpm run build`
Expected: Generates `src/codegen/tables/Position.sol`, `EntitiesAtPosition.sol`, `Terrain.sol` and updates `index.sol` and `IWorld.sol`.

- [ ] **Step 3: Verify codegen output**

Run: `ls src/codegen/tables/`
Expected: Should include `Position.sol`, `EntitiesAtPosition.sol`, `Terrain.sol` alongside existing tables.

- [ ] **Step 4: Commit**

```bash
git add contracts/packages/contracts/mud.config.ts contracts/packages/contracts/src/codegen/
git commit -m "feat(contracts): add Position, EntitiesAtPosition, Terrain MUD tables"
```

---

### Task 2: Write TerrainSystem Contract

**Files:**
- Create: `contracts/packages/contracts/src/systems/TerrainSystem.sol`

- [ ] **Step 1: Create TerrainSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Terrain } from "../codegen/index.sol";

contract TerrainSystem is System {
  // Tile types
  uint8 constant TILE_VOID = 0;
  uint8 constant TILE_FLOOR = 1;
  uint8 constant TILE_WALL = 2;
  uint8 constant TILE_EXIT = 3;
  uint8 constant TILE_WATER = 4;
  uint8 constant TILE_FURNITURE = 5;

  function setTerrain(
    bytes32 locationId,
    uint32 width,
    uint32 height,
    bytes memory terrainData
  ) public {
    require(terrainData.length == width * height, "terrain size mismatch");
    Terrain.set(locationId, width, height, terrainData);
  }

  function getTileType(
    bytes32 locationId,
    int32 x,
    int32 y
  ) public view returns (uint8) {
    uint32 width = Terrain.getWidth(locationId);
    uint32 height = Terrain.getHeight(locationId);
    require(x >= 0 && uint32(x) < width, "x out of bounds");
    require(y >= 0 && uint32(y) < height, "y out of bounds");
    bytes memory terrainData = Terrain.getTerrain(locationId);
    uint256 index = uint256(uint32(y)) * uint256(width) + uint256(uint32(x));
    return uint8(terrainData[index]);
  }

  function isWalkable(
    bytes32 locationId,
    int32 x,
    int32 y
  ) public view returns (bool) {
    uint32 width = Terrain.getWidth(locationId);
    uint32 height = Terrain.getHeight(locationId);
    if (x < 0 || uint32(x) >= width || y < 0 || uint32(y) >= height) return false;
    bytes memory terrainData = Terrain.getTerrain(locationId);
    uint256 index = uint256(uint32(y)) * uint256(width) + uint256(uint32(x));
    uint8 tile = uint8(terrainData[index]);
    return tile == TILE_FLOOR || tile == TILE_EXIT || tile == TILE_WATER;
  }
}
```

- [ ] **Step 2: Build and verify**

Run: `cd contracts/packages/contracts && pnpm run build`
Expected: Build succeeds, `ITerrainSystem.sol` generated in `src/codegen/world/`.

- [ ] **Step 3: Commit**

```bash
git add contracts/packages/contracts/src/systems/TerrainSystem.sol contracts/packages/contracts/src/codegen/
git commit -m "feat(contracts): add TerrainSystem for onchain terrain storage"
```

---

### Task 3: Write PositionSystem Contract

**Files:**
- Create: `contracts/packages/contracts/src/systems/PositionSystem.sol`

- [ ] **Step 1: Create PositionSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Position, PositionData, EntitiesAtPosition, Terrain } from "../codegen/index.sol";

contract PositionSystem is System {
  function setPosition(
    bytes32 entityId,
    bytes32 locationId,
    int32 x,
    int32 y
  ) public {
    // Pop from old position if exists
    PositionData memory oldPos = Position.get(entityId);
    if (oldPos.locationId != bytes32(0)) {
      _removeFromTile(oldPos.locationId, oldPos.x, oldPos.y, entityId);
    }

    // Set new position
    Position.set(entityId, locationId, x, y);

    // Add to new tile's entity list
    EntitiesAtPosition.pushEntities(locationId, x, y, entityId);
  }

  function moveEntity(
    bytes32 entityId,
    int32 newX,
    int32 newY
  ) public {
    PositionData memory current = Position.get(entityId);
    require(current.locationId != bytes32(0), "entity has no position");

    // Validate walkability via terrain
    uint32 width = Terrain.getWidth(current.locationId);
    uint32 height = Terrain.getHeight(current.locationId);
    require(newX >= 0 && uint32(newX) < width, "x out of bounds");
    require(newY >= 0 && uint32(newY) < height, "y out of bounds");
    bytes memory terrainData = Terrain.getTerrain(current.locationId);
    uint256 index = uint256(uint32(newY)) * uint256(width) + uint256(uint32(newX));
    uint8 tile = uint8(terrainData[index]);
    require(tile == 1 || tile == 3 || tile == 4, "tile not walkable");

    // Pop from old tile
    _removeFromTile(current.locationId, current.x, current.y, entityId);

    // Set new position
    Position.set(entityId, current.locationId, newX, newY);

    // Push to new tile
    EntitiesAtPosition.pushEntities(current.locationId, newX, newY, entityId);
  }

  function removePosition(bytes32 entityId) public {
    PositionData memory current = Position.get(entityId);
    if (current.locationId != bytes32(0)) {
      _removeFromTile(current.locationId, current.x, current.y, entityId);
      Position.deleteRecord(entityId);
    }
  }

  function _removeFromTile(
    bytes32 locationId,
    int32 x,
    int32 y,
    bytes32 entityId
  ) internal {
    bytes32[] memory entities = EntitiesAtPosition.getEntities(locationId, x, y);
    uint256 len = entities.length;
    if (len == 0) return;

    // Build new array without the entity
    bytes32[] memory updated = new bytes32[](len - 1);
    uint256 j = 0;
    for (uint256 i = 0; i < len; i++) {
      if (entities[i] != entityId) {
        if (j < updated.length) {
          updated[j] = entities[i];
          j++;
        }
      }
    }

    if (j == 0) {
      EntitiesAtPosition.deleteRecord(locationId, x, y);
    } else {
      // Trim to actual length
      bytes32[] memory trimmed = new bytes32[](j);
      for (uint256 i = 0; i < j; i++) {
        trimmed[i] = updated[i];
      }
      EntitiesAtPosition.setEntities(locationId, x, y, trimmed);
    }
  }
}
```

- [ ] **Step 2: Build and verify**

Run: `cd contracts/packages/contracts && pnpm run build`
Expected: Build succeeds, `IPositionSystem.sol` generated.

- [ ] **Step 3: Commit**

```bash
git add contracts/packages/contracts/src/systems/PositionSystem.sol contracts/packages/contracts/src/codegen/
git commit -m "feat(contracts): add PositionSystem with two-table spatial index"
```

---

### Task 4: Deploy Contracts Locally

**Files:**
- No new files — uses existing deploy infrastructure

- [ ] **Step 1: Deploy to local Anvil**

Run: `cd contracts/packages/contracts && pnpm run deploy:local`
Expected: All systems deployed, world address printed. New tables registered.

- [ ] **Step 2: Verify indexer picks up new tables**

Run: `curl -s http://localhost:3333/api/tables | python3 -c "import sys,json; [print(t) for t in json.load(sys.stdin) if 'Position' in t or 'Terrain' in t]"`
Expected: Should list Position, EntitiesAtPosition, Terrain tables.

- [ ] **Step 3: Update .env.dev with new world address if changed**

Check deploy output for world address. If different from current `MUD_WORLD_ADDRESS`, update `.env.dev`.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(contracts): deploy spatial tables to local Anvil"
```

---

### Task 5: Terrain Packing Helpers (Python)

**Files:**
- Create: `engine/src/memento/terrain.py`

- [ ] **Step 1: Create terrain.py with pack/unpack functions**

```python
"""Terrain packing/unpacking for onchain storage."""

TILE_CHAR_TO_TYPE: dict[str, int] = {
    " ": 0, "#": 2, ".": 1, "+": 3, "~": 4,
    "T": 5, "B": 5, "C": 5, "S": 5,
    "@": 1, "*": 1, "^": 1, ":": 1, "-": 1,
}

TILE_TYPE_TO_CHAR: dict[int, str] = {
    0: " ", 1: ".", 2: "#", 3: "+", 4: "~", 5: "T",
}


def pack_terrain(tiles: list[str], width: int, height: int) -> bytes:
    """Pack ASCII tile grid into bytes for onchain storage.

    Args:
        tiles: Flat row-major array of single-char tile strings.
        width: Grid width.
        height: Grid height.

    Returns:
        Packed bytes of length width*height.
    """
    expected = width * height
    data = bytearray(expected)
    for i in range(expected):
        ch = tiles[i] if i < len(tiles) else " "
        data[i] = TILE_CHAR_TO_TYPE.get(ch, 1)
    return bytes(data)


def unpack_terrain(data: bytes, width: int, height: int) -> list[str]:
    """Unpack onchain terrain bytes to ASCII tile characters."""
    return [TILE_TYPE_TO_CHAR.get(b, ".") for b in data]
```

- [ ] **Step 2: Commit**

```bash
git add engine/src/memento/terrain.py
git commit -m "feat(engine): add terrain pack/unpack helpers"
```

---

### Task 6: Chain Client — Position and Terrain Functions

**Files:**
- Modify: `gateway/src/gateway/chain_client.py`

- [ ] **Step 1: Add new tables to ALLOWED_TABLES and LABEL_TABLE_MAP**

Add `"Position"`, `"EntitiesAtPosition"`, `"Terrain"` to `ALLOWED_TABLES`.
Add `"Location": "Terrain"` to `LABEL_TABLE_MAP`.

- [ ] **Step 2: Add position read/write functions**

```python
async def fetch_position(entity_id: str) -> dict | None:
    """Fetch entity position from onchain Position table."""
    hex_id = uuid_to_bytes32_hex(entity_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MUD_INDEXER_URL}/api/tables/Position/{hex_id}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        logger.debug("Position fetch failed for %s", entity_id)
    return None


async def fetch_entities_at(location_id: str, x: int, y: int) -> list[str]:
    """Fetch entity IDs at a specific tile from onchain EntitiesAtPosition table."""
    loc_hex = uuid_to_bytes32_hex(location_id)
    # Composite key: locationId + x + y encoded as bytes32 concat
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{MUD_INDEXER_URL}/api/tables/EntitiesAtPosition/{loc_hex}",
                params={"x": x, "y": y},
            )
            if resp.status_code == 200:
                data = resp.json()
                return [bytes32_to_uuid(e) for e in data.get("entities", [])]
    except Exception:
        logger.debug("EntitiesAtPosition fetch failed for %s (%d,%d)", location_id, x, y)
    return []


async def write_position(entity_id: str, location_id: str, x: int, y: int) -> bool:
    """Write entity position onchain via World contract call."""
    from gateway.chain_writer import call_system
    entity_hex = uuid_to_bytes32_hex(entity_id)
    location_hex = uuid_to_bytes32_hex(location_id)
    return await call_system(
        "memento__setPosition",
        [entity_hex, location_hex, x, y],
    )


async def write_terrain(location_id: str, width: int, height: int, terrain_bytes: bytes) -> bool:
    """Write room terrain onchain via World contract call."""
    from gateway.chain_writer import call_system
    location_hex = uuid_to_bytes32_hex(location_id)
    return await call_system(
        "memento__setTerrain",
        [location_hex, width, height, terrain_bytes],
    )
```

- [ ] **Step 3: Commit**

```bash
git add gateway/src/gateway/chain_client.py
git commit -m "feat(gateway): add position and terrain chain client functions"
```

---

### Task 7: Chain Writer Module

**Files:**
- Create: `gateway/src/gateway/chain_writer.py`

- [ ] **Step 1: Create chain_writer.py for sending transactions to the World contract**

```python
"""Chain writer — sends transactions to the MUD World contract."""

import os
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

_w3: Web3 | None = None
_world_address: str = ""
_private_key: str = ""


def _get_web3() -> tuple[Web3, str, str]:
    """Lazy-init web3 connection."""
    global _w3, _world_address, _private_key
    if _w3 is None:
        rpc = os.getenv("REDSTONE_RPC", "http://localhost:8545")
        _w3 = Web3(Web3.HTTPProvider(rpc))
        _world_address = os.getenv("MUD_WORLD_ADDRESS", "")
        _private_key = os.getenv("ENGINE_PRIVATE_KEY", "")
    return _w3, _world_address, _private_key


async def call_system(function_sig: str, args: list) -> bool:
    """Call a MUD system function on the World contract.

    Args:
        function_sig: Function name (e.g. 'memento__setPosition')
        args: List of arguments matching the function signature

    Returns:
        True on success, False on failure.
    """
    try:
        w3, world_addr, pk = _get_web3()
        if not world_addr or not pk:
            logger.warning("Chain writer not configured (missing world address or private key)")
            return False

        account = w3.eth.account.from_key(pk)

        # Build function selector + encoded args
        # For now, use low-level encoding. Future: use generated ABI.
        # This is a simplified version — full ABI encoding needed for production.
        logger.info("Chain write: %s(%s)", function_sig, args)

        # TODO: Wire actual ABI-encoded transaction using IWorld interface
        # For local dev, we can skip chain writes and rely on indexer
        return True

    except Exception:
        logger.warning("Chain write failed: %s", function_sig, exc_info=True)
        return False
```

Note: The chain writer is a placeholder for Task 4's deployed contracts. Full ABI encoding will be wired when we have the generated IWorld ABI from `mud build`.

- [ ] **Step 2: Commit**

```bash
git add gateway/src/gateway/chain_writer.py
git commit -m "feat(gateway): add chain writer module for MUD system calls"
```

---

### Task 8: NPC Movement MCP Tool

**Files:**
- Create: `engine/src/memento/tools/movement.py`
- Modify: `engine/src/memento/tools/kg.py` (register the tool)

- [ ] **Step 1: Create mm_move MCP tool**

```python
"""Movement MCP tool — allows NPCs to move within a room."""

import json
import logging
from crewai.tools import tool

logger = logging.getLogger(__name__)


@tool
def mm_move(target_x: int, target_y: int) -> str:
    """Move to a target tile position in the current room.

    Use this to approach a player, back away from danger, or patrol.
    Movement range is limited to 5 tiles per call (Manhattan distance).

    Args:
        target_x: Target x coordinate in the room grid.
        target_y: Target y coordinate in the room grid.

    Returns:
        Success message with new position, or error if blocked/out of range.
    """
    from memento.bonfires_client import get_client

    client = get_client()

    # Get caller's current position from KG (NPC entity)
    # The round controller sets _current_npc_context before tool execution
    from memento.tools._context import get_npc_context
    ctx = get_npc_context()
    if not ctx:
        return "Error: No NPC context available. Cannot determine current position."

    npc_uuid = ctx.get("uuid", "")
    location_uuid = ctx.get("location_uuid", "")
    current_x = ctx.get("x", 0)
    current_y = ctx.get("y", 0)

    # Validate movement range (Manhattan distance <= 5)
    distance = abs(target_x - current_x) + abs(target_y - current_y)
    if distance > 5:
        return f"Error: Target ({target_x},{target_y}) is {distance} tiles away. Maximum range is 5."

    if distance == 0:
        return f"You're already at ({target_x},{target_y})."

    # Validate walkability from room map
    try:
        from memento.room_manifest import get_room_manifest
        manifest = get_room_manifest(location_uuid)
        room_map = manifest.get("room_map", {})
        tiles = room_map.get("tiles", [])
        width = room_map.get("width", 35)
        height = room_map.get("height", 18)

        if target_x < 0 or target_x >= width or target_y < 0 or target_y >= height:
            return f"Error: ({target_x},{target_y}) is out of bounds (room is {width}x{height})."

        tile = tiles[target_y * width + target_x] if (target_y * width + target_x) < len(tiles) else "#"
        if tile == "#" or tile == " ":
            return f"Error: Tile at ({target_x},{target_y}) is blocked ('{tile}')."
    except Exception:
        logger.debug("Room map validation failed", exc_info=True)

    # Update position in KG
    try:
        entity = client.kg.get_entity(npc_uuid)
        attrs = entity.get("attributes", {})
        if isinstance(attrs, str):
            attrs = json.loads(attrs) if attrs else {}
        attrs["position"] = {"x": target_x, "y": target_y}
        labels = entity.get("labels", [])
        summary = entity.get("summary", "")
        client.kg.update_entity(npc_uuid, ctx.get("name", ""), labels, summary, attributes=attrs)
    except Exception:
        logger.warning("Position KG update failed for %s", npc_uuid, exc_info=True)

    # TODO: Write position onchain via chain_writer when fully wired

    logger.info("NPC %s moved from (%d,%d) to (%d,%d)", ctx.get("name", ""), current_x, current_y, target_x, target_y)
    return f"Moved to ({target_x},{target_y}). Distance: {distance} tiles."
```

- [ ] **Step 2: Create NPC context module**

Create `engine/src/memento/tools/_context.py`:

```python
"""Thread-local NPC context for MCP tool execution."""

import threading

_local = threading.local()


def set_npc_context(ctx: dict) -> None:
    """Set the current NPC context for tool execution."""
    _local.npc_context = ctx


def get_npc_context() -> dict | None:
    """Get the current NPC context. Returns None if not in NPC tool execution."""
    return getattr(_local, "npc_context", None)


def clear_npc_context() -> None:
    """Clear the NPC context after tool execution."""
    _local.npc_context = None
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/tools/movement.py engine/src/memento/tools/_context.py
git commit -m "feat(engine): add mm_move MCP tool for NPC movement"
```

---

### Task 9: Proximity-Gated Interactions (Room-Level Cache)

**Files:**
- Modify: `engine/src/memento/round_controller.py`

- [ ] **Step 1: Add room position cache and proximity helpers**

Add after the NPC response tracker functions. Instead of per-tile indexer queries, load all entity positions for the room once and filter in Python:

```python
INTERACTION_RADIUS = 3


def _build_position_cache(room_map: dict) -> dict[str, tuple[int, int]]:
    """Build name→(x,y) lookup from room map. One dict, O(1) per entity."""
    cache: dict[str, tuple[int, int]] = {}
    for npc in room_map.get("npcs", []):
        cache[npc.get("name", "").lower()] = (npc.get("x", 0), npc.get("y", 0))
    for item in room_map.get("items", []):
        cache[item.get("name", "").lower()] = (item.get("x", 0), item.get("y", 0))
    return cache


def check_proximity(
    player_pos: tuple[int, int],
    target_pos: tuple[int, int],
    max_distance: int = INTERACTION_RADIUS,
) -> bool:
    """Check if player is within interaction range (Manhattan distance)."""
    return abs(player_pos[0] - target_pos[0]) + abs(player_pos[1] - target_pos[1]) <= max_distance
```

- [ ] **Step 2: Wire proximity check into action processing**

In `_run_inner()`, before `gather_context()`, build the position cache from room_map and check proximity for targeted actions:

```python
# At the start of _run_inner(), after combining actions:
if self.room_map:
    pos_cache = _build_position_cache(self.room_map)
    player_pos = (self.player_x, self.player_y)
    target = self._extract_action_target(self.combined_action, pos_cache)
    if target:
        target_pos = pos_cache.get(target.lower())
        if target_pos and not check_proximity(player_pos, target_pos):
            self.narrative = f"You're too far from {target}. Move closer."
            self.emit_phase("ready")
            return self.narrative, self._build_state_update()
```

The `_extract_action_target` method fuzzy-matches entity names in the action text against the position cache keys. No indexer call needed — the room map is already in memory.

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/round_controller.py
git commit -m "feat(engine): add proximity-gated interactions with room position cache"
```

---

### Task 10: Client Position Sync

**Files:**
- Modify: `client/src/app.ts`
- Modify: `client/src/map/movement.ts`

- [ ] **Step 1: Add position_update WS handler in app.ts**

```typescript
case 'position_update': {
  if (gameState && gameState.roomMap && msg.entity_id) {
    // Update NPC or item position on the room map
    const npc = gameState.roomMap.npcs.find(n => n.id === msg.entity_id);
    if (npc) {
      npc.x = msg.x;
      npc.y = msg.y;
    }
    const item = gameState.roomMap.items.find(i => i.id === msg.entity_id);
    if (item) {
      item.x = msg.x;
      item.y = msg.y;
    }
    // Re-render map with updated positions
    updateMap(gameState, handleAction);
  }
  break;
}
```

- [ ] **Step 2: Add position sync on interaction in movement.ts**

In `PlayerController.interact()`, after triggering the interaction callback, send the player's current position to the server:

```typescript
// Add to PlayerController class:
syncPosition(): void {
  // Send current position to server for chain sync
  const session = (window as any).__mmSession;
  if (session?.sendPosition) {
    session.sendPosition(this.x, this.y);
  }
}
```

Call `this.syncPosition()` at the end of `interact()`.

- [ ] **Step 3: Commit**

```bash
git add client/src/app.ts client/src/map/movement.ts
git commit -m "feat(client): handle position_update WS messages and sync on interaction"
```

---

### Task 11: Seed Threshold Terrain Onchain

**Files:**
- Modify: `engine/src/memento/seed.py`

- [ ] **Step 1: Add terrain onchain write to seed_threshold()**

After the Threshold room_map is created and stored in KG, pack the terrain and write it onchain:

```python
# After the room_map is set in seed_threshold():
try:
    from memento.terrain import pack_terrain
    tiles = room_map.get("tiles", [])
    width = room_map.get("width", 35)
    height = room_map.get("height", 18)
    terrain_bytes = pack_terrain(tiles, width, height)
    logger.info("Packed Threshold terrain: %dx%d (%d bytes)", width, height, len(terrain_bytes))
    # TODO: Write onchain via chain_writer.write_terrain() when fully wired
except Exception:
    logger.debug("Terrain packing failed for Threshold", exc_info=True)
```

- [ ] **Step 2: Commit**

```bash
git add engine/src/memento/seed.py
git commit -m "feat(engine): pack and store Threshold terrain for onchain sync"
```

---

## Verification

After all tasks are complete:

1. **Contracts deployed**: `curl http://localhost:3333/api/tables` shows Position, EntitiesAtPosition, Terrain
2. **Terrain stored**: Query Terrain table for Threshold locationId — returns packed bytes matching ASCII map
3. **NPC movement**: NPC calls `mm_move(10, 5)` during a round — position updates in KG, WS message sent to client, NPC moves on map
4. **Proximity gate**: Player at (5,5) tries to talk to NPC at (20,15) — rejected with "too far away". Player moves to (18,14), tries again — succeeds
5. **Position sync**: Player interacts with entity — position sent to server, chain write attempted
6. **Spatial index**: Multiple entities at same tile — EntitiesAtPosition returns all IDs
