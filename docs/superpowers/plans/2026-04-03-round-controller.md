# Round Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-chaining GameTurnFlow with an explicit RoundController that orchestrates crew execution like a stoplight — gating LLM calls on preconditions, waiting for NPC responses before narrating, and emitting phase messages so the client tracks real-time progress.

**Architecture:** New `RoundController` replaces `GameTurnFlow`. It drives crew execution step-by-step, emits phases to Matrix, waits for NPC responses before narrating, and gates world events on cooldown. Gateway forwards phase messages to WebSocket and emits `collecting` phase. Client maintains shared round state for UI rendering and input locking.

**Tech Stack:** Python (matrix-nio, asyncio), FastAPI, TypeScript (Bun/Pretext client), WebSocket, Matrix protocol.

---

### Task 1: Add `on_action` Callback to RoundManager

**Files:**
- Modify: `engine/src/memento/round_manager.py:31-66`

- [ ] **Step 1: Add `_action_callbacks` list and `on_action` registration method**

In `engine/src/memento/round_manager.py`, add a second callback list for action-received events:

```python
class RoundManager:
    """Batches actions from multiple players at the same location."""

    def __init__(self, window_seconds: int = 20) -> None:
        self.window = window_seconds
        self.active_rounds: dict[str, Round] = {}  # location -> Round
        self._callbacks: list[Any] = []
        self._action_callbacks: list[Any] = []

    def on_round_close(self, callback: Any) -> None:
        """Register a callback for when a round closes.

        Callback signature: async def callback(location: str, actions: list[PlayerAction])
        """
        self._callbacks.append(callback)

    def on_action(self, callback: Any) -> None:
        """Register a callback for when an action is received.

        Callback signature: async def callback(location: str, action_count: int, deadline: float)
        """
        self._action_callbacks.append(callback)
```

- [ ] **Step 2: Fire action callbacks in `submit_action`**

At the end of `submit_action`, after appending the action, fire the action callbacks:

```python
    async def submit_action(
        self, player_id: str, player_name: str, location: str, action: str
    ) -> None:
        """Submit a player action. Starts a round timer if first action at location."""
        if location not in self.active_rounds:
            self.active_rounds[location] = Round(
                location=location,
                deadline=time.time() + self.window,
            )
            # Start timer for this location
            asyncio.create_task(self._close_after_window(location))

        round_ = self.active_rounds[location]
        if not round_.closed:
            round_.actions.append(
                PlayerAction(
                    player_id=player_id,
                    player_name=player_name,
                    action=action,
                )
            )
            # Notify listeners of new action
            for cb in self._action_callbacks:
                try:
                    await cb(location, len(round_.actions), round_.deadline)
                except Exception:
                    logger.error("Action callback error", exc_info=True)
```

- [ ] **Step 3: Verify the module loads**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori && python3 -c "from memento.round_manager import RoundManager; rm = RoundManager(); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add engine/src/memento/round_manager.py
git commit -m "feat(engine): add on_action callback to RoundManager for phase tracking"
```

---

### Task 2: Emit `collecting` Phase from Gateway

**Files:**
- Modify: `gateway/src/gateway/round_callback.py:17-69`
- Modify: `gateway/src/gateway/app.py:26-34`

- [ ] **Step 1: Add `make_action_callback` to `round_callback.py`**

Add a second factory function that creates the action-received callback. Place it after the existing `make_round_callback` function:

```python
def make_action_callback(ws_hub: WebSocketHub):
    """Create an async callback for RoundManager.on_action.

    Emits 'collecting' phase to all players at the location.
    """

    async def on_action_received(location: str, action_count: int, deadline: float) -> None:
        await ws_hub.broadcast_to_location(location, {
            "type": "phase",
            "phase": "collecting",
            "action_count": action_count,
            "deadline": int(deadline * 1000),  # unix ms for client
        })

    return on_action_received
```

- [ ] **Step 2: Wire the action callback in `app.py`**

In `gateway/src/gateway/app.py`, import the new factory and register it alongside the existing round close callback. Change line 12 and lines 33-34:

```python
from gateway.round_callback import make_round_callback, make_action_callback
```

And in the lifespan, after `round_manager.on_round_close(...)`:

```python
        round_manager.on_round_close(make_round_callback(bridge, ws_hub))
        round_manager.on_action(make_action_callback(ws_hub))
```

- [ ] **Step 3: Verify gateway starts**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python3 -c "from gateway.round_callback import make_round_callback, make_action_callback; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add gateway/src/gateway/round_callback.py gateway/src/gateway/app.py
git commit -m "feat(gateway): emit collecting phase on action received"
```

