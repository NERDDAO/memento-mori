"""WebSocket hub — manages player connections and message broadcast."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from gateway.log import get_logger

logger = get_logger(__name__)


class WebSocketHub:
    """Manages WebSocket connections per player."""

    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}  # player_id -> websocket
        self.player_locations: dict[str, str] = {}   # player_id -> location_name

    async def connect(self, player_id: str, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self.connections[player_id] = websocket

    def disconnect(self, player_id: str) -> None:
        """Remove a disconnected player."""
        self.connections.pop(player_id, None)
        self.player_locations.pop(player_id, None)

    def set_location(self, player_id: str, location: str) -> None:
        """Track which location a player is in."""
        self.player_locations[player_id] = location

    async def send_to_player(self, player_id: str, message: dict[str, Any]) -> None:
        """Send a message to a specific player."""
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("WebSocket send failed for %s, disconnecting", player_id, exc_info=True)
                self.disconnect(player_id)

    async def broadcast_to_location(self, location: str, message: dict[str, Any]) -> None:
        """Send a message to all players at a location."""
        for pid, loc in list(self.player_locations.items()):
            if loc == location:
                await self.send_to_player(pid, message)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        """Send a message to all connected players."""
        for pid in list(self.connections.keys()):
            await self.send_to_player(pid, message)
