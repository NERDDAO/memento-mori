"""Unit tests for TurnRouter — Task 3, M2 ATTACK vertical slice.

No NLP, no LLM, no HTTP.  ComprehensionClient is faked via
FakeComprehensionClient; the real EffectExecutor runs over
InMemoryStateRepository + CapturingMemoryClient + NoopChainMirror.

Fixture world mirrors test_executor.py exactly:
  Kael  — player character in The Ash Market, Iron Sword equipped
  Goblin — NPC in The Ash Market, hp=9, armor=2
  Iron Sword — damage=8, in Kael's inventory (equipped main_hand)
"""

from __future__ import annotations

import pytest

from tests.fixtures import ASH_MARKET, GOBLIN, IRON_SWORD, KAEL, RIVER_GATE
from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.kernel_client import FakeComprehensionClient
from memento.cxn.turn_router import TurnRouter
from memento.cxn.types import ComprehendedFrame, FrameRole
from memento.memory.capturing_client import CapturingMemoryClient
from memento.state.chain_mirror import NoopChainMirror
from memento.state.in_memory import InMemoryStateRepository
from memento.state.repository import EntityDoc, ItemDoc


# ---------------------------------------------------------------------------
# Fixture world builders — mirror test_executor.py §4.2 worked example
# ---------------------------------------------------------------------------

TATTERED_SCROLL = "6650000000000000000000b2"


def _make_kael() -> EntityDoc:
    return EntityDoc(
        uuid=KAEL,
        name="Kael",
        kind="character",
        labels=["Character", "Player"],
        location_uuid=ASH_MARKET,
        attrs={
            "hp": 20,
            "max_hp": 20,
            "strength": 3,
            "armor": 1,
            "inventory": [IRON_SWORD],
            "equipped": {"main_hand": IRON_SWORD},
        },
        is_dead=False,
    )


def _make_goblin() -> EntityDoc:
    return EntityDoc(
        uuid=GOBLIN,
        name="Goblin Scout",
        kind="character",
        labels=["Character", "NPC"],
        location_uuid=ASH_MARKET,
        attrs={
            "hp": 9,
            "max_hp": 9,
            "strength": 1,
            "armor": 2,
            "inventory": [],
            "equipped": {},
        },
        is_dead=False,
    )


def _make_ash_market() -> EntityDoc:
    return EntityDoc(
        uuid=ASH_MARKET,
        name="The Ash Market",
        kind="location",
        labels=["Location"],
        location_uuid=None,
        attrs={
            "description": "A smoky bazaar.",
            "item_ids": [TATTERED_SCROLL],
            "exits": [{"direction": "north", "target_uuid": RIVER_GATE, "locked": False}],
        },
        is_dead=False,
    )


def _make_river_gate() -> EntityDoc:
    return EntityDoc(
        uuid=RIVER_GATE,
        name="The River Gate",
        kind="location",
        labels=["Location"],
        location_uuid=None,
        attrs={
            "description": "The northern gate.",
            "item_ids": [],
            "exits": [{"direction": "south", "target_uuid": ASH_MARKET, "locked": False}],
        },
        is_dead=False,
    )


def _make_iron_sword() -> ItemDoc:
    return ItemDoc(
        uuid=IRON_SWORD,
        name="Iron Sword",
        kind="item",
        labels=["Item", "Weapon"],
        owner_uuid=KAEL,
        location_uuid=None,
        attrs={"damage": 8, "slot_type": "main_hand", "carryable": True, "onchain": True},
    )


def _make_scroll() -> ItemDoc:
    return ItemDoc(
        uuid=TATTERED_SCROLL,
        name="Tattered Scroll",
        kind="item",
        labels=["Item"],
        owner_uuid=None,
        location_uuid=ASH_MARKET,
        attrs={"carryable": True, "onchain": False},
    )


