# Redstone MUD Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy MUD tables and systems on a local anvil chain that model the Memento Mori game world — Characters, Deaths, Items, Locations, WorldEvents, Episodes, and Reputation.

**Architecture:** MUD framework with `defineWorld` config defining 7 tables. Systems provide write access for the engine wallet (game master). Local anvil for development, Redstone L2 for production later. The engine will call system functions via web3 to dual-write alongside the KG.

**Tech Stack:** MUD v2, Solidity, Foundry, anvil (local chain), pnpm, Node 20

**Spec:** `docs/superpowers/specs/2026-04-01-redstone-integration-design.md`

---

## Task 1: Scaffold MUD Project

**Files:**
- Create: `contracts/` directory (MUD project root)

- [ ] **Step 1: Create the MUD project**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
pnpm create mud@latest --name contracts --template vanilla
```

This creates `contracts/` with `packages/contracts/` and `packages/client/`. We only need the contracts package — the client is our existing Pretext MUD client.

- [ ] **Step 2: Remove the client package**

We already have our own client. Remove the generated one:

```bash
rm -rf contracts/packages/client
```

Edit `contracts/pnpm-workspace.yaml` to remove the client package reference if present.

- [ ] **Step 3: Verify the contracts package builds**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts
pnpm install
cd packages/contracts
pnpm build
```

Expected: Compiles with no errors. You'll see the default Counter table and IncrementSystem.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/
git commit -m "chore: scaffold MUD contracts project"
```

---

## Task 2: Define Game Tables in mud.config.ts

**Files:**
- Modify: `contracts/packages/contracts/mud.config.ts`

- [ ] **Step 1: Replace the default config with game tables**

Replace the entire contents of `contracts/packages/contracts/mud.config.ts`:

```typescript
import { defineWorld } from "@latticexyz/world";

export default defineWorld({
  namespace: "memento",
  enums: {
    EntityType: ["Character", "NPC", "Item", "Location", "Region", "Quest", "Faction"],
    EventType: ["CombatOutcome", "QuestComplete", "NPCDeath", "Discovery", "FactionChange", "Death", "GameEvent"],
  },
  tables: {
    // Player/NPC characters
    Characters: {
      schema: {
        id: "bytes32",          // KG UUID as bytes32
        name: "string",
        wallet: "address",      // player wallet (0x0 for NPCs)
        entityType: "EntityType",
        level: "uint32",
        alive: "bool",
        createdAt: "uint256",
      },
      key: ["id"],
    },

    // Permanent death records
    Deaths: {
      schema: {
        id: "bytes32",          // auto-generated death record ID
        characterId: "bytes32", // FK to Characters
        cause: "string",
        location: "string",
        level: "uint32",
        tick: "uint256",        // in-game time
        timestamp: "uint256",   // block timestamp
      },
      key: ["id"],
    },

    // Items with ownership
    Items: {
      schema: {
        id: "bytes32",          // KG UUID as bytes32
        name: "string",
        rarity: "string",
        ownerId: "bytes32",     // FK to Characters (0x0 if unowned)
        locationId: "bytes32",  // FK to Locations (where it sits if unowned)
      },
      key: ["id"],
    },

    // Discovered locations
    Locations: {
      schema: {
        id: "bytes32",          // KG UUID as bytes32
        name: "string",
        region: "string",
        discoveredBy: "address", // wallet of first player to enter
        discoveredAt: "uint256",
      },
      key: ["id"],
    },

    // Significant world events
    WorldEvents: {
      schema: {
        id: "bytes32",
        eventType: "EventType",
        actors: "string",       // comma-separated entity names
        location: "string",
        summary: "string",
        tick: "uint256",
        timestamp: "uint256",
      },
      key: ["id"],
    },

    // Graphiti episodes — the reconstruction primitive
    Episodes: {
      schema: {
        id: "bytes32",          // episode UUID
        name: "string",
        summary: "string",      // narrative summary
        entities: "string",     // JSON: [{uuid, name, labels, summary}]
        edges: "string",        // JSON: [{source, target, relationship, fact}]
        tick: "uint256",
        timestamp: "uint256",
      },
      key: ["id"],
    },

    // Cross-death faction reputation (keyed by wallet + faction)
    Reputation: {
      schema: {
        wallet: "address",
        factionId: "bytes32",   // KG UUID
        standing: "int32",      // -100 to 100
      },
      key: ["wallet", "factionId"],
    },
  },
});
```

- [ ] **Step 2: Run codegen to generate table libraries**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm mud tablegen
```