---

### Task 3: Create RoundController (Replaces GameTurnFlow)

**Files:**
- Create: `engine/src/memento/round_controller.py`
- Modify: `engine/src/memento/matrix_listener.py:110-251`

The `RoundController` replaces `GameTurnFlow`. It calls the same crews but controls execution explicitly — emitting phases, gating on preconditions, and waiting for NPC responses before narrating.

- [ ] **Step 1: Create `round_controller.py`**

Create `engine/src/memento/round_controller.py`:

```python
"""Round controller — stoplight that orchestrates crew execution and phase emissions."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from memento.config import load_config
from memento.core import LLM
from memento.crews.context import make_context_crew
from memento.crews.narrative.narration import make_narration_crew
from memento.crews.faction.reputation import make_reputation_crew
from memento.flows.event_detection import EventDetectionFlow
from memento.flows.combat import CombatFlow
from memento.flows.episodic_memory import EpisodicMemoryFlow
from memento.flows.quest import QuestFlow
from memento.log import get_logger
from memento.tools.time import advance_time

logger = get_logger(__name__)

# Track last narration time per location — prevents world event stacking.
_last_narration: dict[str, float] = {}

# Minimum seconds between world narrations at the same location.
NARRATION_COOLDOWN = 30


class RoundController:
    """Stoplight — drives crew execution step by step, emitting phases between each.

    Replaces GameTurnFlow's auto-chaining @start/@listen decorators with explicit
    sequential control. Gates crews on preconditions (cooldowns, NPC windows).
    """

    def __init__(self, matrix_client: Any, room_id: str, location: str) -> None:
        self.matrix_client = matrix_client
        self.room_id = room_id
        self.location = location
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Cache the running event loop (called from worker thread)."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        return self._loop

    def emit_phase(self, phase: str, crew: str | None = None) -> None:
        """Post a phase message to the Matrix room."""
        if not self.matrix_client or not self.room_id:
            return
        msg: dict[str, Any] = {
            "type": "phase",
            "phase": phase,
            "location": self.location,
        }
        if crew:
            msg["crew"] = crew
        content = {
            "msgtype": "m.text",
            "body": f"[phase] {phase}" + (f":{crew}" if crew else ""),
            "com.bonfires.rpg": msg,
        }
        try:
            loop = self._get_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.matrix_client.room_send(self.room_id, "m.room.message", content),
                loop,
            )
            future.result(timeout=5)
        except Exception:
            logger.warning("Failed to emit phase %s:%s", phase, crew, exc_info=True)

    def await_npc_responses(self, timeout: int = 15) -> list[str]:
        """Wait for NPC agent messages in the room. Returns collected response texts.

        Blocks the worker thread for up to `timeout` seconds. NPC messages are
        Matrix messages from @bonfires-* users with no com.bonfires.rpg metadata.
        We poll recent room messages rather than hooking into the sync stream
        (the engine's nio client is read-only for sync; the gateway handles sync).

        For now, this is a simple sleep — NPC responses will be picked up by the
        narration crew's context gathering from room history. The sleep gives NPCs
        time to respond before the narration crew reads the room.
        """
        self.emit_phase("npc_response")
        time.sleep(timeout)
        # NPC responses are now in room history; narration crew reads them via context.
        # Future: actively poll room messages and return texts for richer context.
        return []

    def should_narrate(self) -> bool:
        """Gate: don't narrate if a world event just fired at this location."""
        last = _last_narration.get(self.location, 0)
        elapsed = time.time() - last
        if elapsed < NARRATION_COOLDOWN:
            logger.info(
                "Narration cooldown: %s had narration %.0fs ago (< %ds), skipping",
                self.location, elapsed, NARRATION_COOLDOWN,
            )
            return False
        return True

    def _record_narration(self) -> None:
        """Record that a narration just fired at this location."""
        _last_narration[self.location] = time.time()

    # --- Crew calls (extracted from GameTurnFlow) ---

    def gather_context(self, player_name: str, action: str) -> str:
        crew = make_context_crew(player_name, self.location, action)
        result = crew.kickoff()
        return result.raw

    def check_plausibility(self, context: str, action: str) -> tuple[bool, str]:
        config = load_config()
        llm = LLM(model=config["llm"]["default_model"])
        response = llm.call(
            f"You are a plausibility checker for a dark fantasy RPG.\n\n"
            f"Scene context:\n{context[:1500]}\n\n"
            f"Player action: '{action}'\n\n"
            f"Is this action physically plausible in this scene? "
            f"Answer ONLY 'yes' or 'no: [brief reason]'."
        )
        raw = response.strip().lower()
        if raw.startswith("no"):
            return False, raw
        return True, ""

    def detect_events(self, action: str, context: str) -> dict:
        flow = EventDetectionFlow()
        flow.state.action = action
        flow.state.context = context
        flow.kickoff()
        return flow.state.events

    def resolve_events(
        self, events: dict, action: str, context: str,
        player_name: str, location: str,
    ) -> tuple[dict, list[str]]:
        """Run event resolution crews. Returns (updated events, subsystem_warnings)."""
        categories = events.get("categories", [])
        warnings: list[str] = []

        if "combat" in categories:
            self.emit_phase("resolving", "combat")
            combat_flow = CombatFlow()
            combat_flow.state.action = action
            combat_flow.state.attacker = player_name
            combat_flow.state.target = "unknown"
            combat_flow.state.location = location
            combat_flow.state.context = context
            combat_flow.kickoff()
            events["combat_result"] = combat_flow.state.resolution
            events["combat_consequences"] = combat_flow.state.consequences

        if "quest" in categories:
            self.emit_phase("resolving", "quest")
            try:
                quest_flow = QuestFlow()
                quest_flow.state.location = location
                quest_flow.state.npc = "unknown"
                quest_flow.state.player_level = 1
                quest_flow.kickoff()
                events["quest_result"] = quest_flow.state.quest_concept
            except Exception:
                logger.warning("Quest flow failed", exc_info=True)
                warnings.append("quest_unavailable")

        if "social" in categories:
            self.emit_phase("resolving", "social")
            try:
                rep_crew = make_reputation_crew(
                    player=player_name, faction="unknown", action=action,
                )
                rep_result = rep_crew.kickoff()
                events["reputation"] = rep_result.raw
            except Exception:
                logger.warning("Reputation flow failed", exc_info=True)
                warnings.append("reputation_unavailable")

        return events, warnings

    def narrate(self, action: str, context: str, events: dict, mode: str = "action") -> str:
        crew = make_narration_crew(
            action=action, context=context, events=str(events), mode=mode,
        )
        result = crew.kickoff()
        return result.raw

    def narrate_rejection(self, action: str, context: str, reason: str) -> str:
        crew = make_narration_crew(
            action=action, context=context,
            events=f"Action rejected: {reason}", mode="rejection",
        )
        result = crew.kickoff()
        return result.raw

    def post_turn(self, narrative: str, events: dict, player_name: str, player_uuid: str) -> tuple[dict, list[str]]:
        """Episodic memory + time advance. Returns (world_time_display, warnings)."""
        warnings: list[str] = []
        try:
            memory_flow = EpisodicMemoryFlow()
            memory_flow.state.narrative = narrative
            memory_flow.state.events = str(events)
            memory_flow.state.player = player_name
            memory_flow.state.session_id = player_uuid
            memory_flow.kickoff()
        except Exception:
            logger.warning("Memory flow failed", exc_info=True)
            warnings.append("memory_unavailable")

        world_time = advance_time(1)
        return world_time.to_display(), warnings

    # --- Main orchestration ---

    def run(
        self,
        player_name: str,
        player_uuid: str,
        action: str,
        actions: list[dict] | None = None,
    ) -> tuple[str, dict]:
        """Execute a full round. Returns (narrative, state_update_dict).

        This is the stoplight — it calls each crew in order, emitting phases,
        gating on preconditions, and waiting for NPC responses before narrating.
        """
        from memento.models.state_update import StateUpdate, EventSummary, CombatEvent

        subsystem_warnings: list[str] = []

        # --- Context ---
        self.emit_phase("resolving", "context")
        context = self.gather_context(player_name, action)

        # --- Plausibility ---
        self.emit_phase("resolving", "plausibility")
        plausible, reason = self.check_plausibility(context, action)
        if not plausible:
            self.emit_phase("resolving", "narrating")
            narrative = self.narrate_rejection(action, context, reason)
            self._record_narration()
            state_update = StateUpdate(location=self.location)
            self.emit_phase("ready")
            return narrative, state_update.model_dump(exclude_none=True)

        # --- Event detection ---
        self.emit_phase("resolving", "events")
        events = self.detect_events(action, context)

        # --- Event resolution (combat/quest/social — conditional) ---
        events, resolve_warnings = self.resolve_events(
            events, action, context, player_name, self.location,
        )
        subsystem_warnings.extend(resolve_warnings)

        # --- NPC response window ---
        # Give NPC agents time to respond in Matrix before narrating.
        # Their responses become part of room history that the narration crew can reference.
        npc_responses = self.await_npc_responses(timeout=15)

        # --- Narration cooldown gate ---
        if not self.should_narrate():
            # Skip narration — too soon after last world event at this location.
            world_time = advance_time(1)
            state_update = StateUpdate(
                location=self.location,
                world_time=world_time.to_display() if hasattr(world_time, 'to_display') else None,
                subsystem_warnings=subsystem_warnings,
            )
            self.emit_phase("ready")
            return "", state_update.model_dump(exclude_none=True)

        # --- Narration ---
        self.emit_phase("resolving", "narrating")
        narrative = self.narrate(action, context, events)
        self._record_narration()

        # --- Post-turn ---
        self.emit_phase("resolving", "post_turn")
        world_time_display, post_warnings = self.post_turn(
            narrative, events, player_name, player_uuid,
        )
        subsystem_warnings.extend(post_warnings)

        # --- Build state update ---
        events_summary = None
        if events and isinstance(events, dict):
            categories = events.get("categories", [])
            combat = None
            if "combat" in categories and "combat_result" in events:
                combat = CombatEvent(
                    action_type=events.get("action_type", "attack"),
                    target_name=events.get("combat_target", ""),
                    target_dead="dead" in str(events.get("combat_consequences", "")).lower(),
                )
            events_summary = EventSummary(categories=categories, combat=combat)

        state_update = StateUpdate(
            location=self.location,
            world_time=world_time_display if isinstance(world_time_display, dict) else None,
            events=events_summary,
            subsystem_warnings=subsystem_warnings,
        )

        self.emit_phase("ready")
        return narrative, state_update.model_dump(exclude_none=True)
```

