"""Unit tests for MemoryClient implementations (C2).

Covers:
    NullMemoryClient  — ingest -> None, search -> []
    CapturingMemoryClient — records ingests; search -> []
    KernelMemoryClient — correct JSON / URL / headers verified via MockTransport;
                         returns episode_uuid from response; 5xx -> None; empty
                         episode_uuids list -> None.

No live kernel required.  No RNG.  No LLM.
"""
from __future__ import annotations

import json

import httpx
import pytest

from memento.cxn.types import EpisodeIn
from memento.memory.capturing_client import CapturingMemoryClient
from memento.memory.kernel_client import KernelMemoryClient
from memento.memory.null_client import NullMemoryClient

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

BONFIRE_ID = "6650000000000000000000f1"
ACTOR_ID = "6650000000000000000000a1"

EPISODE: EpisodeIn = {
    "bonfire_id": BONFIRE_ID,
    "actor_id": ACTOR_ID,
    "content": "Kael moved to The Ash Market.",
    "metadata": {"action_type": "MOVE", "location_uuid": "6650000000000000000000c1"},
}

BASE_URL = "http://kernel.test"
TOKEN = "test-gm-token"

EXPECTED_INDEX_URL = f"{BASE_URL}/v1/bonfires/{BONFIRE_ID}/kernel/index"


# ---------------------------------------------------------------------------
# NullMemoryClient
# ---------------------------------------------------------------------------


async def test_null_ingest_returns_none():
    client = NullMemoryClient()
    result = await client.ingest_episode(EPISODE)
    assert result is None


async def test_null_search_returns_empty_list():
    client = NullMemoryClient()
    result = await client.search_context("query", BONFIRE_ID, ACTOR_ID)
    assert result == []


# ---------------------------------------------------------------------------
# CapturingMemoryClient
# ---------------------------------------------------------------------------


async def test_capturing_ingest_records_episode():
    client = CapturingMemoryClient()
    assert client.ingested == []
    result = await client.ingest_episode(EPISODE)
    assert result is None  # no live kernel — no UUID
    assert len(client.ingested) == 1
    recorded = client.ingested[0]
    assert recorded["bonfire_id"] == BONFIRE_ID
    assert recorded["actor_id"] == ACTOR_ID
    assert recorded["content"] == EPISODE["content"]
    assert recorded["metadata"] == EPISODE["metadata"]


async def test_capturing_ingest_accumulates_multiple():
    client = CapturingMemoryClient()
    second: EpisodeIn = {
        "bonfire_id": BONFIRE_ID,
        "actor_id": ACTOR_ID,
        "content": "Kael attacked Goblin Scout.",
        "metadata": {"action_type": "ATTACK"},
    }
    await client.ingest_episode(EPISODE)
    await client.ingest_episode(second)
    assert len(client.ingested) == 2
    assert client.ingested[0]["content"] == EPISODE["content"]
    assert client.ingested[1]["content"] == second["content"]


async def test_capturing_search_returns_empty_list():
    client = CapturingMemoryClient()
    result = await client.search_context("some query", BONFIRE_ID, ACTOR_ID)
    assert result == []


# ---------------------------------------------------------------------------
# KernelMemoryClient — MockTransport helpers
# ---------------------------------------------------------------------------


def _make_kernel_client(transport: httpx.MockTransport) -> KernelMemoryClient:
    """Construct KernelMemoryClient with an injected mock transport."""
    http_client = httpx.AsyncClient(transport=transport)
    return KernelMemoryClient(
        base_url=BASE_URL,
        token=TOKEN,
        http_client=http_client,
    )


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Captures the last request for assertion; returns a configurable response."""

    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self.body = body
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            status_code=self.status,
            headers={"Content-Type": "application/json"},
            content=json.dumps(self.body).encode(),
        )


# ---------------------------------------------------------------------------
# KernelMemoryClient — correct URL / headers / body
# ---------------------------------------------------------------------------


async def test_kernel_posts_to_correct_url():
    transport = _RecordingTransport(200, {"episode_uuids": ["uuid-abc"]})
    client = _make_kernel_client(transport)
    await client.ingest_episode(EPISODE)
    assert len(transport.requests) == 1
    assert str(transport.requests[0].url) == EXPECTED_INDEX_URL


async def test_kernel_sends_auth_header():
    transport = _RecordingTransport(200, {"episode_uuids": ["uuid-abc"]})
    client = _make_kernel_client(transport)
    await client.ingest_episode(EPISODE)
    req = transport.requests[0]
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"


async def test_kernel_sends_correct_json_body():
    transport = _RecordingTransport(200, {"episode_uuids": ["uuid-abc"]})
    client = _make_kernel_client(transport)
    await client.ingest_episode(EPISODE)
    req = transport.requests[0]
    body = json.loads(req.content)
    # Top-level fields per spec §5.3 KernelIndexRequest shape
    assert body["actor_id"] == ACTOR_ID
    assert body["mode"] == "upsert"
    # message_batches must be a list containing one batch (a list of one message)
    batches = body["message_batches"]
    assert isinstance(batches, list) and len(batches) == 1
    batch = batches[0]
    assert isinstance(batch, list) and len(batch) == 1
    msg = batch[0]
    assert msg["content"] == EPISODE["content"]
    assert msg["speaker"] == ACTOR_ID
    assert "timestamp" in msg  # ISO-8601 string; value varies by wall clock
    assert msg["metadata"] == EPISODE["metadata"]
    # top-level metadata echoed
    assert "metadata" in body


async def test_kernel_returns_first_episode_uuid():
    transport = _RecordingTransport(200, {"episode_uuids": ["uuid-first", "uuid-second"]})
    client = _make_kernel_client(transport)
    result = await client.ingest_episode(EPISODE)
    assert result == "uuid-first"


# ---------------------------------------------------------------------------
# KernelMemoryClient — failure modes (spec §5.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_kernel_5xx_returns_none(status: int):
    transport = _RecordingTransport(status, {"detail": "internal error"})
    client = _make_kernel_client(transport)
    result = await client.ingest_episode(EPISODE)
    assert result is None


async def test_kernel_empty_episode_uuids_returns_none():
    transport = _RecordingTransport(200, {"episode_uuids": []})
    client = _make_kernel_client(transport)
    result = await client.ingest_episode(EPISODE)
    assert result is None


async def test_kernel_search_returns_empty_list_day1():
    """Day-1 stub: search_context always returns [] regardless of transport."""
    transport = _RecordingTransport(200, {"hits": []})
    client = _make_kernel_client(transport)
    result = await client.search_context("some query", BONFIRE_ID, ACTOR_ID)
    assert result == []
    # No HTTP request should be made on Day 1
    assert len(transport.requests) == 0


# ---------------------------------------------------------------------------
# KernelMemoryClient — constructor validation
# ---------------------------------------------------------------------------


def test_kernel_client_raises_on_missing_base_url(monkeypatch):
    monkeypatch.delenv("KERNEL_BASE_URL", raising=False)
    monkeypatch.delenv("GM_INTERNAL_TOKEN", raising=False)
    with pytest.raises(ValueError, match="KERNEL_BASE_URL"):
        KernelMemoryClient(base_url="", token="tok")


def test_kernel_client_raises_on_missing_token(monkeypatch):
    monkeypatch.delenv("KERNEL_BASE_URL", raising=False)
    monkeypatch.delenv("GM_INTERNAL_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GM_INTERNAL_TOKEN"):
        KernelMemoryClient(base_url="http://kernel.test", token="")
