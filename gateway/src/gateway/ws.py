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
        self.player_names: dict[str, str] = {}       # player_id -> display name

    async def connect(self, player_id: str, websocket: WebSocket, player_name: str = "") -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self.connections[player_id] = websocket
        if player_name:
            self.player_names[player_id] = player_name

    async def disconnect(self, player_id: str) -> None:
        """Remove a disconnected player and broadcast their departure."""
        location = self.player_locations.get(player_id, "")
        name = self.player_names.get(player_id, player_id)
        self.connections.pop(player_id, None)
        self.player_locations.pop(player_id, None)
        self.player_names.pop(player_id, None)
        if location:
            await self.broadcast_to_location(location, {
                "type": "player_left",
                "player_id": player_id,
                "player_name": name,
                "location": location,
            })

    async def set_location(self, player_id: str, location: str) -> None:
        """Track which location a player is in and broadcast presence updates."""
        old_location = self.player_locations.get(player_id, "")
        name = self.player_names.get(player_id, player_id)
        self.player_locations[player_id] = location
        if old_location and old_location != location:
            await self.broadcast_to_location(old_location, {
                "type": "player_left", "player_id": player_id,
                "player_name": name, "location": old_location,
            })
        for pid, loc in list(self.player_locations.items()):
            if loc == location and pid != player_id:
                await self.send_to_player(pid, {
                    "type": "player_joined", "player_id": player_id,
                    "player_name": name, "location": location,
                })
        players = self.get_players_at_location(location)
        await self.send_to_player(player_id, {
            "type": "presence", "players": players, "location": location,
        })

    def get_players_at_location(self, location: str) -> list[dict[str, str]]:
        """Return all players currently at a given location."""
        return [
            {"player_id": pid, "player_name": self.player_names.get(pid, pid)}
            for pid, loc in self.player_locations.items()
            if loc == location
        ]

    def players_at_location(self, location: str) -> int:
        """Count connected players at a given location."""
        return sum(1 for loc in self.player_locations.values() if loc == location)

    async def send_to_player(self, player_id: str, message: dict[str, Any]) -> None:
        """Send a message to a specific player."""
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("WebSocket send failed for %s, disconnecting", player_id, exc_info=True)
                await self.disconnect(player_id)

    async def broadcast_to_location(self, location: str, message: dict[str, Any]) -> None:
        """Send a message to all players at a location."""
        for pid, loc in list(self.player_locations.items()):
            if loc == location:
                await self.send_to_player(pid, message)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        """Send a message to all connected players."""
        for pid in list(self.connections.keys()):
            await self.send_to_player(pid, message)

    async def broadcast_death(
        self, player_name: str, level: int, cause: str, location: str
    ) -> None:
        """Broadcast a permadeath announcement to all connected players."""
        msg = {
            "type": "death_feed",
            "player_name": player_name,
            "level": level,
            "cause": cause,
            "location": location,
        }
        logger.info("Death feed: %s (Lv %d) at %s — %s", player_name, level, location, cause)
        await self.broadcast_all(msg)

    async def broadcast_episode(self, episode: dict) -> None:
        """Broadcast a new episode to all connected clients."""
        msg = {
            "type": "episode_feed",
            "episode_uuid": episode.get("uuid", ""),
            "agent_id": episode.get("agent_id", ""),
            "name": episode.get("name", ""),
            "summary": episode.get("content", episode.get("summary", "")),
            "location": episode.get("location", ""),
            "timestamp": episode.get("created_at", ""),
        }
        await self.broadcast_all(msg)
