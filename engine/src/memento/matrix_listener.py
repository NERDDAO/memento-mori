"""Matrix listener — watches location rooms, dispatches to GameTurnFlow."""

from __future__ import annotations

import asyncio
import os

from nio import AsyncClient, InviteMemberEvent, MatrixRoom, RoomMessageText

from memento.log import get_logger

logger = get_logger(__name__)


class EngineMatrixListener:
    """Listens for player actions on Matrix, runs GameTurnFlow, posts narrative back."""

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

        # Auto-join on invite
        self.client.add_event_callback(self._on_invite, InviteMemberEvent)
        self.client.add_event_callback(self._on_action, RoomMessageText)
        logger.info("Listening for player actions...")
        await self.client.sync_forever(timeout=30000)

    async def _on_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Auto-join rooms when invited."""
        if self.client and event.state_key == self.client.user_id:
            await self.client.join(room.room_id)
            logger.info("Joined room: %s", room.display_name or room.room_id)

    async def _on_action(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle a player action message."""
        content = event.source.get("content", {})
        rpg_meta = content.get("com.bonfires.rpg", {})

        if rpg_meta.get("type") != "player-action":
            return

        player_id = rpg_meta.get("player_id", "unknown")
        action_text = event.body
        logger.info("Action from %s: %s", player_id, action_text)

        # Run GameTurnFlow in a thread (sync CrewAI in async context)
        location_name = room.display_name or "Unknown"
        narrative, state_update = await asyncio.to_thread(
            self._run_turn, player_id, location_name, action_text
        )

        # Post narrative back to Matrix room
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

    @staticmethod
    def _run_turn(player_id: str, location_name: str, action: str) -> tuple[str, dict]:
        """Run GameTurnFlow synchronously (called from thread). Returns (narrative, state_update)."""
        from memento.flows.game_turn import GameTurnFlow
        from memento.models.state_update import StateUpdate, EventSummary, CombatEvent, QuestSummary

        flow = GameTurnFlow()
        flow.state.player_name = player_id
        flow.state.location_name = location_name
        flow.state.action = action
        flow.kickoff()

        # Build structured event summary from flow state
        events_summary = None
        flow_events = getattr(flow.state, "events", {})
        if flow_events and isinstance(flow_events, dict):
            categories = flow_events.get("categories", [])
            combat = None
            if "combat" in categories and "combat_result" in flow_events:
                combat = CombatEvent(
                    action_type=flow_events.get("action_type", "attack"),
                    target_name=flow_events.get("combat_target", ""),
                    target_dead="dead" in str(flow_events.get("combat_consequences", "")).lower(),
                )
            events_summary = EventSummary(
                categories=categories,
                combat=combat,
            )

        # Query active quests for this player
        active_quests = None
        raw_quests = GameTurnFlow.query_active_quests(player_id)
        if raw_quests:
            active_quests = [
                QuestSummary(**q) for q in raw_quests
            ]

        state_update = StateUpdate(
            location=location_name,
            world_time=flow.state.world_time if isinstance(flow.state.world_time, dict) else None,
            events=events_summary,
            active_quests=active_quests,
            subsystem_warnings=getattr(flow.state, "subsystem_warnings", []),
        )
        return flow.state.narrative, state_update.model_dump(exclude_none=True)


async def main():
    listener = EngineMatrixListener()
    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
