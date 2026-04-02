"""Round close callback — sends batched actions to Matrix for engine processing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gateway.log import get_logger

if TYPE_CHECKING:
    from gateway.matrix_bridge import MatrixBridge
    from gateway.ws import WebSocketHub
    from memento.round_manager import PlayerAction

logger = get_logger(__name__)


def make_round_callback(bridge: MatrixBridge, ws_hub: WebSocketHub):
    """Create an async callback for RoundManager.on_round_close.

    When a round closes, sends a batch message to the Matrix room
    for that location so the engine can process all actions together.
    """

    async def on_round_close(location: str, actions: list[PlayerAction]) -> None:
        if not bridge or not bridge.connected:
            logger.warning("Round closed but bridge disconnected: %s (%d actions)", location, len(actions))
            return

        room_id = await bridge.get_or_create_room(location)

        # Send thinking indicator to all players at this location
        await ws_hub.broadcast_to_location(location, {
            "type": "thinking",
            "action": f"Processing round ({len(actions)} actions)",
        })

        # Build batch message for engine
        action_list = [
            {
                "player_id": a.player_id,
                "player_name": a.player_name,
                "action": a.action,
            }
            for a in actions
        ]

        content = {
            "msgtype": "m.text",
            "body": f"Round closed at {location} ({len(actions)} actions)",
            "com.bonfires.rpg": {
                "type": "player-action-batch",
                "batch": True,
                "location": location,
                "actions": action_list,
            },
        }

        # Send as narrator bot
        if bridge.client:
            await bridge.client.room_send(room_id, "m.room.message", content)
            logger.info("Batch sent to %s: %d actions", location, len(actions))

    return on_round_close
