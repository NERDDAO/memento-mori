# engine/src/memento/tools/tool_labels.py
"""Maps KG entity labels to allowed engine tools.

An NPC's KG labels determine which tools it can call.
Gateway fetches the NPC's labels and checks against this map.
"""

# Tier 1 — innate, every NPC gets these regardless of labels
INNATE_TOOLS = frozenset({
    "mm_get_state",
    "mm_get_world_time",
    "mm_search_world",
    "mm_get_entity",
    "mm_skill_check",
    "mm_calculate_damage",
    "mm_evaluate_disposition",
    "mm_send_gossip",
})

# Tier 2 & 3 — label grants access
LABEL_TOOLS: dict[str, set[str]] = {
    "Combat": {
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
    },
    "Trade": {
        "mm_give_item",
        "mm_create_item",
    },
    "Memory": {
        "mm_remember_event",
        "mm_npc_memory",
        "mm_update_entity",
    },
    "Travel": {
        "mm_move_to",
    },
    "Explore": {
        "mm_create_location",
        "mm_create_room",
    },
    "Leadership": {
        "mm_create_npc",
        "mm_design_npc",
    },
    "QuestGiver": {
        "mm_give_quest",
        "mm_design_quest",
        "mm_write_quest_dialogue",
    },
    "MasterCraft": {
        "mm_design_item",
    },
    "Cartography": {
        "mm_design_location",
        "mm_design_region",
    },
    "Perception": {
        "mm_detect_events",
        "mm_reputation_check",
    },
    "Narrator": {
        "mm_world_reaction",
        "mm_heartbeat",
    },
}


def get_allowed_tools(labels: list[str]) -> set[str]:
    """Given an NPC's KG labels, return the set of tools it can call."""
    allowed = set(INNATE_TOOLS)
    for label in labels:
        if label in LABEL_TOOLS:
            allowed |= LABEL_TOOLS[label]
    return allowed
