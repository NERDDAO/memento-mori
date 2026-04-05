"""Thread-local NPC context for MCP tool execution."""

import threading

_local = threading.local()


def set_npc_context(ctx: dict) -> None:
    """Set the current NPC context for tool execution."""
    _local.npc_context = ctx


def get_npc_context() -> dict | None:
    """Get the current NPC context. Returns None if not in NPC tool execution."""
    return getattr(_local, "npc_context", None)


def clear_npc_context() -> None:
    """Clear the NPC context after tool execution."""
    _local.npc_context = None
