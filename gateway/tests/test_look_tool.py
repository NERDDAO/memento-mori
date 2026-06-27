"""Tests for the gateway-hosted mm_look MCP tool (Plan 2, Task 1)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from memento.opening.deep_roads import LOC_DEEP_ROADS, deep_roads_seed
from memento.opening.reveal import seed_room_ecs
from memento.state.in_memory import InMemoryStateRepository

from gateway.look_tool import register_look_tool, seed_opening_room

_ACTOR = "player-uuid-1"


def _fastmcp():
    from mcp.server.fastmcp import FastMCP

    return FastMCP("memento-engine")


@contextmanager
def _with_identity(entity_id=_ACTOR):
    from gateway.mcp_server import _current_identity

    token = _current_identity.set(entity_id)
    try:
        yield
    finally:
        _current_identity.reset(token)


def _extract(call_result) -> dict:
    return json.loads(call_result[0].text)


def _hub():
    hub = AsyncMock()
    hub.broadcast_to_location = AsyncMock()
    return hub


async def _seed_room_and_actor(repo, *, location=LOC_DEEP_ROADS):
    await seed_room_ecs(repo, deep_roads_seed())
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": location,
            "attrs": {},  # no reveal_level -> the actor is not itself a candidate
            "is_dead": False,
        }
    )


async def _call_look(mcp):
    with (
        patch("gateway.mcp_server.check_tool_access", new_callable=AsyncMock),
        _with_identity(),
    ):
        return _extract(await mcp.call_tool("mm_look", {}))


@pytest.mark.asyncio
async def test_mm_look_reveals_in_salience_order_and_broadcasts():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    names = []
    for _ in range(3):
        res = await _call_look(mcp)
        assert res["kind"] == "revealed"
        names.append(res["entity"]["name"])
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]

    # one room_draw per reveal, to the actor's location, carrying the entity
    assert hub.broadcast_to_location.await_count == 3
    loc, msg = hub.broadcast_to_location.await_args.args
    assert loc == LOC_DEEP_ROADS
    assert msg["type"] == "room_draw" and msg["kind"] == "revealed"
    assert (
        msg["entity"]["name"] == "an iron blade" and msg["location"] == LOC_DEEP_ROADS
    )


@pytest.mark.asyncio
async def test_mm_look_deepens_after_all_revealed():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)  # default max_depth=3

    for _ in range(3):
        await _call_look(mcp)  # reveal all three
    res = await _call_look(mcp)  # 4th -> deepen the most salient
    assert res["kind"] == "deepened"
    assert res["entity"]["name"] == "a dying adventurer" and res["depth"] == 2
    assert hub.broadcast_to_location.await_args.args[1]["kind"] == "deepened"


@pytest.mark.asyncio
async def test_mm_look_exhausts_and_does_not_broadcast():
    repo = InMemoryStateRepository()
    await _seed_room_and_actor(repo)
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo, max_depth=1)  # no deepening: reveal-only

    for _ in range(3):
        await _call_look(mcp)  # reveal all three
    hub.broadcast_to_location.reset_mock()
    res = await _call_look(mcp)  # 4th -> exhausted
    assert res["kind"] == "exhausted" and res["entity"] is None
    assert hub.broadcast_to_location.await_count == 0  # nothing to draw


@pytest.mark.asyncio
async def test_mm_look_degrades_when_actor_has_no_location():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": None,  # no room
            "attrs": {},
            "is_dead": False,
        }
    )
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    res = await _call_look(mcp)  # must not raise
    assert res["kind"] == "exhausted" and res["entity"] is None
    assert hub.broadcast_to_location.await_count == 0


@pytest.mark.asyncio
async def test_seed_opening_room_seeds_latent_reveal_tracked_facts():
    repo = InMemoryStateRepository()
    await seed_opening_room(repo)
    ents = await repo.get_entities_at_location(LOC_DEEP_ROADS)
    items = await repo.get_items_at_location(LOC_DEEP_ROADS)
    by_name = {t["name"]: t for t in (list(ents) + list(items))}
    assert by_name["a dying adventurer"]["attrs"]["reveal_level"] == 0
    assert by_name["a dying adventurer"]["attrs"]["salience"] == 1_000_000
    assert by_name["something in the dark"]["attrs"]["reveal_level"] == 0
    assert by_name["an iron blade"]["kind"] == "item"  # item arm
    assert by_name["an iron blade"]["attrs"]["reveal_level"] == 0


@pytest.mark.asyncio
async def test_seeded_room_drives_mm_look_in_authored_order():
    repo = InMemoryStateRepository()
    await seed_opening_room(repo)  # boot-seed path (no manual seed_room_ecs)
    repo.seed_entity(
        {
            "uuid": _ACTOR,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC_DEEP_ROADS,
            "attrs": {},
            "is_dead": False,
        }
    )
    hub = _hub()
    mcp = _fastmcp()
    register_look_tool(mcp, hub, repo)

    names = [(await _call_look(mcp))["entity"]["name"] for _ in range(3)]
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]
