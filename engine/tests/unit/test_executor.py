"""Unit tests for EffectExecutor — the 3-phase deterministic executor (C4).

No LLM, no NLP, no RNG. The executor is driven with a directly-constructed
MatchedCxn (cxn def + bound_roles of fixture UUIDs), per spec §8.4.

Doubles: InMemoryStateRepository + CapturingMemoryClient + RecordingChainMirror.

Fixtures match the spec §4.2 worked examples:
- Kael: Character/Player, str 3, in The Ash Market, Iron Sword (dmg 8) equipped main_hand
- Goblin: Character/NPC, hp 9, armor 2, in The Ash Market
- Iron Sword: Item/Weapon, damage 8
- Tattered Scroll: Item, on the floor at The Ash Market (onchain False)
"""
from __future__ import annotations

import pytest

from tests.fixtures import ASH_MARKET, GOBLIN, IRON_SWORD, KAEL, RIVER_GATE
from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.executor import EffectExecutor
from memento.cxn.types import ConstructionError
from memento.memory.capturing_client import CapturingMemoryClient
from memento.state.in_memory import InMemoryStateRepository
from memento.state.repository import EntityDoc, ItemDoc

TATTERED_SCROLL = "6650000000000000000000b2"  # non-onchain floor item


# ---------------------------------------------------------------------------
# RecordingChainMirror double
# ---------------------------------------------------------------------------


class RecordingChainMirror:
    """Records every chain call so tests can assert death/transfer firing."""

    def __init__(self) -> None:
        self.deaths: list[dict] = []
        self.transfers: list[dict] = []

    def on_character_death(
        self, character_id: str, cause: str, location_id: str, tick: int
    ) -> None:
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
# Fixture builders
# ---------------------------------------------------------------------------


def _make_kael(*, equip_sword: bool = True) -> EntityDoc:
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
            "inventory": [IRON_SWORD] if equip_sword else [],
            "equipped": {"main_hand": IRON_SWORD} if equip_sword else {},
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
        attrs={"hp": 9, "max_hp": 9, "strength": 1, "armor": 2, "inventory": [], "equipped": {}},
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


def _make_iron_sword(*, owner: str = KAEL) -> ItemDoc:
    return ItemDoc(
        uuid=IRON_SWORD,
        name="Iron Sword",
        kind="item",
        labels=["Item", "Weapon"],
        owner_uuid=owner,
        location_uuid=None,
        attrs={"damage": 8, "slot_type": "main_hand", "carryable": True, "onchain": True},
    )


def _make_tattered_scroll() -> ItemDoc:
    return ItemDoc(
        uuid=TATTERED_SCROLL,
        name="Tattered Scroll",
        kind="item",
        labels=["Item"],
        owner_uuid=None,
        location_uuid=ASH_MARKET,
        attrs={"carryable": True, "onchain": False},
    )


def _world(*, equip_sword: bool = True) -> InMemoryStateRepository:
    repo = InMemoryStateRepository()
    repo.seed_entity(_make_ash_market())
    repo.seed_entity(_make_river_gate())
    repo.seed_entity(_make_kael(equip_sword=equip_sword))
    repo.seed_entity(_make_goblin())
    repo.seed_item(_make_iron_sword())
    repo.seed_item(_make_tattered_scroll())
    return repo


def _executor(repo: InMemoryStateRepository, chain: RecordingChainMirror):
    mem = CapturingMemoryClient()
    return EffectExecutor(repo=repo, memory=mem, chain=chain), mem


# ---------------------------------------------------------------------------
# MOVE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_relocates_agent_and_captures_one_episode() -> None:
    repo = _world()
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    update = await ex.execute(
        CONSTRUCTION_REGISTRY["MOVE"],
        caller_id=KAEL,
        bindings={"location": RIVER_GATE},  # destination
    )

    # Location updated in the store and reflected in the StateUpdate.
    kael = await repo.get_entity(KAEL)
    assert kael is not None
    assert kael["location_uuid"] == RIVER_GATE
    assert update["location"] == RIVER_GATE

    # Exactly one episode captured, with the rendered destination name.
    assert len(mem.ingested) == 1
    assert mem.ingested[0]["content"] == "Kael moved to The River Gate."
    assert mem.ingested[0]["actor_id"] == KAEL

    # Exactly one delta — the move_entity relocation (I-12).
    deltas = update["state_deltas"]
    assert len(deltas) == 1
    move_delta = deltas[0]
    assert move_delta["op"] == "move_entity"
    assert move_delta["before"] == ASH_MARKET
    assert move_delta["after"] == RIVER_GATE
    # No chain firing for MOVE.
    assert chain.deaths == []
    assert chain.transfers == []


@pytest.mark.asyncio
async def test_move_rejects_when_no_exit() -> None:
    repo = _world()
    # Remove the exit so exit_exists fails.
    repo._entities[ASH_MARKET]["attrs"]["exits"] = []
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    with pytest.raises(ConstructionError) as exc:
        await ex.execute(
            CONSTRUCTION_REGISTRY["MOVE"], caller_id=KAEL, bindings={"location": RIVER_GATE}
        )
    assert "exit_exists" in str(exc.value)
    # No write happened.
    kael = await repo.get_entity(KAEL)
    assert kael is not None
    assert kael["location_uuid"] == ASH_MARKET
    assert mem.ingested == []