def _world() -> InMemoryStateRepository:
    repo = InMemoryStateRepository()
    repo.seed_entity(_make_ash_market())
    repo.seed_entity(_make_river_gate())
    repo.seed_entity(_make_kael())
    repo.seed_entity(_make_goblin())
    repo.seed_item(_make_iron_sword())
    repo.seed_item(_make_scroll())
    return repo


def _router(
    fake_client: FakeComprehensionClient,
    repo: InMemoryStateRepository,
    mem: CapturingMemoryClient,
) -> TurnRouter:
    constructicon = ConstructiconRegistry()
    resolver = EntityResolver(repo)
    executor = EffectExecutor(repo=repo, memory=mem, chain=NoopChainMirror())
    return TurnRouter(
        comprehension=fake_client,
        constructicon=constructicon,
        resolver=resolver,
        executor=executor,
        bonfire_id="mm-world-v1",
    )


# ---------------------------------------------------------------------------
# (a) Fully-resolved attack frame → executed with hp 9→0 and 1 episode
# ---------------------------------------------------------------------------


async def test_attack_frame_executes_kills_goblin() -> None:
    """Canned attack frame with resolvable roles → status==executed, hp 9→0."""
    repo = _world()
    mem = CapturingMemoryClient()

    # Frame from kernel: predicate=attack, roles resolved to surface fillers
    canned_frame = ComprehendedFrame(
        predicate="attack",
        roles=[
            FrameRole(role="patient", filler="the goblin"),
            FrameRole(role="instrument", filler="iron sword"),
        ],
        matched=True,
        raw_text="attack the goblin with iron sword",
    )
    fake_client = FakeComprehensionClient(
        {"attack the goblin with iron sword": canned_frame}
    )

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("attack the goblin with iron sword", KAEL)

    assert outcome["status"] == "executed"
    assert outcome["update"] is not None

    update = outcome["update"]
    # hp delta: 9 → 0  (damage = max(0, 8+3-2) = 9, exactly depletes)
    deltas = update["state_deltas"]
    assert any(
        d["op"] == "set_attr"
        and d["field"] == "hp"
        and d["before"] == 9
        and d["after"] == 0
        for d in deltas
    ), f"Expected hp 9→0 delta in {deltas}"

    # Exactly 1 episode captured
    assert len(mem.ingested) == 1

    # Goblin is now dead
    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    assert goblin["attrs"]["hp"] == 0
    assert goblin["is_dead"] is True


# ---------------------------------------------------------------------------
# (a-death) Death sub-case: is_dead, DIED_IN link, chain kill
# ---------------------------------------------------------------------------


async def test_attack_death_subcase_sets_is_dead_and_died_in() -> None:
    """Death path: goblin.is_dead=True, DIED_IN link to ASH_MARKET, damage_dealt=9."""
    repo = _world()
    mem = CapturingMemoryClient()

    canned_frame = ComprehendedFrame(
        predicate="attack",
        roles=[
            FrameRole(role="patient", filler="goblin"),
            FrameRole(role="instrument", filler="iron sword"),
        ],
        matched=True,
        raw_text="attack goblin with iron sword",
    )
    fake_client = FakeComprehensionClient(
        {"attack goblin with iron sword": canned_frame}
    )

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("attack goblin with iron sword", KAEL)

    assert outcome["status"] == "executed"
    update = outcome["update"]
    assert update is not None

    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    assert goblin["is_dead"] is True
    # DIED_IN link to The Ash Market
    links = goblin["attrs"].get("links", {})
    assert ASH_MARKET in links.get("DIED_IN", []), f"Missing DIED_IN link: {links}"

    # Combat event
    assert update["events"]["combat"]["damage_dealt"] == 9
    assert update["events"]["combat"]["target_dead"] is True


# ---------------------------------------------------------------------------
# (b) matched=False frame → clarify with reason=="no_match", store untouched
# ---------------------------------------------------------------------------


