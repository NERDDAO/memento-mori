# Multiplayer Turn Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire RoundManager into the action dispatch path so multiplayer turns batch by location, resolve together, and broadcast to all players.

**Architecture:** Gateway's action route submits to RoundManager instead of sending directly to Matrix. On round close, a callback sends a batch message to the Matrix room. The engine detects batch messages and runs GameTurnFlow with all actions. Narrative broadcasts to all players at the location. Solo players get a fast-path (immediate round close).

**Tech Stack:** Python 3.10+ (FastAPI gateway, CrewAI engine), Matrix (nio), asyncio

**Spec:** `docs/superpowers/specs/2026-04-01-multiplayer-turn-sync-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `engine/src/memento/round_manager.py` | Modify | Add `close_round()` method |
| `gateway/src/gateway/app.py` | Modify | Init RoundManager, register callback |
| `gateway/src/gateway/routes/action.py` | Modify | Use RoundManager + solo fast-path |
| `gateway/src/gateway/round_callback.py` | Create | Batch dispatch callback for Matrix |
| `gateway/src/gateway/ws.py` | Modify | Add `players_at_location()` helper |
| `gateway/src/gateway/matrix_bridge.py` | Modify | Broadcast to location instead of unicast |
| `engine/src/memento/matrix_listener.py` | Modify | Handle batch messages |
| `engine/src/memento/flows/game_turn.py` | Modify | Accept actions list, fix stale chain call |
| `engine/tests/test_round_manager.py` | Modify | Add close_round test |
| `gateway/tests/test_round_callback.py` | Create | Test batch callback |

---

### Task 1: Add `close_round()` to RoundManager

**Files:**
- Modify: `engine/src/memento/round_manager.py:68-78`
- Modify: `engine/tests/test_round_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `engine/tests/test_round_manager.py`:

```python
@pytest.mark.asyncio
async def test_close_round_fires_immediately():
    rm = RoundManager(window_seconds=10)
    results = []

    async def on_close(location, actions):
        results.append((location, [a.action for a in actions]))

    rm.on_round_close(on_close)

    await rm.submit_action("p1", "Kael", "tavern", "look around")
    assert rm.active_count == 1

    await rm.close_round("tavern")
    # Give event loop a tick to process the task
    await asyncio.sleep(0.05)

    assert len(results) == 1
    assert results[0] == ("tavern", ["look around"])
    assert rm.active_count == 0


@pytest.mark.asyncio
async def test_close_round_noop_for_unknown_location():
    rm = RoundManager(window_seconds=10)
    results = []

    async def on_close(location, actions):
        results.append(location)

    rm.on_round_close(on_close)

    await rm.close_round("nonexistent")
    await asyncio.sleep(0.05)

    assert len(results) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/test_round_manager.py -v
```

Expected: FAIL — `AttributeError: 'RoundManager' object has no attribute 'close_round'`

- [ ] **Step 3: Implement `close_round()`**

Add this method to `RoundManager` in `engine/src/memento/round_manager.py`, after the `_close_after_window` method (after line 78):

```python
async def close_round(self, location: str) -> None:
    """Immediately close and fire the round for a location (solo fast-path)."""
    round_ = self.active_rounds.pop(location, None)
    if not round_ or round_.closed:
        return
    round_.closed = True
    for callback in self._callbacks:
        try:
            await callback(location, round_.actions)
        except Exception:
            logger.error("Round close callback error", exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/test_round_manager.py -v
```

Expected: 4/4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add engine/src/memento/round_manager.py engine/tests/test_round_manager.py
git commit -m "feat(engine): add close_round() to RoundManager for solo fast-path"
```

---

### Task 2: Add `players_at_location()` to WebSocketHub

**Files:**
- Modify: `gateway/src/gateway/ws.py`

- [ ] **Step 1: Add the helper method**

Add this method to `WebSocketHub` in `gateway/src/gateway/ws.py`, after `set_location` (after line 34):

```python
def players_at_location(self, location: str) -> int:
    """Count connected players at a given location."""
    return sum(1 for loc in self.player_locations.values() if loc == location)
