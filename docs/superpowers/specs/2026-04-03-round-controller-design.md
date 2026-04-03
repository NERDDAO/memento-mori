# Round Controller Design

## Overview

A round phase indicator that replaces the left span of the client's status bar. Shows the player what phase of the round they're in, which engine crew is active during resolution, and contextual info (location, action count, countdown) between phases. Input locks when the player can't act.

## Phase Model

```
READY  →  COLLECTING  →  RESOLVING  →  NPC_RESPONSE  →  READY
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 Context  Plausibility Events
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 Combat    Quest     Social
                              │
                         ┌────┼────┐
                         ▼         ▼
                     Narrating  Post-Turn
```

### States

| Phase | Label Example | When |
|-------|--------------|------|
| `ready` | `✓ Ready · The Threshold` | Idle, waiting for player input |
| `collecting` | `⟳ Collecting · 2 actions (14s)` | Round open, 20s window |
| `resolving` | `⟳ Resolving · Plausibility` | Engine crews running |
| `npc_response` | `⟳ NPCs Responding` | Agents replying via Matrix |

### Resolving Sub-steps

These map 1:1 to `GameTurnFlow` methods:

| Crew Key | Display Label | GameTurnFlow Method |
|----------|--------------|---------------------|
| `context` | Context | `gather_context()` |
| `plausibility` | Plausibility | `plausibility_check()` |
| `events` | Events | `detect_events()` |
| `combat` | Combat | `resolve_events()` — combat path |
| `quest` | Quest | `resolve_events()` — quest path |
| `social` | Social | `resolve_events()` — social path |
| `narrating` | Narrating | `narrate()` |
| `post_turn` | Post-Turn | `post_turn()` |

Conditional crews (combat/quest/social) only appear if `detect_events` routes to them.

## WebSocket Protocol

### New Message Type: `phase`

```typescript
{
  type: "phase";
  phase: "ready" | "collecting" | "resolving" | "npc_response";
  crew?: string;          // only during "resolving"
  location?: string;      // for "ready" context
  action_count?: number;  // for "collecting"
  deadline?: number;      // unix timestamp ms, for "collecting" countdown
}
```

### Emission Points

| Phase | Emitter | Trigger |
|-------|---------|---------|
| `collecting` | Gateway — `round_callback.py` | First action opens round |
| `collecting` (update) | Gateway — `round_callback.py` | Subsequent actions increment `action_count` |
| `resolving` + `crew` | Engine — `round_controller.py` | Before each crew call |
| `npc_response` | Engine — `round_controller.py` | After event detection, before narration |
| `ready` | Engine — `round_controller.py` | After post-turn completes (or cooldown skip) |

### Engine → Gateway Path

Engine posts phase messages to the Matrix room using the existing `com.bonfires.rpg` metadata pattern:

```python
# Engine posts to Matrix room
{
    "msgtype": "m.text",
    "body": "[phase] resolving:plausibility",
    "com.bonfires.rpg": {
        "type": "phase",
        "phase": "resolving",
        "crew": "plausibility",
        "location": "The Threshold"  # required — gateway uses this to route broadcast
    }
}
```

### Solo Fast-Path

When only one player is at a location, `close_round()` fires immediately — the 20s collection window is skipped. In this case:
- No `collecting` phase is emitted.
- The phase goes directly from `ready` → `resolving` (first crew).
- Client sees the resolving sub-steps without a collecting countdown.

Gateway's `_on_message()` in `matrix_bridge.py` picks up `type == "phase"` and forwards to WebSocket.

## Client Changes

### Shared Round State

New module `state/round-state.ts` — central round state that components subscribe to:

```typescript
interface RoundState {
  phase: "ready" | "collecting" | "resolving" | "npc_response";
  crew?: string;
  location?: string;
  actionCount?: number;
  deadline?: number;       // unix ms
  secondsLeft?: number;    // computed locally, ticks down every 1s
}

type RoundListener = (state: RoundState) => void;

function getRoundState(): RoundState;
function onRoundStateChange(listener: RoundListener): () => void;  // returns unsubscribe
function updateRoundState(msg: PhaseMessage): void;
```

### Component Integration

| Component | File | Behavior |
|-----------|------|----------|
| **Status bar** | `ui/status.ts` | Renders phase label. Subscribes to round state. Replaces current `setPhase()` with round-state-driven rendering. |
| **Input panel** | `panels/input.ts` | `collecting`: placeholder shows countdown ("14s left to act..."). `resolving` / `npc_response`: input disabled, greyed out. `ready`: input enabled. |
| **Narrative panel** | `panels/narrative.ts` | `collecting` with queued actions: subtle "Round in progress" divider. `resolving` start: separator before incoming narrative. |
| **Present panel** | `panels/present.ts` | `npc_response`: pulse/highlight NPC names that are "thinking". |

### Timer Mechanics

- Client receives `deadline` as unix timestamp in the `collecting` phase message.
- Starts a `setInterval(1000)` that computes `secondsLeft = Math.ceil((deadline - Date.now()) / 1000)`.
- Updates `secondsLeft` in round state each tick; components re-render.
- Timer clears when phase transitions away from `collecting`.
- If timer hits 0, client doesn't force transition — waits for server's next phase message.

### Input Locking

- Input is locked (disabled, greyed out) during `resolving` and `npc_response` phases.
- Input is enabled during `ready` and `collecting`.
- Any text typed during `collecting` submits as a new action via the existing `/api/action` endpoint.
- If player tries to type while locked, input does nothing (no queue, no buffer).

### Removing Old Phase States

The current phase states (`synced`, `thinking`, `processing`, `extracting`, `fetching`, `pushing`, `error`) are replaced by the round controller phases. The `error` state is kept as an overlay that can appear in any phase.

