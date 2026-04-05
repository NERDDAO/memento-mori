# World Map Panel Design

## Context

The game has a world map renderer (`world-renderer.ts`) hidden behind a `w` key toggle, and a separate Exits panel showing directional navigation. Players need spatial awareness of the world without toggling views. This design replaces the Exits panel with an always-visible world map that doubles as navigation, using the ASCII compass rose style rendered as pre-text on a TerminalPanel canvas.

## Design

### Placement

Replace the Exits panel (`exitsWin`) with a World Map panel. The compass rose shows exits as clickable directions — no separate Exits panel needed. The `w` key toggle and `world-renderer.ts` canvas renderer become unused.

### Visual Style — ASCII Compass Rose (Pre-text Rendered)

Rendered as `CharCell[][]` grid on a `TerminalPanel` canvas, matching how all other panels render (Present, Inventory, Character, etc.). Not DOM elements.

```
         Dark Cave
             |
   ? ---- [Threshold] ---- ?
             |
         Market
```

- Current room: entity color (purple `#8b5cf6`) in brackets
- Visited rooms: location color (blue `#7aa2d4`), show name
- Undiscovered exits: dim gray (`#3a3a48`), show `?`
- Connections: dim lines (`|`, `----`)
- Clickable: panel-click events on room names trigger `go {direction}`

### Fog of War — KG VISITED_BY Edges

- `VISITED_BY` edge from player entity to location entity in KG
- Created when player enters a room (during session restore / room transition)
- `/api/worldmap/{player_id}` returns only visited rooms + 1-hop adjacent unknowns
- Unknown rooms have `visited: false` and no name (just direction from a visited room)
- Per-player discovery — each player has their own fog

### API Response

`GET /api/worldmap/{player_id}`

```json
{
  "current": "The Threshold",
  "current_id": "uuid",
  "rooms": [
    {"id": "uuid1", "name": "The Threshold", "visited": true},
    {"id": "uuid2", "name": "Dark Cave", "visited": true},
    {"id": "", "name": "?", "visited": false, "direction": "east", "from_id": "uuid1"},
    {"id": "", "name": "?", "visited": false, "direction": "west", "from_id": "uuid1"}
  ],
  "connections": [
    {"from": "uuid1", "to": "uuid2", "direction": "north"}
  ]
}
```

### Compass Rose Layout Algorithm

1. Place current room at center of the grid
2. For each exit direction from current room:
   - Place the connected room (or `?`) at the directional offset
   - North: above center, South: below, East: right, West: left
3. For visited rooms that are 2 hops away (connected to an adjacent visited room but not directly to current): show them extending from their parent
4. Limit depth to 2 hops from current room to keep the compass compact
5. Each room name is centered at its position in the CharCell grid

### Panel Click Handling

The world map panel emits `panel-click` events with `{ action: "go {direction}" }` when a room or `?` node is clicked. Same pattern as the exits panel currently uses — `handleAction` receives the `go` command.

### Data Flow

1. Player enters room → engine creates `VISITED_BY` edge if not exists
2. State update arrives at client with new location → client re-fetches `/api/worldmap/{player_id}`
3. Response filtered to visited rooms + adjacent unknowns
4. `renderWorldMapPanel()` builds `CharCell[][]` compass rose
5. Panel renders on canvas via existing `TerminalPanel.setContent()`
6. Click on direction → `handleAction("go north")` → room transition → step 1

### Room Transition Trigger

Currently the world map is fetched lazily on `w` press. With this change:
- Fetch on game start (session join)
- Re-fetch after every room transition (when `state_update` contains a new location)
- Cache in game state as `worldMap: WorldMapData | null`

## Files

### New
| File | Purpose |
|------|---------|
| `client/src/panels/worldmap.ts` | Compass rose renderer (CharCell grid + panel-click) |
| `gateway/src/gateway/routes/worldmap.py` | `/api/worldmap/{player_id}` endpoint |

### Modified
| File | Change |
|------|--------|
| `client/src/app.ts` | Replace exitsWin with worldMapWin, fetch on room change, remove `w` toggle |
| `client/src/state/game-state.ts` | Add `worldMap: WorldMapData` to GameState |
| `engine/src/memento/session.py` | Create VISITED_BY edge on room entry |
| `client/index.html` | Rename exits window to world map |

### Removed (dead code)
| File | Reason |
|------|--------|
| `client/src/panels/exits.ts` | Replaced by worldmap.ts |
| `client/src/map/world-renderer.ts` | Canvas renderer replaced by panel pre-text |

## Verification

1. **Compass renders**: Open game, world map panel shows current room in center with exit directions
2. **Fog of war**: Only visited rooms show names. Unvisited exits show `?`
3. **Navigation**: Click a direction in the compass → player moves to that room → compass re-centers
4. **Discovery**: Visit a new room → `?` becomes room name on return
5. **Persistence**: Refresh page → visited rooms still show (KG edges persist)