# ---------------------------------------------------------------------------
# ATTACK — death sub-case (exact arithmetic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attack_kills_goblin_exact_hp_and_fires_chain_kill() -> None:
    repo = _world()
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    update = await ex.execute(
        CONSTRUCTION_REGISTRY["ATTACK"],
        caller_id=KAEL,
        bindings={"patient": GOBLIN, "instrument": IRON_SWORD},
    )

    # damage = max(0, 8 + 3 - 2) = 9; hp 9 -> 0 EXACT.
    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    assert goblin["attrs"]["hp"] == 0
    assert goblin["is_dead"] is True

    # DIED_IN link to the agent's current room (Ash Market).
    links = goblin["attrs"].get("links", {})
    assert ASH_MARKET in links.get("DIED_IN", [])

    # hp delta 9 -> 0 exact.
    deltas = update["state_deltas"]
    assert any(
        d["op"] == "set_attr" and d["field"] == "hp" and d["before"] == 9 and d["after"] == 0
        for d in deltas
    )

    # chain_kill captured: no killer_id, cause combat, location = Ash Market.
    assert len(chain.deaths) == 1
    death = chain.deaths[0]
    assert death["character_id"] == GOBLIN
    assert death["cause"] == "combat"
    assert death["location_id"] == ASH_MARKET
    assert "killer_id" not in death

    # CombatEvent surfaced on the StateUpdate.
    assert update["events"]["combat"]["damage_dealt"] == 9
    assert update["events"]["combat"]["target_dead"] is True

    # Episode rendered with damage + death suffix.
    assert len(mem.ingested) == 1
    # death_suffix (§4.2) is " — {patient_name} has died" (NO trailing period);
    # the episode template's own "." terminates the sentence — single period.
    assert mem.ingested[0]["content"] == (
        "Kael attacked Goblin Scout with Iron Sword for 9 damage"
        " — Goblin Scout has died."
    )


@pytest.mark.asyncio
async def test_attack_defaults_instrument_from_equipped() -> None:
    """When instrument omitted, the equipped main-hand weapon is resolved."""
    repo = _world()
    chain = RecordingChainMirror()
    ex, _ = _executor(repo, chain)

    update = await ex.execute(
        CONSTRUCTION_REGISTRY["ATTACK"],
        caller_id=KAEL,
        bindings={"patient": GOBLIN},  # no instrument
    )
    # Same lethal outcome via the equipped sword.
    goblin = await repo.get_entity(GOBLIN)
    assert goblin is not None
    assert goblin["attrs"]["hp"] == 0
    assert update["events"]["combat"]["damage_dealt"] == 9


# ---------------------------------------------------------------------------
# TAKE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_moves_item_to_agent_off_floor() -> None:
    repo = _world()
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    update = await ex.execute(
        CONSTRUCTION_REGISTRY["TAKE"],
        caller_id=KAEL,
        bindings={"patient": TATTERED_SCROLL},
    )

    scroll = await repo.get_entity(TATTERED_SCROLL)
    assert scroll is not None
    assert scroll["owner_uuid"] == KAEL
    assert scroll["location_uuid"] is None

    # Off the floor.
    ash = await repo.get_entity(ASH_MARKET)
    assert ash is not None
    assert TATTERED_SCROLL not in ash["attrs"].get("item_ids", [])

    # In Kael's inventory.
    kael = await repo.get_entity(KAEL)
    assert kael is not None
    assert TATTERED_SCROLL in kael["attrs"]["inventory"]

    # transfer_item delta to agent — from the floor (before owner None).
    deltas = update["state_deltas"]
    assert any(
        d["op"] == "transfer_item"
        and d["target_uuid"] == TATTERED_SCROLL
        and d["before"] is None
        and d["after"] == KAEL
        for d in deltas
    )

    # Scroll is NOT onchain -> no chain transfer.
    assert chain.transfers == []

    # Inventory event + one episode.
    assert update["events"]["inventory_changes"][0]["event_type"] == "PICKUP"
    assert len(mem.ingested) == 1
    assert mem.ingested[0]["content"] == "Kael picked up Tattered Scroll from The Ash Market."


@pytest.mark.asyncio
async def test_take_onchain_item_fires_chain_transfer() -> None:
    """An onchain floor item fires the chain_transfer mirror."""
    repo = _world()
    # Drop the Iron Sword (onchain True) onto the floor.
    sword = repo._items[IRON_SWORD]
    sword["owner_uuid"] = None
    sword["location_uuid"] = ASH_MARKET
    repo._entities[ASH_MARKET]["attrs"]["item_ids"].append(IRON_SWORD)
    # Unequip from Kael so capacity/inventory is clean.
    repo._entities[KAEL]["attrs"]["inventory"] = []
    repo._entities[KAEL]["attrs"]["equipped"] = {}

    chain = RecordingChainMirror()
    ex, _ = _executor(repo, chain)

    await ex.execute(
        CONSTRUCTION_REGISTRY["TAKE"], caller_id=KAEL, bindings={"patient": IRON_SWORD}
    )

    assert len(chain.transfers) == 1
    assert chain.transfers[0]["item_id"] == IRON_SWORD
    assert chain.transfers[0]["new_owner_id"] == KAEL


