"""Round manager — batches player actions for multiplayer turns."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from memento.log import get_logger

logger = get_logger(__name__)


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
    deadline: float = 0.0
    closed: bool = False


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
        """Register a callback fired on every submitted action.

        Callback signature: async def callback(location: str, action_count: int, deadline: float)
        """
        self._action_callbacks.append(callback)

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

    async def _close_after_window(self, location: str) -> None:
        """Wait for the window, then close the round and dispatch."""
        await asyncio.sleep(self.window)
        round_ = self.active_rounds.pop(location, None)
        if round_ and not round_.closed:
            round_.closed = True
            for callback in self._callbacks:
                try:
                    await callback(location, round_.actions)
                except Exception as e:
                    logger.error("Round close callback error", exc_info=True)

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

    @property
    def active_count(self) -> int:
        return len(self.active_rounds)
