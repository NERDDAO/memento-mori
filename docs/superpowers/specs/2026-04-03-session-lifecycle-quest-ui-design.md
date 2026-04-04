# Session Lifecycle & Quest UI Improvements

**Date**: 2026-04-03
**Approach**: B — Shared Overlay System + Session Refactor

## Context

The core game loop (action -> crews -> narration -> NPC response) is working. Five improvements were identified during chatroom testing to improve the player experience around that loop: player resume, intro modal, loading screen, world bootstrap, and quest interface.

These items share code paths through `app.ts` session initialization and overlay management. Rather than building each as an isolated vertical slice (growing `app.ts` from 672 to 800+ lines), we extract two shared foundations first — an overlay manager and a unified session flow — then build features on top.

## 1. Overlay Manager

**New file**: `client/src/ui/overlay.ts` (~60 lines)

Manages named overlays: `char-create`, `loading`, `intro`, `death`. Only one visible at a time.

```typescript
interface OverlayManager {
  show(name: string): void       // unhide overlay, hide current
  dismiss(name: string): void    // hide overlay, fire callback
  onDismiss(name: string, cb: () => void): void
  current(): string | null
}
```

Replaces all direct `classList.add/remove('hidden')` calls scattered across `app.ts`. Each overlay div stays in `index.html` — the manager just controls visibility.

**Files modified**:
- `client/src/ui/overlay.ts` (new)
- `client/src/app.ts` — replace ~15 direct classList calls with overlay manager calls
- `client/index.html` — add `#loading-overlay` and `#intro-overlay` divs

## 2. Session Flow

**New file**: `client/src/flows/session-flow.ts` (~100 lines)

Extracts `enterWorld()` and `enterWorldExisting()` from `app.ts` into a unified function:

```typescript
async function startGame(config: {
  playerId?: string
  playerName: string
  walletAddress: string
  isReturning: boolean
  archetype?: string
}): Promise<void>
```

**Sequence**:
1. `overlays.show('loading')`
2. If `isReturning`: `POST /api/session/join` with `player_id` -> full game state
3. If new: `POST /api/session/create` with name, wallet, archetype -> full game state
4. Apply response to `gameState` via `applyStateUpdate()`
5. Connect WebSocket, await `onopen`
6. `overlays.dismiss('loading')`
7. If `!localStorage.getItem('mm_intro_seen')`: `overlays.show('intro')`, await dismiss
8. Render all panels, enable command input

Both new and returning players go through the same path. `app.ts` drops ~120 lines.

**Dependencies**: `startGame()` needs access to `gameState`, `renderAllPanels()`, `registerMapEntities()`, and the message handler setup from `app.ts`. These are passed as a callbacks object: `startGame(config, { onStateReady, onMessage })` — `app.ts` provides the wiring, `session-flow.ts` owns the sequence.

**Files modified**:
- `client/src/flows/session-flow.ts` (new)
- `client/src/app.ts` — remove `enterWorld()`, `enterWorldExisting()`, replace with `startGame()` call
- `client/src/state/session.ts` — `initSession()` may need minor refactor to return the full response

## 3. World Bootstrap

Auto-seed The Threshold on first player connect.

**Change**: In `SessionManager._find_starting_location()` (`engine/src/memento/session.py:168-184`), when KG search finds no Location entity, call `seed_threshold()` before returning.

```python
def _find_starting_location(self) -> tuple[str, str, dict | None]:
    # Search KG for a location with room_map
    locations = self._search_locations()
    if locations:
        return locations[0]
    
    # No locations exist — seed The Threshold
    try:
        result = seed_threshold(self.client)
        return (result["uuid"], "The Threshold", result["map"])
    except Exception as e:
        logger.warning(f"seed_threshold failed: {e}")
        return (None, "The Threshold", None)
```

The existing fallback behavior (returning `"The Threshold"` as a string) is preserved on failure.

**Files modified**:
- `engine/src/memento/session.py` — `_find_starting_location()` calls `seed_threshold()` on empty KG

## 4. Loading Screen

**New div**: `#loading-overlay` in `index.html`

Content: game title/logo, thematic loading text, animated ellipsis or phase indicator.

**Gate conditions** (managed by `session-flow.ts`):
1. HTTP session response received (create or join)
2. WebSocket `onopen` fires

Both must complete before `overlays.dismiss('loading')`. The overlay shows immediately when `startGame()` is called and dismisses when both conditions are met.

**Files modified**:
- `client/index.html` — add `#loading-overlay` div
- `client/src/flows/session-flow.ts` — gate logic (Promise.all on session HTTP + WS ready)
- `client/src/styles/` — loading overlay styles (thematic, dark background)

## 5. Player Resume

### Engine (`engine/src/memento/session.py`)

**`get_user_characters()`** — add death info to each character:
- Check for `HAS_STATUS` edge containing "DEAD" on each player entity
- If dead, extract cause and query `DIED_AT` edge for location
- Return: `{player_id, player_name, archetype, health, is_dead, death_cause?, death_location?}`

