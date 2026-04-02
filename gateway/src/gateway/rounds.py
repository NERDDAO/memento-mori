"""Gateway round management — wires RoundManager to WebSocket + Matrix + engine."""

from __future__ import annotations

import asyncio
from typing import Any

from gateway.log import get_logger
from gateway.ws import WebSocketHub

logger = get_logger(__name__)


class GatewayRoundManager:
    """Manages action batching at the gateway layer.

    Owns a RoundManager instance and wires it to:
    - WebSocket hub: broadcasts pending actions and resolving status
    - Matrix bridge: sends batched actions to engine for resolution
    """

    def __init__(self, ws_hub: WebSocketHub, window_seconds: float = 5.0) -> None:
        from memento.round_manager import RoundManager
        self.ws_hub = ws_hub
        self.rm = RoundManager(window_seconds=window_seconds)
        self.bridge: Any = None

        # Wire callbacks
        self.rm.on_action(self._on_new_action)
        self.rm.on_round_close(self._on_round_close)

    def set_bridge(self, bridge: Any) -> None:
        """Set the Matrix bridge for sending resolved rounds to the engine."""
        self.bridge = bridge

    async def submit_action(
        self, player_id: str, player_name: str, location: str, action: str
    ) -> bool:
        """Submit a player action. Returns True if accepted, False if duplicate."""
        # Track player location
        self.ws_hub.set_location(player_id, location)
        accepted = await self.rm.submit_action(player_id, player_name, location, action)

        if accepted:
            # Send "thinking" to the acting player
            await self.ws_hub.send_to_player(player_id, {
                "type": "thinking",
                "action": action,
            })
        else:
            # Duplicate — notify player
            await self.ws_hub.send_to_player(player_id, {
                "type": "system",
                "text": "You've already acted this round. Wait for resolution.",
            })

        return accepted

    async def _on_new_action(
        self,
        location: str,
        new_action: Any,
        all_actions: list,
    ) -> None:
        """Broadcast pending actions to all players at the location (group chat feel)."""
        # Send the new action to everyone at the location (except the actor)
        msg = {
            "type": "pending_action",
            "player_name": new_action.player_name,
            "player_id": new_action.player_id,
            "action": new_action.action,
            "actions_in_round": len(all_actions),
        }
        for pid, loc in list(self.ws_hub.player_locations.items()):
            if loc == location and pid != new_action.player_id:
                await self.ws_hub.send_to_player(pid, msg)

    async def _on_round_close(self, location: str, actions: list) -> None:
        """Round closed — send all actions to engine for resolution."""
        if not actions:
            return

        # Notify all players at location that resolution is starting
        await self.ws_hub.broadcast_to_location(location, {
            "type": "status",
            "phase": "resolving",
        })

        # Build multi-action payload for engine
        action_list = [
            {
                "player_id": a.player_id,
                "player_name": a.player_name,
                "action": a.action,
            }
            for a in actions
        ]

        if self.bridge and self.bridge.connected:
            # Send batched actions to Matrix room for engine processing
            room_id = await self.bridge.get_or_create_room(location)
            import json
            import uuid
            txn_id = str(uuid.uuid4())
            content = {
                "msgtype": "m.text",
                "body": " | ".join(f"{a['player_name']}: {a['action']}" for a in action_list),
                "com.bonfires.rpg": {
                    "type": "round-actions",
                    "location": location,
                    "actions": action_list,
                },
            }
            # Send via narrator bot token (bridge owns it)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                resp = await session.put(
                    f"{self.bridge.homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                    headers={"Authorization": f"Bearer {self.bridge.token}"},
                    json=content,
                )
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("Failed to send round to Matrix (HTTP %d): %s", resp.status, text)
        else:
            # No Matrix bridge — process locally via engine
            logger.info("No bridge, processing round locally for %s", location)
            try:
                narrative, state_updates = await asyncio.to_thread(
                    self._run_round_locally, location, action_list
                )
                # Broadcast narrative to all players at location
                await self.ws_hub.broadcast_to_location(location, {
                    "type": "narrative",
                    "text": narrative,
                    "location": location,
                    "state_update": state_updates,
                })
            except Exception:
                logger.error("Local round processing failed", exc_info=True)
                await self.ws_hub.broadcast_to_location(location, {
                    "type": "status",
                    "phase": "error",
                })

    @staticmethod
    def _run_round_locally(location: str, actions: list[dict]) -> tuple[str, dict]:
        """Process a round of actions locally (no Matrix). Returns (narrative, state_update)."""
        from memento.flows.game_turn import GameTurnFlow
        from memento.models.state_update import StateUpdate, EventSummary

        # Build combined action description for the flow
        if len(actions) == 1:
            # Single player — standard flow
            a = actions[0]
            flow = GameTurnFlow()
            flow.state.player_name = a["player_name"]
            flow.state.player_uuid = a["player_id"]
            flow.state.location_name = location
            flow.state.action = a["action"]
            flow.kickoff()

            state_update = StateUpdate(
                location=location,
                world_time=flow.state.world_time if isinstance(flow.state.world_time, dict) else None,
                subsystem_warnings=getattr(flow.state, "subsystem_warnings", []),
            )
            return flow.state.narrative, state_update.model_dump(exclude_none=True)
        else:
            # Multi-player — combine actions into one turn
            combined_action = "\n".join(
                f"{a['player_name']}: {a['action']}" for a in actions
            )
            player_names = ", ".join(a["player_name"] for a in actions)

            flow = GameTurnFlow()
            flow.state.player_name = player_names
            flow.state.player_uuid = actions[0]["player_id"]
            flow.state.location_name = location
            flow.state.action = combined_action
            flow.kickoff()

            state_update = StateUpdate(
                location=location,
                world_time=flow.state.world_time if isinstance(flow.state.world_time, dict) else None,
                subsystem_warnings=getattr(flow.state, "subsystem_warnings", []),
            )
            return flow.state.narrative, state_update.model_dump(exclude_none=True)
