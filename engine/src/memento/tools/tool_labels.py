# engine/src/memento/tools/tool_labels.py
"""Maps KG entity labels to allowed engine tools.

Two layers:
1. INNATE — every agent gets these (read-only state + speaking + memory)
2. KITS  — role-based bundles assigned via a single KG label
3. LABEL — granular capability labels (additive, for special NPCs)

An NPC with label "NPC" gets the full NPC kit.
A narrator with label "Room" gets the room narrator kit.
Individual labels like "QuestGiver" can be added on top of a kit.
"""

# ── Innate — every agent, no label needed ──

INNATE_TOOLS = frozenset(
    {
        # Read-only state
        "mm_get_state",
        "mm_get_world_time",
        "mm_search_world",
        "mm_get_entity",
        # Basic mechanics
        "mm_skill_check",
        "mm_calculate_damage",
        "mm_evaluate_disposition",
        # Communication
        "mm_npc_response",
        "mm_send_gossip",
        "mm_npc_memory",
        # Perception
        "mm_look",
    }
)

# ── Kits — role-based bundles (one label = full role) ──

KITS: dict[str, set[str]] = {
    # Sentient NPC — can fight, trade, move, remember, give quests
    "NPC": {
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
        "mm_give_item",
        "mm_create_item",
        "mm_inventory",
        "mm_inventory_transfer",
        "mm_remember_event",
        "mm_update_entity",
        "mm_move_to",
        "mm_move_within",
        "mm_give_quest",
        # Construction control system tools (cxn skeleton, §7.5)
        "mm_move",
        "mm_attack",
        "mm_take",
    },
    # Non-sentient NPC — animal, elemental, construct: fight and move, no trade/quests
    "NonSentientNPC": {
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_check_plausibility",
        "mm_move_to",
        "mm_move_within",
        "mm_remember_event",
    },
    # Engine agent — stateless referee, resolves game mechanics
    "Engine": {
        "mm_check_plausibility",
        "mm_resolve_combat",
        "mm_assess_combat",
        "mm_skill_check",
        "mm_calculate_damage",
        "mm_evaluate_disposition",
        "mm_inventory",
        "mm_inventory_transfer",
        "mm_give_item",
        "mm_move_to",
        "mm_move_within",
        "mm_update_entity",
        "mm_remember_event",
        "mm_narrate",
        "mm_design_quest",
        "mm_give_quest",
        "mm_trigger_npc",
    },
    # Room narrator — world evolution, entity creation, design, narration
    "Room": {
        "mm_world_reaction",
        "mm_heartbeat",
        "mm_narrate",
        "mm_trigger_npc",
        "mm_remember_event",
        "mm_update_entity",
        "mm_create_npc",
        "mm_create_item",
        "mm_create_location",
        "mm_design_npc",
        "mm_design_item",
        "mm_design_quest",
        "mm_design_location",
        "mm_design_region",
        "mm_give_quest",
    },
    # World chronicler — synthesis only, no world mutation
    "World": {
        "mm_remember_event",
    },
    # Human player controlling their character via an MCP-enabled agent
    # (Claude Code, Cursor, etc.). Players get INNATE tools for free plus
    # this kit for inspection, movement, and trade. They deliberately do
    # NOT get design tools (mm_design_*), world-creation tools
    # (mm_create_*), mutation tools that affect other entities
    # (mm_update_entity, mm_remember_event), or referee tools
    # (mm_resolve_combat — that's the Engine's job).
    "Player": {
        "mm_inventory",
        "mm_move_to",
        "mm_check_plausibility",
        "mm_give_item",
        # Construction control system tools (cxn skeleton, §7.5).
        # Players deliberately do NOT get mm_attack — combat is the Engine's job.
        "mm_move",
        "mm_take",
    },
}

# ── Granular labels — additive specializations on top of kits ──

LABEL_TOOLS: dict[str, set[str]] = {
    "QuestGiver": {
        "mm_give_quest",
        "mm_design_quest",
    },
    "MasterCraft": {
        "mm_design_item",
        "mm_create_item",
    },
    "Leadership": {
        "mm_create_npc",
        "mm_design_npc",
    },
    "Cartography": {
        "mm_design_location",
        "mm_design_region",
        "mm_create_location",
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
    """Given an NPC's KG labels, return the set of tools it can call.

    Checks kits first (role bundles), then granular labels (specializations).
    """
    allowed = set(INNATE_TOOLS)
    for label in labels:
        if label in KITS:
            allowed |= KITS[label]
        if label in LABEL_TOOLS:
            allowed |= LABEL_TOOLS[label]
    return allowed


def build_tool_section(labels: list[str]) -> str:
    """Build a formatted tools section for a system prompt based on agent labels.

    Returns a string like:
    YOUR TOOLS: mm_get_state, mm_move_to, mm_resolve_combat, ...
    Only use these tools. Do not attempt to call tools not in this list.
    """
    tools = sorted(get_allowed_tools(labels))
    return (
        f"YOUR TOOLS: {', '.join(tools)}\n"
        "Only use these tools. Do not attempt to call tools not in this list."
    )
