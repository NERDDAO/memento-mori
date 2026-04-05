from memento.type_selector import TypeSelector
from memento.rpg_types import RPG_ENTITY_TYPES


def test_select_quest_seed():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("The innkeeper mentions a lost artifact in the caves")
    assert "QuestSeed" in result


def test_select_new_entity_seed():
    ts = TypeSelector(threshold=0.3)
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("A mysterious stranger appears at the tavern door")
    assert "NewEntitySeed" in result


def test_simple_action_may_match_nothing_or_few():
    ts = TypeSelector(threshold=0.6)  # stricter threshold
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("I look around the room")
    # At strict threshold, a generic action shouldn't match specific seeds
    assert "QuestSeed" not in result


def test_lenient_threshold_over_includes():
    ts = TypeSelector(threshold=0.0)  # match everything
    for name, model in RPG_ENTITY_TYPES.items():
        ts.register(name, model)

    result = ts.select("anything")
    assert len(result) == len(RPG_ENTITY_TYPES)


def test_empty_registry_returns_empty():
    ts = TypeSelector(threshold=0.3)
    result = ts.select("attack the goblin")
    assert result == []