- [ ] **Step 2: Verify module loads**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori && python3 -c "from memento.round_controller import RoundController; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add engine/src/memento/round_controller.py
git commit -m "feat(engine): add RoundController — stoplight orchestrator replacing GameTurnFlow"
```

---

### Task 4: Wire RoundController into MatrixListener

**Files:**
- Modify: `engine/src/memento/matrix_listener.py:110-251`

Replace `GameTurnFlow` calls with `RoundController`. The listener creates a controller per round and calls `controller.run()`.

- [ ] **Step 1: Rewrite `_run_turn_inner` and `_run_batch_turn_inner`**

Replace both static methods in `EngineMatrixListener`:

```python
    @staticmethod
    def _run_turn_inner(player_id: str, location_name: str, action: str,
                        matrix_client=None, room_id: str = "") -> tuple[str, dict]:
        from memento.round_controller import RoundController

        controller = RoundController(matrix_client, room_id, location_name)
        return controller.run(
            player_name=player_id,
            player_uuid=player_id,
            action=action,
        )

    @staticmethod
    def _run_batch_turn_inner(location_name: str, actions: list[dict],
                              matrix_client=None, room_id: str = "") -> tuple[str, dict]:
        from memento.round_controller import RoundController

        controller = RoundController(matrix_client, room_id, location_name)
        # Build combined action string
        player_name = actions[0].get("player_name", "unknown") if actions else "unknown"
        combined = "; ".join(
            f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
        )
        return controller.run(
            player_name=player_name,
            player_uuid=player_name,
            action=combined,
            actions=actions,
        )
