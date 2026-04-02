# Multiplayer Turn Sync

## Context

Player actions currently bypass turn batching entirely. The gateway sends each action directly to a Matrix room, the engine processes it immediately, and the narrative goes back to only the acting player. This means:

- No multiplayer awareness (players at the same location don't see each other's actions)
- No turn sync (actions resolve instantly and independently)
- RoundManager exists and is tested but never called

This design wires RoundManager into the action dispatch path so multiplayer turns batch by location, resolve together, and broadcast to all players.

## Architecture

```
Player action → POST /api/action
  → Gateway: RoundManager.submit_action(player_id, player_name, location, action)
    → Solo fast-path: if 1 player at location, close round immediately
    → Multi-player: collect actions for 20s window
      → on_round_close callback fires
        → Format batch message
        → Send to Matrix room for that location
          → Engine: matrix_listener detects batch message
            → GameTurnFlow.kickoff(actions=[...all player actions...])
              → Single narration covering all actions
                → Post narrative to Matrix room
                  → Gateway: broadcast to ALL players at location via WebSocket
```

## Solo Fast-Path

When a player submits an action and they are the only player at that location, the round closes immediately — no 20s wait. Detection uses `ws_hub.players_at_location(location)` which already tracks player→location mappings.

The fast-path check happens in the gateway's action route after calling `submit_action()`:

```
if ws_hub.players_at_location(location) == 1:
    round_manager.close_round(location)
```

Multi-player locations still batch for the full 20s window.

## Gateway Changes

### `gateway/app.py` — Initialize RoundManager

Import and instantiate `RoundManager` at startup. Register the round-close callback that sends batched actions to Matrix.

```python
round_manager = RoundManager(window_seconds=20)
round_manager.on_round_close(send_batch_to_matrix)
```

Inject `round_manager` into the action route via FastAPI dependency or module-level import.

### `gateway/routes/action.py` — Replace direct dispatch

Current flow (lines 40-60): receives `ActionRequest`, calls `bridge.send_action()` directly.

New flow:
1. Receive `ActionRequest` (player_id, action, location)
2. Call `round_manager.submit_action(player_id, player_name, location, action)`
3. Check solo fast-path: if `ws_hub.players_at_location(location) == 1`, call `round_manager.close_round(location)`
4. Return immediately with `{"status": "queued"}` (narrative comes async via WebSocket)

### `gateway/round_callback.py` — New: batch dispatch to Matrix

Callback registered on `round_manager.on_round_close`. When a round closes:

1. Receive `(location: str, actions: list[PlayerAction])`
2. Format as batch Matrix message:
   ```json
   {
     "msgtype": "com.bonfires.rpg.batch",
     "body": "Round closed",
     "batch": true,
     "location": "The Threshold",
     "actions": [
       {"player_id": "p1", "player_name": "Kael", "action": "attack the goblin"},
       {"player_id": "p2", "player_name": "Thane", "action": "search the room"}
     ]
   }
   ```
3. Send to the Matrix room for that location via `bridge.send_batch(room_id, batch_message)`

### `gateway/ws.py` — Add players_at_location helper

Add a method to count players at a given location:

```python
def players_at_location(self, location: str) -> int:
    return sum(1 for loc in self.player_locations.values() if loc == location)
```

The existing `broadcast_to_location()` method already handles sending messages to all players at a location — no changes needed for the broadcast side.

## Engine Changes

### `engine/matrix_listener.py` — Detect batch messages

Add handler for `com.bonfires.rpg.batch` message type alongside the existing action handler:

1. Check `content.get("batch")` flag
2. Extract `actions` list and `location`
3. Call `_run_batch_turn(location, actions)` instead of `_run_turn()`

`_run_batch_turn()`:
1. Build action list as `[{"player_id": a["player_id"], "player_name": a["player_name"], "action": a["action"]} for a in actions]`
2. Call `GameTurnFlow` with `actions=action_list` instead of single `action=action_text`
3. Post resulting narrative to the Matrix room (same as current single-action flow)

### `engine/flows/game_turn.py` — Accept batch actions

