"""Day-1 vertical-slice integration test (spec §8.4 / §4.2).

Drives the three constructions (MOVE / ATTACK / TAKE) end-to-end through the
real EffectExecutor against InMemoryStateRepository, with NO NLP and NO
PatternComprehensionClient: each test builds a MatchedCxn directly from the
registry + a bound_roles dict of fixture UUIDs (spec §8.4), then calls
``executor.execute(cxn, caller_id, bindings)``.

Substrates:
  state   -> InMemoryStateRepository (dict-backed, default store)
  memory  -> CapturingMemoryClient   (records episodes for assertions)
  chain   -> RecordingChainMirror     (records chain_kill / chain_transfer)
            / NoopChainMirror          (where chain is irrelevant: MOVE)

All assertions are over exact values from the §4.2 worked examples:
  - damage == 9, Goblin hp 9 -> 0 exactly, is_dead True
  - chain_kill character_id == GOBLIN, cause "combat", NO killer_id
"""
from __future__ import annotations

from typing import Any

from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.executor import EffectExecutor
from memento.cxn.types import MatchedCxn
from memento.memory.capturing_client import CapturingMemoryClient
from memento.state.chain_mirror import NoopChainMirror
from memento.state.in_memory import InMemoryStateRepository

from tests.fixtures import (
    ASH_MARKET,
    GOBLIN,
    IRON_SWORD,
    KAEL,
    RIVER_GATE,
    SCROLL,
    character_doc,
    item_doc,
    location_doc,
)


# ---------------------------------------------------------------------------
# RecordingChainMirror — a ChainMirror test double that captures every call.
# ---------------------------------------------------------------------------


class RecordingChainMirror:
    """Records on_character_death / on_item_transferred calls for assertions.

    Satisfies the ChainMirror Protocol. Must NOT raise (gameplay continues).
    """

    def __init__(self) -> None:
        self.deaths: list[dict[str, Any]] = []
        self.transfers: list[dict[str, Any]] = []

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
        # NOTE: signature carries NO killer_id (spec §6.3 / chain.py record_death).
        self.deaths.append(
            {
                "character_id": character_id,
                "cause": cause,
                "location_id": location_id,
                "tick": tick,
            }
        )

    def on_item_transferred(self, item_id: str, new_owner_id: str) -> None:
        self.transfers.append({"item_id": item_id, "new_owner_id": new_owner_id})


# ---------------------------------------------------------------------------
# Seed helpers — the §4.2 worked-example world.
# ---------------------------------------------------------------------------


def _seed_world() -> InMemoryStateRepository:
    """Build the §4.2 worked-example world: Kael, Goblin, Iron Sword, scroll, rooms."""
    repo = InMemoryStateRepository()

    # Locations — ASH_MARKET has an exit to RIVER_GATE.
    repo.seed_entity(
        location_doc(
            ASH_MARKET,
            "The Ash Market",
            exits=[{"direction": "north", "target_uuid": RIVER_GATE}],
        )
    )
    repo.seed_entity(location_doc(RIVER_GATE, "The River Gate"))

    # Kael — Character in ASH_MARKET, strength 3, hp set, equipped main-hand = Iron Sword.
    repo.seed_entity(
        character_doc(
            KAEL,
            "Kael",
            ASH_MARKET,
            labels=["Character"],
            strength=3,
            hp=20,
            max_hp=20,
            equipped={"main_hand": IRON_SWORD},
            inventory=[],
        )
    )

    # Goblin — Character in ASH_MARKET, hp 9, armor 2, NOT Dead.
    repo.seed_entity(
        character_doc(
            GOBLIN,
            "Goblin",
            ASH_MARKET,
            labels=["Character"],
            hp=9,
            armor=2,
        )
    )

    # Iron Sword — Item + Weapon, damage 8, owned by Kael.
    repo.seed_item(
        item_doc(
            IRON_SWORD,
            "Iron Sword",
            labels=["Item", "Weapon"],
            owner_uuid=KAEL,
            damage=8,
        )
    )

    # Tattered Scroll — carryable item on the ASH_MARKET floor, onchain=False.
    repo.seed_item(
        item_doc(
            SCROLL,
            "Tattered Scroll",
            labels=["Item"],
            owner_uuid=None,
            location_uuid=ASH_MARKET,
            carryable=True,
            onchain=False,
        )
    )

    return repo


