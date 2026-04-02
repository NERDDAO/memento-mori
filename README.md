# Memento Mori

A permadeath MUD powered by CrewAI, where AI agents collaboratively narrate a dark fantasy world. The world lives in a knowledge graph. Death is permanent. The world remembers.

## Architecture

```
Client (TypeScript/Bun)          Gateway (FastAPI)              Engine (CrewAI/Python)
Pretext-rendered MUD UI    -->   Matrix bridge + WebSocket  --> 32 crews, 42 agents, 11 flows
mandatory wallet (EIP-1193)      MUD indexer proxy              Bonfires KG for world state
wiki with Lore/Chain tabs        canonical entity filter         episodic memory via Graphiti
virtualized narrative             action queuing                 dual-write KG + Redstone L2
dynamic side panels               state sync                    permadeath with memorials
```

**~5700 LOC** across engine, gateway, and client. Replaces a 90K LOC JavaScript RPG engine.

### Stack

| Layer | Tech | Purpose |
|-------|------|---------|
| Engine | Python, CrewAI, Pydantic | AI agent orchestration, game logic |
| Gateway | FastAPI, matrix-nio, httpx | HTTP/WebSocket bridge, Matrix transport, MUD indexer proxy |
| Client | TypeScript, Bun, Pretext | Rich text MUD interface, wallet gate |
| Data | Bonfires KG (Neo4j), Matrix (Synapse) | World graph, chat persistence |
| Chain | MUD framework, Solidity, Redstone L2 | Onchain world state, canonical entity verification |
| LLM | OpenRouter (Gemini Flash) | All AI reasoning |

### How It Works

1. Player types an action in the web UI
2. Gateway posts it to a Matrix room (one room per location)
3. Engine listens on Matrix, runs **GameTurnFlow**:
   - Context crew gathers world knowledge from the KG
   - Plausibility check validates the action
   - Classification crew categorizes it (combat, social, movement, etc.)
   - Detector crews extract specific events
   - Resolution flows handle combat, quests, world changes
   - Narration crew writes the prose (narrator + NPC voice actor + slopword filter)
   - Episodic memory flow records what happened
4. Engine posts narrative back to Matrix
5. Gateway relays to client via WebSocket
6. Client renders with Pretext-powered virtualized scrolling

## Quick Start

### Prerequisites

- Python 3.10+
- Bun (for client build)
- Browser wallet (MetaMask or EIP-1193 compatible)
- OpenRouter API key
- Bonfires API access (for KG)

### Install

```bash
# Engine
cd engine && pip install -e ".[dev]"

# Gateway  
cd gateway && pip install -e .

# Client
cd client && bun install
```

### Run

```bash
# Set env vars
export OPENROUTER_API_KEY="your-key"
export BONFIRE_API_KEY="your-key"
export BONFIRE_ID="your-bonfire-id"
export BONFIRE_AGENT_ID="your-agent-id"

# Chain (optional — game works without, but no onchain persistence)
export REDSTONE_RPC="https://rpc.redstone.xyz"
export MUD_WORLD_ADDRESS="0x..."
export ENGINE_PRIVATE_KEY="0x..."
export MUD_INDEXER_URL="http://localhost:3001"

# Engine-only (no gateway needed)
cd engine && python -m memento.flows.run_turn

# Full stack
./start.sh
# Open http://localhost:8080
```

### Test

```bash
cd engine && pytest tests/ -v
# 42 tests, all passing
```

## Project Structure

