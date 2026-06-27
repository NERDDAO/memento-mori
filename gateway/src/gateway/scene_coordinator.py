"""Routes a player message to an active persona scene's RoomDriver and broadcasts
the NPC reply over the existing WS tool_event path. Keeps submit_action thin.

P1 scope: assumes a scene is ALREADY registered for the location (auto-activation
is P2). handle_player_message returns False (no-op) whenever a persona scene is
not available, so the caller falls through to the existing RoundManager path.

P2 extension: ensure_scene auto-activates when NPCs are present and an
activation_service is provided. P1-style direct construction (no activation_service)
preserves the original behavior.
"""

from __future__ import annotations

from typing import Any

from gateway.location_resolver import LocationResolver
from gateway.log import get_logger
from gateway.scene_activation import (
    SceneActivationError,
    SceneActivationService,
    SceneAlreadyOpen,
    SceneNotOpen,
)

logger = get_logger(__name__)

# Construct id -> player-facing display name for the cxn_fired catch beat.
# The kernel returns predicate="" for the minimal LOOK, so we key on the id.
CXN_DISPLAY_NAMES: dict[str, str] = {"mm.look.v1": "LOOK"}


class SceneCoordinator:
    def __init__(
        self,
        *,
        scene_registry: Any,
        cxn_repo: Any,
        ws_hub: Any,
        activation_service: Any = None,
        location_resolver: Any = None,
    ) -> None:
        self._registry = scene_registry
        self._repo = cxn_repo
        self._ws_hub = ws_hub
        self._activation = activation_service
        self._resolver = location_resolver or LocationResolver(cxn_repo, {})

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneCoordinator":
        registry = getattr(state, "scene_registry", None)
        repo = getattr(state, "cxn_repo", None)
        ws_hub = getattr(state, "ws_hub", None)
        cache = getattr(state, "scene_locations", None)
        activation = None
        if (
            registry is not None
            and repo is not None
            and getattr(state, "agent_runtime_client", None) is not None
        ):
            activation = SceneActivationService.from_app_state(state)
        return cls(
            scene_registry=registry,
            cxn_repo=repo,
            ws_hub=ws_hub,
            activation_service=activation,
            location_resolver=LocationResolver(repo, cache),
        )

    async def ensure_scene(self, location_uuid: str) -> Any | None:
        if self._registry is None:
            return None
        driver = self._registry.get(location_uuid)
        if driver is not None:
            return driver  # already active (idempotent)
        if self._activation is None:
            return None  # no auto-activation capability (P1-style direct construction)
        if not await self._has_persona_npcs(location_uuid):
            return None  # nothing to talk to here -> caller falls through
        try:
            await self._activation.activate(location_uuid)
        except SceneAlreadyOpen:
            pass  # concurrent activation won the race
        except SceneActivationError as exc:  # incl. AgentRuntimeUnavailable
            logger.warning("scene_coordinator.activate_failed: %s", exc)
            return None
        return self._registry.get(location_uuid)

    async def maybe_close(self, departed_location_name: str) -> None:
        if (
            not departed_location_name
            or self._ws_hub is None
            or self._activation is None
        ):
            return
        location_uuid = self._resolver.uuid_for_name(departed_location_name)
        if (
            not location_uuid
            or self._registry is None
            or location_uuid not in self._registry
        ):
            return
        if self._ws_hub.players_at_location(departed_location_name) > 0:
            return  # someone is still here
        try:
            await self._activation.close(location_uuid)
        except SceneNotOpen:
            pass
        except SceneActivationError as exc:  # incl. AgentRuntimeUnavailable
            logger.warning("scene_coordinator.close_failed: %s", exc)
            return
        self._resolver.forget_name(departed_location_name)

    async def _broadcast_npcs_joined(
        self, location_uuid: str, location_name: str
    ) -> None:
        if self._ws_hub is None or self._repo is None:
            return
        try:
            entities = await self._repo.get_entities_at_location(location_uuid)
        except Exception:  # surfacing is best-effort, never breaks the turn
            return
        for entity in entities:
            if entity.get("kind") != "character":
                continue
            await self._ws_hub.broadcast_to_location(
                location_name,
                {
                    "type": "npc_joined",
                    "npc_name": entity.get("name", ""),
                    "npc_id": entity.get("uuid", ""),
                },
            )

    async def _has_persona_npcs(self, location_uuid: str) -> bool:
        if self._repo is None:
            return False
        try:
            entities = await self._repo.get_entities_at_location(location_uuid)
        except Exception:  # repo failure must not break the action path
            return False
        return any(e.get("kind") == "character" for e in entities)

    async def handle_player_message(
        self, player_id: str, location_name: str, message: str
    ) -> bool:
        if self._registry is None or self._ws_hub is None:
            return False
        location_uuid = await self._resolver.uuid_for(player_id, location_name)
        if not location_uuid:
            return False
        self._resolver.record(location_name, location_uuid)  # for maybe_close (Task 4)
        was_registered = location_uuid in self._registry
        driver = await self.ensure_scene(location_uuid)
        if driver is None:
            return False
        if not was_registered:  # scene just opened -> surface its NPCs once
            await self._broadcast_npcs_joined(location_uuid, location_name)
        try:
            turn = await driver.drive_turn(location_uuid, message)
        except Exception as exc:  # persona failure must NOT break the action path
            logger.warning("scene_coordinator.drive_turn_failed: %s", exc)
            return True  # claimed by the persona path; degrade to silence, not 500

        await self._broadcast_cxn_fired(turn, location_name)

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

    async def _broadcast_cxn_fired(
        self, turn: dict[str, Any], location_name: str
    ) -> None:
        """Emit one cxn_fired WS event per fired construction (the catch beat).
        Best-effort: never breaks the turn; no-op when nothing fired."""
        if self._ws_hub is None:
            return
        fired = turn.get("fired_cxns") or []
        actor_id = turn.get("self_id")
        for construct_id in fired:
            display = CXN_DISPLAY_NAMES.get(construct_id, construct_id)
            logger.info(
                "cxn_fired: %s (%s) actor=%s loc=%s",
                display,
                construct_id,
                actor_id,
                location_name,
            )
            await self._ws_hub.broadcast_to_location(
                location_name,
                {
                    "type": "cxn_fired",
                    "cxn": display,
                    "construct_id": construct_id,
                    "actor_id": actor_id,
                    "location": location_name,
                },
            )

    async def _npc_name(self, self_id: str | None) -> str:
        if not self_id or self._repo is None:
            return ""
        try:
            entity = await self._repo.get_entity(self_id)
        except Exception:
            return ""
        return entity.get("name", "") if entity else ""
