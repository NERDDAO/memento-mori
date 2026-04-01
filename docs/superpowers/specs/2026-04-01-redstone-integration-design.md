# Redstone Onchain Integration

## Overview

Dual-write world state to both the Bonfires Knowledge Graph (Neo4j) and Redstone L2 (MUD tables). Every significant world mutation — character creation, death, item creation, location discovery, world events — gets recorded onchain as an immutable, verifiable record. The KG remains the fast read layer for AI crews; the chain becomes the source of truth for ownership, permadeath, and world history.

## Current Architecture

All world mutations flow through 5 KG tools in `engine/src/memento/tools/kg.py`:

| Tool | What it writes |
|------|---------------|
| `create_entity(name, type, summary)` | New entity node |
| `create_edge(source, target, relationship, fact)` | Relationship between entities |
| `update_entity(name, summary, labels)` | Update entity properties |
| `mark_status(entity, status, cause)` | Status change (dead, cursed, etc.) |
| `remember_event(summary)` | Episodic memory entry |

These are called by:
- `SessionManager.create_player()` → `create_entity` + `create_edge(LOCATED_IN)`
- `SessionManager.handle_death()` → `create_edge(DIED_AT, KILLED_BY)`
- `CombatFlow` → crews use `mark_status`, `create_edge`, `update_entity`
- `WorldGenFlow` → crews use `create_entity`, `create_edge` for locations/NPCs/items
- `GameTurnFlow` → crews use all tools during event resolution

**Key insight:** All mutations go through these 5 functions. The dual-write intercept is clean — decorate these tools to also emit onchain transactions.

## Design

### MUD Tables (Onchain Schema)

Deployed on Redstone L2 using the MUD framework's table system.

**Characters**
```
id:          bytes32    (KG UUID as bytes32)
name:        string
wallet:      address
level:       uint32
alive:       bool
createdAt:   uint256    (block timestamp)
```

**Deaths**
```
id:          bytes32    (auto-generated)
characterId: bytes32    (FK to Characters)
cause:       string
location:    string
level:       uint32
tick:        uint256    (in-game time tick)
timestamp:   uint256    (block timestamp)
```

**Items**
```
id:          bytes32    (KG UUID as bytes32)
name:        string
rarity:      string
ownerId:     bytes32    (FK to Characters, or 0x0 if unowned)
locationId:  bytes32    (FK to Locations, where it sits if unowned)
```

**Locations**
```
id:          bytes32    (KG UUID as bytes32)
name:        string
region:      string
discoveredBy: address   (wallet of first player to enter)
```

**WorldEvents**
```
id:          bytes32    (auto-generated)
eventType:   string     (combat_outcome, quest_complete, npc_death, discovery)
actors:      string     (comma-separated entity names)
location:    string
summary:     string
tick:        uint256    (in-game time tick)
```

**Episodes**
```
id:          bytes32    (episode UUID)
name:        string
summary:     string     (full episode text — the reconstructable unit)
entities:    string     (JSON array of entity refs: [{uuid, name, role}])
edges:       string     (JSON array of edges: [{source, target, relationship, fact}])
tick:        uint256    (in-game time tick)
timestamp:   uint256    (block timestamp)
```

Episodes are the **reconstruction primitive**. Each episode contains enough structured data (entity refs + edges + summary) to rebuild the KG subgraph it represents. Given the full chain of episodes, a fresh graph database can be populated by replaying them in order — creating entities on first mention, creating edges as they appear, and accumulating summaries as entity descriptions.

**Reputation**
```
wallet:      address
factionId:   bytes32    (KG UUID)
standing:    int32      (-100 to 100)
```

### Engine Changes

#### New: `engine/src/memento/tools/chain.py`

