"""Unit tests for EntityResolver (Task 2 — M2 ATTACK slice).

No NLP, no LLM, no HTTP. Resolution is purely over InMemoryStateRepository
seeded with fixtures from tests/fixtures.py.

Scenario: Kael (player) in ASH_MARKET; Goblin NPC in ASH_MARKET; Iron Sword
in Kael's inventory.
"""

from __future__ import annotations


from tests.fixtures import (
    ASH_MARKET,
    GOBLIN,
    IRON_SWORD,
    KAEL,
    character_doc,
    item_doc,
    location_doc,
)
from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.types import ComprehendedFrame
from memento.state.in_memory import InMemoryStateRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTACK_CXN = CONSTRUCTION_REGISTRY["ATTACK"]


def _frame(roles: list[dict[str, str]]) -> ComprehendedFrame:
    return {
        "predicate": "attack",
        "roles": [{"role": r["role"], "filler": r["filler"]} for r in roles],
        "matched": True,
        "raw_text": "attack something",
    }


def _make_repo() -> InMemoryStateRepository:
    """Seed: KAEL (player) in ASH_MARKET with IRON_SWORD; GOBLIN NPC in ASH_MARKET."""
    repo = InMemoryStateRepository()
    repo.seed_entity(location_doc(ASH_MARKET, "The Ash Market"))
    repo.seed_entity(
        character_doc(
            KAEL,
            "Kael",
            ASH_MARKET,
            labels=["Character", "Player"],
            hp=20,
            max_hp=20,
            strength=3,
            inventory=[IRON_SWORD],
            equipped={"main_hand": IRON_SWORD},
        )
    )
    repo.seed_entity(
        character_doc(
            GOBLIN,
            "Goblin Sentinel",
            ASH_MARKET,
            labels=["Character", "NPC"],
            hp=9,
            max_hp=9,
            armor=2,
        )
    )
    repo.seed_item(
        item_doc(
            IRON_SWORD,
            "Iron Sword",
            labels=["Item", "Weapon"],
            owner_uuid=KAEL,
            location_uuid=None,
            damage=8,
            slot_type="main_hand",
        )
    )
    return repo


# ---------------------------------------------------------------------------
# Case (a): patient + instrument both resolve
# ---------------------------------------------------------------------------


async def test_resolve_patient_and_instrument() -> None:
    """frame with patient:'the goblin', instrument:'the iron sword' → UUIDs."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    frame = _frame(
        [
            {"role": "patient", "filler": "the goblin"},
            {"role": "instrument", "filler": "the iron sword"},
        ]
    )

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert not isinstance(result, dict) or "reason" not in result, (
        f"Expected UUIDs, got failure: {result}"
    )
    assert isinstance(result, dict)
    assert result["patient"] == GOBLIN
    assert result["instrument"] == IRON_SWORD
    # agent / location NOT filled here — executor's job
    assert "agent" not in result
    assert "location" not in result


# ---------------------------------------------------------------------------
# Case (b): absent patient → unresolved_role:patient
# ---------------------------------------------------------------------------


async def test_resolve_absent_patient_returns_unresolved() -> None:
    """patient filler 'the dragon' doesn't exist in the room → unresolved."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    frame = _frame([{"role": "patient", "filler": "the dragon"}])

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert isinstance(result, dict)
    assert "reason" in result
    assert result["reason"] == "unresolved_role:patient"


# ---------------------------------------------------------------------------
# Case (c): two goblins in room → ambiguous_role:patient
# ---------------------------------------------------------------------------

GOBLIN_2 = "6650000000000000000000a9"


async def test_resolve_ambiguous_patient_returns_ambiguous() -> None:
    """Two goblins in the room → ambiguous when frame says 'goblin'."""
    repo = _make_repo()
    repo.seed_entity(
        character_doc(
            GOBLIN_2,
            "Goblin Scout",
            ASH_MARKET,
            labels=["Character", "NPC"],
            hp=5,
            max_hp=5,
        )
    )
    resolver = EntityResolver(repo)

    frame = _frame([{"role": "patient", "filler": "goblin"}])

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert isinstance(result, dict)
    assert "reason" in result
    assert result["reason"] == "ambiguous_role:patient"


# ---------------------------------------------------------------------------
# Case (d): actor itself is never a patient candidate
# ---------------------------------------------------------------------------


async def test_actor_not_a_patient_candidate() -> None:
    """Filler that would match the actor itself should return unresolved, not ambiguous."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    # "Kael" is KAEL's own name; should not be resolvable as patient
    frame = _frame([{"role": "patient", "filler": "kael"}])

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert isinstance(result, dict)
    assert "reason" in result
    assert result["reason"] == "unresolved_role:patient"


# ---------------------------------------------------------------------------
# Case (e): bare token without article
# ---------------------------------------------------------------------------


async def test_resolve_bare_token_no_article() -> None:
    """Bare filler 'goblin' (no 'the') still resolves by substring."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    frame = _frame([{"role": "patient", "filler": "goblin"}])

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    # Should resolve because only one goblin in room
    assert isinstance(result, dict)
    assert "reason" not in result
    assert result["patient"] == GOBLIN


# ---------------------------------------------------------------------------
# Case (f): instrument filler absent from inventory → unresolved_role:instrument
# ---------------------------------------------------------------------------


async def test_resolve_missing_instrument_returns_unresolved() -> None:
    """instrument filler 'magic staff' not in inventory → unresolved."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    frame = _frame(
        [
            {"role": "patient", "filler": "the goblin"},
            {"role": "instrument", "filler": "magic staff"},
        ]
    )

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert isinstance(result, dict)
    assert "reason" in result
    assert result["reason"] == "unresolved_role:instrument"


# ---------------------------------------------------------------------------
# Case (g): no instrument in frame → only patient resolved; instrument absent
# ---------------------------------------------------------------------------


async def test_resolve_patient_only_no_instrument_key() -> None:
    """When frame has no instrument role, resolver returns only patient UUID."""
    repo = _make_repo()
    resolver = EntityResolver(repo)

    frame = _frame([{"role": "patient", "filler": "goblin"}])

    result = await resolver.resolve(frame, KAEL, ATTACK_CXN)

    assert isinstance(result, dict)
    assert "reason" not in result
    assert result["patient"] == GOBLIN
    assert "instrument" not in result
