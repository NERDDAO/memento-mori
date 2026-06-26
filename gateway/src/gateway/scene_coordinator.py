"""Routes a player message to an active persona scene's RoomDriver and broadcasts
the NPC reply over the existing WS tool_event path. Keeps submit_action thin.

P1 scope: assumes a scene is ALREADY registered for the location (auto-activation
is P2). handle_player_message returns False (no-op) whenever a persona scene is
not available, so the caller falls through to the existing RoundManager path.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)


class SceneCoordinator:
    def __init__(self, *, scene_registry: Any, cxn_repo: Any, ws_hub: Any) -> None:
        self._registry = scene_registry
        self._repo = cxn_repo
        self._ws_hub = ws_hub

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneCoordinator":
        # Tolerant: scene infra may be absent (e.g. lifespan not run) -> no-op path.
        return cls(
            scene_registry=getattr(state, "scene_registry", None),
            cxn_repo=getattr(state, "cxn_repo", None),
            ws_hub=getattr(state, "ws_hub", None),
        )

    async def handle_player_message(
        self, player_id: str, location_name: str, message: str
    ) -> bool:
        if self._registry is None or self._ws_hub is None:
            return False
        from gateway.routes.codex import _get_location_uuid

        location_uuid = await _get_location_uuid(player_id)
        if not location_uuid:
            return False
        driver = self._registry.get(location_uuid)
        if driver is None:
            return False

        try:
            turn = await driver.drive_turn(location_uuid, message)
        except Exception as exc:  # persona failure must NOT break the action path
            logger.warning("scene_coordinator.drive_turn_failed: %s", exc)
            return True  # claimed by the persona path; degrade to silence, not 500

        if turn.get("should_respond", True):
            npc_name = await self._npc_name(turn.get("self_id"))
            msg = {
                "type": "tool_event",
                "tool": "mm_npc_response",
                "npc": npc_name,
                "summary": turn.get("response_text", ""),
                "data": {},
                "location": location_name,
                "channel": "narrative",
            }
            await self._ws_hub.broadcast_to_location(location_name, msg)
        return True

    async def _npc_name(self, self_id: str | None) -> str:
        if not self_id or self._repo is None:
            return ""
        try:
            entity = await self._repo.get_entity(self_id)
        except Exception:
            return ""
        return entity.get("name", "") if entity else ""
