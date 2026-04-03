# Room Presence + @Mention Autocomplete Design

## Overview

Show connected players in the Present panel using gateway WebSocket tracking for real-time updates and Matrix for canonical player identity. Add `@mention` autocomplete in the input that suggests NPCs (first) and players at the current location. Ensure the presence system properly handles join/leave/disconnect lifecycle.

## Presence System

### Data Flow

```
Player connects WebSocket → ws_hub.connect()
Player submits action with location → ws_hub.set_location()
  → broadcast "player_joined" to location
  → send full player list to joining player
  → Matrix: invite/join player to room

Player disconnects → ws_hub.disconnect()
  → broadcast "player_left" to old location
  → Matrix: leave room (optional, graceful)

Player moves (state_update.location changes) →
  → broadcast "player_left" at old location
  → ws_hub.set_location(new)
  → broadcast "player_joined" at new location
  → Matrix: join new room
```

### WebSocket Messages

**`player_joined`** — broadcast to all players at the location:
```json
{
  "type": "player_joined",
  "player_id": "cb07a36e-...",
  "player_name": "Kael",
  "location": "The Threshold"
}
```

**`player_left`** — broadcast to all remaining players at the location:
```json
{
  "type": "player_left",
  "player_id": "cb07a36e-...",
  "player_name": "Kael",
  "location": "The Threshold"
}
```

**`presence`** — sent to a player on join with the full list of who's already there:
```json
{
  "type": "presence",
  "players": [
    { "player_id": "abc...", "player_name": "Wanderer" },
    { "player_id": "def...", "player_name": "Kael" }
  ],
  "location": "The Threshold"
}
```

### Player Name Resolution

The gateway needs player names (not just IDs). Two sources:

1. **Session creation** — `/api/session/create` already receives `player_name`. Store it in `ws_hub`.
2. **Matrix display name** — query Synapse for the player's Matrix display name as fallback.

Simplest: add a `player_names: dict[str, str]` to `WebSocketHub` that maps `player_id → player_name`. Populated during session creation.

### Gateway Changes

**`ws.py`:**
- Add `player_names: dict[str, str]` — maps player_id to display name
- `connect()` accepts `player_name` parameter, stores in `player_names`
- `disconnect()` broadcasts `player_left` to the player's last location before removing them
- `set_location()` broadcasts `player_left` at old location (if any), `player_joined` at new location, sends `presence` (full list) to the player
- Add `get_players_at_location(location) → list[dict]` — returns `[{player_id, player_name}]`

**`routes/session.py`:**
- Pass `player_name` through to `ws_hub` on session creation (or on first WebSocket connect)

**`app.py` WebSocket endpoint:**
- On disconnect, ensure `ws_hub.disconnect()` fires the leave broadcast

**`matrix_bridge.py`:**
- On disconnect, optionally leave the player from the Matrix room (graceful cleanup)

### Disconnect = Leave Room

When the WebSocket closes:
1. `ws_hub.disconnect(player_id)` looks up the player's current location
2. Broadcasts `player_left` to everyone remaining at that location
3. Removes player from `connections`, `player_locations`, `player_names`

This ensures the Present panel updates immediately when someone disconnects.

## Client: Present Panel

### Player Rendering

Add a players section to the Present panel, below NPCs and above items:

```
◆ Grumlock Stonebrow — Bartender
◆ Roric the Sly — Fence
◆ Elara Brightwood — Herbalist
@ Kael
@ Wanderer
· Tattered Journal
· Dull Iron Dagger
```

Players use `@` prefix with a distinct color (cyan/teal to contrast with NPC gold).

### Client State

**`game-state.ts`** — add `players` to location:
```typescript
location: {
  name: string;
  description: string;
  exits: LocationExit[];
  npcs: LocationEntity[];
  items: LocationEntity[];
  players: LocationEntity[];  // NEW
};
```

**`app.ts`** — handle new message types:
```typescript
case 'player_joined':
  gameState.location.players.push({ name: msg.player_name, id: msg.player_id });
  renderPresentPanel(...);
  break;
case 'player_left':
  gameState.location.players = gameState.location.players.filter(p => p.id !== msg.player_id);
  renderPresentPanel(...);
  break;
case 'presence':
  gameState.location.players = msg.players.map(p => ({ name: p.player_name, id: p.player_id }));
  renderPresentPanel(...);
  break;
```

## @Mention Autocomplete

### Trigger

Typing `@` in the input opens a dropdown above the input bar. The dropdown shows:

1. **NPCs** at the current location (from `gameState.location.npcs`)
2. **Players** at the current location (from `gameState.location.players`)

NPCs listed first, then players. Each entry shows the name with a type indicator (◆ for NPC, @ for player).

### Behavior

- `@` opens the dropdown with all suggestions
- Typing after `@` filters by prefix match (case-insensitive)
- Arrow keys navigate suggestions
- Enter/Tab selects — inserts `@Name` into the input and closes dropdown
- Escape dismisses
- Backspacing past `@` dismisses
- Clicking a suggestion selects it

### UI

The dropdown is a small floating panel positioned above the input, anchored to the cursor position or left edge of the input. Styled to match the TUI aesthetic (dark background, border, monospace).

```
┌─────────────────────┐
│ ◆ Roric the Sly     │
│ ◆ Elara Brightwood  │
│ @ Wanderer          │
└─────────────────────┘
> @r|
```

### Implementation

New module `client/src/ui/mention-dropdown.ts`:
- Creates a floating div positioned above the input
- Accepts a list of suggestions `{name, type: 'npc' | 'player'}`
- Handles keyboard navigation (arrow keys, enter, escape)
- Returns selected name on pick

Modified `client/src/panels/input.ts`:
- Detects `@` typed in input
- Gathers NPCs + players from game state
- Opens mention dropdown
- On selection, inserts `@Name` at cursor position

### Engine Handling

No engine changes. `@Name` is just text in the action string. The existing `shouldAgentRespond` in bonfires-ai already matches character names — `@Roric` triggers Roric the same way "talk to Roric" does.

## Files to Change

| File | Change |
|------|--------|
| `gateway/src/gateway/ws.py` | Add player_names tracking, join/leave broadcasts, presence messages |
| `gateway/src/gateway/app.py` | Pass player_name on WebSocket connect, handle disconnect cleanup |
| `gateway/src/gateway/routes/session.py` | Store player_name for WebSocket hub |
| `client/src/state/game-state.ts` | Add `players` to location state |
| `client/src/panels/present.ts` | Render players section |
| `client/src/panels/input.ts` | @mention trigger, wire dropdown |
| `client/src/ui/mention-dropdown.ts` | New — floating autocomplete dropdown |
| `client/src/app.ts` | Handle player_joined/player_left/presence messages |
| `client/index.html` | CSS for player styling, dropdown |
