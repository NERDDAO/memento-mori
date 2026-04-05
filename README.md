# Memento Mori

A permadeath MUD powered by CrewAI, where AI agents collaboratively narrate a dark fantasy world. The world lives in a knowledge graph. Death is permanent. The world remembers.

## Architecture

```
Client (TypeScript/Bun)          Gateway (FastAPI)              Engine (CrewAI/Python)
Pretext-rendered MUD UI    -->   Matrix bridge + WebSocket  --> 32 crews, 42 agents, 11 flows
mandatory wallet (EIP-1193)      MUD indexer proxy              Bonfires KG for world state
codex entity browser             inventory REST endpoints       episodic memory via Graphiti
optimistic state updates         codex data assembly            dual-write KG + Redstone L2
dynamic side panels              NPC agent MCP tools            entity enrichment crew
```

### Stack

| Layer | Tech | Purpose |
|-------|------|---------|
| Engine | Python, CrewAI, Pydantic | AI agent orchestration, game logic, enrichment |
| Gateway | FastAPI, matrix-nio, httpx | HTTP/WebSocket bridge, Matrix transport, MUD indexer proxy |
| Client | TypeScript, Bun, Pretext | Rich text MUD interface, wallet gate, optimistic inventory |
| Data | Bonfires KG (Neo4j/LadybugDB), Matrix (Synapse) | World graph, chat persistence |
| Chain | MUD framework, Solidity, Redstone L2 | Onchain world state, canonical entity verification |
| LLM | OpenRouter (Gemini Flash) | All AI reasoning |

### How It Works

1. Player types an action in the web UI (command input below narrative)
2. Gateway posts it to a Matrix room (one room per location)
3. Engine listens on Matrix, runs **RoundController**:
   - Context crew gathers world knowledge from the KG
   - Plausibility check validates the action
   - Classification crew categorizes it (combat, social, movement, etc.)
   - Detector crews extract specific events (combat, inventory, quest, world change)
   - Resolution flows handle combat, quests, world changes
   - NPC response window (15s) lets NPC agents respond first
   - Narration crew writes the prose (narrator + NPC voice actor + slopword filter)
   - Episodic memory flow records what happened
4. Engine posts narrative back to Matrix
5. Gateway relays to client via WebSocket with structured state updates
6. Client renders with Pretext-powered virtualized scrolling

### Inventory System

Structured actions bypass the narrative crew pipeline for instant feedback:

| Action | Flow |
|--------|------|
| Equip/Unequip | Client → REST → KG update → WebSocket broadcast |
| Drop | Client → REST → Chain tx + KG edge expire → Room manifest update |
| Pickup | Client → REST → Chain tx + KG edge create → Inventory manifest update |
| Use | Client → REST → Apply effects + KG update → State broadcast |
| Trade | Narrative input → Inventory detector crew → Structured transfer |

Chain is canonical owner (MUD Items table). KG stores temporal edges (CARRIES with valid_at/expired_at). Manifests merge both into unified views. Client uses optimistic updates with snapshot/rollback.

### Codex (Entity Browser)

The Codex (`k` hotkey) replaces the wiki panel — a location-centric entity browser:

- **Sidebar**: Current room with NPCs + ground items nested, exits, player
- **Detail panel**: Entity summary, structured attributes (stats, abilities, personality), inline onchain data
- **Manifest-scoped**: Only shows entities the player can interact with
- **Enrichment crew**: Background LLM fills missing entity attributes on first codex open
- **Jump bar**: Section chips for quick navigation within entity detail

### NPC Agent Architecture

Each NPC is a Bonfires AI agent with its own Matrix identity:
- Agents connect via Matrix appservice
- 30 engine tools exposed as gateway endpoints (MCP HTTP tools)
- Tool access gated by KG entity labels
- NPC response window in round controller ensures NPCs respond before narration

## Quick Start

### Prerequisites

- Python 3.10+
- Bun (for client build)
- Browser wallet (MetaMask or EIP-1193 compatible)
- OpenRouter API key
- Bonfires API access (for KG)
- Docker (for MongoDB, Neo4j/LadybugDB, Weaviate, Synapse)

### Run

```bash
# Set env vars (copy .env.dev for local development)
cp .env.dev.example .env.dev

# Full stack (gateway + engine + client build)
./start.sh --dev

# Open http://localhost:8081
```

### Test

```bash
cd engine && pytest tests/ -v
# 123+ tests passing
```

## Project Structure