```

- [ ] **Step 2: Commit**

```bash
git add gateway/src/gateway/ws.py
git commit -m "feat(gateway): add players_at_location() helper to WebSocketHub"
```

---

### Task 3: Create round callback module

**Files:**
- Create: `gateway/src/gateway/round_callback.py`
- Create: `gateway/tests/test_round_callback.py`

- [ ] **Step 1: Write the failing test**

Create `gateway/tests/test_round_callback.py`:

```python
"""Tests for round close callback."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from memento.round_manager import PlayerAction


@pytest.mark.asyncio
async def test_send_batch_to_matrix():
    from gateway.round_callback import make_round_callback

    mock_bridge = MagicMock()
    mock_bridge.connected = True
    mock_bridge.get_or_create_room = AsyncMock(return_value="!room123")
    mock_bridge.client = MagicMock()
    mock_bridge.client.room_send = AsyncMock()
    mock_bridge.token = "test-token"

    mock_ws_hub = MagicMock()
    mock_ws_hub.broadcast_to_location = AsyncMock()

    callback = make_round_callback(mock_bridge, mock_ws_hub)

    actions = [
        PlayerAction(player_id="p1", player_name="Kael", action="attack goblin"),
        PlayerAction(player_id="p2", player_name="Thane", action="search room"),
    ]

    await callback("The Threshold", actions)

    # Verify batch message was sent to Matrix room
    mock_bridge.client.room_send.assert_called_once()
    call_args = mock_bridge.client.room_send.call_args
    assert call_args[0][0] == "!room123"
    content = call_args[0][2]
    assert content["com.bonfires.rpg"]["type"] == "player-action-batch"
    assert content["com.bonfires.rpg"]["batch"] is True
    assert len(content["com.bonfires.rpg"]["actions"]) == 2

    # Verify thinking indicator sent to all players at location
    mock_ws_hub.broadcast_to_location.assert_called_once()


@pytest.mark.asyncio
async def test_callback_noop_when_bridge_disconnected():
    from gateway.round_callback import make_round_callback

    mock_bridge = MagicMock()
    mock_bridge.connected = False

    callback = make_round_callback(mock_bridge, MagicMock())

    actions = [PlayerAction(player_id="p1", player_name="Kael", action="look")]
    await callback("tavern", actions)

    # Should not attempt to send
    assert not mock_bridge.get_or_create_room.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -m pytest tests/test_round_callback.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'gateway.round_callback'`

- [ ] **Step 3: Write the round callback module**

Create `gateway/src/gateway/round_callback.py`:

```python
"""Round close callback — sends batched actions to Matrix for engine processing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gateway.log import get_logger

if TYPE_CHECKING:
    from gateway.matrix_bridge import MatrixBridge
    from gateway.ws import WebSocketHub
    from memento.round_manager import PlayerAction

logger = get_logger(__name__)


def make_round_callback(bridge: MatrixBridge, ws_hub: WebSocketHub):
    """Create an async callback for RoundManager.on_round_close.

    When a round closes, sends a batch message to the Matrix room
    for that location so the engine can process all actions together.
    """

    async def on_round_close(location: str, actions: list[PlayerAction]) -> None:
        if not bridge or not bridge.connected:
            logger.warning("Round closed but bridge disconnected: %s (%d actions)", location, len(actions))
            return

        room_id = await bridge.get_or_create_room(location)

        # Send thinking indicator to all players at this location
        await ws_hub.broadcast_to_location(location, {
            "type": "thinking",
            "action": f"Processing round ({len(actions)} actions)",
        })

        # Build batch message for engine
        action_list = [
            {
                "player_id": a.player_id,
                "player_name": a.player_name,
                "action": a.action,
            }
            for a in actions
        ]

        content = {
            "msgtype": "m.text",
            "body": f"Round closed at {location} ({len(actions)} actions)",
            "com.bonfires.rpg": {
                "type": "player-action-batch",
                "batch": True,
                "location": location,
                "actions": action_list,
            },
        }

        # Send as narrator bot
        if bridge.client:
            await bridge.client.room_send(room_id, "m.room.message", content)
            logger.info("Batch sent to %s: %d actions", location, len(actions))

    return on_round_close
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -m pytest tests/test_round_callback.py -v
```

Expected: 2/2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add gateway/src/gateway/round_callback.py gateway/tests/test_round_callback.py
git commit -m "feat(gateway): add round close callback for batch Matrix dispatch"
```

---

### Task 4: Wire RoundManager into gateway app and action route

**Files:**
- Modify: `gateway/src/gateway/app.py:19-31`
- Modify: `gateway/src/gateway/routes/action.py:40-60`

- [ ] **Step 1: Update gateway app.py to init RoundManager**

Replace the `lifespan` function and add `round_manager` global in `gateway/src/gateway/app.py`:

Add import at top (after existing imports):