# ---------------------------------------------------------------------------
# Guard failure — unarmed agent, NO writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attack_unarmed_agent_raises_before_any_write() -> None:
    repo = _world(equip_sword=False)
    # No equipped weapon and no instrument passed -> agent_armed fails.
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    goblin_before = await repo.get_entity(GOBLIN)
    assert goblin_before is not None
    hp_before = goblin_before["attrs"]["hp"]

    with pytest.raises(ConstructionError) as exc:
        await ex.execute(
            CONSTRUCTION_REGISTRY["ATTACK"], caller_id=KAEL, bindings={"patient": GOBLIN}
        )
    assert "agent_armed" in str(exc.value)

    # Store untouched: goblin hp unchanged, not dead, no episode, no chain.
    goblin_after = await repo.get_entity(GOBLIN)
    assert goblin_after is not None
    assert goblin_after["attrs"]["hp"] == hp_before
    assert goblin_after["is_dead"] is False
    assert mem.ingested == []
    assert chain.deaths == []


@pytest.mark.asyncio
async def test_take_guard_failure_non_carryable_raises_no_write() -> None:
    """A non-carryable item fails the item_carryable guard with NO write (I-14)."""
    repo = _world()
    # Pin the scroll to the floor but mark it non-carryable.
    repo._items[TATTERED_SCROLL]["attrs"]["carryable"] = False
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    with pytest.raises(ConstructionError) as exc:
        await ex.execute(
            CONSTRUCTION_REGISTRY["TAKE"], caller_id=KAEL, bindings={"patient": TATTERED_SCROLL}
        )
    assert "item_carryable" in str(exc.value)

    # No write: scroll still on the floor (owner None), no episode captured.
    scroll = await repo.get_entity(TATTERED_SCROLL)
    assert scroll is not None
    assert scroll["owner_uuid"] is None
    assert scroll["location_uuid"] == ASH_MARKET
    assert mem.ingested == []
    assert chain.transfers == []


# ---------------------------------------------------------------------------
# transfer_item rollback (§3.3) — a later transactional primitive fails after
# the pickup, and the item is restored to the floor (C-1).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_item_rollback_restores_item_to_floor() -> None:
    """When a transactional op AFTER transfer_item fails, the item is restored.

    Drives a TAKE-like CxnDef whose effect_template runs transfer_item (scroll
    floor -> Kael) then a set_attr against a non-existent UUID, which raises in
    Phase 2. The §3.3 compensation must put the scroll back on the floor with
    owner_uuid None and location_uuid == the original room.
    """
    from copy import deepcopy

    from memento.cxn.types import StatePrimitive

    repo = _world()
    chain = RecordingChainMirror()
    ex, mem = _executor(repo, chain)

    MISSING_UUID = "6650000000000000000000ff"  # not seeded -> set_attr raises

    # A TAKE-shaped cxn: pickup then a guaranteed-failing transactional op.
    broken_cxn = deepcopy(CONSTRUCTION_REGISTRY["TAKE"])
    broken_cxn["chain_mirror"] = False  # isolate the rollback path from chain
    broken_cxn["effect_template"] = [
        StatePrimitive(
            substrate="transactional",
            op="transfer_item",
            args={
                "item_uuid": "$patient",
                "from_uuid": "$location",
                "to_uuid": "$agent",
                "to_location_uuid": None,
            },
            if_condition=None,
        ),
        StatePrimitive(
            substrate="transactional",
            op="set_attr",
            args={"uuid": MISSING_UUID, "field": "hp", "value": 0},
            if_condition=None,
        ),
    ]

    with pytest.raises(ConstructionError) as exc:
        await ex.execute(broken_cxn, caller_id=KAEL, bindings={"patient": TATTERED_SCROLL})
    assert "transactional_failed" in str(exc.value)

    # Compensation restored the scroll to the floor: owner None, original room.
    scroll = await repo.get_entity(TATTERED_SCROLL)
    assert scroll is not None
    assert scroll["owner_uuid"] is None
    assert scroll["location_uuid"] == ASH_MARKET

    # Off Kael's inventory, back in the room's item_ids.
    kael = await repo.get_entity(KAEL)
    assert kael is not None
    assert TATTERED_SCROLL not in kael["attrs"].get("inventory", [])
    ash = await repo.get_entity(ASH_MARKET)
    assert ash is not None
    assert TATTERED_SCROLL in ash["attrs"].get("item_ids", [])

    # No episode (Phase 3 never runs after a Phase-2 failure).
    assert mem.ingested == []
