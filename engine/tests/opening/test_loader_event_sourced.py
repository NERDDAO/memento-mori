"""Tests for load_seed_room with both sync (InMemory) and async (EventSourced) repos.

TDD gate:
    cd engine && python -m pytest tests/opening/test_loader_event_sourced.py -q

Covers:
  - load_seed_room into EventSourcedStateRepository:
      - location EntityDoc is present in the projection after seeding
      - dying_adventurer (canon fact) is present in the projection after seeding
      - genesis TxEntries exist in the TxLog (one per seeded entity)
      - iron_blade (latent fact) is NOT present in the projection
      - returned SceneDirector has dying_adventurer key→uuid registered

  - load_seed_room into InMemoryStateRepository (sync path regression):
      - location EntityDoc is present after seeding
      - dying_adventurer (canon fact) is present after seeding
      - iron_blade (latent fact) is NOT present
      - returned SceneDirector has dying_adventurer key→uuid registered
"""

from __future__ import annotations

import pytest

from memento.opening.deep_roads import (
    LOC_DEEP_ROADS,
    UUID_DYING_ADVENTURER,
    deep_roads_seed,
)
from memento.opening.loader import load_seed_room
from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR = "actor-uuid-test-0001"
# iron_blade has no uuid in deep_roads_seed (latent, uuid=None)
# We only need to confirm it's absent from the projection.
_LATENT_ITEM_KEY = "iron_blade"


def _make_es_repo() -> tuple[EventSourcedStateRepository, InMemoryTxLog]:
    """Build an EventSourcedStateRepository wired with in-memory fakes."""
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    proj = KgProjectionFake()
    chain = NoopChainMirror()
    repo = EventSourcedStateRepository(
        tx_log=tx_log,
        activation_log=act_log,
        projection=proj,
        chain=chain,
    )
    return repo, tx_log


# ---------------------------------------------------------------------------
# EventSourced path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_seed_room_event_sourced_location_present() -> None:
    """The location EntityDoc is written to the projection."""
    seed = deep_roads_seed()
    repo, _ = _make_es_repo()

    await load_seed_room(seed, repo, ACTOR)

    loc = await repo.get_entity(LOC_DEEP_ROADS)
    assert loc is not None, "Location entity missing from projection"
    assert loc["uuid"] == LOC_DEEP_ROADS
    assert loc["kind"] == "location"


@pytest.mark.asyncio
async def test_load_seed_room_event_sourced_canon_fact_present() -> None:
    """The dying_adventurer (canon fact) is written to the projection."""
    seed = deep_roads_seed()
    repo, _ = _make_es_repo()

    await load_seed_room(seed, repo, ACTOR)

    adventurer = await repo.get_entity(UUID_DYING_ADVENTURER)
    assert adventurer is not None, "dying_adventurer entity missing from projection"
    assert adventurer["uuid"] == UUID_DYING_ADVENTURER
    assert adventurer["location_uuid"] == LOC_DEEP_ROADS


@pytest.mark.asyncio
async def test_load_seed_room_event_sourced_genesis_txs_present() -> None:
    """Genesis TxEntries exist in the TxLog for the seeded entities."""
    seed = deep_roads_seed()
    repo, tx_log = _make_es_repo()

    await load_seed_room(seed, repo, ACTOR)

    # Location + dying_adventurer = at least 2 genesis entries
    loc_entries = tx_log.for_actor(LOC_DEEP_ROADS)
    adv_entries = tx_log.for_actor(UUID_DYING_ADVENTURER)
    assert len(loc_entries) >= 1, "No TxEntry for location"
    assert loc_entries[0].activation_id == "genesis"
    assert len(adv_entries) >= 1, "No TxEntry for dying_adventurer"
    assert adv_entries[0].activation_id == "genesis"


