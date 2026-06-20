"""ComprehensionClient — HTTP client against graph-memory kernel/comprehend.

Contract (graph-memory InternalAuthMiddleware is authoritative):
    POST /v1/bonfires/{bonfire_id}/kernel/comprehend
    Headers:
        X-Internal-Token: <GM_INTERNAL_TOKEN>
        X-Permission: read
    Request:  {actor_id, utterance, entity_hints:[], allowed_construct_ids:[]}
    Response: {bonfire_id, actor_id, utterance, frame: SemanticFrameDTO|null, diagnostics}

NOTE on auth-header discrepancy:
    The existing KernelMemoryClient (memory/kernel_client.py) uses the legacy
    `Authorization: Bearer <token>` scheme.  This client intentionally uses
    `X-Internal-Token` + `X-Permission: read` as specified by the
    graph-memory InternalAuthMiddleware contract in the M2 brief.  The two
    clients are inconsistent; that discrepancy is documented here and should
    be reconciled (KernelMemoryClient migrated) in a follow-up task.

Environment variables:
    KERNEL_BASE_URL   — base URL of graph-memory (no trailing slash)
    GM_INTERNAL_TOKEN — shared internal token (InternalAuthMiddleware)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

import httpx

from memento.cxn.types import ComprehendError, ComprehendedFrame, FrameRole

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ComprehensionClient(Protocol):
    """Abstract surface for comprehension — real HTTP or fake for tests."""

    async def comprehend(
        self,
        utterance: str,
        actor_id: str,
        entity_hints: list[str] | None = None,
        allowed_construct_ids: list[str] | None = None,
    ) -> ComprehendedFrame: ...


# ---------------------------------------------------------------------------
# Real HTTP client
# ---------------------------------------------------------------------------


class HttpComprehensionClient:
    """Async HTTP client over POST /v1/bonfires/{bonfire_id}/kernel/comprehend.

    Args:
        base_url:   KERNEL_BASE_URL (no trailing slash).
                    Defaults to os.environ["KERNEL_BASE_URL"].
        token:      GM_INTERNAL_TOKEN.
                    Defaults to os.environ["GM_INTERNAL_TOKEN"].
        bonfire_id: Fixed bonfire identifier ("mm-world-v1" for Day-1).
        client:     Injected httpx.AsyncClient (for tests via MockTransport).
                    If None, a fresh client is created per request.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        bonfire_id: str = "mm-world-v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url: str = (
            base_url or os.environ.get("KERNEL_BASE_URL", "")
        ).rstrip("/")
        self._token: str = token or os.environ.get("GM_INTERNAL_TOKEN", "")

        if not self._base_url:
            raise ValueError(
                "KERNEL_BASE_URL is not set — HttpComprehensionClient cannot be created."
            )
        if not self._token:
            raise ValueError(
                "GM_INTERNAL_TOKEN is not set — HttpComprehensionClient cannot be created."
            )

        self._bonfire_id = bonfire_id
        self._client: httpx.AsyncClient | None = client

    async def comprehend(
        self,
        utterance: str,
        actor_id: str,
        entity_hints: list[str] | None = None,
        allowed_construct_ids: list[str] | None = None,
    ) -> ComprehendedFrame:
        """POST to kernel/comprehend and map the SemanticFrameDTO response.

        Returns:
            ComprehendedFrame with matched=False and roles=[] when frame is null.

        Raises:
            ComprehendError: on any non-200 response (400, 401, 403, 422, 503, …).
        """
        url = f"{self._base_url}/v1/bonfires/{self._bonfire_id}/kernel/comprehend"
        body: dict[str, Any] = {
            "actor_id": actor_id,
            "utterance": utterance,
            "entity_hints": entity_hints or [],
            "allowed_construct_ids": allowed_construct_ids or [],
        }
        # Auth scheme: X-Internal-Token + X-Permission: read
        # (InternalAuthMiddleware in graph-memory is authoritative — see module docstring)
        headers = {
            "X-Internal-Token": self._token,
            "X-Permission": "read",
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient() as http:
                    response = await http.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ComprehendError(f"kernel/comprehend network error: {exc}") from exc

        if response.status_code != 200:
            raise ComprehendError(
                f"kernel/comprehend returned {response.status_code} for bonfire={self._bonfire_id}",
                status_code=response.status_code,
            )

        data = response.json()
        return _map_frame(data.get("frame"), utterance)


# ---------------------------------------------------------------------------
# Frame mapping
# ---------------------------------------------------------------------------


def _map_frame(frame_dto: dict[str, Any] | None, utterance: str) -> ComprehendedFrame:
    """Convert a SemanticFrameDTO (or null) into a ComprehendedFrame."""
    if frame_dto is None:
        return ComprehendedFrame(
            predicate="",
            roles=[],
            matched=False,
            raw_text=utterance,
        )

    roles: list[FrameRole] = [
        FrameRole(role=r["role"], filler=r["filler"])
        for r in frame_dto.get("roles", [])
    ]
    return ComprehendedFrame(
        predicate=frame_dto.get("predicate", ""),
        roles=roles,
        matched=bool(frame_dto.get("matched", False)),
        raw_text=frame_dto.get("raw_meaning") or utterance,
    )


# ---------------------------------------------------------------------------
# Fake client for unit tests
# ---------------------------------------------------------------------------


class FakeComprehensionClient:
    """In-process fake ComprehensionClient backed by a canned lookup dict.

    Args:
        canned: utterance → ComprehendedFrame mapping.
                Utterances not present return a no-match frame.
    """

    def __init__(self, canned: dict[str, ComprehendedFrame]) -> None:
        self._canned = canned

    async def comprehend(
        self,
        utterance: str,
        actor_id: str,
        entity_hints: list[str] | None = None,
        allowed_construct_ids: list[str] | None = None,
    ) -> ComprehendedFrame:
        if utterance in self._canned:
            return self._canned[utterance]
        return ComprehendedFrame(
            predicate="",
            roles=[],
            matched=False,
            raw_text=utterance,
        )
