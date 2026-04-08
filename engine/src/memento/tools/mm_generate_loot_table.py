"""mm_generate_loot_table — CrewAI tool for generating themed loot tables.

Exposed as an mm_ tool that NPC agents and the engine can invoke to
generate location-specific loot.
"""

import json
import logging
import re

from crewai.tools import tool

logger = logging.getLogger(__name__)


def _get_loot_designer_crew(location_name, theme, num_items, rarity_budget):
    """Get loot designer crew. Separated for test mocking."""
    from memento.crews.loot_designer.crew import make_loot_designer_crew
    return make_loot_designer_crew(location_name, theme, num_items, rarity_budget)


@tool("mm_generate_loot_table")
def mm_generate_loot_table(
    location_name: str,
    theme: str = "",
    num_items: int = 3,
    rarity_budget: str = "common",
) -> str:
    """Generate a themed loot table for a specific location or event.

    Creates location-appropriate items with names, stats, lore, and effects.
    Also updates the shared item grammar/affix tables with any new names invented.

    Args:
        location_name: Name of the location the loot is for.
        theme: Optional theme (e.g. "undead", "nature", "fire").
        num_items: Number of items to generate (default 3).
        rarity_budget: Rarity tier budget (common, uncommon, rare).

    Returns:
        JSON array of items with name, rarity, slot, damage, defense, weight, lore, effects.
    """
    try:
        crew = _get_loot_designer_crew(location_name, theme, num_items, rarity_budget)
        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        # Try to extract JSON array from output
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            return match.group()
        return raw

    except Exception:
        logger.exception("Loot table generation failed for %s", location_name)
        # Fallback: return table-rolled items without LLM refinement
        from memento.tools.procgen.stat_roller import roll_loot
        items = roll_loot(rarity_budget, num_items)
        return json.dumps(items)
