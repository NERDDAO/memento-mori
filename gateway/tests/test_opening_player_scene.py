"""Tests for B1 + B2 in POST /api/opening/start.

B1: player is seeded into app.state.cxn_repo at LOC_DEEP_ROADS.
B2: a player-gm_self scene is opened with mm_look in capabilities, empty roster.

When app.state.cxn_repo is absent, /opening/start must still return 200
(B1/B2 no-op gracefully).
"""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from memento.opening.deep_roads import LOC_DEEP_ROADS
from memento.state.in_memory import InMemoryStateRepository


def _ar_stub(captured):
    async def _open(request):
        captured["open_body"] = await request.json()
        return JSONResponse({"source_episode_id": "ep-1"})

    app = Starlette(routes=[Route("/v1/scenes/{loc}/open", _open, methods=["POST"])])
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://ar"
    )


@pytest.fixture()
def _patch_opening_hooks(monkeypatch):
    """Replace all DI builder hooks on the opening module with fakes.

    Replicates the autouse fixture body from test_opening_routes.py so that
    /opening/start runs without any real KG/network I/O.
    """
    import gateway.routes.opening as opening_mod

    def _make_fake_comprehension():
        from memento.cxn.kernel_client import FakeComprehensionClient
        from memento.cxn.types import ComprehendedFrame, FrameRole

        canned = {
            "look around": ComprehendedFrame(
                predicate="look",
                roles=[],
                matched=True,
                raw_text="look around",
            ),
            "go on": ComprehendedFrame(
                predicate="move",
                roles=[FrameRole(role="location", filler="on")],
                matched=True,
                raw_text="go on",
            ),
        }
        return FakeComprehensionClient(canned)

    def _make_fake_memory():
        from memento.memory.null_client import NullMemoryClient

        return NullMemoryClient()

    def _make_fake_mirror():
        from memento.state.chain_mirror import NoopChainMirror

        return NoopChainMirror()

    def _make_fake_projection():
        from memento.state.kg_projection import KgProjectionFake

        return KgProjectionFake()

    async def _fake_create_player(
        player_name: str, wallet_address: str, archetype: str
    ) -> str:
        return "deadbeef00000000000000aa"

    monkeypatch.setattr(opening_mod, "build_comprehension", _make_fake_comprehension)
    monkeypatch.setattr(opening_mod, "build_memory", _make_fake_memory)
    monkeypatch.setattr(opening_mod, "build_mirror", _make_fake_mirror)
    monkeypatch.setattr(opening_mod, "build_projection", _make_fake_projection)
    monkeypatch.setattr(opening_mod, "create_player", _fake_create_player)


@pytest.mark.asyncio
async def test_start_seeds_player_into_cxn_repo_and_opens_player_scene(
    _patch_opening_hooks,
):
    from gateway.app import app

    captured = {}
    cxn_repo = InMemoryStateRepository()
    app.state.cxn_repo = cxn_repo
    app.state.agent_runtime_client = _ar_stub(captured)
    app.state.bonfire_id = "bf-1"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0x" + "a" * 40,
                "archetype": "",
            },
        )
    assert resp.status_code == 200, resp.text
    player_id = resp.json()["player_id"]

    # B1: player is in app.state.cxn_repo at the Deep Roads
    ent = await cxn_repo.get_entity(player_id)
    assert ent is not None and ent["location_uuid"] == LOC_DEEP_ROADS
    assert ent["kind"] == "character" and "Character" in ent["labels"]

    # B2: a player-gm_self scene was opened
    body = captured["open_body"]
    assert body["gm_self"]["id"] == player_id and body["gm_self"]["seat"] == "LLM"
    assert "mm_look" in body["gm_self"]["capabilities"] and body["roster"] == []


@pytest.mark.asyncio
async def test_start_still_succeeds_without_cxn_repo(_patch_opening_hooks):
    from gateway.app import app

    if hasattr(app.state, "cxn_repo"):
        delattr(app.state, "cxn_repo")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/opening/start",
            json={
                "player_name": "Tester",
                "wallet_address": "0x" + "b" * 40,
                "archetype": "",
            },
        )
    assert resp.status_code == 200  # B1/B2 no-op gracefully when cxn_repo absent
