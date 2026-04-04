"""Matrix listener — watches location rooms, dispatches to RoundController."""

from __future__ import annotations

import asyncio
import os
import threading

from nio import AsyncClient, InviteMemberEvent, MatrixRoom, RoomMessageText

from memento.log import get_logger

logger = get_logger(__name__)


# Global lock — serializes all RoundController execution across threads.
# Prevents concurrent KG mutations and world-time races.
_turn_lock = threading.Lock()


class EngineMatrixListener:
    """Listens for player actions on Matrix, runs RoundController, posts narrative back."""

    def __init__(self) -> None:
        self.homeserver = os.getenv("MATRIX_HOMESERVER", "http://localhost:8008")
        self.token = os.getenv("MATRIX_BOT_TOKEN", "")
        self.client: AsyncClient | None = None

    async def start(self) -> None:
        """Connect to Matrix and start listening."""
        if not self.token:
            logger.error("MATRIX_BOT_TOKEN not set")
            return

        self.client = AsyncClient(self.homeserver)
        self.client.access_token = self.token
        # nio requires user_id to be set before most API calls
        self.client.user_id = "@narrator:localhost"

        resp = await self.client.whoami()
        if hasattr(resp, "user_id") and resp.user_id:
            self.client.user_id = resp.user_id
            logger.info("Connected as %s", resp.user_id)
        else:
            logger.warning("whoami failed: %s", resp)

        # Join all existing rooms
        try:
            joined = await self.client.joined_rooms()
            if hasattr(joined, "rooms"):
                logger.info("Already in %d rooms", len(joined.rooms))
        except Exception as e:
            logger.warning("Could not list rooms: %s", e)

        # Reconcile NPC agents for known locations
        await asyncio.to_thread(self._reconcile_npcs)

        # Auto-join on invite
        self.client.add_event_callback(self._on_invite, InviteMemberEvent)  # type: ignore[arg-type]
        self.client.add_event_callback(self._on_action, RoomMessageText)  # type: ignore[arg-type]
        logger.info("Listening for player actions...")
        await self.client.sync_forever(timeout=30000)

    @staticmethod
    def _reconcile_npcs() -> None:
        """Spawn Bonfires agents for any NPCs that don't have them yet."""
        try:
            from memento.agent_controller import get_agent_controller
            controller = get_agent_controller()

            # Get known locations from the KG
            from memento.bonfires_client import get_client
            client = get_client()
            result = client.kg.search("Location", num_results=20)
            locations = [
                e.get("name", "")
                for e in result.get("entities", result.get("nodes", []))
                if "Location" in e.get("labels", []) and e.get("name")
            ]

            for loc in locations:
                controller.reconcile_location(loc)

            logger.info("NPC reconciliation complete: %d agents active", len(controller.list_alive()))
        except Exception:
            logger.warning("NPC reconciliation failed (non-fatal)", exc_info=True)

    async def _on_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Auto-join rooms when invited."""
        if self.client and event.state_key == self.client.user_id:
            await self.client.join(room.room_id)
            logger.info("Joined room: %s", room.display_name or room.room_id)
            # Reconcile NPCs in the newly joined room
            location = room.display_name or ""
            if location:
                await asyncio.to_thread(self._reconcile_single_location, location)

    @staticmethod
    def _reconcile_single_location(location_name: str) -> None:
        """Reconcile NPCs at a single location (non-fatal)."""
        try:
            from memento.agent_controller import get_agent_controller
            controller = get_agent_controller()
            spawned = controller.reconcile_location(location_name)
            if spawned:
                logger.info("Reconciled %d NPC agents at %s", len(spawned), location_name)
        except Exception:
            logger.debug("Reconcile failed for %s", location_name, exc_info=True)

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

            # Reconcile NPCs at this location (lazy — only spawns missing ones)
            await asyncio.to_thread(self._reconcile_single_location, location_name)

            narrative, state_update = await asyncio.to_thread(
                self._run_batch_turn, location_name, actions,
                self.client, room.room_id, asyncio.get_event_loop()
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
            # Individual player messages are for NPC agents to see — not for engine processing.
            # The engine only processes batches (player-action-batch).
            logger.debug("Ignoring individual player-action (engine uses batches): %s", event.body[:80])

    @staticmethod
    def _run_turn(player_id: str, location_name: str, action: str,
                  matrix_client=None, room_id: str = "",
                  loop=None) -> tuple[str, dict]:
        """Run RoundController synchronously (called from thread). Returns (narrative, state_update)."""
        with _turn_lock:
            return EngineMatrixListener._run_turn_inner(
                player_id, location_name, action, matrix_client, room_id, loop
            )

    @staticmethod
    def _run_turn_inner(player_id: str, location_name: str, action: str,
                        matrix_client=None, room_id: str = "",
                        loop=None) -> tuple[str, dict]:
        from memento.round_controller import RoundController

        controller = RoundController(
            location=location_name,
            actions=[{"player_name": player_id, "action": action}],
            loop=loop,
            room_id=room_id,
            matrix_client=matrix_client,
        )
        return controller.run()

    @staticmethod
    def _run_batch_turn(location_name: str, actions: list[dict],
                        matrix_client=None, room_id: str = "",
                        loop=None) -> tuple[str, dict]:
        """Run RoundController with multiple actions. Returns (narrative, state_update)."""
        with _turn_lock:
            return EngineMatrixListener._run_batch_turn_inner(
                location_name, actions, matrix_client, room_id, loop
            )

    @staticmethod
    def _run_batch_turn_inner(location_name: str, actions: list[dict],
                              matrix_client=None, room_id: str = "",
                              loop=None) -> tuple[str, dict]:
        from memento.round_controller import RoundController

        controller = RoundController(
            location=location_name,
            actions=actions,
            loop=loop,
            room_id=room_id,
            matrix_client=matrix_client,
        )
        return controller.run()


async def main():
    listener = EngineMatrixListener()
    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