```
memento-mori/
  engine/                          # CrewAI game engine
    src/memento/
      models/                      # Pydantic models (Character, Location, Item, etc.)
      tools/                       # CrewAI tools
        kg.py                      #   10 KG tools (search, create, edge, status, etc.)
        mechanics.py               #   8 deterministic tools (skill checks, damage, XP, etc.)
      crews/                       # 32 crews across 9 subsystems
        context/                   #   KG context assembly
        event_detection/           #   Action classification + 5 detector crews + merge
        combat/                    #   Assessment, attack, ability, consequence, permadeath
        world_gen/                 #   Region design, location planning, location, exits
        npc_gen/                   #   Planning, concept, mechanics, finalization
        item_gen/                  #   Concept, mechanics, balance
        quest/                     #   Design, stages, dialogue
        narrative/                 #   Narration (3 agents), memory consolidation
        faction/                   #   Generation, reputation
      flows/                       # 11 flows
        game_turn.py               #   Main loop: context -> plausibility -> detect -> resolve -> narrate -> memory
        event_detection.py         #   Classify -> dispatch detectors -> merge
        combat.py                  #   Assess -> resolve -> consequences -> death check
        world_gen.py               #   Region -> locations -> NPCs -> items -> exits
        npc_gen.py                 #   Plan -> concept -> mechanics -> finalize
        item_gen.py                #   Concept -> mechanics -> balance
        quest.py                   #   Design -> stages -> dialogue
        episodic_memory.py         #   Consolidate scene -> NPC memories
        permadeath.py              #   Narrate death -> mark dead -> memorial
        faction.py                 #   Generate factions
      session.py                   # Player lifecycle (create, end, death)
      round_manager.py             # Multiplayer action batching (20s window)
      matrix_listener.py           # Engine-side Matrix watcher
      config/                      # YAML config + per-crew model assignments
    tests/                         # 42 tests

  gateway/                         # FastAPI bridge
    src/gateway/
      app.py                       # FastAPI app, WebSocket endpoint, static serving
      matrix_bridge.py             # Matrix room management, message relay
      ws.py                        # WebSocket hub, location-aware broadcast
      routes/
        action.py                  # POST /api/action
        session.py                 # POST /api/session/create (requires wallet_address)
        state.py                   # GET /api/state (queries KG)
        entity.py                  # GET /api/entity/{id} — KG entity lookup, canonical verification
        chain.py                   # GET /api/chain/{table}/{id} — MUD indexer proxy
      chain_client.py              # MUD indexer HTTP client, canonical verification helpers

  client/                          # Pretext MUD interface
    index.html                     # Dark fantasy layout, wallet gate + character creation + death overlays
    src/
      app.ts                       # Orchestrator: wires panels, wallet gate, handles messages
      chain/
        wallet.ts                  # EIP-1193 wallet connection (connectWallet, hasProvider, formatAddress)
      state/
        session.ts                 # Session management, wallet address, WebSocket, reconnect
        game-state.ts              # GameState interface, applyStateUpdate, renderState
      renderer/
        text-renderer.ts           # Styled segment parser (NPC dialogue, damage, healing)
        line-cache.ts              # NarrativeStore with Pretext measurement
        theme.ts                   # Color/font tokens
      panels/
        narrative.ts               # Virtualized narrative pane (Pretext-powered)
        input.ts                   # Command input with history
        character.ts               # Player stats panel
        inventory.ts               # Item list with rarity colors
        map.ts                     # Location, exits, NPCs present
        actions.ts                 # Dynamic contextual action buttons

  contracts/                       # MUD framework (Redstone L2)
    packages/contracts/
      mud.config.ts                # MUD table definitions (7 tables)
      src/systems/                 # Solidity systems (Character, Item, Location, Event, Reputation, Episode)
      src/codegen/                 # Auto-generated table libraries

  defs/                            # Game content
    banned_words.yaml              # Slopword filter list
    skill_defaults.yaml            # Skill categories and names
    rarities.yaml                  # Item rarity weights and colors
```

## Game Design

### Permadeath

When a character dies:
- Player node stays in the KG forever (append-only, never deleted)
- `HAS_STATUS: DEAD` and `DIED_AT` edges are created
- Death recorded onchain (immutable, timestamped)
- NPCs remember the fallen character
- Items drop at the death location
- Session kEngram is finalized as a memorial
- The death feed announces to all players
- A new character starts with nothing in the same world

### Onchain Integration (Redstone L2)

All significant world mutations are dual-written to the Bonfires KG and Redstone L2 via MUD tables. The chain is the **canonicality gate** — entities only appear in the client if they exist onchain.

| Table | What it stores |
|-------|---------------|
| Characters | Name, wallet, level, alive/dead, creation time |
| Deaths | Cause, location, level at death, game tick |
| Items | Name, rarity, owner, location |
| Locations | Name, region, discoverer |
| WorldEvents | Type, actors, location, summary, tick |
| Episodes | Full Graphiti extraction (entities + edges as JSON) |
| Reputation | Wallet, faction, standing |

The gateway proxies MUD indexer reads via `/api/chain/{table}/{id}`. The wiki's Chain tab displays structured onchain fields alongside KG lore. Wallet connection is mandatory (x402 payments).

### Knowledge Graph

Every game object is a KG entity with edges:

```
Player --[LOCATED_IN]--> Location --[EXIT_TO]--> Location
Player --[CARRIES]--> Item
NPC --[MEMBER_OF]--> Faction
NPC --[DISPOSITION]--> Player  (friendship, trust, respect, romance)
Faction --[ALLIED_WITH|HOSTILE_TO]--> Faction
Player --[HAS_QUEST]--> Quest
Player --[DIED_AT]--> Location  (permadeath memorial)
```

### Episodic Memory

After each turn, the scene is consolidated into an episode via the Bonfires stack. NPCs form memories from their own perspective. The world accumulates history that influences future narration via centered KG searches.

### Crews

| Subsystem | Crews | Agents | Purpose |
|-----------|-------|--------|---------|
| Context | 1 | 1 | KG search before narration |
| Event Detection | 8 | 8 | Classify + detect + merge |
| Combat | 5 | 7 | Assess, resolve, consequences, permadeath |
| World Gen | 4 | 6 | Regions, locations, exits |
| NPC Gen | 4 | 5 | Concept, personality, stats, placement |
| Item Gen | 3 | 3 | Concept, stats, balance |
| Quest | 3 | 4 | Design, stages, dialogue |
| Narrative | 2 | 5 | Narration + memory |
| Faction | 2 | 3 | Generation + reputation |
| **Total** | **32** | **42** | |

## License

MIT
