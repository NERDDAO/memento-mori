"""Matrix bridge — connects to Synapse, manages rooms, relays messages."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp
from nio import AsyncClient, MatrixRoom, RoomMessageText

from gateway.log import get_logger

logger = get_logger(__name__)


class MatrixBridge:
    """Async Matrix client that bridges messages between gateway and game engine.

    Uses the narrator bot token for listening to narrative responses.
    Player actions are sent via Synapse REST API using per-player tokens.
    """

    def __init__(self, homeserver: str, token: str, ws_hub: Any) -> None:
        self.homeserver = homeserver
        self.token = token  # narrator bot token
        self.ws_hub = ws_hub
        self.client: AsyncClient | None = None
        self.connected = False
        self.room_to_location: dict[str, str] = {}
        self.location_to_room: dict[str, str] = {}
        self.player_tokens: dict[str, str] = {}  # player_id -> matrix access_token

    async def connect(self) -> None:
        """Connect to Matrix homeserver as narrator bot."""
        self.client = AsyncClient(self.homeserver)
        self.client.access_token = self.token
        self.client.user_id = "@narrator:localhost"
        try:
            resp = await self.client.whoami()
            if hasattr(resp, "user_id") and resp.user_id:
                self.client.user_id = resp.user_id
            self.client.add_event_callback(self._on_message, RoomMessageText)
            self.connected = True
            asyncio.create_task(self._sync_loop())
            logger.info("Connected as %s", self.client.user_id)

            # Pre-populate known rooms
            await self._discover_rooms()
        except Exception as e:
            logger.error("Connection failed", exc_info=True)
            self.connected = False

    async def _discover_rooms(self) -> None:
        """Discover existing rooms via REST API and populate the location cache."""
        try:
            async with aiohttp.ClientSession() as session:
                # Get joined rooms
                resp = await session.get(
                    f"{self.homeserver}/_matrix/client/v3/joined_rooms",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if resp.status != 200:
                    logger.warning("Room discovery failed: HTTP %d", resp.status)
                    return
                data = await resp.json()
                rooms = data.get("joined_rooms", [])

                for room_id in rooms:
                    # Get room state to find name
                    state_resp = await session.get(
                        f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/state",
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    if state_resp.status != 200:
                        continue
                    events = await state_resp.json()
                    for event in events:
                        if event.get("type") == "m.room.name":
                            name = event.get("content", {}).get("name", "")
                            if name:
                                self.location_to_room[name] = room_id
                                self.room_to_location[room_id] = name
                                logger.info("Cached room: %s -> %s", name, room_id)
        except Exception as e:
            logger.warning("Room discovery failed", exc_info=True)

    async def disconnect(self) -> None:
        if self.client:
            await self.client.close()
        self.connected = False

    async def _sync_loop(self) -> None:
        if not self.client:
            return
        try:
            await self.client.sync_forever(timeout=30000)
        except Exception as e:
            logger.error("Sync error", exc_info=True)
            self.connected = False

    async def _on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle incoming Matrix messages — relay narratives to WebSocket clients."""
        content = event.source.get("content", {})
        rpg_meta = content.get("com.bonfires.rpg", {})

        rpg_type = rpg_meta.get("type", "")

        # Phase messages — forward to WebSocket
        if rpg_type == "phase":
            location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
            if location:
                await self.ws_hub.broadcast_to_location(location, {
                    "type": "phase",
                    "phase": rpg_meta.get("phase", "resolving"),
                    "crew": rpg_meta.get("crew"),
                    "channel": rpg_meta.get("channel", "events"),
                })
            return

        if rpg_type == "narrative":
            location = self.room_to_location.get(room.room_id, "")
            state_update = rpg_meta.get("state_update", {})
            player_id = rpg_meta.get("player_id", "")

            # Helper to send status to the relevant player(s)
            async def _send_status(phase: str) -> None:
                status_msg = {"type": "status", "phase": phase}
                location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
                if location:
                    await self.ws_hub.broadcast_to_location(location, status_msg)
                elif player_id and self.ws_hub.connections.get(player_id):
                    await self.ws_hub.send_to_player(player_id, status_msg)
                else:
                    await self.ws_hub.broadcast_all(status_msg)

            await _send_status("extracting")

            # Ensure schema_version is present in state updates
            if isinstance(state_update, dict) and "schema_version" not in state_update:
                state_update["schema_version"] = 1

            msg = {
                "type": "narrative",
                "text": event.body,
                "location": location or room.display_name or "unknown",
                "state_update": state_update,
                "channel": rpg_meta.get("channel", "narrative"),
            }
            # Batch narratives go to all players at location
            # Single-player narratives go to the specific player
            location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
            if location:
                await self.ws_hub.broadcast_to_location(location, msg)
            elif player_id and self.ws_hub.connections.get(player_id):
                await self.ws_hub.send_to_player(player_id, msg)
            else:
                await self.ws_hub.broadcast_all(msg)

            await _send_status("synced")
            return

        # NPC agent message — forward to players as narrative
        sender = event.sender or ""
        if sender.startswith("@bonfires-") and not rpg_meta:
            location = self.room_to_location.get(room.room_id, "")
            npc_username = sender.split(":")[0].lstrip("@")  # "bonfires-roric"
            npc_name = npc_username.replace("bonfires-", "").replace("_", " ").title()

            msg = {
                "type": "narrative",
                "text": event.body,
                "npc": npc_name,
                "location": location or room.display_name or "unknown",
                "channel": "narrative",
            }
            if location:
                await self.ws_hub.broadcast_to_location(location, msg)
            else:
                await self.ws_hub.broadcast_all(msg)
            logger.info("NPC %s spoke at %s", npc_name, location)

    async def register_player(self, player_name: str, player_id: str) -> str | None:
        """Register a Matrix user for a player. Returns access_token or None."""
        # Use Synapse admin API to register
        username = f"player_{player_id[:8]}"
        password = f"mm_{player_id}"

        async with aiohttp.ClientSession() as session:
            # Register
            try:
                async with session.post(
                    f"{self.homeserver}/_matrix/client/v3/register",
                    json={
                        "username": username,
                        "password": password,
                        "auth": {"type": "m.login.dummy"},
                    },
                ) as resp:
                    if resp.status in (200, 429):
                        data = await resp.json()
                        token = data.get("access_token", "")
                        if token:
                            self.player_tokens[player_id] = token
                            logger.info("Registered player %s", username)
                            return token
            except Exception as e:
                logger.warning("Registration failed for %s", username, exc_info=True)

            # Try login if already registered
            try:
                async with session.post(
                    f"{self.homeserver}/_matrix/client/v3/login",
                    json={
                        "type": "m.login.password",
                        "user": username,
                        "password": password,
                    },
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token = data.get("access_token", "")
                        if token:
                            self.player_tokens[player_id] = token
                            logger.info("Logged in player %s", username)
                            return token
            except Exception as e:
                logger.warning("Login failed for %s", username, exc_info=True)

        return None

    async def send_action(self, room_id: str, player_id: str, action_text: str) -> None:
        """Send a player action to a Matrix room using the player's token."""
        token = self.player_tokens.get(player_id)
        if not token:
            logger.info("No token for player %s, registering...", player_id)
            token = await self.register_player("player", player_id)

        if not token:
            logger.error("Cannot send action — no player token for %s", player_id)
            return

        # Invite player to the room (as narrator), then join as player
        username = f"player_{player_id[:8]}"
        player_user_id = f"@{username}:localhost"

        async with aiohttp.ClientSession() as session:
            # Narrator invites player
            if self.token:
                await session.post(
                    f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/invite",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"user_id": player_user_id},
                )

            # Player joins
            await session.post(
                f"{self.homeserver}/_matrix/client/v3/join/{room_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Send message
            import uuid
            txn_id = str(uuid.uuid4())
            content = {
                "msgtype": "m.text",
                "body": action_text,
                "com.bonfires.rpg": {
                    "type": "player-action",
                    "player_id": player_id,
                },
            }
            resp = await session.put(
                f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                headers={"Authorization": f"Bearer {token}"},
                json=content,
            )
            if resp.status != 200:
                text = await resp.text()
                logger.error("Send failed (HTTP %d): %s", resp.status, text)

    async def get_or_create_room(self, location_name: str, space_id: str = "") -> str:
        """Get or create a Matrix room for a location. Returns room_id."""
        if location_name in self.location_to_room:
            return self.location_to_room[location_name]

        if not self.client:
            room_id = f"!local-{location_name}"
            self.location_to_room[location_name] = room_id
            self.room_to_location[room_id] = location_name
            return room_id

        # Try to resolve existing room alias via REST API
        alias = f"loc-{location_name.lower().replace(' ', '-')}"
        full_alias = f"#{alias}:localhost"
        try:
            async with aiohttp.ClientSession() as session:
                encoded = full_alias.replace("#", "%23")
                resp = await session.get(
                    f"{self.homeserver}/_matrix/client/v3/directory/room/{encoded}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if resp.status == 200:
                    data = await resp.json()
                    room_id = data.get("room_id", "")
                    if room_id:
                        self.location_to_room[location_name] = room_id
                        self.room_to_location[room_id] = location_name
                        logger.info("Resolved room %s -> %s", alias, room_id)
                        return room_id
        except Exception as e:
            logger.warning("Alias resolve failed for %s", alias, exc_info=True)

        # Create new room via nio
        try:
            from nio import RoomPreset
            resp = await self.client.room_create(
                name=location_name,
                alias=alias,
                topic=f"Location: {location_name}",
                preset=RoomPreset.public_chat,
            )
            if hasattr(resp, "room_id") and resp.room_id:
                room_id = resp.room_id
                logger.info("Created room %s -> %s", alias, room_id)
            else:
                logger.warning("Room creation returned unexpected response: %s", resp)
                room_id = f"!local-{location_name}"
        except Exception as e:
            logger.error("Room creation failed for %s", location_name, exc_info=True)
            room_id = f"!local-{location_name}"

        self.location_to_room[location_name] = room_id
        self.room_to_location[room_id] = location_name
        return room_id