```python
from memento.round_manager import RoundManager
from gateway.round_callback import make_round_callback
```

Add global after `ws_hub`:

```python
round_manager: RoundManager | None = None
```

Replace the `lifespan` function (lines 19-32):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, ws_hub, round_manager
    ws_hub = WebSocketHub()
    round_manager = RoundManager(window_seconds=20)
    # Matrix bridge connects on startup if env vars are set
    import os
    homeserver = os.getenv("MATRIX_HOMESERVER", "")
    token = os.getenv("MATRIX_BOT_TOKEN", "")
    if homeserver and token:
        bridge = MatrixBridge(homeserver, token, ws_hub)
        await bridge.connect()
        round_manager.on_round_close(make_round_callback(bridge, ws_hub))
    yield
    if bridge:
        await bridge.disconnect()
```

- [ ] **Step 2: Update action route to use RoundManager**

Replace the `submit_action` function (lines 40-60) in `gateway/src/gateway/routes/action.py`:

```python
@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest):
    """Submit a player action. Batched by location via RoundManager."""
    from gateway.rate_limit import action_limiter
    action_limiter.check(req.player_id)

    from gateway.app import round_manager, ws_hub

    # Track player location
    if ws_hub:
        ws_hub.set_location(req.player_id, req.location)

    if round_manager:
        await round_manager.submit_action(
            req.player_id, req.player_id, req.location, req.action
        )
        # Solo fast-path: if only 1 player at location, close round immediately
        if ws_hub and ws_hub.players_at_location(req.location) <= 1:
            await round_manager.close_round(req.location)
        else:
            # Multi-player: send thinking indicator
            if ws_hub:
                await ws_hub.send_to_player(req.player_id, {
                    "type": "thinking",
                    "action": req.action,
                })

    return ActionResponse(status="queued")
```

- [ ] **Step 3: Commit**

```bash
git add gateway/src/gateway/app.py gateway/src/gateway/routes/action.py
git commit -m "feat(gateway): wire RoundManager into action route with solo fast-path"
```

---

### Task 5: Handle batch messages in engine Matrix listener

**Files:**
- Modify: `engine/src/memento/matrix_listener.py:61-93`

- [ ] **Step 1: Update `_on_action` to detect and handle batch messages**

Replace the `_on_action` method (lines 61-93) in `engine/src/memento/matrix_listener.py`:

```python
async def _on_action(self, room: MatrixRoom, event: RoomMessageText) -> None:
    """Handle player action messages — single or batch."""
    content = event.source.get("content", {})
    rpg_meta = content.get("com.bonfires.rpg", {})

    msg_type = rpg_meta.get("type", "")

    if msg_type == "player-action-batch":
        # Batch turn — multiple actions from RoundManager
        actions = rpg_meta.get("actions", [])
        location_name = rpg_meta.get("location", room.display_name or "Unknown")
        logger.info("Batch turn at %s: %d actions", location_name, len(actions))

        narrative, state_update = await asyncio.to_thread(
            self._run_batch_turn, location_name, actions
        )

        if self.client and narrative:
            await self.client.room_send(
                room.room_id,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": narrative,
                    "com.bonfires.rpg": {
                        "type": "narrative",
                        "location": location_name,
                        "state_update": state_update,
                    },
                },
            )

    elif msg_type == "player-action":
        # Legacy single action (backwards compatibility)
        player_id = rpg_meta.get("player_id", "unknown")
        action_text = event.body
        logger.info("Action from %s: %s", player_id, action_text)

        location_name = room.display_name or "Unknown"
        narrative, state_update = await asyncio.to_thread(
            self._run_turn, player_id, location_name, action_text
        )

        if self.client and narrative:
            await self.client.room_send(
                room.room_id,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": narrative,
                    "com.bonfires.rpg": {
                        "type": "narrative",
                        "player_id": player_id,
                        "state_update": state_update,
                    },
                },
            )
