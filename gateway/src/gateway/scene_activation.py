"""Scene activation: construct a RoomDriver and open/close a scene for a location."""

from __future__ import annotations

from typing import Any

import httpx

from gateway.room_driver import RoomDriver
from gateway.routes.opening import BONFIRE_ID


class SceneActivationError(Exception):
    """Base for scene-activation domain errors."""


class SceneAlreadyOpen(SceneActivationError):
    """A scene is already open for this location."""


class SceneNotOpen(SceneActivationError):
    """No scene is open for this location."""


class AgentRuntimeUnavailable(SceneActivationError):
    """The agent-runtime could not be reached or returned an error."""


class SceneActivationService:
    """Opens/closes a RoomDriver-backed scene for a location.

    Constructed per request from app.state; the open-scene registry persists
    on app.state (location_uuid -> live RoomDriver).
    """

    def __init__(
        self,
        *,
        repo: Any,  # StateRepository Protocol impl (matches RoomDriver(repo: Any))
        agent_runtime_client: httpx.AsyncClient,
        scene_registry: dict[str, RoomDriver],
        bonfire_id: str = BONFIRE_ID,
    ) -> None:
        self._repo = repo
        self._client = agent_runtime_client
        self._registry = scene_registry
        self._bonfire_id = bonfire_id

    @classmethod
    def from_app_state(cls, state: Any) -> "SceneActivationService":
        return cls(
            repo=state.cxn_repo,
            agent_runtime_client=state.agent_runtime_client,
            scene_registry=state.scene_registry,
        )

    def _build_driver(self) -> RoomDriver:
        # KG-backed repos expose .projection (Task 1); InMemory repos do not
        # -> None -> RoomDriver falls back to the engine uuid for embodiment.
        projection = getattr(self._repo, "projection", None)
        return RoomDriver(
            repo=self._repo,
            agent_runtime_client=self._client,
            bonfire_id=self._bonfire_id,
            projection=projection,
        )

    async def activate(self, location_uuid: str) -> dict[str, Any]:
        if location_uuid in self._registry:
            raise SceneAlreadyOpen(location_uuid)
        driver = self._build_driver()
        try:
            result = await driver.open_room(location_uuid)
        except httpx.HTTPError as exc:
            raise AgentRuntimeUnavailable(str(exc)) from exc
        self._registry[location_uuid] = driver  # register only after a successful open
        return {"scene_id": location_uuid, **result}

    async def close(self, location_uuid: str) -> dict[str, Any]:
        driver = self._registry.get(location_uuid)
        if driver is None:
            raise SceneNotOpen(location_uuid)
        try:
            result = await driver.close_room(location_uuid)
        except httpx.HTTPError as exc:
            raise AgentRuntimeUnavailable(str(exc)) from exc
        self._registry.pop(location_uuid, None)  # deregister only after a successful close
        return {"scene_id": location_uuid, **result}