Expected: Generates Solidity libraries in `src/codegen/` for each table (Characters.sol, Deaths.sol, Items.sol, etc.) with type-safe getters/setters.

- [ ] **Step 3: Verify build**

```bash
pnpm build
```

Expected: Compiles with no errors.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/mud.config.ts contracts/packages/contracts/src/codegen/
git commit -m "feat(contracts): define MUD tables for game world state"
```

---

## Task 3: Character System

**Files:**
- Create: `contracts/packages/contracts/src/systems/CharacterSystem.sol`
- Remove: `contracts/packages/contracts/src/systems/IncrementSystem.sol` (default template)

- [ ] **Step 1: Remove the default IncrementSystem**

```bash
rm contracts/packages/contracts/src/systems/IncrementSystem.sol
```

Also remove the Counter table import from any test files if they exist.

- [ ] **Step 2: Create CharacterSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Characters, Deaths, Items } from "../codegen/index.sol";
import { EntityType } from "../codegen/common.sol";

contract CharacterSystem is System {
  /// Register a new character (player or NPC)
  function registerCharacter(
    bytes32 id,
    string memory name,
    address wallet,
    EntityType entityType
  ) public {
    Characters.set(id, name, wallet, entityType, 1, true, block.timestamp);
  }

  /// Record a character's death — permanent, cannot be undone
  function killCharacter(
    bytes32 characterId,
    string memory cause,
    string memory location,
    uint256 tick
  ) public {
    // Mark as dead
    Characters.setAlive(characterId, false);

    // Create death record
    bytes32 deathId = keccak256(abi.encodePacked(characterId, block.timestamp));
    uint32 level = Characters.getLevel(characterId);
    Deaths.set(deathId, characterId, cause, location, level, tick, block.timestamp);
  }

  /// Level up a character
  function levelUp(bytes32 characterId, uint32 newLevel) public {
    Characters.setLevel(characterId, newLevel);
  }

  /// Release all items owned by a dead character back to a location
  function releaseItems(bytes32 characterId, bytes32 locationId) public {
    // Note: MUD doesn't support iteration over table rows by a non-key field.
    // The engine must call transferItem for each item individually.
    // This is a convenience marker — actual item release is done per-item.
  }
}
```

- [ ] **Step 3: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm build
```

Expected: Compiles. Fix any import path issues from codegen.

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/src/systems/CharacterSystem.sol
git rm contracts/packages/contracts/src/systems/IncrementSystem.sol 2>/dev/null || true
git commit -m "feat(contracts): add CharacterSystem with register, kill, levelUp"
```

---

## Task 4: Item System

**Files:**
- Create: `contracts/packages/contracts/src/systems/ItemSystem.sol`

- [ ] **Step 1: Create ItemSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Items } from "../codegen/index.sol";

