"""MCP tool: world reaction — spawn entities from episode seeds."""

from crewai.tools import tool


@tool("mm_world_reaction")
def mm_world_reaction(entities_json: str, location: str, location_uuid: str, episode_summary: str = "") -> str:
    """Process world seeds and spawn entities (NPCs, items, quests, lore).

    Args:
        entities_json: JSON array of entity seeds. Each seed must have a "type" field
            (NewEntitySeed, QuestSeed, LocationChange, LoreSeed) and type-specific fields.
        location: Display name of the location where entities spawn.
        location_uuid: KG UUID of the location.
        episode_summary: Optional episode narrative for context.

    Returns:
        Summary of what was created.
    """
    import json
    from memento.world_reaction import TurnContext, WorldReactionCrew

    try:
        entities = json.loads(entities_json)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON — {e}"

    if not isinstance(entities, list):
        return "Error: entities_json must be a JSON array"

    ctx = TurnContext(
        location=location,
        location_uuid=location_uuid,
        player_name="narrator",
        combined_action="",
        episode_summary=episode_summary,
    )

    crew = WorldReactionCrew()
    reactions = crew.react(entities, ctx)

    # Format results
    parts = []
    for key, items in reactions.items():
        if items:
            parts.append(f"{key}: {len(items)} created")

    if not parts:
        return "No entities created from the provided seeds."

    return "World reaction complete. " + ", ".join(parts)