```

- [ ] **Step 2: Update `_run_turn` and `_run_batch_turn` to pass matrix_client and room_id**

```python
    @staticmethod
    def _run_turn(player_id: str, location_name: str, action: str,
                  matrix_client=None, room_id: str = "") -> tuple[str, dict]:
        with _turn_lock:
            return EngineMatrixListener._run_turn_inner(
                player_id, location_name, action, matrix_client, room_id
            )

    @staticmethod
    def _run_batch_turn(location_name: str, actions: list[dict],
                        matrix_client=None, room_id: str = "") -> tuple[str, dict]:
        with _turn_lock:
            return EngineMatrixListener._run_batch_turn_inner(
                location_name, actions, matrix_client, room_id
            )
```

- [ ] **Step 3: Update `_on_action` to pass matrix_client and room_id to thread calls**

In the batch path (around line 126):

```python
            narrative, state_update = await asyncio.to_thread(
                self._run_batch_turn, location_name, actions, self.client, room.room_id
            )
```

In the single-action path (around line 152):

```python
            narrative, state_update = await asyncio.to_thread(
                self._run_turn, player_id, location_name, action_text, self.client, room.room_id
            )
```

- [ ] **Step 4: Remove old GameTurnFlow imports**

Remove the `GameTurnFlow` import from `_run_turn_inner` and `_run_batch_turn_inner` (they now import `RoundController` instead). The old `game_turn.py` file can stay for now (other code may reference `query_active_quests`).

- [ ] **Step 5: Verify module loads**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori && python3 -c "from memento.matrix_listener import EngineMatrixListener; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add engine/src/memento/matrix_listener.py
git commit -m "feat(engine): wire RoundController into MatrixListener, replacing GameTurnFlow"
```