The `status` message type continues to exist for chain sync status only — it updates the center span (Redstone online/offline), not the left span.

## Engine Changes

### Replace `GameTurnFlow` with `RoundController`

The current `GameTurnFlow` uses CrewAI's `@start/@listen` decorator chaining, which auto-sequences crews with no ability to gate, pause, or inject phase emissions between steps. Replace it with an explicit `RoundController` that drives crew execution step by step.

**Key difference:** The controller is a stoplight — it checks preconditions before greenlighting each crew, and it waits for NPC responses *before* narrating so the engine can incorporate what NPCs said.

```python
class RoundController:
    """Stoplight — drives crew execution, emits phases, gates on preconditions."""

    def __init__(self, matrix_client, room_id: str, location: str):
        self.matrix_client = matrix_client
        self.room_id = room_id
        self.location = location

    async def emit_phase(self, crew: str):
        """Post phase message to Matrix room."""
        # ... posts com.bonfires.rpg type=phase to room

    async def run(self, player_name, action, actions=None):
        await self.emit_phase("context")
        context = gather_context(player_name, self.location, action)

        await self.emit_phase("plausibility")
        plausible, reason = check_plausibility(context, action)
        if not plausible:
            await self.emit_phase("narrating")
            return narrate_rejection(action, context, reason)

        await self.emit_phase("events")
        events = detect_events(action, context)

        # --- NPC response window ---
        # Wait for NPCs to respond before narrating.
        # NPCs see the player actions (already posted to Matrix by gateway).
        # Controller pauses here to let them respond.
        await self.emit_phase("npc_response")
        npc_responses = await self.await_npc_responses(timeout=15)

        # --- World event cooldown gate ---
        # Don't narrate if a world event just fired recently.
        if self.should_skip_narration():
            return None, minimal_state_update()

        await self.emit_phase("narrating")
        # Narration crew receives NPC responses as additional context
        narrative = narrate(action, context, events, npc_responses)

        await self.emit_phase("post_turn")
        state_update = post_turn(narrative, events, player_name)

        return narrative, state_update
```

### Gating Rules

**World event cooldown:** The controller checks the last narration timestamp for this location. If a world narration fired within the last N seconds (configurable, e.g., 30s), skip narration and return a minimal state update. This prevents the `world → npc → world → world` stacking.

**NPC response window:** After player actions are posted to Matrix (by the gateway, before the controller runs), the controller waits up to 15s for NPC responses. It collects any `@bonfires-*` messages that arrive in the room during this window, then passes them to the narration crew as additional context. If no NPCs respond within the timeout, narration proceeds without them.

### NPC Response Flow (Reordered)

**Before (current — broken):**
```
player acts → gateway posts to Matrix → engine runs immediately → narration arrives
                                        → NPCs see action, respond (too late, after narration)
```

**After (controller — correct):**
```
player acts → gateway posts to Matrix → controller starts
  → context crew
  → plausibility crew
  → event detection
  → NPC RESPONSE WINDOW (15s) ← NPCs respond during this window
  → cooldown gate check
  → narration crew (has NPC responses as context)
  → post-turn
```

### Crew Functions

The individual crew functions (`make_context_crew`, `make_narration_crew`, `EventDetectionFlow`, etc.) stay unchanged. The controller calls them as plain functions instead of via `@listen` chaining. `GameTurnFlow` is deleted and replaced by `RoundController`.

### Matrix Client Access

`RoundController` receives the Matrix client and room_id from `matrix_listener.py` at construction. The controller uses the client to emit phases and to listen for NPC responses during the response window.

## Gateway Changes

### `round_callback.py` — Collecting Phase

Emit `collecting` phase when round opens and on each subsequent action:

```python
async def on_round_close(location, actions):
    # ... existing code ...

# New: called from RoundManager.submit_action()
async def on_action_received(location, action_count, deadline):
    await ws_hub.broadcast_to_location(location, {
        "type": "phase",
        "phase": "collecting",
        "action_count": action_count,
        "deadline": int(deadline * 1000),  # unix ms
    })
```

This requires `RoundManager` to call a second callback when actions arrive, not just on close.

### `matrix_bridge.py` — Phase Forwarding

In `_on_message()`, add a handler for `com.bonfires.rpg.type == "phase"`:

```python
if rpg_type == "phase":
    await ws_hub.broadcast_to_location(rpg_meta["location"], {
        "type": "phase",
        "phase": rpg_meta["phase"],
        "crew": rpg_meta.get("crew"),
    })
```

NPC timeout logic is no longer in the gateway — it lives in the engine's `RoundController` which owns the NPC response window. The gateway just forwards phase messages and narrative as before.

## Files to Change

| File | Change |
|------|--------|
| `engine/src/memento/round_controller.py` | New — stoplight controller replacing GameTurnFlow |
| `engine/src/memento/flows/game_turn.py` | Delete (replaced by round_controller.py) |
| `engine/src/memento/matrix_listener.py` | Call RoundController instead of GameTurnFlow |
| `engine/src/memento/round_manager.py` | Add `on_action` callback |
| `gateway/src/gateway/round_callback.py` | Emit `collecting` phase on action received |
| `gateway/src/gateway/app.py` | Wire action callback |
| `gateway/src/gateway/matrix_bridge.py` | Forward phase messages (no NPC timeout — moved to engine) |
| `client/src/state/round-state.ts` | New — shared round state + subscription |
| `client/src/ui/status.ts` | Overhaul left span to use round state |
| `client/src/panels/input.ts` | Subscribe to round state, lock/unlock input |
| `client/src/panels/narrative.ts` | Round dividers |
| `client/src/panels/present.ts` | NPC thinking highlight |
| `client/src/app.ts` | Handle `phase` message type, dispatch to round state |
