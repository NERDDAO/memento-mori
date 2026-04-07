"""MCP tool: mm_heartbeat — trigger world evolution."""

from crewai.tools import tool


@tool("mm_heartbeat")
def mm_heartbeat() -> str:
    """Trigger world evolution — processes the stack and triggers the room
    narrator to narrate and evolve the world. Skips if nothing to process.

    Call this when something significant happens that should cause the world
    to react — a major battle, an important revelation, a notable event.
    The heartbeat also runs periodically in the background, so you don't
    need to call this for routine interactions.

    Returns a status summary.
    """
    from memento.heartbeat import HeartbeatRunner

    result = HeartbeatRunner().run()

    if result.get("skipped"):
        return f"World heartbeat skipped: {result.get('reason', 'nothing to process')}"

    if result.get("error"):
        return f"World heartbeat error: {result.get('error')}"

    msg_count = result.get("message_count", 0)
    episode = result.get("episode_uuid", "none")
    triggered = result.get("triggered", False)

    if triggered:
        return f"World heartbeat: processed {msg_count} messages, episode {episode}, narrator triggered."
    return f"World heartbeat: processed {msg_count} messages, episode {episode}, narrator not triggered."