**GameTurnState** gains:
- `actions: list[dict] = []` — each dict has `{"player_id": str, "player_name": str, "action": str}`

The existing `action` field stays for backwards compatibility (solo turns). If `actions` is populated, the flow uses it; otherwise falls back to `action`.

**Key flow changes:**

- `gather_context()` — context crew sees all player names and their intended actions
- `plausibility_check()` — checks each action for plausibility (any rejected action gets a rejection narrative for that player only)
- `detect_events()` / `resolve_events()` — event detection considers all actions together (e.g., two players attacking same NPC)
- `narrate()` — narration crew receives all actions and their outcomes, produces a single narrative covering the full round
- `post_turn()` — episode covers all players' actions

The narrative is shared — all players at the location receive the same text. Per-player state updates (inventory changes, HP, etc.) are still player-specific and sent via individual WebSocket messages.

## RoundManager Changes

### `engine/round_manager.py` — Add close_round method

Add `close_round(location: str)` method for the solo fast-path:

```python
def close_round(self, location: str) -> None:
    """Immediately close and fire the round for a location."""
    if location in self._rounds:
        round_ = self._rounds.pop(location)
        round_.timer.cancel()
        for cb in self._callbacks:
            asyncio.create_task(cb(location, round_.actions))
```

This cancels the timer and fires callbacks immediately. Used by the gateway when solo-player fast-path triggers.

## Matrix Message Format

### Batch action message (gateway → engine)

```json
{
  "msgtype": "com.bonfires.rpg.batch",
  "body": "Round closed at The Threshold (2 actions)",
  "batch": true,
  "location": "The Threshold",
  "actions": [
    {"player_id": "p1", "player_name": "Kael", "action": "attack the goblin"},
    {"player_id": "p2", "player_name": "Thane", "action": "search the room"}
  ]
}
```

### Narrative response (engine → gateway, unchanged format)

The engine posts narrative back as the existing `com.bonfires.rpg` message type. The gateway's Matrix bridge already relays this and calls `broadcast_to_location()` — which now correctly sends to all players, not just one.

## Broadcast Fix

Currently `matrix_bridge.py` calls `ws_hub.send_to_player(player_id)` for the acting player only. Change to `ws_hub.broadcast_to_location(location, message)` so all players at the location receive the narrative.

The `broadcast_to_location` method already exists in `ws.py` (lines 46-50). The fix is in `matrix_bridge.py`'s message handler — use broadcast instead of unicast.

## Files Changed

| File | Action | Change |
|------|--------|--------|
| `gateway/src/gateway/app.py` | Modify | Init RoundManager, register callback |
| `gateway/src/gateway/routes/action.py` | Modify | Replace direct dispatch with submit_action + solo fast-path |
| `gateway/src/gateway/round_callback.py` | Create | Batch dispatch callback for Matrix |
| `gateway/src/gateway/ws.py` | Modify | Add `players_at_location()` helper |
| `gateway/src/gateway/matrix_bridge.py` | Modify | Broadcast to location instead of unicast |
| `engine/src/memento/matrix_listener.py` | Modify | Handle batch messages, call _run_batch_turn |
| `engine/src/memento/flows/game_turn.py` | Modify | Accept actions list, batch-aware context/narration |
| `engine/src/memento/round_manager.py` | Modify | Add `close_round()` method |

## Testing

1. **RoundManager.close_round()** — unit test: submit 1 action, close immediately, verify callback fires
2. **Solo fast-path** — integration test: 1 player at location, action queued and round closes immediately
3. **Batch round** — integration test: 2 players at location, both submit within 20s, round closes with 2 actions
4. **GameTurnFlow batch** — unit test: pass actions list, verify narration crew receives all actions
5. **Broadcast** — verify all players at location receive the narrative, not just the acting player
6. **Matrix batch message** — verify `com.bonfires.rpg.batch` format is correct and engine parses it

## Out of Scope

- Dynamic map generation (separate spec)
- World time sync (separate spec)
- UI changes (client doesn't change — it already handles async narrative via WebSocket)
- Turn order within a batch (all actions resolve simultaneously)
- Player-specific narrative variants (everyone sees the same text)