**New method `restore_player_state(player_id)`**:
- Query player entity from KG
- Get `LOCATED_IN` edge -> location UUID + room_map
- Get `CARRIES` edges -> inventory items
- Query active quests, factions, skills from entity attributes
- Return same shape as `create_player` response

### Gateway (`gateway/src/gateway/routes/session.py`)

**`POST /api/session/join`** — expand from `{"status": "joined"}` to full game state:
- Call `SessionManager.restore_player_state(player_id)`
- Register Matrix user (same as create)
- Return: `{player_id, session_id, location, opening_narrative?, health, max_health, skills, inventory, quests, factions, room_map}`

### Client

**Character picker** (`app.ts:showCharacterPicker`):
- Split characters into alive and dead lists
- Alive characters: clickable, current styling
- Dead characters (memorial): dimmed text color, skull glyph prefix, "Fell at {location}" subtitle, cause of death, not clickable
- "Create New Character" button at bottom (existing)

**Selection**: Alive character click calls `startGame({isReturning: true, playerId: char.player_id, ...})`

**Files modified**:
- `engine/src/memento/session.py` — `get_user_characters()` adds death fields, new `restore_player_state()`
- `gateway/src/gateway/routes/session.py` — expand `/session/join` response
- `client/src/app.ts` — memorial rendering in character picker

## 6. Intro Modal (Tutorial)

**New div**: `#intro-overlay` in `index.html`

3-4 step tutorial walkthrough:

1. **"Welcome to Memento Mori"** — A permadeath MUD where your actions shape a living world
2. **"Rounds & Actions"** — Type commands in the input bar. Actions are batched into rounds. NPCs and the world respond to what you do.
3. **"Permadeath"** — When you die, it's permanent. Your character becomes a memorial. Connect your wallet to start a new one.
4. **"Enter"** — Dismiss button

Navigation: Next / Skip buttons. Skip jumps straight to game.

On dismiss: `localStorage.setItem('mm_intro_seen', 'true')`. Returning players skip automatically. `session-flow.ts` checks the flag after loading completes.

**Files modified**:
- `client/index.html` — add `#intro-overlay` div with step content
- `client/src/flows/session-flow.ts` — intro gate check after loading
- `client/src/styles/` — intro overlay styles (step indicator, navigation buttons)

## 7. Quest Interface

### Quest Log Hit Regions (`client/src/panels/questlog.ts`)

Follow the exits panel pattern (`exits.ts:38-44`):
- At render start: `panel.clearHitRegions()`
- For each quest row: `panel.registerHitRegion({ row, col: 0, width: cols, height: questRowHeight, id: quest.name })`

### Dialog Extension (`client/src/ui/dialog.ts`)

Add `showQuest(quest: QuestEntry)` method to the dialog:
- Title: quest name (bold)
- Body sections: Giver, full description (not truncated), stage progress bar, completed status
- Uses existing typewriter canvas rendering
- Dismiss on click outside or Escape key (existing behavior)

### Wiring (`client/src/app.ts`)

Add click listener on `questWin.panel.canvas` (same pattern as exits at line ~465):
```typescript
questWin.panel.canvas.addEventListener('click', (e) => {
  const hit = questWin.panel.handleClick(e)
  if (hit) {
    const quest = gameState.quests.find(q => q.name === hit.id)
    if (quest) npcDialog.showQuest(quest)
  }
})
```

**Files modified**:
- `client/src/panels/questlog.ts` — register hit regions per quest row
- `client/src/ui/dialog.ts` — add `showQuest()` method
- `client/src/app.ts` — wire quest panel click -> dialog

## Implementation Sequence

```
Phase 1 (parallel):
  [Engine] World Bootstrap — seed_threshold in _find_starting_location
  [Client] Overlay Manager — extract from app.ts

Phase 2:
  [Client] Session Flow — extract startGame(), wire overlay manager

Phase 3:
  [Client] Loading Screen — #loading-overlay, gate in session-flow

Phase 4 (parallel):
  [Full stack] Player Resume — engine death fields, gateway join, client memorial
  [Client] Quest Interface — hit regions, dialog extension, wiring

Phase 5:
  [Client] Intro Modal — #intro-overlay, tutorial content, localStorage gate
```

## Verification

1. **World bootstrap**: Start with empty KG, create first player -> The Threshold + NPCs should exist in KG
2. **Loading screen**: Observe loading overlay during session create, verify it dismisses only after WS connects
3. **Player resume**: Create character, disconnect, reconnect with same wallet -> character picker shows character with correct state. Kill character, reconnect -> memorial entry visible
4. **Intro modal**: Clear localStorage, create new character -> tutorial shows. Dismiss, reconnect -> no tutorial. Returning player -> no tutorial.
5. **Quest interface**: Get a quest (via gameplay or seed), click quest name in sidebar -> dialog shows full quest details
6. **Overlay transitions**: Verify char-create -> loading -> intro -> game flows smoothly. Death overlay still works. No overlay stuck visible.