---

### Task 5: Forward Phase Messages in Gateway (Simplified)

**Files:**
- Modify: `gateway/src/gateway/matrix_bridge.py:102-166`

NPC timeout logic is now in the engine's RoundController. The gateway just forwards phase messages and removes the post-narrative npc_response emission.

- [ ] **Step 1: Add phase handler to `_on_message`**

In `_on_message`, add a phase handler before the existing narrative handler. Insert after `rpg_meta` extraction:

```python
        rpg_type = rpg_meta.get("type", "")

        # Phase messages — forward to WebSocket
        if rpg_type == "phase":
            location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
            if location:
                await self.ws_hub.broadcast_to_location(location, {
                    "type": "phase",
                    "phase": rpg_meta.get("phase", "resolving"),
                    "crew": rpg_meta.get("crew"),
                })
            return
```

The rest of `_on_message` stays unchanged — narrative forwarding and NPC message forwarding work as before. Remove the post-narrative `npc_response` emission and timeout logic (lines 487-493 from the old plan) since the engine now handles this.

- [ ] **Step 2: Verify module loads**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/gateway && python3 -c "from gateway.matrix_bridge import MatrixBridge; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add gateway/src/gateway/matrix_bridge.py
git commit -m "feat(gateway): forward phase messages from engine to WebSocket"
```

---

### Task 6: Client — Shared Round State

**Files:**
- Create: `client/src/state/round-state.ts`

- [ ] **Step 1: Create the round state module**

Create `client/src/state/round-state.ts`:

```typescript
// src/state/round-state.ts
/** Shared round state — components subscribe to phase changes. */

export type Phase = "ready" | "collecting" | "resolving" | "npc_response";

export interface RoundState {
  phase: Phase;
  crew?: string;
  location?: string;
  actionCount?: number;
  deadline?: number;       // unix ms
  secondsLeft?: number;    // computed locally
}

export interface PhaseMessage {
  type: "phase";
  phase: Phase;
  crew?: string;
  location?: string;
  action_count?: number;
  deadline?: number;
}

type RoundListener = (state: RoundState) => void;

const listeners: RoundListener[] = [];
let countdownTimer: ReturnType<typeof setInterval> | null = null;

const state: RoundState = {
  phase: "ready",
};

export function getRoundState(): RoundState {
  return state;
}

export function onRoundStateChange(listener: RoundListener): () => void {
  listeners.push(listener);
  return () => {
    const idx = listeners.indexOf(listener);
    if (idx >= 0) listeners.splice(idx, 1);
  };
}

function notify(): void {
  for (const fn of listeners) fn(state);
}

function stopCountdown(): void {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
  state.secondsLeft = undefined;
  state.deadline = undefined;
}

function startCountdown(deadline: number): void {
  stopCountdown();
  state.deadline = deadline;
  state.secondsLeft = Math.ceil((deadline - Date.now()) / 1000);

  countdownTimer = setInterval(() => {
    if (!state.deadline) { stopCountdown(); return; }
    const left = Math.ceil((state.deadline - Date.now()) / 1000);
    state.secondsLeft = Math.max(0, left);
    notify();
  }, 1000);
}

