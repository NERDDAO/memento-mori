"""MCP tool: mm_heartbeat — trigger world evolution."""

from crewai.tools import tool


@tool("mm_heartbeat")
def mm_heartbeat() -> str:
    """Trigger world evolution — processes accumulated events and generates
    new entities, quests, locations, and lore. Skips if nothing to process.

    Call this when something significant happens that should cause the world
    to react — a major battle, an important revelation, a notable event.
    The heartbeat also runs periodically in the background, so you don't
    need to call this for routine interactions.

    Returns a summary of what was created or "skipped" if the stack was empty.
    """
    from memento.heartbeat import HeartbeatRunner

    result = HeartbeatRunner().run()

    if result.get("skipped"):
        return f"World heartbeat skipped: {result.get('reason', 'nothing to process')}"

    if result.get("error"):
        return f"World heartbeat error: {result.get('error')}"

    reactions = result.get("reactions", {})
    parts = []
    if reactions.get("new_entities"):
        names = [e.get("name", "?") for e in reactions["new_entities"] if not e.get("error")]
        if names:
            parts.append(f"New entities: {', '.join(names)}")
    if reactions.get("new_quests"):
        names = [q.get("name", "?") for q in reactions["new_quests"] if not q.get("error")]
        if names:
            parts.append(f"New quests: {', '.join(names)}")
    if reactions.get("location_changes"):
        changes = [c.get("change", "?") for c in reactions["location_changes"] if not c.get("error")]
        if changes:
            parts.append(f"Location changes: {', '.join(changes)}")
    if reactions.get("lore"):
        topics = [l.get("topic", "?") for l in reactions["lore"] if not l.get("error")]
        if topics:
            parts.append(f"New lore: {', '.join(topics)}")

    if parts:
        return "World evolved:\n" + "\n".join(f"- {p}" for p in parts)
    return f"World heartbeat processed {result.get('message_count', 0)} messages, episode {result.get('episode_uuid', 'unknown')}"