async def test_no_match_frame_returns_clarify_no_match() -> None:
    """Kernel returns matched=False → TurnRouter returns clarify/no_match, no writes."""
    repo = _world()
    mem = CapturingMemoryClient()

    canned_frame = ComprehendedFrame(
        predicate="",
        roles=[],
        matched=False,
        raw_text="blorp florp",
    )
    fake_client = FakeComprehensionClient({"blorp florp": canned_frame})

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("blorp florp", KAEL)

    assert outcome["status"] == "clarify"
    assert outcome["reason"] == "no_match"
    assert outcome["message"] is not None  # player-facing string

    # Store untouched: 0 ingests
    assert mem.ingested == []


# ---------------------------------------------------------------------------
# (c) frame predicate "sing" → no cxn → clarify with reason=="unknown_predicate"
# ---------------------------------------------------------------------------


async def test_unknown_predicate_returns_clarify() -> None:
    """Matched frame whose predicate has no registered cxn → clarify/unknown_predicate."""
    repo = _world()
    mem = CapturingMemoryClient()

    canned_frame = ComprehendedFrame(
        predicate="sing",
        roles=[],
        matched=True,
        raw_text="sing a song",
    )
    fake_client = FakeComprehensionClient({"sing a song": canned_frame})

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("sing a song", KAEL)

    assert outcome["status"] == "clarify"
    assert outcome["reason"] == "unknown_predicate"
    assert outcome["message"] is not None

    # Store untouched
    assert mem.ingested == []


# ---------------------------------------------------------------------------
# (d) patient unresolvable → clarify with reason=="unresolved_role:patient"
# ---------------------------------------------------------------------------


async def test_unresolvable_patient_returns_clarify() -> None:
    """patient filler 'the dragon' not in room → clarify/unresolved_role:patient, no writes."""
    repo = _world()
    mem = CapturingMemoryClient()

    canned_frame = ComprehendedFrame(
        predicate="attack",
        roles=[
            FrameRole(role="patient", filler="the dragon"),
        ],
        matched=True,
        raw_text="attack the dragon",
    )
    fake_client = FakeComprehensionClient({"attack the dragon": canned_frame})

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("attack the dragon", KAEL)

    assert outcome["status"] == "clarify"
    assert outcome["reason"] == "unresolved_role:patient"
    assert outcome["message"] is not None

    # Store untouched: 0 ingests
    assert mem.ingested == []


# ---------------------------------------------------------------------------
# (e) patient filler matches TWO entities → clarify with reason=="ambiguous_role:patient"
# ---------------------------------------------------------------------------

# A second goblin-type NPC for the ambiguity test only
_GOBLIN_SENTINEL = "6650000000000000000000a3"


async def test_ambiguous_patient_returns_clarify() -> None:
    """Two room entities both match filler 'goblin' → clarify/ambiguous_role:patient, no writes."""
    repo = _world()
    mem = CapturingMemoryClient()

    # Seed a second goblin in the same room so EntityResolver sees two matches
    goblin_sentinel = EntityDoc(
        uuid=_GOBLIN_SENTINEL,
        name="Goblin Sentinel",
        kind="character",
        labels=["Character", "NPC"],
        location_uuid=ASH_MARKET,
        attrs={
            "hp": 7,
            "max_hp": 7,
            "strength": 1,
            "armor": 1,
            "inventory": [],
            "equipped": {},
        },
        is_dead=False,
    )
    repo.seed_entity(goblin_sentinel)

    # Filler "goblin" is a substring of both "Goblin Scout" and "Goblin Sentinel"
    canned_frame = ComprehendedFrame(
        predicate="attack",
        roles=[
            FrameRole(role="patient", filler="goblin"),
        ],
        matched=True,
        raw_text="attack goblin",
    )
    fake_client = FakeComprehensionClient({"attack goblin": canned_frame})

    router = _router(fake_client, repo, mem)
    outcome = await router.handle("attack goblin", KAEL)

    assert outcome["status"] == "clarify"
    assert outcome["reason"] == "ambiguous_role:patient"
    assert outcome["update"] is None

    # Store untouched: 0 ingests
    assert mem.ingested == []
