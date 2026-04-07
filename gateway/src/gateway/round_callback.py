"""Round close callback — sends player actions to Matrix for agent processing."""

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

    When a round closes, send each player action as a readable message from
    the player's Matrix user. NPC agents and the engine agent see these and
    respond directly — no batch metadata needed.
    """

    async def on_round_close(location: str, actions: list[PlayerAction]) -> None:
        if not bridge or not bridge.connected:
            logger.warning("Round closed but bridge disconnected: %s (%d actions)", location, len(actions))
            return

        room_id = await bridge.get_or_create_room(location)

        # Ensure all kicked NPCs are back in the room + reset budgets
        try:
            await bridge.ensure_npcs_in_room(room_id)
        except Exception:
            logger.debug("NPC rejoin failed for %s", location, exc_info=True)

        # Send each player action — engine agent and NPC agents pick these up
        # via the bonfires-ai runtime's @tag-based routing
        for a in actions:
            await bridge.send_action(room_id, a.player_id, a.action)

        logger.info("Round closed at %s: %d actions sent to agents", location, len(actions))

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
            "channel": "events",
        })

    return on_action_received
