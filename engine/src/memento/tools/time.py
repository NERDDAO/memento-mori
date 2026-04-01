# engine/src/memento/tools/time.py
from crewai.tools import tool
from memento.models.time import WorldTime

_world_time = WorldTime(tick=0)


def get_current_time() -> WorldTime:
    """Get current world time (helper for flows, not a CrewAI tool)."""
    return _world_time


def advance_time(ticks: int = 1) -> WorldTime:
    """Advance world time (helper for flows, not a CrewAI tool)."""
    global _world_time
    _world_time = _world_time.advance(ticks)
    return _world_time


@tool("get_world_time")
def get_world_time() -> str:
    """Get the current in-game world time including moon phase, date, and time of day."""
    t = _world_time
    return f"{t.moon_icon} {t.moon_phase} | {t.day_number} of {t.month} | {t.time_of_day} | {t.season}"