export function updateRoundState(msg: PhaseMessage): void {
  state.phase = msg.phase;
  state.crew = msg.crew;

  if (msg.location) state.location = msg.location;
  if (msg.action_count != null) state.actionCount = msg.action_count;

  if (msg.phase === "collecting" && msg.deadline) {
    startCountdown(msg.deadline);
  } else if (msg.phase !== "collecting") {
    stopCountdown();
    state.actionCount = undefined;
  }

  notify();
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && npx tsc --noEmit src/state/round-state.ts 2>&1 | head -20`
Expected: No errors (or only unrelated ambient type errors)

- [ ] **Step 3: Commit**

```bash
git add client/src/state/round-state.ts
git commit -m "feat(client): add shared round state module with countdown timer"
```

---

### Task 7: Client — Overhaul Status Bar

**Files:**
- Modify: `client/src/ui/status.ts:1-77`

- [ ] **Step 1: Rewrite `status.ts` to use round state**

Replace the full contents of `client/src/ui/status.ts`:

```typescript
// src/ui/status.ts
/**
 * Status bar — round phase indicator (left), chain status (center), tick (right).
 */

import { onRoundStateChange, type RoundState } from '../state/round-state';

export interface StatusBar {
  el: HTMLElement;
  setChain(connected: boolean): void;
  setTick(tick: number): void;
}

export function createStatusBar(): StatusBar {
  const el = document.createElement('div');
  el.className = 'status-bar';
  el.innerHTML = `
    <span class="status-phase">\u2713 Ready</span>
    <span class="status-chain">\u25C7 Redstone: offline</span>
    <span class="status-tick">\u263D Tick 0</span>
  `;

  const phaseEl = el.querySelector('.status-phase') as HTMLElement;
  const chainEl = el.querySelector('.status-chain') as HTMLElement;
  const tickEl = el.querySelector('.status-tick') as HTMLElement;

  function renderPhase(rs: RoundState): void {
    switch (rs.phase) {
      case 'ready':
        phaseEl.textContent = rs.location
          ? `\u2713 Ready \u00B7 ${rs.location}`
          : '\u2713 Ready';
        phaseEl.className = 'status-phase ready';
        break;
      case 'collecting': {
        const count = rs.actionCount ?? 0;
        const timer = rs.secondsLeft != null ? ` (${rs.secondsLeft}s)` : '';
        phaseEl.textContent = `\u27F3 Collecting \u00B7 ${count} action${count !== 1 ? 's' : ''}${timer}`;
        phaseEl.className = 'status-phase collecting';
        break;
      }
      case 'resolving': {
        const crewLabel = rs.crew
          ? rs.crew.charAt(0).toUpperCase() + rs.crew.slice(1).replace('_', '-')
          : '';
        phaseEl.textContent = crewLabel
          ? `\u27F3 Resolving \u00B7 ${crewLabel}`
          : '\u27F3 Resolving';
        phaseEl.className = 'status-phase resolving';
        break;
      }
      case 'npc_response':
        phaseEl.textContent = '\u27F3 NPCs Responding';
        phaseEl.className = 'status-phase npc-response';
        break;
    }
  }

  onRoundStateChange(renderPhase);

  return {
    el,
    setChain(connected: boolean) {
      chainEl.textContent = connected
        ? '\u25C6 Redstone: synced'
        : '\u25C7 Redstone: offline';
      chainEl.className = `status-chain ${connected ? 'connected' : ''}`;
    },
    setTick(tick: number) {
      tickEl.textContent = `\u263D Tick ${tick}`;
    },
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/ui/status.ts
git commit -m "feat(client): overhaul status bar to render round phases"
```

---

### Task 8: Client — Handle `phase` Messages in `app.ts`

**Files:**
- Modify: `client/src/app.ts:1-215`

- [ ] **Step 1: Import round state and wire up phase handling**

Add import at top of `client/src/app.ts` (after the other state imports):

```typescript
import { updateRoundState, getRoundState, type PhaseMessage } from './state/round-state';
```

- [ ] **Step 2: Add `phase` case to `handleMessage` switch**

In `handleMessage`, add a new case before the `default` case (around line 212):

```typescript
    case 'phase':
      updateRoundState(msg as PhaseMessage);
      break;
```

- [ ] **Step 3: Remove old `setPhase` calls**

Remove these lines that call the old `statusBar.setPhase()`:

1. In the `narrative` case (line 147): remove `statusBar.setPhase('synced');`
2. In the `thinking` case (line 199): remove `statusBar.setPhase('thinking');`
3. In the `status` case (line 208): remove `if (msg.phase) statusBar.setPhase(msg.phase);`

The `status` case becomes:

```typescript
    case 'status':
      if (msg.tick != null) statusBar.setTick(msg.tick);
      if (msg.chain != null) statusBar.setChain(msg.chain);
      break;
```

- [ ] **Step 4: Update location in round state when narrative arrives**

In the `narrative` case, after `session.currentLocation = gameState.location.name;` (around line 155), add:

```typescript
        // Update round state location for "Ready · Location" display
        updateRoundState({
          type: 'phase',
          phase: 'ready',
          location: gameState.location.name,
        });
```

Wait — this would override the current phase. Instead, we should only set the location on the round state when entering ready. A better approach: after `applyStateUpdate` updates the location, just update the round state location without changing the phase. Add a helper in round-state for this.

Actually, the `ready` phase message from the gateway will include `location`. And the `narrative` case already represents the end of a turn. But the gateway sends `npc_response` after narrative, not `ready`. So the location gets set when `ready` arrives from the NPC timeout.

For the initial state (before any round), set location in `enterWorld`:

In the `enterWorld` function (around line 266), after setting `session.currentLocation`:

```typescript
  updateRoundState({ type: 'phase', phase: 'ready', location: session.currentLocation });
```

- [ ] **Step 5: Verify client compiles**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 6: Commit**

```bash
git add client/src/app.ts
git commit -m "feat(client): handle phase messages, remove old setPhase calls"
```

---

### Task 9: Client — Input Locking

**Files:**
- Modify: `client/src/panels/input.ts:1-38`
- Modify: `client/src/app.ts` (pass inputEl reference)

- [ ] **Step 1: Add round state subscription to input panel**

Rewrite `client/src/panels/input.ts`:

```typescript
// src/panels/input.ts
/** Input panel — text input with command history navigation and round-phase locking. */

import { onRoundStateChange, type RoundState } from '../state/round-state';

export function initInput(
  inputEl: HTMLInputElement,
  onSubmit: (action: string) => void,
): void {
  const history: string[] = [];
  let historyIndex = -1;
  let locked = false;
  const defaultPlaceholder = inputEl.placeholder || 'What do you do?';

  function setLocked(isLocked: boolean): void {
    locked = isLocked;
    inputEl.disabled = isLocked;
    inputEl.classList.toggle('input-locked', isLocked);
  }

  onRoundStateChange((rs: RoundState) => {
    switch (rs.phase) {
      case 'ready':
        setLocked(false);
        inputEl.placeholder = defaultPlaceholder;
        break;
      case 'collecting': {
        setLocked(false);
        const timer = rs.secondsLeft != null ? `${rs.secondsLeft}s left to act...` : 'Round open...';
        inputEl.placeholder = timer;
        break;
      }
      case 'resolving':
        setLocked(true);
        inputEl.placeholder = 'Resolving...';
        break;
      case 'npc_response':
        setLocked(true);
        inputEl.placeholder = 'NPCs responding...';
        break;
    }
  });

  inputEl.addEventListener('keydown', (e: KeyboardEvent) => {
    if (locked) return;
    if (e.key === 'Enter') {
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = '';
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = '';
      }
    }
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/panels/input.ts
git commit -m "feat(client): lock input during resolving and npc_response phases"
```

---

### Task 10: Client — Narrative Dividers

**Files:**
- Modify: `client/src/panels/narrative.ts:93-129`

- [ ] **Step 1: Add round state subscription for dividers**

In `client/src/panels/narrative.ts`, import round state at the top:

```typescript
import { onRoundStateChange, type RoundState } from '../state/round-state';
```

Then inside `initNarrative`, before the `return` statement (before line 93), add the subscription:

```typescript
  // Round phase dividers
  let lastPhase = '';
  onRoundStateChange((rs: RoundState) => {
    if (rs.phase === 'resolving' && lastPhase !== 'resolving') {
      addBlockInternal('', '<hr class="round-divider">', 'divider');
    }
    lastPhase = rs.phase;
  });
```

- [ ] **Step 2: Commit**

```bash
git add client/src/panels/narrative.ts
git commit -m "feat(client): add round divider in narrative when resolving starts"
```

---

### Task 11: Client — NPC Thinking Highlight in Present Panel

**Files:**
- Modify: `client/src/panels/present.ts:1-28`

- [ ] **Step 1: Add round state subscription for NPC highlighting**

Rewrite `client/src/panels/present.ts`:

```typescript
// client/src/panels/present.ts
import type { GameState } from '../state/game-state';
import { onRoundStateChange, getRoundState, type RoundState } from '../state/round-state';

let currentBody: HTMLElement | null = null;

// Pulse NPC rows during npc_response phase
onRoundStateChange((rs: RoundState) => {
  if (!currentBody) return;
  const rows = currentBody.querySelectorAll('.npc-row');
  rows.forEach((row) => {
    (row as HTMLElement).classList.toggle('npc-thinking', rs.phase === 'npc_response');
  });
});

export function renderPresentPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  currentBody = body;
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  if (npcs.length === 0 && items.length === 0) {
    body.innerHTML = '<div class="empty-msg">Nothing here</div>';
    return;
  }
  const rs = getRoundState();
  const thinkingClass = rs.phase === 'npc_response' ? ' npc-thinking' : '';
  let html = '';
  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : (npc as any).name;
    const role = typeof npc === 'string' ? '' : ((npc as any).role || '');
    html += `<div class="npc-row${thinkingClass}" data-action="talk to ${name}" style="cursor:pointer"><span class="npc-diamond">\u25C6</span><span class="npc">${name}</span>${role ? `<span class="npc-role">\u2014 ${role}</span>` : ''}</div>`;
  }
  for (const item of items) {
    const name = typeof item === 'string' ? item : (item as any).name;
    html += `<div class="item-row" data-action="examine ${name}" style="cursor:pointer"><span class="item-bullet">\u00B7</span> ${name}</div>`;
  }
  body.innerHTML = html;
  body.querySelectorAll('[data-action]').forEach((el) => {
    el.addEventListener('click', () => onAction((el as HTMLElement).dataset.action!));
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/panels/present.ts
git commit -m "feat(client): pulse NPC names during npc_response phase"
```

---

### Task 12: CSS for Round Controller States

**Files:**
- Modify: `client/index.html` (or wherever CSS lives)

- [ ] **Step 1: Find where CSS is defined**

Run: `grep -rn "status-phase\|status-bar" /home/at0x/Vaults/Bonfires/memento-mori/client/index.html | head -10`

- [ ] **Step 2: Add CSS for round controller states**

Add these styles to the existing CSS (in the `<style>` block or CSS file):

```css
/* Round controller phases */
.status-phase.ready { color: var(--text-green, #6a9955); }
.status-phase.collecting { color: var(--text-yellow, #d7ba7d); }
.status-phase.resolving { color: var(--text-blue, #569cd6); }
.status-phase.npc-response { color: var(--text-purple, #c586c0); }

/* Input locking */
.input-locked {
  opacity: 0.4;
  cursor: not-allowed;
}

/* NPC thinking pulse */
.npc-thinking {
  animation: npc-pulse 1.5s ease-in-out infinite;
}
@keyframes npc-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Round divider */
.narrative-block.divider hr.round-divider {
  border: none;
  border-top: 1px solid var(--border-dim, #333);
  margin: 0.5em 0;
}
```

- [ ] **Step 3: Commit**

```bash
git add client/index.html
git commit -m "style(client): add CSS for round controller phases, input lock, NPC pulse"
```

---

### Task 13: Remove Old `thinking` Message Handling

**Files:**
- Modify: `client/src/app.ts`
- Modify: `gateway/src/gateway/round_callback.py`

- [ ] **Step 1: Remove the `thinking` case from `handleMessage` in `app.ts`**

The `thinking` message type is replaced by the `phase` message. Remove the `thinking` case:

```typescript
    // DELETE this entire case:
    case 'thinking':
      narrative.showThinking();
      statusBar.setPhase('thinking');
      break;
```

The `showThinking()` indicator in the narrative panel is now unnecessary — the status bar shows the resolving phase directly. If we still want the "The world responds" text in the narrative during resolving, we can trigger it from the round state subscription. For now, remove it — the status bar is sufficient.

- [ ] **Step 2: Remove the thinking broadcast from `round_callback.py`**

In `gateway/src/gateway/round_callback.py`, remove lines 33-37 (the thinking broadcast) from `on_round_close`:

```python
    async def on_round_close(location: str, actions: list[PlayerAction]) -> None:
        if not bridge or not bridge.connected:
            logger.warning("Round closed but bridge disconnected: %s (%d actions)", location, len(actions))
            return

        room_id = await bridge.get_or_create_room(location)

        # Step 1: Send each player action as a readable message from the player
        # NPC agents see these and can respond
        for a in actions:
            await bridge.send_action(room_id, a.player_id, a.action)

        # Step 2: Send batch metadata for the engine listener
        # ... rest unchanged
```

- [ ] **Step 3: Remove thinking broadcast from action route solo path**

In `gateway/src/gateway/routes/action.py`, remove the multi-player thinking indicator (lines 60-65):

```python
    if round_manager:
        await round_manager.submit_action(
            req.player_id, req.player_id, req.location, req.action
        )
        # Solo fast-path: if only 1 player at location, close round immediately
        if ws_hub and ws_hub.players_at_location(req.location) <= 1:
            await round_manager.close_round(req.location)

    return ActionResponse(status="queued")
```

The `collecting` phase message from the `on_action` callback now handles player feedback.

- [ ] **Step 4: Commit**

```bash
git add client/src/app.ts gateway/src/gateway/round_callback.py gateway/src/gateway/routes/action.py
git commit -m "refactor: remove old thinking indicator, replaced by round controller phases"
```
