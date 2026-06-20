"""KernelMemoryClient — real httpx client against graph-memory kernel/index.

Spec §5.1 (auth), §5.3 (endpoint shapes), §5.5 (failure modes).

Environment variables:
    KERNEL_BASE_URL   — base URL of the graph-memory service (no trailing slash)
    GM_INTERNAL_TOKEN — shared internal bearer token (InternalAuthMiddleware)

Both are required when KernelMemoryClient is instantiated.  Missing values raise
ValueError at construction time so misconfiguration is surfaced at startup, not
on the first ingest call.

Non-fatal contract (spec §5.5):
    - 5xx / timeout → logged, returns None; player action still succeeds
    - 200 but episode_uuids=[] → warning logged, returns None; non-fatal
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from memento.cxn.types import EpisodeIn
from memento.memory.client import WorldContext

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KernelMemoryClient:
    """Thin async HTTP client over POST /v1/bonfires/{bonfire_id}/kernel/index.

    search_context is a Day-1 stub returning [] — the full KernelSearchRequest
    path will be wired at Milestone 2 alongside EntityResolver.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Args:
            base_url: KERNEL_BASE_URL env var value (no trailing slash).
                      Defaults to os.environ["KERNEL_BASE_URL"].
            token:    GM_INTERNAL_TOKEN env var value.
                      Defaults to os.environ["GM_INTERNAL_TOKEN"].
            http_client: Injected AsyncClient (for tests via MockTransport).
                         If None, a fresh client is created per ingest call
                         (acceptable for Day-1 fire-and-forget semantics).
        """
        self._base_url: str = base_url or os.environ.get("KERNEL_BASE_URL", "")
        self._token: str = token or os.environ.get("GM_INTERNAL_TOKEN", "")

        if not self._base_url:
            raise ValueError(
                "KERNEL_BASE_URL is not set — KernelMemoryClient cannot be created."
            )
        if not self._token:
            raise ValueError(
                "GM_INTERNAL_TOKEN is not set — KernelMemoryClient cannot be created."
            )

        self._base_url = self._base_url.rstrip("/")
        # Optional injected client (used by tests via MockTransport).
        self._http_client: httpx.AsyncClient | None = http_client

    # ------------------------------------------------------------------
    # Public API — MemoryClient Protocol
    # ------------------------------------------------------------------

    async def ingest_episode(self, episode: EpisodeIn) -> str | None:
        """POST to kernel/index for the bonfire named in episode['bonfire_id'].

        Request body (KernelIndexRequest shape, spec §5.3):
            {
                "actor_id": "<actor_id>",
                "mode": "upsert",
                "message_batches": [[{
                    "content": "<content>",
                    "speaker": "<actor_id>",
                    "timestamp": "<iso8601>",
                    "metadata": {...}
                }]],
                "metadata": {...}
            }

        Returns the first episode_uuid on success, None on 5xx or empty list.
        """
        bonfire_id = episode["bonfire_id"]
        actor_id = episode["actor_id"]
        url = f"{self._base_url}/v1/bonfires/{bonfire_id}/kernel/index"

        body: dict[str, Any] = {
            "actor_id": actor_id,
            "mode": "upsert",
            "message_batches": [
                [
                    {
                        "content": episode["content"],
                        "speaker": actor_id,
                        "timestamp": _utcnow_iso(),
                        "metadata": episode.get("metadata", {}),
                    }
                ]
            ],
            "metadata": episode.get("metadata", {}),
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=body, headers=headers)

            if response.status_code >= 500:
                logger.error(
                    "kernel/index returned %s for bonfire=%s actor=%s — will retry next turn",
                    response.status_code,
                    bonfire_id,
                    actor_id,
                )
                return None

            data = response.json()
            uuids: list[str] = data.get("episode_uuids", [])
            if not uuids:
                logger.warning(
                    "kernel/index returned 200 but episode_uuids=[] for bonfire=%s actor=%s",
                    bonfire_id,
                    actor_id,
                )
                return None

            return uuids[0]

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.error(
                "kernel/index request failed for bonfire=%s actor=%s: %s — will retry next turn",
                bonfire_id,
                actor_id,
                exc,
            )
            return None

    async def search_context(
        self,
        query: str,
        bonfire_id: str,
        actor_id: str,
        k: int = 5,
    ) -> list[WorldContext]:
        """Day-1 stub — returns [].

        Milestone 2 will send KernelSearchRequest to kernel/search and map
        KernelSearchHit objects to WorldContext TypedDicts.
        """
        return []
