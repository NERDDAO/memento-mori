"""TDD gate: activation_id threading in TurnRouter.

Verifies:
1. MOVE turn → exactly one ActivationRecord in activation_log; Tx Log entries
   for that turn carry the SAME activation_id; cxn_id/tool match MOVE_CXN.
2. LOOK turn triggering the "die" surface beat → is_dead Tx Log write stamped
   with the same turn's activation_id (proves director-beat path is covered).
3. Two successive turns get DISTINCT activation_ids and context is cleared
   between turns (genesis stamp does not leak forward).

Wiring mirrors test_opening_arc.py: deep_roads_seed + FakeComprehensionClient +
EventSourcedStateRepository + NoopChainMirror.  No LLM, no network.

NOTE on loader compatibility: load_seed_room calls repo.seed_entity/seed_item
synchronously (typed for InMemoryStateRepository).  EventSourcedStateRepository
has async variants.  Rather than change the loader contract, the tests replicate
what load_seed_room does, awaiting each seed call, then construct SceneDirector
directly and register canon UUIDs.
"""

from __future__ import annotations

import pytest

from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.kernel_client import FakeComprehensionClient
from memento.cxn.types import ComprehendedFrame, FrameRole
from memento.cxn.turn_router import TurnRouter
from memento.memory.capturing_client import CapturingMemoryClient
from memento.opening.deep_roads import (
    LOC_DEEP_ROADS,
    NEXT_ROOM,
    UUID_DYING_ADVENTURER,
    deep_roads_seed,
)
from memento.opening.describe import TemplateDescribeClient
from memento.opening.director import SceneDirector
from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

PLAYER = "507f1f77bcf86cd799439021"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_es_repo() -> tuple[EventSourcedStateRepository, InMemoryTxLog, InMemoryActivationLog]:
    tx_log = InMemoryTxLog()
    act_log = InMemoryActivationLog()
    projection = KgProjectionFake()
    chain = NoopChainMirror()
    repo = EventSourcedStateRepository(tx_log, act_log, projection, chain)
    return repo, tx_log, act_log