```

- [ ] **Step 2: Add `_run_batch_turn` method**

Add this method to `EngineMatrixListener` after `_run_turn` (after line 139):

```python
@staticmethod
def _run_batch_turn(location_name: str, actions: list[dict]) -> tuple[str, dict]:
    """Run GameTurnFlow with multiple actions. Returns (narrative, state_update)."""
    from memento.flows.game_turn import GameTurnFlow
    from memento.models.state_update import StateUpdate

    flow = GameTurnFlow()
    flow.state.location_name = location_name
    # Set first player as primary (for context gathering), pass all actions
    if actions:
        flow.state.player_name = actions[0].get("player_name", "unknown")
    flow.state.actions = actions
    # Build combined action string for crews that expect a single action
    combined = "; ".join(
        f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
    )
    flow.state.action = combined
    flow.kickoff()

    state_update = StateUpdate(
        location=location_name,
        world_time=flow.state.world_time if isinstance(flow.state.world_time, dict) else None,
        subsystem_warnings=getattr(flow.state, "subsystem_warnings", []),
    )
    return flow.state.narrative, state_update.model_dump(exclude_none=True)
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/matrix_listener.py
git commit -m "feat(engine): handle batch action messages in Matrix listener"
```

---

### Task 6: Add `actions` field to GameTurnFlow state

**Files:**
- Modify: `engine/src/memento/flows/game_turn.py:20-31, 226`

- [ ] **Step 1: Add `actions` to TurnState**

In `engine/src/memento/flows/game_turn.py`, add `actions` field to `TurnState` (after line 24):

```python
class TurnState(BaseModel):
    player_name: str = ""
    player_uuid: str = ""
    location_name: str = ""
    action: str = ""
    actions: list[dict] = []
    context: str = ""
    events: dict = {}
    narrative: str = ""
    world_time: dict = {}
    plausible: bool = True
    rejection_reason: str = ""
    subsystem_warnings: list[str] = []
```

- [ ] **Step 2: Fix stale `record_episode` call**

Line 226 still calls the old 6-arg signature. Replace line 226:

```python
            _chain.record_episode(ep_uuid, ep_name, ep_summary, entity_list, edge_list, tick)
```

With:

```python
            from memento.tools.ipfs import pin_json
            episode_data = {
                "version": 1,
                "episodeId": ep_uuid,
                "tick": tick,
                "name": ep_name,
                "summary": ep_summary,
                "entities": entity_list,
                "edges": edge_list,
            }
            cid, content_hash = pin_json(episode_data)
            if cid and content_hash:
                _chain.record_episode(ep_uuid, content_hash, tick)
```

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/flows/game_turn.py
git commit -m "feat(engine): add actions list to TurnState, fix stale record_episode call"
```

---

### Task 7: Fix narrative broadcast in matrix_bridge.py

**Files:**
- Modify: `gateway/src/gateway/matrix_bridge.py:102-143`

- [ ] **Step 1: Update `_on_message` to broadcast batch narratives**

Replace lines 134-141 in `gateway/src/gateway/matrix_bridge.py` (the section that sends narrative to clients):

```python
            # Batch narratives go to all players at location
            # Single-player narratives go to the specific player
            location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
            if location:
                await self.ws_hub.broadcast_to_location(location, msg)
            elif player_id and self.ws_hub.connections.get(player_id):
                await self.ws_hub.send_to_player(player_id, msg)
            else:
                await self.ws_hub.broadcast_all(msg)
```

Also update the `_send_status` helper (lines 113-120) to prefer location broadcast:

```python
            async def _send_status(phase: str) -> None:
                status_msg = {"type": "status", "phase": phase}
                location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
                if location:
                    await self.ws_hub.broadcast_to_location(location, status_msg)
                elif player_id and self.ws_hub.connections.get(player_id):
                    await self.ws_hub.send_to_player(player_id, status_msg)
                else:
                    await self.ws_hub.broadcast_all(status_msg)
```

- [ ] **Step 2: Commit**

```bash
git add gateway/src/gateway/matrix_bridge.py
git commit -m "feat(gateway): broadcast narratives to all players at location"
```

---

## Verification

After all tasks are complete:

1. **Engine tests pass:**
   ```bash
   cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -m pytest tests/test_round_manager.py -v
   ```
   Expected: 4/4 pass (including new `close_round` tests)

2. **Gateway tests pass:**
   ```bash
   cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -m pytest tests/ -v
   ```

3. **All imports resolve:**
   ```bash
   cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python -c "
   from gateway.round_callback import make_round_callback
   from gateway.app import round_manager
   print('Gateway imports OK')
   "
   ```

4. **Engine batch handler imports:**
   ```bash
   cd /home/at0x/Vaults/Bonfires/memento-mori/engine && python -c "
   from memento.matrix_listener import EngineMatrixListener
   from memento.flows.game_turn import TurnState
   ts = TurnState(actions=[{'player_id': 'p1', 'player_name': 'Kael', 'action': 'test'}])
   assert len(ts.actions) == 1
   print('Engine imports OK')
   "
   ```
