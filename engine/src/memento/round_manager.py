"""Round manager — batches player actions per location with extend-on-action.

Each location is like a group chat: actions pile up, the window extends
each time a new player acts, and once the window expires the round resolves.
Players can only act once per round.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from memento.log import get_logger

logger = get_logger(__name__)

# Type aliases for callbacks
RoundCloseCallback = Callable[[str, list["PlayerAction"]], Awaitable[None]]
ActionCallback = Callable[[str, "PlayerAction", list["PlayerAction"]], Awaitable[None]]


@dataclass
class PlayerAction:
    player_id: str
    player_name: str
    action: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Round:
    location: str
    actions: list[PlayerAction] = field(default_factory=list)
    player_ids: set[str] = field(default_factory=set)
    deadline: float = 0.0
    closed: bool = False


class RoundManager:
    """Batches actions from multiple players at the same location.

    - First action at a location opens a round with a window timer.
    - Each new action from a DIFFERENT player extends the window.
    - Same player cannot submit twice in one round (returns False).
    - When the window expires with no new actions, the round closes
      and the on_round_close callbacks fire with all batched actions.
    """

    def __init__(self, window_seconds: float = 5.0) -> None:
        self.window = window_seconds
        self.active_rounds: dict[str, Round] = {}  # location -> Round
        self._close_callbacks: list[RoundCloseCallback] = []
        self._action_callbacks: list[ActionCallback] = []
        self._timer_tasks: dict[str, asyncio.Task] = {}

    def on_round_close(self, callback: RoundCloseCallback) -> None:
        """Register a callback for when a round closes and resolves.

        Callback signature: async def callback(location: str, actions: list[PlayerAction])
        """
        self._close_callbacks.append(callback)

    def on_action(self, callback: ActionCallback) -> None:
        """Register a callback for when a new action is added to a round.

        Used to broadcast pending actions to other players at the location.
        Callback signature: async def callback(location: str, new_action: PlayerAction, all_actions: list[PlayerAction])
        """
        self._action_callbacks.append(callback)

    async def submit_action(
        self, player_id: str, player_name: str, location: str, action: str
    ) -> bool:
        """Submit a player action. Returns True if accepted, False if duplicate.

        - First action at a location opens the round.
        - Subsequent actions from different players extend the window.
        - Same player acting twice in one round is rejected.
        """
        round_ = self.active_rounds.get(location)

        if round_ and not round_.closed:
            # Round already open — check for duplicate
            if player_id in round_.player_ids:
                logger.info("Duplicate action from %s at %s, rejected", player_id, location)
                return False
            # New player joining the round — extend the window
            self._extend_window(location)
        else:
            # No active round — start one
            round_ = Round(
                location=location,
                deadline=time.time() + self.window,
            )
            self.active_rounds[location] = round_
            self._start_timer(location)

        # Add the action
        new_action = PlayerAction(
            player_id=player_id,
            player_name=player_name,
            action=action,
        )
        round_.actions.append(new_action)
        round_.player_ids.add(player_id)

        logger.info(
            "Action accepted: %s at %s (%d actions in round)",
            player_name, location, len(round_.actions),
        )

        # Notify listeners about the new action
        for callback in self._action_callbacks:
            try:
                await callback(location, new_action, list(round_.actions))
            except Exception:
                logger.error("Action callback error", exc_info=True)

        return True

    def _start_timer(self, location: str) -> None:
        """Start the countdown timer for a location's round."""
        # Cancel existing timer if any
        if location in self._timer_tasks:
            self._timer_tasks[location].cancel()
        self._timer_tasks[location] = asyncio.create_task(
            self._timer_loop(location)
        )

    def _extend_window(self, location: str) -> None:
        """Reset the deadline for a location's round."""
        round_ = self.active_rounds.get(location)
        if round_ and not round_.closed:
            round_.deadline = time.time() + self.window
            logger.info("Window extended for %s (now %d actions)", location, len(round_.actions))
            # Restart the timer
            self._start_timer(location)

    async def _timer_loop(self, location: str) -> None:
        """Wait for the window to expire, then close the round."""
        round_ = self.active_rounds.get(location)
        if not round_:
            return

        remaining = round_.deadline - time.time()
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Check if window was extended during sleep
        round_ = self.active_rounds.get(location)
        if not round_ or round_.closed:
            return
        if round_.deadline > time.time():
            # Window was extended — timer will be restarted by _extend_window
            return

        # Close the round
        self.active_rounds.pop(location, None)
        self._timer_tasks.pop(location, None)
        round_.closed = True

        logger.info(
            "Round closed at %s: %d actions from %d players",
            location, len(round_.actions), len(round_.player_ids),
        )

        for callback in self._close_callbacks:
            try:
                await callback(location, round_.actions)
            except Exception:
                logger.error("Round close callback error", exc_info=True)

    def is_round_active(self, location: str) -> bool:
        """Check if there's an active round at a location."""
        round_ = self.active_rounds.get(location)
        return round_ is not None and not round_.closed

    def get_pending_actions(self, location: str) -> list[PlayerAction]:
        """Get the current pending actions for a location."""
        round_ = self.active_rounds.get(location)
        if round_ and not round_.closed:
            return list(round_.actions)
        return []

    @property
    def active_count(self) -> int:
        return len(self.active_rounds)