@pytest.mark.asyncio
async def test_load_seed_room_event_sourced_latent_item_absent() -> None:
    """The iron_blade (latent fact) is NOT written to the projection."""
    seed = deep_roads_seed()
    repo, tx_log = _make_es_repo()

    await load_seed_room(seed, repo, ACTOR)

    # iron_blade has no uuid in the seed (latent, uuid=None); confirm no
    # item docs crept into the projection by checking the full tx_log
    # Verify no item doc with kind=="item" bearing the iron_blade name exists
    all_entries = tx_log._entries  # type: ignore[attr-defined]
    for entry in all_entries:
        for delta in entry.deltas:
            if delta.get("op") == "create":
                doc = delta.get("doc", {})
                if doc.get("kind") == "item":
                    assert "iron_blade" not in doc.get("name", ""), (
                        f"Latent iron_blade was seeded: {doc}"
                    )


@pytest.mark.asyncio
async def test_load_seed_room_event_sourced_director_registry() -> None:
    """The returned SceneDirector has dying_adventurer key→uuid registered."""
    seed = deep_roads_seed()
    repo, _ = _make_es_repo()

    director = await load_seed_room(seed, repo, ACTOR)

    resolved = director._uuid_by_key.get("dying_adventurer")  # type: ignore[attr-defined]
    assert resolved == UUID_DYING_ADVENTURER, (
        f"Expected director to map dying_adventurer→{UUID_DYING_ADVENTURER}, got {resolved!r}"
    )


# ---------------------------------------------------------------------------
# InMemory (sync) path regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_seed_room_in_memory_location_present() -> None:
    """InMemory path: location is seeded correctly."""
    seed = deep_roads_seed()
    repo = InMemoryStateRepository()

    director = await load_seed_room(seed, repo, ACTOR)

    loc = await repo.get_entity(LOC_DEEP_ROADS)
    assert loc is not None, "Location entity missing from InMemory repo"
    assert loc["uuid"] == LOC_DEEP_ROADS


@pytest.mark.asyncio
async def test_load_seed_room_in_memory_canon_fact_present() -> None:
    """InMemory path: dying_adventurer (canon fact) is seeded correctly."""
    seed = deep_roads_seed()
    repo = InMemoryStateRepository()

    await load_seed_room(seed, repo, ACTOR)

    adventurer = await repo.get_entity(UUID_DYING_ADVENTURER)
    assert adventurer is not None, "dying_adventurer missing from InMemory repo"
    assert adventurer["location_uuid"] == LOC_DEEP_ROADS


@pytest.mark.asyncio
async def test_load_seed_room_in_memory_latent_absent() -> None:
    """InMemory path: iron_blade (latent) is NOT seeded."""
    seed = deep_roads_seed()
    repo = InMemoryStateRepository()

    await load_seed_room(seed, repo, ACTOR)

    # iron_blade has no uuid; nothing with its name should be in the store
    # We know all entities in the deep-roads seed; just check item lookup is clean
    # The latent facts have no uuid=None, so there's nothing to look up by uuid.
    # Verify by confirming the repo only holds location + dying_adventurer.
    # (InMemory exposes _entities dict for testing convenience)
    from memento.state.in_memory import InMemoryStateRepository as _IMR  # noqa: PLC0415
    assert isinstance(repo, _IMR)
    # location + dying_adventurer = 2 entities
    entity_count = len(repo._entities)  # type: ignore[attr-defined]
    assert entity_count == 2, (
        f"Expected exactly 2 entities (location + dying_adventurer), got {entity_count}"
    )


@pytest.mark.asyncio
async def test_load_seed_room_in_memory_director_registry() -> None:
    """InMemory path: director maps dying_adventurer→its uuid."""
    seed = deep_roads_seed()
    repo = InMemoryStateRepository()

    director = await load_seed_room(seed, repo, ACTOR)

    resolved = director._uuid_by_key.get("dying_adventurer")  # type: ignore[attr-defined]
    assert resolved == UUID_DYING_ADVENTURER
