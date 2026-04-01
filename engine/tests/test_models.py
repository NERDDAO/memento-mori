import pytest
from memento.models import (
    EntityRef,
    CharacterStats,
    Disposition,
    Character,
    Exit,
    Location,
    Region,
    Item,
    Faction,
    Quest,
)


def test_entity_ref_creation():
    ref = EntityRef(uuid="abc-123", name="Aragorn", labels=["hero", "ranger"])
    assert ref.uuid == "abc-123"
    assert ref.name == "Aragorn"
    assert ref.labels == ["hero", "ranger"]


def test_entity_ref_defaults():
    ref = EntityRef(uuid="xyz", name="Nobody")
    assert ref.labels == []


def test_character_stats_defaults():
    stats = CharacterStats()
    assert stats.level == 1
    assert stats.health == 100
    assert stats.max_health == 100
    assert stats.experience == 0
    assert stats.currency == 0
    assert stats.attributes == {}


def test_disposition_defaults():
    d = Disposition()
    assert d.friendship == 0.0
    assert d.trust == 0.0
    assert d.respect == 0.0
    assert d.romance == 0.0


def test_character_full():
    ref = EntityRef(uuid="c-1", name="Elara", labels=["pc"])
    char = Character(
        ref=ref,
        stats=CharacterStats(level=5, health=80, currency=50),
        personality_type="brave",
        personality_traits=["loyal", "stubborn"],
        skills={"sword": 3, "stealth": 2},
        abilities=["parry", "dodge"],
        inventory=[EntityRef(uuid="i-1", name="Sword")],
        equipped={"main_hand": EntityRef(uuid="i-1", name="Sword")},
        status_effects=["poisoned"],
        dispositions={"npc-1": Disposition(friendship=0.5, trust=0.3)},
        important_memories=["first kill"],
        is_npc=False,
        is_dead=False,
    )
    assert char.ref.name == "Elara"
    assert char.stats.level == 5
    assert char.skills["sword"] == 3
    assert len(char.inventory) == 1
    assert char.equipped["main_hand"].uuid == "i-1"
    assert char.dispositions["npc-1"].friendship == 0.5
    assert char.is_npc is False


def test_character_serialization_roundtrip():
    ref = EntityRef(uuid="c-2", name="Brom")
    char = Character(ref=ref, is_npc=True)
    data = char.model_dump()
    restored = Character.model_validate(data)
    assert restored.ref.uuid == "c-2"
    assert restored.is_npc is True


def test_location_with_exits():
    region_ref = EntityRef(uuid="r-1", name="Darkwood")
    loc_ref = EntityRef(uuid="l-1", name="Crossroads")
    target_ref = EntityRef(uuid="l-2", name="Village Gate")

    exit_ = Exit(target_location=target_ref, direction="north", description="A dirt path", locked=False)
    loc = Location(
        ref=loc_ref,
        description="A lonely crossroads.",
        region=region_ref,
        exits=[exit_],
        npc_ids=["npc-1"],
        item_ids=["item-1"],
        is_stub=False,
    )
    assert loc.ref.name == "Crossroads"
    assert loc.region.uuid == "r-1"
    assert len(loc.exits) == 1
    assert loc.exits[0].direction == "north"
    assert loc.exits[0].locked is False


def test_region():
    ref = EntityRef(uuid="r-1", name="Ashfields")
    faction_ref = EntityRef(uuid="f-1", name="Iron Compact")
    region = Region(
        ref=ref,
        description="Scorched plains.",
        biome="wasteland",
        controlling_faction=faction_ref,
        locations=[EntityRef(uuid="l-1", name="Ruin")],
        danger_level=3,
    )
    assert region.biome == "wasteland"
    assert region.controlling_faction.uuid == "f-1"
    assert region.danger_level == 3
    assert len(region.locations) == 1


def test_item():
    ref = EntityRef(uuid="i-1", name="Health Potion", labels=["consumable"])
    item = Item(
        ref=ref,
        description="Restores 50 HP.",
        rarity="uncommon",
        slot_type="",
        effects=["heal:50"],
        is_consumable=True,
        is_quest_item=False,
    )
    assert item.rarity == "uncommon"
    assert item.is_consumable is True
    assert "heal:50" in item.effects


def test_faction():
    ref = EntityRef(uuid="f-1", name="Merchant Guild")
    faction = Faction(
        ref=ref,
        description="Controls trade.",
        reputation={"player": 0.6},
        relationships={"f-2": "hostile"},
    )
    assert faction.reputation["player"] == 0.6
    assert faction.relationships["f-2"] == "hostile"


def test_quest():
    ref = EntityRef(uuid="q-1", name="The Lost Blade")
    giver = EntityRef(uuid="npc-1", name="Old Blacksmith")
    quest = Quest(
        ref=ref,
        description="Find the ancient sword.",
        giver=giver,
        stages=["Talk to blacksmith", "Search the ruins", "Return the blade"],
        current_stage=1,
        completed=False,
        rewards=["gold:100", "item:ancient-sword"],
    )
    assert quest.giver.name == "Old Blacksmith"
    assert quest.current_stage == 1
    assert len(quest.stages) == 3
    assert quest.completed is False
    assert "gold:100" in quest.rewards
