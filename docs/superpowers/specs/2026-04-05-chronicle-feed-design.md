# Chronicle Feed — Per-Room Narrator Agents + Delve Subscriptions

## Context

The TurnController creates fast turns (NPC wait, narrate, time advance) and the HeartbeatRunner processes the narrator's Delve stack into episodes. Currently all room messages go to one narrator agent's stack, and WorldReactionCrew handles entity spawning engine-side.

This spec replaces the single narrator + engine-side WorldReactionCrew with **per-room narrator agents** that are fully autonomous: they process their own stacks, spawn entities via MCP tools, and post narration into their location's Matrix room. A **master narrator** agent synthesizes world-level episodes from room narrator output. A **chronicle API** serves episodes to clients.

Key simplification: no custom heartbeat cycles. The bonfires-ai supervisor cron (`@Cron('19,39,59 * * * *')`, ~20 min) already processes all active agents' stacks. The engine's `mm_heartbeat` MCP tool remains for on-demand processing during active gameplay.

## Architecture

```
Game Events (player actions, NPC dialogue in Matrix rooms)
  │
  ├─ Bridge tees room messages → room narrator's Delve stack
  │
  │  [Supervisor cron ~20 min] processes all agent stacks → episodes
  │  [mm_heartbeat MCP tool] on-demand processing
  │
  ├─ Room Narrator Agent (per location, not directly addressable)
  │     Reads episode → calls MCP tools (spawn NPCs, items, world reaction)
  │     Tool calls appear in location Matrix room
  │     Final message = useful narration/chronicle posted to location room
  │
  │  [Delve subscription] auto-forwards episode summary → master narrator stack
  │
  └─ Master Narrator Agent (no Matrix room)
       Supervisor cron processes its stack → world-level episodes
       Available via chronicle API
```

## Layer 1: Room Narrator Agents

### What they are

Bonfires-ai agents on the memento bonfire. One per location. **Not directly addressable** — no one messages them. They only activate when the supervisor cron processes their stack and the LangGraph agent loop runs.

### What they do

After stack processing creates an episode:
1. Agent reads the episode (game events that happened in this location)
2. Decides what the world needs — new NPCs, items, location changes, lore
3. Calls MCP tools to execute: `mm_world_reaction` (wraps WorldReactionCrew), `mm_search_world`, `mm_get_state`, `mm_spawn_entity`
4. Tool calls post into the **location's Matrix room** — players see entities appearing
5. Final agent message is a useful narration/chronicle of what happened, posted to the location room

### MCP tools

| Tool | Purpose |
|------|---------|
| `mm_world_reaction` | Wraps WorldReactionCrew — spawns NPCs, items, quests, lore from seeds |
| `mm_search_world` | Query KG for existing entities (avoid duplicates) |
| `mm_get_state` | Read current location state (who/what is here) |
| `mm_spawn_entity` | Direct entity creation (single NPC, item) |
| `mm_heartbeat` | Trigger on-demand stack processing |

### System prompt pattern

Location-specific. Instructs the agent to:
- Review the episode for significant events
- Check existing entities via `mm_search_world` before spawning (deduplication)
- Use `mm_world_reaction` for batch entity creation from extracted seeds
- Post a concise, atmospheric narration as its final message
- Never duplicate entities that already exist in the KG

### Spawning

- **Seed time**: `seed.py` creates Threshold narrator + master narrator during world seed
- **Dynamic**: `agent_controller.spawn_room_narrator(location_uuid, location_name)` when a location is first visited by a player
- Narrator `agent_id` stored on the KG location entity
- New narrators auto-subscribe to the master narrator via Delve subscription API

### Matrix posting

Room narrators post to the **location's Matrix room** (not their own room). The bridge identifies narrator messages by sender and routes them as `narrative` type to WebSocket clients at that location.

The narrator agent needs a Matrix identity (`@narrator-{slug}:localhost`) registered via the appservice, but it only sends — never receives from players.

## Layer 2: Master Narrator Agent

Single agent on the memento bonfire. No Matrix room. No Matrix identity.

- Stack fed by **Delve subscriptions** from all room narrators
- When room narrator episodes are created, Delve auto-forwards summaries to master's stack
- Supervisor cron processes master's stack → world-level episodes
- World episodes synthesize cross-room events: "While the Market burned, the Caverns stirred..."
- System prompt: synthesize location episodes into world-level chronicle entries

Master narrator does NOT call MCP tools or post to Matrix. It exists solely to produce world-level episodes available via the chronicle API.

## Layer 3: Delve Agent Subscriptions (new platform feature)

Reusable feature — not memento-specific. Any agent can subscribe to another agent's episode output.

### Agent model change

New field on `Agent` document:

