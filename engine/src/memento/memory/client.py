"""MemoryClient Protocol + local WorldContext TypedDict (Milestone-2 type, local to memory/).

See spec §5.4 for the Protocol contract; §5.3 for endpoint shapes.
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict

from memento.cxn.types import EpisodeIn


class WorldContext(TypedDict):
    """Minimal search-result type for kernel/search hits.

    Kept local to engine/src/memento/memory/ — NOT exported from types.py.
    Milestone-2 will expand this once kernel/comprehend + EntityResolver land.
    """

    uuid: str
    score: float
    text: str
    family: str
    metadata: dict[str, Any]
    episode_ids: list[str]


class MemoryClient(Protocol):
    """Async thin wrapper over graph-memory kernel HTTP endpoints.

    Day-1 required method: ingest_episode (kernel/index).
    search_context is optional Day-1 (NullMemoryClient returns []).

    Return contract:
    - ingest_episode -> str | None  (first episode_uuid, or None on 5xx/empty)
    - search_context -> list[WorldContext]  (empty on failure; non-fatal)
    """

    async def ingest_episode(self, episode: EpisodeIn) -> str | None:
        """POST to kernel/index; returns first episode_uuid or None (non-fatal on 5xx)."""
        ...

    async def search_context(
        self,
        query: str,
        bonfire_id: str,
        actor_id: str,
        k: int = 5,
    ) -> list[WorldContext]:
        """POST to kernel/search; returns [] on failure (non-fatal).

        Day-1: NullMemoryClient returns [].
        Milestone-2: KernelMemoryClient sends KernelSearchRequest and maps hits.
        """
        ...
