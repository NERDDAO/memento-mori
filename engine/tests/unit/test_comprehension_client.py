"""Unit tests for ComprehensionClient (Task 1 — M2 ATTACK slice).

Uses httpx.MockTransport so no real HTTP or NLP is involved.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from memento.cxn.kernel_client import (
    FakeComprehensionClient,
    HttpComprehensionClient,
)
from memento.cxn.types import ComprehendError, ComprehendedFrame, FrameRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(status: int, body: dict[str, Any]) -> httpx.MockTransport:
    """Return an httpx.MockTransport that always replies with the given status+body."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status,
            content=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )

    return httpx.MockTransport(handler)


def _comprehend_response(frame_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Build a canned KernelComprehendResponse payload."""
    return {
        "bonfire_id": "mm-world-v1",
        "actor_id": "actor-123",
        "utterance": "attack the goblin",
        "frame": frame_payload,
        "diagnostics": {},
    }


ATTACK_FRAME_DTO = {
    "predicate": "attack",
    "confidence": 0.95,
    "roles": [
        {"role": "patient", "filler": "the goblin", "entity_id": None},
    ],
    "applied_cxn_ids": ["ATTACK"],
    "matched": True,
    "raw_meaning": "attack the goblin",
}


# ---------------------------------------------------------------------------
# Case 1: populated frame → ComprehendedFrame with matched=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comprehend_populated_frame() -> None:
    transport = _make_transport(200, _comprehend_response(ATTACK_FRAME_DTO))
    client = httpx.AsyncClient(transport=transport)

    comprehension = HttpComprehensionClient(
        base_url="http://graph-memory",
        token="test-token",
        bonfire_id="mm-world-v1",
        client=client,
    )

    result = await comprehension.comprehend(
        utterance="attack the goblin",
        actor_id="actor-123",
    )

    assert result["predicate"] == "attack"
    assert result["matched"] is True
    assert result["raw_text"] == "attack the goblin"
    # Roles mapped verbatim from DTO
    assert len(result["roles"]) == 1
    role: FrameRole = result["roles"][0]
    assert role["role"] == "patient"
    assert role["filler"] == "the goblin"


# ---------------------------------------------------------------------------
# Case 2: frame: null → matched=False, roles=[]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comprehend_null_frame() -> None:
    transport = _make_transport(200, _comprehend_response(None))
    client = httpx.AsyncClient(transport=transport)

    comprehension = HttpComprehensionClient(
        base_url="http://graph-memory",
        token="test-token",
        bonfire_id="mm-world-v1",
        client=client,
    )

    result = await comprehension.comprehend(
        utterance="attack the goblin",
        actor_id="actor-123",
    )

    assert result["matched"] is False
    assert result["roles"] == []
    assert result["predicate"] == ""
    assert result["raw_text"] == "attack the goblin"


# ---------------------------------------------------------------------------
# Case 3: 503 → raises ComprehendError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comprehend_503_raises() -> None:
    transport = _make_transport(503, {"detail": "service unavailable"})
    client = httpx.AsyncClient(transport=transport)

    comprehension = HttpComprehensionClient(
        base_url="http://graph-memory",
        token="test-token",
        bonfire_id="mm-world-v1",
        client=client,
    )

    with pytest.raises(ComprehendError):
        await comprehension.comprehend(
            utterance="attack the goblin",
            actor_id="actor-123",
        )


# ---------------------------------------------------------------------------
# Case 4: FakeComprehensionClient — canned dict lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_client_returns_canned_frame() -> None:
    canned: ComprehendedFrame = {
        "predicate": "attack",
        "roles": [{"role": "patient", "filler": "goblin"}],
        "matched": True,
        "raw_text": "attack the goblin",
    }
    fake = FakeComprehensionClient(canned={"attack the goblin": canned})

    result = await fake.comprehend(utterance="attack the goblin", actor_id="any")
    assert result["predicate"] == "attack"
    assert result["matched"] is True


@pytest.mark.asyncio
async def test_fake_client_unrecognised_utterance_returns_no_match() -> None:
    fake = FakeComprehensionClient(canned={})

    result = await fake.comprehend(utterance="dance", actor_id="any")
    assert result["matched"] is False
    assert result["roles"] == []


# ---------------------------------------------------------------------------
# Auth header check — X-Internal-Token + X-Permission: read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comprehend_sends_correct_auth_headers() -> None:
    """HttpComprehensionClient must use X-Internal-Token + X-Permission: read."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            content=json.dumps(_comprehend_response(ATTACK_FRAME_DTO)).encode(),
            headers={"Content-Type": "application/json"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    comprehension = HttpComprehensionClient(
        base_url="http://graph-memory",
        token="my-secret",
        bonfire_id="mm-world-v1",
        client=client,
    )

    _ = await comprehension.comprehend(
        utterance="attack the goblin", actor_id="actor-123"
    )

    assert len(captured) == 1
    req = captured[0]
    assert req.headers.get("x-internal-token") == "my-secret"
    assert req.headers.get("x-permission") == "read"
    # Must NOT use legacy Authorization: Bearer scheme
    assert "authorization" not in {k.lower() for k in req.headers}
