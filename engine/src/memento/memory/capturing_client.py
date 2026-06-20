"""CapturingMemoryClient — records every ingest call for test assertions.

Use in unit/integration tests where you need to verify that the executor
produced the correct episode content and metadata.
"""
from __future__ import annotations

from memento.cxn.types import EpisodeIn
from memento.memory.client import WorldContext


class CapturingMemoryClient:
    """Records every ingest_episode call so tests can assert on episode content.

    ingested: list[EpisodeIn] grows with each ingest; never cleared automatically.
    search_context returns [] (no kernel needed in test scenarios).
    """

    def __init__(self) -> None:
        self.ingested: list[EpisodeIn] = []

    async def ingest_episode(self, episode: EpisodeIn) -> str | None:
        """Record the episode and return None (no live kernel, so no UUID)."""
        self.ingested.append(episode)
        return None

    async def search_context(
        self,
        query: str,
        bonfire_id: str,
        actor_id: str,
        k: int = 5,
    ) -> list[WorldContext]:
        return []
