"""Tests for the canonical StateUpdate model."""

from memento.models.state_update import (
    StateUpdate,
    ExitUpdate,
    EntityRefUpdate,
    InventoryItemUpdate,
    WorldTimeDisplay,
    RoomMapUpdate,
)


def test_state_update_defaults():
    update = StateUpdate()
    assert update.schema_version == 1
    assert update.location is None
    assert update.health is None
    assert update.subsystem_warnings == []


def test_state_update_partial():
    update = StateUpdate(location="Tavern", health=80)
    assert update.location == "Tavern"
    assert update.health == 80
    assert update.level is None


def test_state_update_with_exits():
    update = StateUpdate(exits=[ExitUpdate(direction="north", name="Forest")])
    assert len(update.exits) == 1
    assert update.exits[0].direction == "north"


def test_state_update_with_inventory():
    update = StateUpdate(inventory=[
        InventoryItemUpdate(name="Sword", rarity="rare", equipped=True),
        InventoryItemUpdate(name="Potion"),
    ])
    assert len(update.inventory) == 2
    assert update.inventory[0].equipped is True
    assert update.inventory[1].rarity == "common"


def test_state_update_with_world_time():
    wt = WorldTimeDisplay(tick=42, time_of_day="Dusk", moon_phase="Full Moon")
    update = StateUpdate(world_time=wt)
    assert update.world_time.tick == 42
    assert update.world_time.time_of_day == "Dusk"


def test_state_update_with_room_map():
    rm = RoomMapUpdate(id="rm-1", name="Tavern", width=10, height=10)
    update = StateUpdate(room_map=rm)
    assert update.room_map.name == "Tavern"


def test_state_update_subsystem_warnings():
    update = StateUpdate(subsystem_warnings=["quest_unavailable", "memory_unavailable"])
    assert len(update.subsystem_warnings) == 2


def test_state_update_serialization_roundtrip():
    update = StateUpdate(
        location="Market",
        health=50,
        max_health=100,
        exits=[ExitUpdate(direction="east", name="Gate")],
        subsystem_warnings=["reputation_unavailable"],
    )
    data = update.model_dump()
    restored = StateUpdate.model_validate(data)
    assert restored.location == "Market"
    assert restored.health == 50
    assert len(restored.exits) == 1
    assert restored.subsystem_warnings == ["reputation_unavailable"]


def test_state_update_json_schema():
    schema = StateUpdate.model_json_schema()
    assert "properties" in schema
    assert "schema_version" in schema["properties"]
    assert "location" in schema["properties"]