```python
episode_subscribers: list[str] = []  # agent IDs that receive episode summaries
```

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/agents/{id}/subscribers` | Add subscriber agent ID |
| `DELETE` | `/agents/{id}/subscribers/{target_id}` | Remove subscriber |
| `GET` | `/agents/{id}/subscribers` | List subscribers |

### Hook point

In `stack_service._process_stack_background()`, after `episode_service.create_single_episode()` succeeds (~line 1125):

1. Read `agent.episode_subscribers`
2. For each subscriber, push a summary message to their stack via `mongo_service.add_message()`:
   ```python
   {
     "text": f"[Episode from {agent.name}] {episode_summary}",
     "userId": agent_id,
     "chatId": f"subscription:{agent_id}",
     "metadata": {"forwarded_from": agent_id, "episode_uuid": uuid}
   }
   ```
3. Loop prevention: messages with `forwarded_from` in metadata are excluded from re-forwarding during stack processing

Follows the existing `_forward_episode_to_clusters()` pattern in stack_service.py.

## Layer 4: Chronicle API

### Gateway endpoints

New file: `gateway/src/gateway/routes/chronicle.py`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/episodes` | Paginated episode feed, proxies Delve |
| `GET` | `/api/episodes/{uuid}` | Single episode detail |

Query params: `agent_id` (filter by narrator), `limit`, `offset`, `type` (room/world).

### WebSocket delivery

New message type `episode_feed`:
```json
{
  "type": "episode_feed",
  "episode_uuid": "...",
  "agent_id": "...",
  "name": "...",
  "summary": "...",
  "location": "...",
  "timestamp": "..."
}
```

Pushed when new episodes are created. The engine's heartbeat (when triggered via `mm_heartbeat`) or a lightweight poller in the gateway checks Delve's latest episode endpoint for active narrators and pushes new episodes to connected WS clients. Initial implementation: gateway polls on a 60s interval, compares episode UUIDs, pushes deltas.

## Crew Prompt Adjustments

### Deduplication

Room narrator agents see the narration crew's output (it's in their stack). The agent's system prompt must instruct:

- **Before spawning**: Always call `mm_search_world` to check if an entity already exists
- **After narration crew runs**: Don't re-narrate what the crew already described — focus on world evolution (spawns, state changes) and a concise chronicle entry
- **WorldReactionCrew as tool**: The crew itself checks KG before creating entities, but the agent adds a second layer of validation

### Narration crew changes

The existing narration crew (`crews/narrative/narration/crew.py`) continues to run during TurnController turns for real-time narration. Room narrators handle the **between-turn** world evolution on the 20-min cycle. No overlap — different cadences, different purposes:

- **Narration crew** (per turn, real-time): Atmospheric prose for player actions
- **Room narrator agent** (20-min cron): World evolution, entity spawning, chronicle entries

## Files Modified

### Delve (new platform feature)

| File | Change |
|------|--------|
| `src/infrastructure/database/models/agent.py` | Add `episode_subscribers: list[str]` field |
| `src/api/routes/agent_routes.py` | Add subscriber CRUD endpoints |
| `src/core/services/stack_service.py` | Add forwarding hook after episode creation |

### Memento-mori engine

| File | Change |
|------|--------|
| `engine/src/memento/agent_controller.py` | Add `spawn_room_narrator()` method |
| `engine/src/memento/seed.py` | Spawn Threshold narrator + master narrator |
| `engine/src/memento/tools/world_reaction_tool.py` | New MCP tool wrapping WorldReactionCrew |

### Memento-mori gateway

| File | Change |
|------|--------|
| `gateway/src/gateway/matrix_bridge.py` | Per-room stack routing (lookup narrator agent_id by location) |
| `gateway/src/gateway/routes/chronicle.py` | New chronicle proxy endpoints |
| `gateway/src/gateway/ws.py` | `episode_feed` WS message type |
| `gateway/src/gateway/app.py` | Register chronicle router |

## Verification

1. **Delve subscriptions**: Create two test agents, subscribe one to the other, process source stack, verify summary appears in subscriber's stack
2. **Room narrator spawn**: Run seed, verify Threshold narrator agent exists on bonfire with correct MCP tools
3. **Stack routing**: Send a message in a location room, verify it arrives in that location's narrator stack (not the global narrator)
4. **Cron cycle**: Wait for supervisor cron, verify room narrator processes stack → creates episode → calls MCP tools → posts to Matrix room
5. **Master narrator**: Verify subscription forwarding delivers room episode summaries to master's stack, and master produces world-level episodes after cron
6. **Chronicle API**: `GET /api/episodes` returns episodes, filtered by agent_id and type
7. **Deduplication**: Verify narrator checks KG before spawning, doesn't duplicate entities the narration crew already described
