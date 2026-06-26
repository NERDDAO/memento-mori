"""Reconciles the two location identities used by the gateway: ws_hub keys on a
location NAME, while scenes / cxn_repo key on a location_uuid. The name->uuid cache
is owned by app.state (passed in) so it survives across requests; it is populated
by the bootstrap persona seed and by KG-confirmed lookups, and read by maybe_close
to resolve a departed location whose player has already moved away.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)


class LocationResolver:
    def __init__(self, cxn_repo: Any, cache: Any) -> None:
        self._repo = cxn_repo
        self._cache = cache if cache is not None else {}

    async def uuid_for(self, player_id: str, location_name: str) -> str | None:
        # Cache first (local seed + previously KG-confirmed names): works without KG.
        cached = self._cache.get(location_name)
        if cached:
            return cached
        # Fall back to the KG-authoritative resolver for the real deployment.
        from gateway.routes.codex import _get_location_uuid

        uuid = await _get_location_uuid(player_id)
        if uuid and location_name:
            self._cache[location_name] = uuid
        return uuid

    async def name_for(self, location_uuid: str) -> str | None:
        if self._repo is None:
            return None
        try:
            entity = await self._repo.get_entity(location_uuid)
        except Exception:  # repo failure must not break the action path
            return None
        return entity.get("name") if entity else None

    def record(self, name: str, uuid: str) -> None:
        if name and uuid:
            self._cache[name] = uuid

    def uuid_for_name(self, name: str) -> str | None:
        return self._cache.get(name)

    def forget_name(self, name: str) -> None:
        self._cache.pop(name, None)
