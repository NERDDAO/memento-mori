"""NullComprehensionClient — production no-op when kernel is not configured.

Used by ``build_mcp_app`` when KERNEL_BASE_URL / GM_INTERNAL_TOKEN are absent
(local dev without the graph-memory service).  Every utterance returns a
no-match ComprehendedFrame, so ``mm_act`` always responds with a
``clarify/no_match`` outcome — safe and predictable.

``FakeComprehensionClient`` (in kernel_client.py) is the TEST double (canned
responses from a dict).  This class is the PRODUCTION fallback for offline
environments; they serve different purposes and must not be conflated.
"""

from __future__ import annotations

from memento.cxn.types import ComprehendedFrame


class NullComprehensionClient:
    """Always returns a no-match frame — safe fallback when kernel is absent."""

    async def comprehend(
        self,
        utterance: str,
        actor_id: str,  # noqa: ARG002
        entity_hints: list[str] | None = None,  # noqa: ARG002
        allowed_construct_ids: list[str] | None = None,  # noqa: ARG002
    ) -> ComprehendedFrame:
        return ComprehendedFrame(
            predicate="",
            roles=[],
            matched=False,
            raw_text=utterance,
        )
