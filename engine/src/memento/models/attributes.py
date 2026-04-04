"""Entity attribute schemas and enrichment helpers.

Defines the expected attribute fields for each entity type (NPC, Item, Location)
and provides a function to detect which fields are missing on a given entity.
"""

from __future__ import annotations

from memento.room_manifest import NPC_LABELS, ITEM_LABELS

# Required attribute fields per entity type.
# Each maps field name -> a brief description (used by the enrichment crew prompt).
NPC_ATTRIBUTE_FIELDS: dict[str, str] = {
    "personality": "2-3 sentence personality description",
    "backstory": "2-3 sentence backstory",
    "speech_pattern": "How they talk (accent, vocabulary, mannerisms)",
    "motivation": "What drives them",
    "traits": "3-5 personality trait words (JSON array)",
    "stats": "D&D-style stats: {STR, DEX, CON, INT, WIS, CHA} values 3-18",
    "skills": "3-5 skills: {skill_name: level} where level is 1-10",
    "abilities": "1-2 special abilities: [{name, description}]",
    "disposition": "One of: hostile, unfriendly, neutral, friendly, allied",
    "secret": "A hidden fact about this NPC",
}

ITEM_ATTRIBUTE_FIELDS: dict[str, str] = {
    "description": "1-2 sentence physical description",
    "rarity": "One of: common, uncommon, rare, epic, legendary",
    "slot_type": "One of: weapon, armor, accessory, ring, or empty string",
    "damage": "Integer damage value (0 for non-weapons)",
    "defense": "Integer defense value (0 for non-armor)",
    "weight": "Integer weight (1-20)",
    "effects": "JSON array of effect strings",
    "lore": "1-2 sentence historical flavor text",
}

LOCATION_ATTRIBUTE_FIELDS: dict[str, str] = {
    "biome": "Terrain type (underground, forest, desert, etc.)",
    "danger_level": "Integer 1-10",
    "culture": "Cultural description",
    "threats": "JSON array of threat strings",
    "secrets": "JSON array of hidden features",
    "atmosphere": "Sensory description (sights, sounds, smells)",
    "lore": "Historical context",
}

_SCHEMAS: dict[str, dict[str, str]] = {
    "npc": NPC_ATTRIBUTE_FIELDS,
    "item": ITEM_ATTRIBUTE_FIELDS,
    "location": LOCATION_ATTRIBUTE_FIELDS,
}


def needs_enrichment(entity_type: str, attributes: dict) -> list[str]:
    """Return a list of attribute fields that are missing or empty for the given entity type.

    Args:
        entity_type: One of 'npc', 'item', 'location'.
        attributes: The entity's current attributes dict.

    Returns:
        List of field names that should be filled in.
    """
    schema = _SCHEMAS.get(entity_type, {})
    missing: list[str] = []
    for field in schema:
        val = attributes.get(field)
        if val is None or val == "" or val == [] or val == {}:
            missing.append(field)
    return missing


__all__ = [
    "NPC_LABELS",
    "ITEM_LABELS",
    "NPC_ATTRIBUTE_FIELDS",
    "ITEM_ATTRIBUTE_FIELDS",
    "LOCATION_ATTRIBUTE_FIELDS",
    "needs_enrichment",
]
