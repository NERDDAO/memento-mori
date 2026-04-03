"""Round close callback — sends player actions to Matrix, then triggers engine."""

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

    When a round closes:
    1. Send each player action as a readable message from the player's Matrix user
       (so NPC agents can see and respond to them)
    2. Send a batch metadata message for the engine to process
    """

    async def on_round_close(location: str, actions: list[PlayerAction]) -> None:
        if not bridge or not bridge.connected:
            logger.warning("Round closed but bridge disconnected: %s (%d actions)", location, len(actions))
            return

        room_id = await bridge.get_or_create_room(location)

        # Step 1: Send each player action as a readable message from the player
        # NPC agents see these and can respond
        for a in actions:
            await bridge.send_action(room_id, a.player_id, a.action)

        # Step 2: Send batch metadata for the engine listener
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
            "body": f"[engine:batch] {len(actions)} actions at {location}",
            "com.bonfires.rpg": {
                "type": "player-action-batch",
                "batch": True,
                "location": location,
                "actions": action_list,
                "channel": "events",
            },
        }

        if bridge.client:
            await bridge.client.room_send(room_id, "m.room.message", content)
            logger.info("Batch sent to %s: %d actions", location, len(actions))

    return on_round_close


def make_action_callback(ws_hub: WebSocketHub):
    """Create an async callback for RoundManager.on_action.

    Emits 'collecting' phase to all players at the location.
    """

    async def on_action_received(location: str, action_count: int, deadline: float) -> None:
        await ws_hub.broadcast_to_location(location, {
            "type": "phase",
            "phase": "collecting",
            "action_count": action_count,
            "deadline": int(deadline * 1000),  # unix ms for client
        })

    return on_action_received