contract ItemSystem is System {
  /// Register a new item in the world
  function registerItem(
    bytes32 id,
    string memory name,
    string memory rarity,
    bytes32 ownerId,
    bytes32 locationId
  ) public {
    Items.set(id, name, rarity, ownerId, locationId);
  }

  /// Transfer item to a new owner
  function transferItem(bytes32 itemId, bytes32 newOwnerId) public {
    Items.setOwnerId(itemId, newOwnerId);
    Items.setLocationId(itemId, bytes32(0)); // owned items have no location
  }

  /// Drop item at a location (e.g., on death)
  function dropItem(bytes32 itemId, bytes32 locationId) public {
    Items.setOwnerId(itemId, bytes32(0));
    Items.setLocationId(itemId, locationId);
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm build
```

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/src/systems/ItemSystem.sol
git commit -m "feat(contracts): add ItemSystem with register, transfer, drop"
```

---

## Task 5: Location System

**Files:**
- Create: `contracts/packages/contracts/src/systems/LocationSystem.sol`

- [ ] **Step 1: Create LocationSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Locations } from "../codegen/index.sol";

contract LocationSystem is System {
  /// Register a new location (from world gen)
  function registerLocation(
    bytes32 id,
    string memory name,
    string memory region,
    address discoveredBy
  ) public {
    Locations.set(id, name, region, discoveredBy, block.timestamp);
  }

  /// Mark a location as discovered by a player (only if not already discovered)
  function discoverLocation(bytes32 locationId, address discoverer) public {
    address current = Locations.getDiscoveredBy(locationId);
    if (current == address(0)) {
      Locations.setDiscoveredBy(locationId, discoverer);
      Locations.setDiscoveredAt(locationId, block.timestamp);
    }
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm build
```

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/src/systems/LocationSystem.sol
git commit -m "feat(contracts): add LocationSystem with register and discover"
```

---

## Task 6: Event and Episode Systems

**Files:**
- Create: `contracts/packages/contracts/src/systems/EventSystem.sol`
- Create: `contracts/packages/contracts/src/systems/EpisodeSystem.sol`

- [ ] **Step 1: Create EventSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { WorldEvents } from "../codegen/index.sol";
import { EventType } from "../codegen/common.sol";

contract EventSystem is System {
  /// Record a significant world event
  function recordEvent(
    bytes32 id,
    EventType eventType,
    string memory actors,
    string memory location,
    string memory summary,
    uint256 tick
  ) public {
    WorldEvents.set(id, eventType, actors, location, summary, tick, block.timestamp);
  }
}
```

- [ ] **Step 2: Create EpisodeSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Episodes } from "../codegen/index.sol";

contract EpisodeSystem is System {
  /// Record a Graphiti episode with extracted entities and edges as JSON
  function recordEpisode(
    bytes32 id,
    string memory name,
    string memory summary,
    string memory entities,
    string memory edges,
    uint256 tick
  ) public {
    Episodes.set(id, name, summary, entities, edges, tick, block.timestamp);
  }
}
```

- [ ] **Step 3: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm build
```

- [ ] **Step 4: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/src/systems/EventSystem.sol contracts/packages/contracts/src/systems/EpisodeSystem.sol
git commit -m "feat(contracts): add EventSystem and EpisodeSystem for world history"
```

---

## Task 7: Reputation System

**Files:**
- Create: `contracts/packages/contracts/src/systems/ReputationSystem.sol`

- [ ] **Step 1: Create ReputationSystem.sol**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import { System } from "@latticexyz/world/src/System.sol";
import { Reputation } from "../codegen/index.sol";

contract ReputationSystem is System {
  /// Update a wallet's standing with a faction
  function updateReputation(address wallet, bytes32 factionId, int32 delta) public {
    int32 current = Reputation.getStanding(wallet, factionId);
    int32 newStanding = current + delta;

    // Clamp to [-100, 100]
    if (newStanding > 100) newStanding = 100;
    if (newStanding < -100) newStanding = -100;

    Reputation.setStanding(wallet, factionId, newStanding);
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm build
```

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/src/systems/ReputationSystem.sol
git commit -m "feat(contracts): add ReputationSystem with clamped standing updates"
```

---

## Task 8: Write Tests

**Files:**
- Create: `contracts/packages/contracts/test/MementoTest.t.sol`

- [ ] **Step 1: Create a test file that exercises all systems**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.24;

import "forge-std/Test.sol";
import { MudTest } from "@latticexyz/world/test/MudTest.t.sol";
import { IWorld } from "../src/codegen/world/IWorld.sol";
import { Characters, Deaths, Items, Locations, WorldEvents, Episodes, Reputation } from "../src/codegen/index.sol";
import { EntityType, EventType } from "../src/codegen/common.sol";

contract MementoTest is MudTest {
  function testRegisterCharacter() public {
    bytes32 id = bytes32("char1");
    IWorld(worldAddress).memento__registerCharacter(id, "Grumlock", address(0x1), EntityType.Character);

    string memory name = Characters.getName(id);
    assertEq(name, "Grumlock");
    assertTrue(Characters.getAlive(id));
    assertEq(Characters.getLevel(id), 1);
    assertEq(Characters.getWallet(id), address(0x1));
  }

  function testKillCharacter() public {
    bytes32 id = bytes32("char2");
    IWorld(worldAddress).memento__registerCharacter(id, "Doomed", address(0x2), EntityType.Character);
    IWorld(worldAddress).memento__killCharacter(id, "dragon fire", "The Threshold", 42);

    assertFalse(Characters.getAlive(id));

    // Death record should exist
    bytes32 deathId = keccak256(abi.encodePacked(id, block.timestamp));
    assertEq(Deaths.getCharacterId(deathId), id);
    assertEq(Deaths.getLevel(deathId), 1);
    assertEq(Deaths.getTick(deathId), 42);
  }

  function testLevelUp() public {
    bytes32 id = bytes32("char3");
    IWorld(worldAddress).memento__registerCharacter(id, "Hero", address(0x3), EntityType.Character);
    IWorld(worldAddress).memento__levelUp(id, 5);

    assertEq(Characters.getLevel(id), 5);
  }

  function testRegisterAndTransferItem() public {
    bytes32 itemId = bytes32("item1");
    bytes32 ownerId = bytes32("char1");
    bytes32 locId = bytes32("loc1");

    IWorld(worldAddress).memento__registerItem(itemId, "Iron Dagger", "common", bytes32(0), locId);
    assertEq(Items.getLocationId(itemId), locId);

    IWorld(worldAddress).memento__transferItem(itemId, ownerId);
    assertEq(Items.getOwnerId(itemId), ownerId);
    assertEq(Items.getLocationId(itemId), bytes32(0));
  }

  function testDropItem() public {
    bytes32 itemId = bytes32("item2");
    bytes32 ownerId = bytes32("char1");
    bytes32 locId = bytes32("loc1");

    IWorld(worldAddress).memento__registerItem(itemId, "Shield", "rare", ownerId, bytes32(0));
    IWorld(worldAddress).memento__dropItem(itemId, locId);

    assertEq(Items.getOwnerId(itemId), bytes32(0));
    assertEq(Items.getLocationId(itemId), locId);
  }

  function testRegisterAndDiscoverLocation() public {
    bytes32 locId = bytes32("loc1");
    IWorld(worldAddress).memento__registerLocation(locId, "The Threshold", "Ashfall", address(0));

    // Not yet discovered
    assertEq(Locations.getDiscoveredBy(locId), address(0));

    // Discover
    IWorld(worldAddress).memento__discoverLocation(locId, address(0x1));
    assertEq(Locations.getDiscoveredBy(locId), address(0x1));

    // Second discovery doesn't overwrite
    IWorld(worldAddress).memento__discoverLocation(locId, address(0x2));
    assertEq(Locations.getDiscoveredBy(locId), address(0x1));
  }

  function testRecordEvent() public {
    bytes32 eventId = bytes32("evt1");
    IWorld(worldAddress).memento__recordEvent(eventId, EventType.CombatOutcome, "Grumlock,Dragon", "The Threshold", "Dragon slain", 100);

    assertEq(WorldEvents.getSummary(eventId), "Dragon slain");
    assertEq(WorldEvents.getTick(eventId), 100);
  }

  function testRecordEpisode() public {
    bytes32 epId = bytes32("ep1");
    string memory entities = '[{"uuid":"abc","name":"Grumlock"}]';
    string memory edges = '[{"source":"Grumlock","target":"Threshold","rel":"LOCATED_IN"}]';

    IWorld(worldAddress).memento__recordEpisode(epId, "Turn 1", "Grumlock entered the tavern", entities, edges, 1);

    assertEq(Episodes.getName(epId), "Turn 1");
    assertEq(Episodes.getSummary(epId), "Grumlock entered the tavern");
    assertEq(Episodes.getTick(epId), 1);
  }

  function testReputation() public {
    bytes32 factionId = bytes32("faction1");
    address wallet = address(0x1);

    IWorld(worldAddress).memento__updateReputation(wallet, factionId, 50);
    assertEq(Reputation.getStanding(wallet, factionId), 50);

    // Delta pushes it up
    IWorld(worldAddress).memento__updateReputation(wallet, factionId, 60);
    // Should clamp to 100
    assertEq(Reputation.getStanding(wallet, factionId), 100);

    // Negative delta
    IWorld(worldAddress).memento__updateReputation(wallet, factionId, -150);
    // Should clamp to -50 (100 + -150 = -50)
    assertEq(Reputation.getStanding(wallet, factionId), -50);
  }
}
```

- [ ] **Step 2: Run tests**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
pnpm test
```

Expected: All tests pass. If any fail, fix the system code and rerun.

Note: MUD test setup may need adjustments — the `MudTest` base class handles world deployment and table registration. The function name prefixes (e.g., `memento__registerCharacter`) come from the namespace — check the generated `IWorld.sol` for exact function signatures.

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/test/MementoTest.t.sol
git commit -m "test(contracts): add tests for all game systems"
```

---

## Task 9: Local Deploy and Verify

**Files:**
- Modify: `contracts/packages/contracts/foundry.toml` (if needed for local profile)

- [ ] **Step 1: Start local anvil chain**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts
pnpm dev
```

This starts anvil on port 8545 and deploys the world. Watch the output for the World contract address.

- [ ] **Step 2: Verify deployment**

In another terminal, check the deployed world:

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/contracts/packages/contracts
cat worlds.json
```

Should show a world address for chain ID 31337 (anvil local).

- [ ] **Step 3: Test with cast**

Use Foundry's `cast` to call a system function on the local chain:

```bash
# Use anvil's default private key
export PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# Register a test character
cast send <WORLD_ADDRESS> "memento__registerCharacter(bytes32,string,address,uint8)" \
  0x0000000000000000000000000000000000000000000000000000000000000001 \
  "TestHero" \
  0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
  0 \
  --private-key $PRIVATE_KEY \
  --rpc-url http://localhost:8545

# Read back the character name
cast call <WORLD_ADDRESS> "memento__Characters_getName(bytes32)(string)" \
  0x0000000000000000000000000000000000000000000000000000000000000001 \
  --rpc-url http://localhost:8545
```

Expected: Returns "TestHero"

- [ ] **Step 4: Commit any config adjustments**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/
git commit -m "chore(contracts): local deployment verified"
```

---

## Task 10: Add Redstone Chain Profile

**Files:**
- Modify: `contracts/packages/contracts/foundry.toml`

- [ ] **Step 1: Add Redstone profile to foundry.toml**

Add under the existing profiles:

```toml
[profile.redstone]
eth_rpc_url = "https://rpc.redstone.xyz"
chain_id = 690
```

- [ ] **Step 2: Document deployment command**

For future production deployment (not running now):

```bash
export PRIVATE_KEY=0x<engine_wallet_key>
cd contracts/packages/contracts
pnpm mud deploy --profile redstone
```

- [ ] **Step 3: Commit**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori
git add contracts/packages/contracts/foundry.toml
git commit -m "chore(contracts): add Redstone chain profile for production deploy"
```