# ---------------------------------------------------------------------------
# MOVE — Kael -> RIVER_GATE
# ---------------------------------------------------------------------------


async def test_move_relocates_kael_and_ingests_episode():
    repo = _seed_world()
    memory = CapturingMemoryClient()
    chain = NoopChainMirror()  # MOVE has no chain step (position not permadeath-critical)
    executor = EffectExecutor(repo, memory, chain)

    matched = MatchedCxn(
        cxn=CONSTRUCTION_REGISTRY["MOVE"],
        bound_roles={"agent": KAEL, "location": RIVER_GATE},
    )
    await executor.execute(
        matched["cxn"], caller_id=KAEL, bindings=matched["bound_roles"]
    )

    kael = await repo.get_entity(KAEL)
    assert kael is not None
    assert kael["location_uuid"] == RIVER_GATE

    assert len(memory.ingested) == 1
    content = memory.ingested[0]["content"]
    assert content == "Kael moved to The River Gate."
    assert content.startswith("Kael moved to")


# ---------------------------------------------------------------------------
# ATTACK — Kael -> Goblin (instrument Iron Sword), death sub-case
# ---------------------------------------------------------------------------


async def test_attack_kills_goblin_with_exact_deltas_and_chain_kill():
    repo = _seed_world()
    memory = CapturingMemoryClient()
    chain = RecordingChainMirror()
    executor = EffectExecutor(repo, memory, chain)

    matched = MatchedCxn(
        cxn=CONSTRUCTION_REGISTRY["ATTACK"],
        bound_roles={"patient": GOBLIN, "instrument": IRON_SWORD},
    )
    result = await executor.execute(
        matched["cxn"], caller_id=KAEL, bindings=matched["bound_roles"]
    )

    # Deterministic damage: max(0, 8 + 3 - 2) == 9.
    deltas = {(d["op"], d["target_uuid"], d["field"]): d for d in result["state_deltas"]}
    hp_delta = deltas[("set_attr", GOBLIN, "hp")]
    assert hp_delta["before"] == 9
    assert hp_delta["after"] == 0  # exact: clamp_hp(9, 9) == 0

    # Goblin state: hp 0, dead, DIED_IN link to its room (ASH_MARKET).
    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    assert goblin["attrs"]["hp"] == 0
    assert goblin["is_dead"] is True
    died_in = goblin["attrs"].get("links", {}).get("DIED_IN", [])
    assert ASH_MARKET in died_in

    # Chain mirror recorded exactly one death: GOBLIN, cause "combat", NO killer_id.
    assert len(chain.deaths) == 1
    death = chain.deaths[0]
    assert death["character_id"] == GOBLIN
    assert death["cause"] == "combat"
    assert death["location_id"] == ASH_MARKET
    assert "killer_id" not in death

    # Episode text carries the exact damage and the death suffix.
    assert len(memory.ingested) == 1
    content = memory.ingested[0]["content"]
    assert "for 9 damage" in content
    assert "has died" in content


# ---------------------------------------------------------------------------
# TAKE — Kael <- scroll
# ---------------------------------------------------------------------------


async def test_take_moves_scroll_to_kael_off_the_floor():
    repo = _seed_world()
    memory = CapturingMemoryClient()
    chain = RecordingChainMirror()
    executor = EffectExecutor(repo, memory, chain)

    matched = MatchedCxn(
        cxn=CONSTRUCTION_REGISTRY["TAKE"],
        bound_roles={"patient": SCROLL},
    )
    await executor.execute(
        matched["cxn"], caller_id=KAEL, bindings=matched["bound_roles"]
    )

    scroll = await repo.get_entity(SCROLL)
    assert scroll is not None
    assert scroll["owner_uuid"] == KAEL          # now owned by Kael
    assert scroll["location_uuid"] is None        # off the floor
    assert SCROLL not in repo._entities[ASH_MARKET]["attrs"].get("item_ids", [])

    # Scroll is onchain=False -> chain step skipped (patient_onchain is false).
    assert chain.transfers == []

    assert len(memory.ingested) == 1
    content = memory.ingested[0]["content"]
    assert content == "Kael picked up Tattered Scroll from The Ash Market."
    assert content.startswith("Kael picked up")
