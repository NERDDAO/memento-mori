"""Matrix bridge — connects to Synapse, manages rooms, relays messages."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from nio import AsyncClient, MatrixRoom, RoomMessageText


class MatrixBridge:
    """Async Matrix client that bridges messages between gateway and game engine."""

    def __init__(self, homeserver: str, token: str, ws_hub: Any) -> None:
        self.homeserver = homeserver
        self.token = token
        self.ws_hub = ws_hub
        self.client: AsyncClient | None = None
        self.connected = False
        self.room_to_location: dict[str, str] = {}  # room_id -> location_name
        self.location_to_room: dict[str, str] = {}  # location_name -> room_id

    async def connect(self) -> None:
        """Connect to Matrix homeserver."""
        self.client = AsyncClient(self.homeserver)
        self.client.access_token = self.token
        self.client.user_id = "@narrator:localhost"  # will be set by whoami
        try:
            resp = await self.client.whoami()
            if hasattr(resp, "user_id"):
                self.client.user_id = resp.user_id
            self.client.add_event_callback(self._on_message, RoomMessageText)
            self.connected = True
            # Start sync in background
            asyncio.create_task(self._sync_loop())
        except Exception as e:
            print(f"[matrix] Connection failed: {e}")
            self.connected = False

    async def disconnect(self) -> None:
        """Disconnect from Matrix."""
        if self.client:
            await self.client.close()
        self.connected = False

    async def _sync_loop(self) -> None:
        """Background sync loop to receive Matrix events."""
        if not self.client:
            return
        try:
            await self.client.sync_forever(timeout=30000)
        except Exception as e:
            print(f"[matrix] Sync error: {e}")
            self.connected = False

    async def _on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle incoming Matrix messages — relay narratives to WebSocket clients."""
        # Skip our own messages
        if self.client and event.sender == self.client.user_id:
            return

        body = event.body
        # Check for RPG message metadata
        content = event.source.get("content", {})
        rpg_meta = content.get("com.bonfires.rpg", {})

        if rpg_meta.get("type") == "narrative":
            # Relay narrative to all connected clients in this room's location
            location = self.room_to_location.get(room.room_id, "unknown")
            await self.ws_hub.broadcast_to_location(location, {
                "type": "narrative",
                "text": body,
                "location": location,
            })

    async def send_action(self, room_id: str, player_id: str, action_text: str) -> None:
        """Send a player action to a Matrix room."""
        if not self.client or not self.connected:
            return
        content = {
            "msgtype": "m.text",
            "body": action_text,
            "com.bonfires.rpg": {
                "type": "player-action",
                "player_id": player_id,
            },
        }
        await self.client.room_send(room_id, "m.room.message", content)

    async def get_or_create_room(self, location_name: str, space_id: str = "") -> str:
        """Get or create a Matrix room for a location. Returns room_id."""
        if location_name in self.location_to_room:
            return self.location_to_room[location_name]

        if not self.client:
            # No Matrix connection — return placeholder
            room_id = f"!local-{location_name}"
            self.location_to_room[location_name] = room_id
            self.room_to_location[room_id] = location_name
            return room_id

        # Create room
        alias = f"loc-{location_name.lower().replace(' ', '-')}"
        try:
            resp = await self.client.room_create(
                name=location_name,
                alias=alias,
                topic=f"Location: {location_name}",
            )
            room_id = resp.room_id
        except Exception:
            # Room might already exist
            room_id = f"!local-{location_name}"

        self.location_to_room[location_name] = room_id
        self.room_to_location[room_id] = location_name
        return room_id
