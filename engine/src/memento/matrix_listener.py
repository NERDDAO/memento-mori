"""Matrix listener — watches location rooms, dispatches to GameTurnFlow."""

from __future__ import annotations

import asyncio
import os

from nio import AsyncClient, MatrixRoom, RoomMessageText


class EngineMatrixListener:
    """Listens for player actions on Matrix, runs GameTurnFlow, posts narrative back."""

    def __init__(self) -> None:
        self.homeserver = os.getenv("MATRIX_HOMESERVER", "http://localhost:8008")
        self.token = os.getenv("MATRIX_BOT_TOKEN", "")
        self.client: AsyncClient | None = None

    async def start(self) -> None:
        """Connect to Matrix and start listening."""
        self.client = AsyncClient(self.homeserver)
        self.client.access_token = self.token

        resp = await self.client.whoami()
        if hasattr(resp, "user_id"):
            self.client.user_id = resp.user_id
            print(f"[engine] Connected as {resp.user_id}")

        self.client.add_event_callback(self._on_action, RoomMessageText)
        print("[engine] Listening for player actions...")
        await self.client.sync_forever(timeout=30000)

    async def _on_action(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle a player action message."""
        # Skip own messages
        if self.client and event.sender == self.client.user_id:
            return

        content = event.source.get("content", {})
        rpg_meta = content.get("com.bonfires.rpg", {})

        if rpg_meta.get("type") != "player-action":
            return

        player_id = rpg_meta.get("player_id", "unknown")
        action_text = event.body
        print(f"[engine] Action from {player_id}: {action_text}")

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

        flow = GameTurnFlow()
        flow.state.player_name = player_id
        flow.state.location_name = location_name
        flow.state.action = action
        flow.kickoff()
        state_update = {
            "location": location_name,
            "events": str(flow.state.events)[:500] if hasattr(flow.state, "events") else "",
        }
        return flow.state.narrative, state_update


async def main():
    listener = EngineMatrixListener()
    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
