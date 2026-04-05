from memento.world_reaction import WorldReactionCrew, TurnContext


def test_no_entities_returns_empty():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    result = crew.react([], ctx)
    assert result == {}


def test_new_entity_seed_creates_entry():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "NewEntitySeed", "entity_name": "Mysterious Stranger", "entity_type": "npc", "description": "A hooded figure"}]
    result = crew.react(entities, ctx)
    assert "new_entities" in result
    assert len(result["new_entities"]) == 1


def test_quest_seed_creates_entry():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "QuestSeed", "quest_name": "The Lost Artifact", "giver_name": "Innkeeper"}]
    result = crew.react(entities, ctx)
    assert "new_quests" in result


def test_unknown_type_is_skipped():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [{"type": "UnknownType", "data": "whatever"}]
    result = crew.react(entities, ctx)
    assert result == {}


def test_multiple_seeds_processed():
    crew = WorldReactionCrew()
    ctx = TurnContext(location="tavern", location_uuid="loc-123", player_name="Kael")
    entities = [
        {"type": "NewEntitySeed", "entity_name": "Dark Blade", "entity_type": "item", "description": "A cursed sword"},
        {"type": "QuestSeed", "quest_name": "Retrieve the Blade", "giver_name": "Blacksmith"},
        {"type": "LoreSeed", "lore_topic": "The Curse of Ironhold", "content": "An ancient curse..."},
    ]
    result = crew.react(entities, ctx)
    assert "new_entities" in result
    assert "new_quests" in result
    assert "lore" in result
