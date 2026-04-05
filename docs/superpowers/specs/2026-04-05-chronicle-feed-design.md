# Chronicle Feed — Per-Room Narrators + Master Agent + Episode UI

## Context

The heartbeat creates episodes from game events via Delve stack/Graphiti. Currently all messages go to one narrator agent's stack. This spec adds per-room narrator agents (MCP-capable, own episode stream) and a master narrator that synthesizes world episodes. A Chronicle panel shows the feed.

## Architecture

```
Bonfire (memento-mori)
  ├─ Narrator: Threshold (agent)  → stack → room episodes
  ├─ Narrator: Market (agent)     → stack → room episodes
  ├─ Narrator: Caverns (agent)    → stack → room episodes
  │         ↓ episode summaries forwarded ↓
  └─ Master Narrator (agent)      → stack → world episodes → Chronicle UI
```

### Layer 1 — Room Narrators

Each location gets a narrator agent on the bonfire with MCP tools (mm_heartbeat, mm_search_world, mm_remember_event, mm_get_state). Room-specific system prompt. Own Matrix ID. Bridge tees room messages to this agent's stack. Heartbeat (5 min) processes stack into room-scoped episodes.

### Layer 2 — Master Narrator

Single master agent, same bonfire. No Matrix room. Stack fed by episode forwarding from room narrators (engine-side). Master heartbeat (15 min) synthesizes world-level episodes.

### Layer 3 — Chronicle Panel

Canvas-rendered sidebar panel. Entity-rich cards: title, timestamp, location, summary, entity tags. Color coded by type. REST + WebSocket delivery.

## Components

1. **Room narrator spawning** — `agent_controller.spawn_room_narrator()`, stores agent_id on KG entity
2. **Seed update** — spawn Threshold narrator + master narrator during seed
3. **Per-room stack tee** — bridge routes messages to correct narrator's stack
4. **Dual heartbeat** — room (5 min) + master (15 min), forward summaries after room processing
5. **Chronicle endpoint** — `GET /api/episodes` + `GET /api/episodes/{uuid}`
6. **Chronicle WebSocket** — `episode_feed` message type
7. **Chronicle panel** — `client/src/panels/chronicle.ts`, hotkey `c`

## Files

**New:** `client/src/panels/chronicle.ts`, `gateway/src/gateway/routes/chronicle.py`

**Modified:** agent_controller.py, seed.py, matrix_bridge.py, heartbeat.py, matrix_listener.py, ws.py, app.py (gateway), app.ts, game-state.ts
