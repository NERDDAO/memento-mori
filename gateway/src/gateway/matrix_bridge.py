"""Matrix bridge — connects to Synapse, manages rooms, relays messages."""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any

import aiohttp
from nio import AsyncClient, MatrixRoom, RoomMessageText

from gateway.log import get_logger

logger = get_logger(__name__)

# Per-NPC message counter per room. Kick after N messages.
_npc_msg_count: dict[tuple[str, str], int] = defaultdict(int)
_NPC_MSG_BUDGET = 2
# Dedup: track last message text per NPC to skip duplicate final messages
_npc_last_text: dict[tuple[str, str], str] = {}


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

        # Scene / entity art — forward to WebSocket clients
        if rpg_type in ("scene_art", "entity_art"):
            location = rpg_meta.get("location", self.room_to_location.get(room.room_id, ""))
            msg = {
                "type": rpg_type,
                "lines": rpg_meta.get("lines", []),
                "width": rpg_meta.get("width", 0),
                "height": rpg_meta.get("height", 0),
                "location": location,
                "channel": "narrative",
            }
            if rpg_type == "entity_art":
                msg["entity_id"] = rpg_meta.get("entity_id", "")
                msg["entity_name"] = rpg_meta.get("entity_name", "")
            if location:
                await self.ws_hub.broadcast_to_location(location, msg)
            return

        if rpg_type == "narrative":
            logger.info("Narrator message at %s (sender=%s)", room.display_name, event.sender)
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

        # Debug: log all unhandled messages to trace the leak
        sender = event.sender or ""
        if not rpg_type and not sender.startswith("@bonfires-"):
            logger.debug("Unhandled msg from %s: rpg_meta=%s body=%.80s", sender, rpg_meta, event.body)

        # NPC agent message — forward to players as narrative
        if sender.startswith("@bonfires-") and not rpg_meta:
            location = self.room_to_location.get(room.room_id, "")
            npc_username = sender.split(":")[0].lstrip("@")  # "bonfires-roric"
            npc_name = npc_username.replace("bonfires-", "").replace("_", " ").title()

            # Detect if this is an edit (m.replace) — used for status/thinking updates
            relates_to = content.get("m.relates_to", {})
            is_replace = relates_to.get("rel_type") == "m.replace"
            new_content = content.get("m.new_content", {})
            text = new_content.get("body", event.body) if is_replace else event.body

            # Check if this is a status message — marked by the agent runtime
            is_status = content.get("com.bonfires.status", False)

            # Dedup: skip if this is the same text we just forwarded (agent sends
            # final text as both an edit and a new message — deduplicate)
            key = (room.room_id, sender)
            if not is_status and text and text == _npc_last_text.get(key):
                return
            if not is_status:
                _npc_last_text[key] = text

            # Budget check — only count final messages (not edits/status).
            is_final = not is_status and not is_replace
            if is_final:
                if _npc_msg_count[key] >= _NPC_MSG_BUDGET:
                    logger.info("NPC %s over budget at %s — dropping", npc_name, location)
                    return
                _npc_msg_count[key] += 1
                if _npc_msg_count[key] >= _NPC_MSG_BUDGET:
                    await self._kick_npc_after_response(room.room_id, sender)

            msg = {
                "type": "npc_status" if is_status else "narrative",
                "text": text,
                "npc": npc_name,
                "npc_username": npc_username,
                "location": location or room.display_name or "unknown",
                "channel": "narrative",
            }
            if is_replace:
                msg["replaces"] = relates_to.get("event_id", "")

            if location:
                await self.ws_hub.broadcast_to_location(location, msg)
            else:
                await self.ws_hub.broadcast_all(msg)

            if not is_status:
                logger.info("NPC %s spoke at %s", npc_name, location)
                # Track response for event-driven NPC phase
                try:
                    from memento.round_controller import record_npc_responded
                    record_npc_responded(location or room.room_id, npc_username)
                except ImportError:
                    pass

    async def _kick_npc_after_response(self, room_id: str, user_id: str) -> None:
        """Kick an NPC bot from a room after it responds, preventing bot-to-bot loops.

        Uses the narrator token (room admin) to kick. The NPC will be
        re-invited before the next round via reinvite_npcs().
        """
        location = self.room_to_location.get(room_id, "")
        npc_username = user_id.split(":")[0].lstrip("@")
        npc_name = npc_username.replace("bonfires-", "").replace("_", " ").title()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/kick",
                    params={"access_token": self.token},
                    json={"user_id": user_id, "reason": "Round complete — will rejoin next round"},
                ) as resp:
                    if resp.status == 200:
                        logger.info("Kicked %s from %s after response", user_id, room_id)
                        # Notify clients so Present panel updates
                        if location:
                            await self.ws_hub.broadcast_to_location(location, {
                                "type": "npc_left",
                                "npc_name": npc_name,
                                "npc_username": npc_username,
                            })
                    else:
                        body = await resp.text()
                        logger.debug("Kick %s failed (%d): %s", user_id, resp.status, body[:100])
        except Exception:
            logger.debug("Kick request failed for %s", user_id, exc_info=True)

    async def ensure_npcs_in_room(self, room_id: str) -> None:
        """Ensure all NPC bots that were kicked are back in the room.

        Scans room membership for bonfires-* users in 'leave' or 'invite' state
        and rejoins them. Also resets message budgets.
        """
        as_token = os.getenv("MATRIX_AS_TOKEN", "")
        if not as_token:
            logger.info("ensure_npcs_in_room: no AS token")
            return

        location = self.room_to_location.get(room_id, "")

        # Get current room members to find kicked NPCs
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/members",
                    params={"access_token": self.token},
                ) as resp:
                    if resp.status != 200:
                        logger.info("ensure_npcs_in_room: members fetch failed %d", resp.status)
                        return
                    data = await resp.json()

                npc_members = [
                    m for m in data.get("chunk", [])
                    if m.get("state_key", "").startswith("@bonfires-")
                    and not m.get("state_key", "").startswith("@bonfires-bot")
                ]
                for m in npc_members:
                    logger.info("  NPC %s: %s", m["state_key"], m.get("content", {}).get("membership", "?"))

                for member in npc_members:
                    user_id = member["state_key"]
                    membership = member.get("content", {}).get("membership", "")

                    # Reset budget and dedup cache
                    _npc_msg_count.pop((room_id, user_id), None)
                    _npc_last_text.pop((room_id, user_id), None)

                    if membership in ("leave", "invite", "ban"):
                        npc_username = user_id.split(":")[0].lstrip("@")
                        npc_name = npc_username.replace("bonfires-", "").replace("_", " ").title()

                        # Invite + join
                        await session.post(
                            f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/invite",
                            params={"access_token": self.token},
                            json={"user_id": user_id},
                        )
                        async with session.post(
                            f"{self.homeserver}/_matrix/client/v3/join/{room_id}",
                            params={"access_token": as_token, "user_id": user_id},
                            json={},
                        ) as join_resp:
                            if join_resp.status == 200:
                                logger.info("Rejoined %s to %s", user_id, room_id)
                                if location:
                                    await self.ws_hub.broadcast_to_location(location, {
                                        "type": "npc_joined",
                                        "npc_name": npc_name,
                                        "npc_username": npc_username,
                                        "npc_id": "",
                                    })
        except Exception:
            logger.debug("ensure_npcs_in_room failed for %s", room_id, exc_info=True)

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
