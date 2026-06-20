"""NullMemoryClient — ingest is a no-op, search returns [].

The wired Day-1 default. Satisfies the MemoryClient Protocol with zero
external dependencies. Safe to use when no kernel service is available.
"""
from __future__ import annotations

from memento.cxn.types import EpisodeIn
from memento.memory.client import WorldContext


class NullMemoryClient:
    """All kernel calls are silent no-ops.

    ingest_episode -> None (episode not persisted, action still succeeds).
    search_context -> [] (no world-context; resolution proceeds with empty hints).
    """

    async def ingest_episode(self, episode: EpisodeIn) -> str | None:
        return None

    async def search_context(
        self,
        query: str,
        bonfire_id: str,
        actor_id: str,
        k: int = 5,
    ) -> list[WorldContext]:
        return []
