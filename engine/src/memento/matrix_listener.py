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
        """Handle incoming messages — single actions or batched round-actions."""
        content = event.source.get("content", {})
        rpg_meta = content.get("com.bonfires.rpg", {})
        msg_type = rpg_meta.get("type", "")

        if msg_type == "round-actions":
            # Batched round from gateway RoundManager
            await self._handle_round(room, rpg_meta)
        elif msg_type == "player-action":
            # Legacy single action (direct send, no round manager)
            await self._handle_single_action(room, rpg_meta, event.body)

    async def _handle_single_action(self, room: MatrixRoom, rpg_meta: dict, body: str) -> None:
        """Process a single player action (legacy path)."""
        player_id = rpg_meta.get("player_id", "unknown")
        logger.info("Single action from %s: %s", player_id, body)

        location_name = room.display_name or "Unknown"
        narrative, state_update = await asyncio.to_thread(
            self._run_turn, location_name, [{"player_id": player_id, "player_name": player_id, "action": body}]
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
                        "player_id": player_id,
                        "state_update": state_update,
                    },
                },
            )

    async def _handle_round(self, room: MatrixRoom, rpg_meta: dict) -> None:
        """Process a batched round of actions from the RoundManager."""
        actions = rpg_meta.get("actions", [])
        location = rpg_meta.get("location", room.display_name or "Unknown")

        player_names = [a.get("player_name", "unknown") for a in actions]
        logger.info("Round at %s: %d actions from %s", location, len(actions), player_names)

        narrative, state_update = await asyncio.to_thread(
            self._run_turn, location, actions
        )

        if self.client and narrative:
            # Broadcast narrative to all players (no specific player_id — it's shared)
            await self.client.room_send(
                room.room_id,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": narrative,
                    "com.bonfires.rpg": {
                        "type": "narrative",
                        "player_id": "",  # shared narrative
                        "state_update": state_update,
                    },
                },
            )

    @staticmethod
    def _run_turn(location_name: str, actions: list[dict]) -> tuple[str, dict]:
        """Run GameTurnFlow for one or more player actions. Returns (narrative, state_update).

        For multi-player rounds, all actions are combined into a single flow
        so the narrative covers everyone's actions coherently.
        """
        from memento.flows.game_turn import GameTurnFlow
        from memento.models.state_update import StateUpdate, EventSummary, CombatEvent, QuestSummary

        if len(actions) == 1:
            # Single player — standard flow
            a = actions[0]
            combined_action = a["action"]
            player_name = a.get("player_name", a["player_id"])
            player_uuid = a["player_id"]
        else:
            # Multi-player — combine into one turn description
            combined_action = "\n".join(
                f"{a.get('player_name', a['player_id'])}: {a['action']}" for a in actions
            )
            player_name = ", ".join(a.get("player_name", a["player_id"]) for a in actions)
            player_uuid = actions[0]["player_id"]

        flow = GameTurnFlow()
        flow.state.player_name = player_name
        flow.state.player_uuid = player_uuid
        flow.state.location_name = location_name
        flow.state.action = combined_action
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

        # Query active quests for first player
        active_quests = None
        raw_quests = GameTurnFlow.query_active_quests(player_uuid)
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