Thin wrapper around MUD system calls. Handles:
- Converting KG UUIDs to bytes32
- Submitting transactions to Redstone via the engine's wallet
- Async transaction submission (fire-and-forget, don't block the game loop)
- Graceful failure — if chain is down, KG write still succeeds, chain write queued for retry

```python
# Public API
def register_character(uuid: str, name: str, wallet: str, level: int) -> None
def record_death(character_uuid: str, cause: str, location: str, level: int, tick: int) -> None
def register_item(uuid: str, name: str, rarity: str, owner_uuid: str, location_uuid: str) -> None
def register_location(uuid: str, name: str, region: str, discoverer_wallet: str) -> None
def record_event(event_type: str, actors: list[str], location: str, summary: str, tick: int) -> None
def update_reputation(wallet: str, faction_uuid: str, delta: int) -> None
def transfer_item(item_uuid: str, new_owner_uuid: str) -> None
def release_items_on_death(character_uuid: str, location_uuid: str) -> None
def record_episode(uuid: str, name: str, summary: str, entities: list[dict], edges: list[dict], tick: int) -> None
```

#### Modified: `engine/src/memento/tools/kg.py`

Add chain calls after successful KG writes. The chain call is async and non-blocking — the KG write is authoritative for game flow, the chain write is the permanent record.

```python
# In create_entity, after KG write succeeds:
if entity_type in ("Character", "Player"):
    chain.register_character(uuid, name, wallet="", level=1)
elif entity_type in ("Item", "Weapon", "Armor", "Consumable"):
    chain.register_item(uuid, name, summary, owner_uuid="", location_uuid="")
elif entity_type in ("Location", "Room", "Region"):
    chain.register_location(uuid, name, region="", discoverer_wallet="")

# In create_edge, after KG write succeeds:
if relationship in ("DIED_AT", "KILLED_BY"):
    chain.record_death(source_uuid, fact, target_name, level=0, tick=0)

# In mark_status, after KG write succeeds:
if status == "dead":
    chain.record_death(entity_uuid, cause, location="", level=0, tick=0)
    chain.release_items_on_death(entity_uuid, location_uuid="")

# In remember_event, after KG write succeeds:
chain.record_event("game_event", [], "", summary, tick=0)
```

**Post-turn chain sync** (in `GameTurnFlow.post_turn`, after Graphiti episode is processed):

```python
# 1. Graphiti has already processed the episode (existing remember_event flow)
# 2. Fetch the structured result from Bonfires SDK
from memento.bonfires_client import get_client
client = get_client()
latest = client.episodes.latest()  # new SDK method

# 3. Push to Redstone
chain.record_episode(
    uuid=latest["episode"]["uuid"],
    name=latest["episode"]["name"],
    summary=latest["episode"]["summary"],
    entities=latest["entities"],   # Graphiti's extracted entities
    edges=latest["edges"],         # Graphiti's extracted edges
    tick=self.state.world_time.get("tick", 0),
)
```

#### Modified: `engine/src/memento/session.py`

- `create_player(player_name, wallet_address)` — accept wallet address, pass to `chain.register_character()`
- `handle_death(player_id, cause, location)` — call `chain.record_death()` and `chain.release_items_on_death()`

#### Modified: `gateway/src/gateway/routes/session.py`

- `CreateSessionRequest` — add optional `wallet_address: str = ""`
- Pass wallet to `SessionManager.create_player()`

#### New: `engine/src/memento/config/chain.py`

Chain configuration:
```python
REDSTONE_RPC = os.getenv("REDSTONE_RPC", "https://rpc.redstone.xyz")
WORLD_CONTRACT = os.getenv("MUD_WORLD_CONTRACT", "")
ENGINE_PRIVATE_KEY = os.getenv("ENGINE_PRIVATE_KEY", "")
CHAIN_ENABLED = bool(WORLD_CONTRACT and ENGINE_PRIVATE_KEY)
```

### Client Changes

#### Wallet Connection

Add wallet connect to the character creation flow:
- Optional — players can play without a wallet (no onchain persistence)
- If connected, wallet address sent with `CreateSessionRequest`
- Show onchain status in the character panel (chain icon if connected)

#### Wiki Panel — Onchain Data

When viewing an entity in the wiki, show onchain data alongside KG data:
- Characters: onchain death count, total XP across lives
- Items: onchain ownership history
- Locations: who discovered it, when
- Pull from MUD indexer (automatic with MUD framework)

### Contracts

#### Directory: `contracts/`

MUD project structure:
```
contracts/
├── mud.config.ts          # MUD table definitions
├── src/
│   ├── systems/
│   │   ├── CharacterSystem.sol    # register, kill, levelUp
│   │   ├── ItemSystem.sol         # register, transfer, release
│   │   ├── LocationSystem.sol     # register, discover
│   │   ├── EventSystem.sol        # record
│   │   └── ReputationSystem.sol   # update
│   └── codegen/                   # auto-generated by MUD
├── package.json
└── foundry.toml
```

#### Access Control

Only the engine wallet can write to the MUD world. Players don't submit transactions directly — the engine is the game master and the sole authority on game outcomes. Players verify by reading the chain.

### Data Flow: Extract-Then-Chain

Graphiti extracts first, then the structured result goes onchain. The chain stores Graphiti's actual extraction output — not raw text that needs re-processing.

```
Engine turn completes (narrative + state changes)
    │
    ▼
Call Graphiti process_episode (existing flow)
    │  ← Graphiti extracts entities, edges, summaries
    ▼
Await extraction completion
    │
    ▼
Fetch latest episode from Bonfires SDK
    │  ← new endpoint: client.episodes.latest()
    │  ← returns: { episode, entities: [{uuid, name, labels, summary}], edges: [{src, tgt, rel, fact}] }
    ▼
Push to Redstone
    ├── Episodes table: full episode with extracted entities + edges as JSON
    ├── Structural table writes (Characters, Items, Locations, Deaths)
    └── Transaction confirmed
```

**Why extract-then-chain:**
- Onchain record contains Graphiti's actual extraction — entities, edges, facts as structured data
- No re-extraction needed for structural reconstruction — just load the JSON
- Re-extraction only needed if you want a *different* semantic interpretation
- Graphiti is the extractor, chain is the store, KG is the index

### Reconstruction Flow

Two types of data, two recovery paths:

**Structural data** (Locations, NPCs, Items, Quests, Deaths):
```
Chain tables → download → load directly into KG as nodes
```
Fixed schema, no AI needed. Create KG nodes with labels and properties from MUD indexer.

**Semantic data** (entity summaries, relationships, NPC memories):
```
Chain episodes → download → entities/edges JSON already extracted → load into KG
```
Each onchain episode already contains Graphiti's extraction output as structured JSON. No re-extraction needed for a faithful copy — just parse the JSON and create the KG nodes/edges.

**Re-extraction** (optional, for different semantic interpretation):
```
Chain episodes → download → re-run summaries through Graphiti → different KG
```
Users who want a different semantic lens can re-extract from the episode summaries. Same events, different entity resolution or relationship inference.

**Full reconstruction:**
1. Download structural tables from chain → create base KG nodes (Characters, Items, Locations)
2. Download Episodes from chain, ordered by tick
3. Parse each episode's `entities` and `edges` JSON → create KG nodes and edges
4. Latest episode's entity summary wins for each node (accumulative)
5. Result: fully populated KG — structural data is exact, semantic data is Graphiti's original extraction

### What Goes Where

| Data | KG (Neo4j) | Chain (Redstone) | Reconstructable? |
|------|-----------|-----------------|-------------------|
| Entity creation | Yes | Yes (Characters, Items, Locations) | From Episodes |
| Entity relationships | Yes | Yes (embedded in Episodes) | From Episodes |
| Entity updates | Yes | Level changes + via Episodes | From Episodes |
| Death | Yes | Yes (immutable record) | Deaths table |
| Item ownership | Yes | Yes (transfer log) | Items table |
| Episodes | Yes (Graphiti) | Yes (full structured data) | **Primary reconstruction source** |
| NPC dialogue | Yes | Embedded in episode summary | From Episodes |
| Narrative text | Yes | Embedded in episode summary | From Episodes |
| Room descriptions | Yes | No (generated, not canonical) | Re-generatable |
| World events | Yes | Yes | WorldEvents table |
| Player position | Yes | No (ephemeral) | N/A |
| Faction reputation | Yes | Yes | Reputation table |

### KG Reconstruction from Chain

Given the Episodes table onchain, a fresh KG can be rebuilt:

1. Read all Episodes from chain, ordered by tick/timestamp
2. For each episode, parse the `entities` JSON — create nodes that don't exist yet
3. For each episode, parse the `edges` JSON — create edges
4. Apply entity summaries (latest episode's summary wins)
5. Cross-reference Characters, Items, Locations, Deaths tables for authoritative state

This means the chain is not just an audit log — it's a **complete world backup**. If the KG is lost, the world can be reconstructed. If you want to fork the world, replay episodes up to a certain tick.

### Failure Modes

- **Chain down, KG up:** Game continues normally. Chain writes queued in a local buffer, replayed when chain recovers. No gameplay impact.
- **KG down, chain up:** Game cannot proceed (AI needs KG for context). Chain is not a substitute for KG reads.
- **Both down:** Game cannot proceed.
- **Chain write fails:** Logged, retried with exponential backoff. KG is already written so game state is consistent. Worst case: some events missing from chain (gaps in the permanent record, not in gameplay).

## Environment Variables

```bash
# Redstone L2
REDSTONE_RPC=https://rpc.redstone.xyz
MUD_WORLD_CONTRACT=0x...          # deployed World contract address
ENGINE_PRIVATE_KEY=0x...           # engine's signing key (hot wallet)
CHAIN_ENABLED=true                 # toggle dual-write (false = KG only)
```

### Status Footer

A persistent footer bar below the command window showing the chain sync pipeline status. Uses the same TUI styling as the rest of the UI.

```
┌─ Status ──────────────────────────────────────────────────────┐
│ ⟳ Fetching episode...  │  ◆ Redstone: synced  │  ☽ Tick 42   │
└───────────────────────────────────────────────────────────────┘
```

**Sections:**
- **Left:** Current pipeline action — cycles through:
  - `Processing turn...` (engine working)
  - `Extracting episode...` (Graphiti processing)
  - `Fetching episode...` (SDK call)
  - `Pushing onchain...` (Redstone transaction)
  - `Synced ✓` (idle, all caught up)
- **Center:** Chain connection status — `◆ Redstone: synced` / `◇ Redstone: offline`
- **Right:** Current game tick — `☽ Tick 42`

**Implementation:**
- New component: `client/src/ui/status.ts`
- Gateway sends status events via WebSocket: `{ type: 'status', phase: 'extracting' | 'fetching' | 'pushing' | 'synced', tick: number }`
- Footer updates on each status message, auto-clears to "synced" after 3s of no updates

## Out of Scope (Phase 2+)

- Player-to-player item trading via chain
- Faction wars resolved by onchain voting
- World gen proposals (players stake to propose regions)
- Token economics / in-game currency on chain
- Cross-instance world state sharing
- Client-side transaction submission
- Chain as authoritative source (currently KG is authoritative)

## Files Changed

### New
- `contracts/` — MUD project (tables, systems, config)
- `engine/src/memento/tools/chain.py` — Redstone write helpers
- `engine/src/memento/config/chain.py` — chain configuration

### Modified
- `engine/src/memento/tools/kg.py` — add chain calls after KG writes (lines 43-116)
- `engine/src/memento/session.py` — accept wallet, call chain on create/death (lines 14-120)
- `gateway/src/gateway/routes/session.py` — wallet_address in CreateSessionRequest (line 9-11)
- `client/src/ui/wiki.ts` — show onchain data tab
- `client/index.html` — wallet connect button in character creation overlay

### Bonfires SDK/CLI Additions

**New SDK endpoint: `client.episodes.latest()`**
- Returns the most recent episode with its extracted entities and edges
- Response shape:
```json
{
  "episode": {
    "uuid": "...",
    "name": "...",
    "summary": "...",
    "created_at": "..."
  },
  "entities": [
    { "uuid": "...", "name": "...", "labels": [...], "summary": "..." }
  ],
  "edges": [
    { "source_uuid": "...", "target_uuid": "...", "source_name": "...", "target_name": "...", "relationship": "...", "fact": "..." }
  ]
}
```

**New CLI command: `bonfire episodes latest`**
- Prints the latest episode with entities and edges
- Flags: `--json` for machine-readable output

These need to be added to the Bonfires platform (delve backend + SDK + CLI), not the memento-mori repo.

### Dependencies
- `web3.py` or `viem` (Python) for chain interaction
- MUD CLI for contract deployment
- Foundry for contract compilation
- Bonfires SDK with `episodes.latest()` endpoint (new)