```
memento-mori/
  engine/                          # CrewAI game engine
    src/memento/
      models/                      # Pydantic models (Character, Location, Item, Quest, etc.)
        attributes.py              #   Entity attribute schemas (NPCAttributes, ItemAttributes, LocationAttributes)
      tools/                       # CrewAI tools
        kg.py                      #   10 KG tools (search, create, edge, status, etc.)
        mechanics.py               #   8 deterministic tools (skill checks, damage, XP, etc.)
        chain.py                   #   Chain write helpers (register, transfer, drop)
      crews/                       # 33 crews across 10 subsystems
        context/                   #   KG context assembly
        event_detection/           #   Action classification + 5 detector crews + merge
        combat/                    #   Assessment, attack, ability, consequence, permadeath
        world_gen/                 #   Region design, location planning, location, exits
        npc_gen/                   #   Planning, concept, mechanics, finalization
        item_gen/                  #   Concept, mechanics, balance
        quest/                     #   Design, stages, dialogue
        narrative/                 #   Narration (3 agents), memory consolidation
        faction/                   #   Generation, reputation
        enrichment/                #   Entity data completeness (fills missing attributes)
      flows/                       # 12 flows
        enrichment.py              #   Entity enrichment on room load
      round_controller.py          # Stoplight orchestrator (replaces GameTurnFlow)
      round_manager.py             # Multiplayer action batching (20s window)
      inventory_manifest.py        # Player inventory from KG edges (temporal filtering)
      inventory_actions.py         # Deterministic equip/drop/use/pickup handlers
      room_manifest.py             # Room state from KG (NPCs, items, exits)
      session.py                   # Player lifecycle (create, join, death)
      agent_controller.py          # NPC agent spawn/move/kill lifecycle
      bonfires_client.py           # Lazy-initialized Bonfires SDK client
    tests/                         # 123+ tests

  gateway/                         # FastAPI bridge
    src/gateway/
      app.py                       # FastAPI app, WebSocket endpoint, static serving
      matrix_bridge.py             # Matrix room management, message relay
      ws.py                        # WebSocket hub, location-aware broadcast
      routes/
        action.py                  # POST /api/action
        session.py                 # POST /api/session/create, /join, /characters
        state.py                   # GET /api/state, /worldmap, /room-manifest
        entity.py                  # GET /api/entity/{id} — KG entity + canonical verification
        chain.py                   # GET /api/chain/{table}/{id} — MUD indexer proxy
        inventory.py               # POST /api/inventory/equip|drop|use|pickup
        codex.py                   # GET /api/codex/{player_id} — manifest-scoped entity assembly
        engine.py                  # 30 engine MCP tool endpoints for NPC agents

  client/                          # Pretext MUD interface
    src/
      app.ts                       # Orchestrator: panels, modals, hotkeys, message handling
      state/
        game-state.ts              # GameState, InventoryItem, applyStateUpdate
        session.ts                 # WebSocket, session management
        inventory-api.ts           # Optimistic inventory actions (snapshot/rollback)
        round-state.ts             # Round phase tracking
      ui/
        inventory-modal.ts         # Two-column paperdoll modal (i hotkey)
        codex-modal.ts             # Location-centric entity browser (k hotkey)
        dialog.ts                  # NPC dialogue + quest detail modal
        status.ts                  # Status bar (phase, chain, tick, activity)
      panels/
        narrative.ts               # Virtualized narrative pane
        inventory.ts               # Sidebar: equipped slots + backpack
        character.ts               # Player stats
        exits.ts                   # Direction buttons
        present.ts                 # NPCs + items in room
        questlog.ts                # Active quests
      types/
        ws-messages.ts             # Discriminated union for all WebSocket message types
        schema.generated.ts        # Auto-generated from engine Pydantic models

  contracts/                       # MUD framework (Redstone L2)
    packages/contracts/
      mud.config.ts                # Characters, Deaths, Items (with slotType, quantity), Epochs
```

## Game Design

### Permadeath

When a character dies:
- Player node stays in the KG forever (append-only, never deleted)
- `HAS_STATUS: DEAD` and `DIED_AT` edges are created
- Death recorded onchain (immutable, timestamped)
- NPCs remember the fallen character
- Items drop at the death location
- The death feed announces to all players
- A new character starts with nothing in the same world

### Onchain Integration (Redstone L2)

All significant world mutations are dual-written to the Bonfires KG and Redstone L2 via MUD tables. The chain is the **canonicality gate** — entities only appear in the client if they exist onchain.

| Table | What it stores |
|-------|---------------|
| Characters | Name, wallet, level, alive/dead, creation time |
| Deaths | Cause, location, level at death, game tick |
| Items | Name, rarity, slotType, quantity, owner, location |
| Epochs | State root, IPFS CID, tick, timestamp |

### Knowledge Graph

Every game object is a KG entity with temporal edges:

```
Player --[CARRIES {valid_at, expired_at}]--> Item
Player --[LOCATED_IN]--> Location --[EXIT_TO]--> Location
NPC --[LOCATED_IN]--> Location
NPC --[MEMBER_OF]--> Faction
Player --[HAS_QUEST]--> Quest
Player --[DIED_AT]--> Location  (permadeath memorial)
```

Edges use Graphiti's bi-temporal model: `valid_at` (when true), `expired_at` (when invalidated). Inventory drops expire CARRIES edges and create LOCATED_IN edges — the KG maintains full ownership history.

### Entity Attributes

Structured data stored in KG entity attributes (JSON):

- **NPCs**: level, stats (STR/DEX/CON/INT/WIS/CHA), skills, abilities, personality, backstory, speech pattern, motivation, disposition
- **Items**: damage, defense, weight, effects, rarity, slot type, lore
- **Locations**: biome, danger level, culture, threats, secrets, atmosphere, lore

The enrichment crew fills missing attributes on room load using a lightweight LLM call.

### Crews

| Subsystem | Crews | Purpose |
|-----------|:-----:|---------|
| Context | 1 | KG search before narration |
| Event Detection | 6 | Classify + detect (combat, inventory, quest, world) + merge |
| Combat | 5 | Assess, resolve, consequences, permadeath |
| World Gen | 4 | Regions, locations, exits |
| NPC Gen | 4 | Concept, personality, stats, placement |
| Item Gen | 3 | Concept, stats, balance |
| Quest | 3 | Design, stages, dialogue |
| Narrative | 2 | Narration + memory |
| Faction | 2 | Generation + reputation |
| Enrichment | 1 | Fill missing entity attributes |
| **Total** | **31** | |

## License

MIT