async def _seed_world(
    repo: EventSourcedStateRepository,
) -> SceneDirector:
    """Async-safe equivalent of load_seed_room for EventSourcedStateRepository.

    Replicates what load_seed_room does (seeds location + canon facts, builds
    director, registers canon UUIDs) using awaited seed calls.
    """
    seed = deep_roads_seed()

    # Seed location
    await repo.seed_entity(
        {
            "uuid": LOC_DEEP_ROADS,
            "name": seed.name,
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "description": seed.description,
                "exits": list(seed.exits),
            },
            "is_dead": False,
        }
    )

    # Seed NEXT_ROOM
    await repo.seed_entity(
        {
            "uuid": NEXT_ROOM,
            "name": "the road on",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"exits": []},
            "is_dead": False,
        }
    )

    # Seed player
    await repo.seed_entity(
        {
            "uuid": PLAYER,
            "name": "you",
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC_DEEP_ROADS,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )

    # Seed canon facts (dying_adventurer is the only canon fact in deep_roads)
    for fact in seed.facts:
        if not fact.canon:
            continue
        assert fact.uuid is not None
        if fact.kind in {"character", "threat"}:
            await repo.seed_entity(
                {
                    "uuid": fact.uuid,
                    "name": fact.name,
                    "kind": fact.kind,
                    "labels": list(fact.labels),
                    "location_uuid": LOC_DEEP_ROADS,
                    "attrs": dict(fact.attrs),
                    "is_dead": False,
                }
            )

    director = SceneDirector(seed, repo, PLAYER)
    for fact in seed.facts:
        if fact.canon and fact.uuid is not None:
            director.register_canon_uuid(fact.key, fact.uuid)

    return director


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_stamps_activation_record_and_tx_log() -> None:
    """MOVE turn produces one ActivationRecord whose activation_id matches all Tx entries."""
    repo, tx_log, act_log = _make_es_repo()
    director = await _seed_world(repo)

    resolver = EntityResolver(repo, director)
    executor = EffectExecutor(repo, CapturingMemoryClient(), NoopChainMirror())

    canned: dict[str, ComprehendedFrame] = {
        "go on": ComprehendedFrame(
            predicate="move",
            roles=[FrameRole(role="location", filler="on")],
            matched=True,
            raw_text="go on",
        ),
    }
    comprehension = FakeComprehensionClient(canned)
    router = TurnRouter(
        comprehension,
        ConstructiconRegistry(),
        resolver,
        executor,
        "mm-world-v1",
        director=director,
        describe_client=TemplateDescribeClient(),
        repo=repo,
        activation_log=act_log,
    )

    # Snapshot Tx log length before the turn
    tx_before = len(tx_log._entries)  # noqa: SLF001

    outcome = await router.handle("go on", PLAYER)
    assert outcome["status"] == "executed", f"Expected executed, got: {outcome}"

    # 1. Exactly one ActivationRecord written for this turn
    act_records = act_log.for_actor(PLAYER)
    assert len(act_records) == 1, f"Expected 1 ActivationRecord, got {len(act_records)}"

    rec = act_records[0]

    # 2. activation_id is non-empty and not "genesis"
    assert rec.activation_id, "activation_id must be non-empty"
    assert rec.activation_id != "genesis", "activation_id must not be genesis"

    # 3. actor_id / tool / cxn_id populated correctly
    assert rec.actor_id == PLAYER
    assert rec.tool == "mm_move", f"Expected mm_move, got {rec.tool!r}"
    assert rec.cxn_id == "MOVE", f"Expected MOVE cxn_id, got {rec.cxn_id!r}"

    # 4. All Tx entries written THIS turn carry the same activation_id
    this_turn_entries = tx_log._entries[tx_before:]  # noqa: SLF001
    assert this_turn_entries, "Expected at least one Tx entry from the MOVE turn"
    for entry in this_turn_entries:
        assert entry.activation_id == rec.activation_id, (
            f"Tx entry activation_id {entry.activation_id!r} != "
            f"ActivationRecord activation_id {rec.activation_id!r}"
        )


@pytest.mark.asyncio
async def test_look_die_beat_stamped_with_turn_activation_id() -> None:
    """LOOK turn: the is_dead Tx Log write from apply_surface_beats is stamped with this turn's activation_id."""
    repo, tx_log, act_log = _make_es_repo()
    director = await _seed_world(repo)

    resolver = EntityResolver(repo, director)
    executor = EffectExecutor(repo, CapturingMemoryClient(), NoopChainMirror())

    canned: dict[str, ComprehendedFrame] = {
        "look around": ComprehendedFrame(
            predicate="look",
            roles=[],
            matched=True,
            raw_text="look around",
        ),
    }
    comprehension = FakeComprehensionClient(canned)
    router = TurnRouter(
        comprehension,
        ConstructiconRegistry(),
        resolver,
        executor,
        "mm-world-v1",
        director=director,
        describe_client=TemplateDescribeClient(),
        repo=repo,
        activation_log=act_log,
    )

    tx_before = len(tx_log._entries)  # noqa: SLF001

    outcome = await router.handle("look around", PLAYER)
    assert outcome["status"] == "narrated", f"Expected narrated, got: {outcome}"

    # One ActivationRecord for LOOK
    act_records = act_log.for_actor(PLAYER)
    assert len(act_records) == 1, f"Expected 1 ActivationRecord, got {len(act_records)}"
    rec = act_records[0]
    assert rec.activation_id != "genesis"
    assert rec.tool == "mm_look"
    assert rec.cxn_id == "LOOK"

    # The die-beat writes is_dead via repo.set_attr → set_top delta
    # That Tx entry must carry this turn's activation_id
    this_turn_entries = tx_log._entries[tx_before:]  # noqa: SLF001
    is_dead_entries = [
        e
        for e in this_turn_entries
        if any(
            delta.get("op") in ("set_top",) and delta.get("field") == "is_dead"
            for delta in e.deltas
        )
    ]
    assert is_dead_entries, (
        "Expected at least one Tx entry with set_top/is_dead from the LOOK die-beat"
    )
    for entry in is_dead_entries:
        assert entry.activation_id == rec.activation_id, (
            f"Die-beat Tx entry activation_id {entry.activation_id!r} != "
            f"ActivationRecord activation_id {rec.activation_id!r}"
        )


@pytest.mark.asyncio
async def test_successive_turns_get_distinct_activation_ids() -> None:
    """Two successive turns produce distinct activation_ids; context does not bleed."""
    repo, tx_log, act_log = _make_es_repo()
    director = await _seed_world(repo)

    resolver = EntityResolver(repo, director)
    executor = EffectExecutor(repo, CapturingMemoryClient(), NoopChainMirror())

    canned: dict[str, ComprehendedFrame] = {
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
    comprehension = FakeComprehensionClient(canned)
    router = TurnRouter(
        comprehension,
        ConstructiconRegistry(),
        resolver,
        executor,
        "mm-world-v1",
        director=director,
        describe_client=TemplateDescribeClient(),
        repo=repo,
        activation_log=act_log,
    )

    await router.handle("look around", PLAYER)
    await router.handle("go on", PLAYER)

    records = act_log.for_actor(PLAYER)
    assert len(records) == 2, f"Expected 2 ActivationRecords, got {len(records)}"

    act_id_1 = records[0].activation_id
    act_id_2 = records[1].activation_id
    assert act_id_1 != act_id_2, (
        "Successive turns must produce distinct activation_ids, "
        f"but both are {act_id_1!r}"
    )

    # After both turns, the repo's internal activation context must be cleared.
    assert repo._activation_id in ("", "genesis"), (  # noqa: SLF001
        f"Repo activation context not cleared after turn; got {repo._activation_id!r}"
    )
