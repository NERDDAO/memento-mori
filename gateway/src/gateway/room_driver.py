"""RoomDriver — mmori-side orchestrator for GM-room sessions.

Maps a Matrix room → location UUID, builds the NPC roster from the world
(get_entities_at_location → character NPCs → self specs with
embodiment_agent_id = entity UUID), runs trivial who-acts (addressed NPC
name → UUID via npc_registry, else the single NPC at the location), and
calls the agent-runtime inbound scene route (open / turn / close).

Config
------
AGENT_RUNTIME_BASE_URL       — base URL of the agent-runtime service
AGENT_RUNTIME_INTERNAL_TOKEN — shared secret for X-Internal-Token header

Both are injected from the environment at construction time (no hardcoded URLs).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import httpx

from memento.tools.tool_labels import get_allowed_tools

if TYPE_CHECKING:
    from memento.state.kg_projection import KgProjectionProtocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# gm_room_registry — location_uuid → gm_entity_id (beside npc_registry)
# ---------------------------------------------------------------------------

gm_room_registry: dict[str, str] = {}
"""Maps location_uuid → gm self id (``gm:<location_uuid>``)."""


# ---------------------------------------------------------------------------
# AgentRuntimeClient factory (mirrors chain_client.py pattern)
# ---------------------------------------------------------------------------


def build_agent_runtime_client() -> httpx.AsyncClient:
    """Build a thin httpx.AsyncClient for the agent-runtime room route.

    Base URL and internal token are read from environment variables:
      AGENT_RUNTIME_BASE_URL          (required at runtime)
      AGENT_RUNTIME_INTERNAL_TOKEN    (required at runtime)
    """
    base_url = os.getenv("AGENT_RUNTIME_BASE_URL", "http://localhost:4000")
    token = os.getenv("AGENT_RUNTIME_INTERNAL_TOKEN", "")
    return httpx.AsyncClient(
        base_url=base_url,
        headers={"X-Internal-Token": token},
        timeout=30.0,
    )


# ---------------------------------------------------------------------------
# RoomDriver
# ---------------------------------------------------------------------------


class RoomDriver:
    """Drives GM-room sessions for a single bonfire / world.

    Parameters
    ----------
    repo:
        StateRepository implementation (Protocol); used to enumerate NPCs at
        a location via ``get_entities_at_location``.
    agent_runtime_client:
        httpx.AsyncClient pre-configured with base_url and X-Internal-Token
        header.  The caller owns the client's lifecycle (aclose).
    bonfire_id:
        Opaque bonfire identifier forwarded to agent-runtime on open.
    internal_token:
        X-Internal-Token value; stored so it can be injected per-request if
        the shared client header is absent (e.g. in tests that pass a raw
        ASGITransport client).
    player_labels:
        Set of EntityDoc labels that identify a PLAYER (excluded from NPC
        roster).  Defaults to ``{"Player"}``.
    """

    def __init__(
        self,
        *,
        repo: Any,
        agent_runtime_client: httpx.AsyncClient,
        bonfire_id: str,
        internal_token: str = "",
        player_labels: set[str] | None = None,
        projection: "KgProjectionProtocol | None" = None,
    ) -> None:
        self._repo = repo
        self._client = agent_runtime_client
        self._bonfire_id = bonfire_id
        self._internal_token = internal_token or os.getenv(
            "AGENT_RUNTIME_INTERNAL_TOKEN", ""
        )
        self._player_labels: set[str] = (
            player_labels if player_labels is not None else {"Player"}
        )
        self._projection = projection
        # Per-instance cache: location_uuid → set of NPC entity UUIDs in the roster
        self._last_roster_uuids: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_player(self, entity: dict[str, Any]) -> bool:
        """Return True if the entity is a player (by label intersection)."""
        labels: set[str] = set(entity.get("labels", []))
        return bool(labels & self._player_labels)

    def _embodiment_id(self, engine_uuid: str) -> str:
        """KG uuid for this entity if the projection resolves it, else the engine uuid."""
        if self._projection is not None:
            kg_uuid = self._projection.kg_uuid_for(engine_uuid)
            if kg_uuid is not None:
                return kg_uuid
        return engine_uuid

    def _npc_self_spec(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Build a self-spec dict for one NPC entity."""
        entity_uuid: str = entity["uuid"]
        return {
            "id": entity_uuid,
            "embodiment_agent_id": self._embodiment_id(entity_uuid),
            "names": [entity.get("name", "")],
            "seat": "LLM",
            "capabilities": sorted(get_allowed_tools(entity.get("labels", []))),
        }

    def _gm_self_spec(self, location_uuid: str) -> dict[str, Any]:
        """Build the GM self-spec for this location (deterministic Phase 1 id)."""
        gm_id = f"gm:{location_uuid}"
        gm_room_registry[location_uuid] = gm_id
        return {
            "id": gm_id,
            "embodiment_agent_id": self._embodiment_id(gm_id),
            "names": ["GM"],
        }

    def _request_headers(self) -> dict[str, str]:
        """Return per-request auth headers (supplements any client-level headers)."""
        return {"X-Internal-Token": self._internal_token}

    def _resolve_actor_uuid(
        self, location_uuid: str, addressed_name: str | None
    ) -> str | None:
        """Trivial who-acts (Phase 1).

        1. If addressed_name is given, resolve name → kg_uuid via npc_registry.
        2. If that fails (name not in registry), fall through to single-NPC pick.
        3. If no address, pick the only NPC at the location from _last_roster.
        4. Returns None if the roster is empty.
        """
        from gateway.npc_registry import _registry

        if addressed_name:
            name_lower = addressed_name.lower()
            for entry in _registry.values():
                if entry.name.lower() == name_lower and entry.kg_uuid:
                    # Verify this entity is actually in the current room roster
                    if entry.kg_uuid in self._last_roster_uuids.get(
                        location_uuid, set()
                    ):
                        return entry.kg_uuid
            # Name not resolved OR not in roster — fall through to single-NPC pick

        # Single-NPC fallback
        uuids = list(self._last_roster_uuids.get(location_uuid, set()))
        if len(uuids) == 1:
            return uuids[0]
        if len(uuids) > 1:
            # Multi-NPC, no address resolved — pick first (deterministic for Phase 1)
            return uuids[0]
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def open_room(self, location_uuid: str) -> dict[str, Any]:
        """Build NPC roster from the world and POST /open to agent-runtime.

        Filters to character entities only, excludes players.
        Each NPC self spec carries embodiment_agent_id = entity UUID.

        Returns the agent-runtime response dict.
        """
        entities = await self._repo.get_entities_at_location(location_uuid)

        npc_roster: list[dict[str, Any]] = []
        roster_uuids: set[str] = set()
        for entity in entities:
            if entity.get("kind") != "character":
                continue
            if self._is_player(entity):
                continue
            spec = self._npc_self_spec(entity)
            npc_roster.append(spec)
            roster_uuids.add(entity["uuid"])

        # Cache roster UUIDs for drive_turn who-acts resolution
        self._last_roster_uuids[location_uuid] = roster_uuids

        gm_self = self._gm_self_spec(location_uuid)
        scene_actor_id = gm_self["id"]

        body: dict[str, Any] = {
            "bonfire_id": self._bonfire_id,
            "scene_actor_id": scene_actor_id,
            "gm_self": gm_self,
            "roster": npc_roster,
        }

        url = f"/v1/scenes/{location_uuid}/open"
        try:
            resp = await self._client.post(
                url, json=body, headers=self._request_headers()
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info(
                "open_room %s → source_episode_id=%s npcs=%d",
                location_uuid,
                data.get("source_episode_id"),
                len(npc_roster),
            )
            return data
        except httpx.HTTPError as exc:
            logger.error("open_room failed for %s: %s", location_uuid, exc)
            raise

    async def drive_turn(
        self,
        location_uuid: str,
        player_message: str,
        *,
        addressed_name: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the acting NPC and POST /turn to agent-runtime.

        Who-acts (Phase 1 trivial):
        - If addressed_name is given → resolve name → uuid via npc_registry.
        - Else (or if name unresolved) → the single NPC at the location.

        Returns the agent-runtime response dict.
        """
        actor_uuid = self._resolve_actor_uuid(location_uuid, addressed_name)
        if actor_uuid is None:
            raise ValueError(
                f"drive_turn: no NPC to act at location {location_uuid!r}"
                f" (addressed_name={addressed_name!r})"
            )

        body: dict[str, Any] = {
            "self_id": actor_uuid,
            "message": player_message,
        }

        url = f"/v1/scenes/{location_uuid}/turn"
        try:
            resp = await self._client.post(
                url, json=body, headers=self._request_headers()
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info(
                "drive_turn %s self_id=%s → response_text=%.60s",
                location_uuid,
                actor_uuid,
                data.get("response_text", ""),
            )
            return data
        except httpx.HTTPError as exc:
            logger.error("drive_turn failed for %s: %s", location_uuid, exc)
            raise

    async def close_room(self, location_uuid: str) -> dict[str, Any]:
        """POST /close to agent-runtime for this location.

        Returns the agent-runtime response dict.
        """
        url = f"/v1/scenes/{location_uuid}/close"
        try:
            resp = await self._client.post(url, headers=self._request_headers())
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info(
                "close_room %s → task_id=%s", location_uuid, data.get("task_id")
            )
            # Clean up local registry
            self._last_roster_uuids.pop(location_uuid, None)
            gm_room_registry.pop(location_uuid, None)
            return data
        except httpx.HTTPError as exc:
            logger.error("close_room failed for %s: %s", location_uuid, exc)
            raise

    def handle_player_message(
        self,
        location_uuid: str,
        player_message: str,
        *,
        addressed_name: str | None = None,
    ) -> None:
        """Single Matrix-bridge call site for incoming player messages.

        This is the ONE wiring point the bridge calls on a player message.
        It schedules drive_turn as a background coroutine.
        Full Matrix-bridge entry is Phase 2 — this stub exposes the surface.
        """
        import asyncio

        asyncio.ensure_future(
            self.drive_turn(
                location_uuid,
                player_message,
                addressed_name=addressed_name,
            )
        )
