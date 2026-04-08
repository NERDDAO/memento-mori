"""Loot Designer crew — generates themed loot tables for locations/events."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.grammar_updater import update_grammar
from memento.tools.procgen.stat_roller import roll_loot

import json


def make_loot_designer_crew(
    location_name: str,
    theme: str = "",
    num_items: int = 3,
    rarity_budget: str = "common",
) -> Crew:
    """Build a crew that designs themed loot and updates the data tables."""
    model = get_model_for_crew("ascii_art")  # reuse art model config

    # Pre-roll a scaffold
    scaffold_items = roll_loot(rarity_budget, num_items)
    scaffold_text = json.dumps(scaffold_items, indent=2)

    designer = Agent(
        role="Loot Designer",
        goal="Create thematically appropriate items for a dark fantasy MUD location",
        backstory=(
            "You design loot tables for a dark-fantasy permadeath MUD.\n\n"
            "You receive pre-rolled item scaffolds with base stats. Your job:\n"
            "1. Rename items to fit the location theme\n"
            "2. Add lore/flavor text to each item\n"
            "3. Adjust stats if thematically appropriate\n"
            "4. Add any special effects that fit the theme\n"
            "5. Use the update_grammar tool to save any good new item names or affixes\n\n"
            "Output a JSON array of items, each with: name, rarity, slot, damage, "
            "defense, weight, lore, effects (array of strings).\n\n"
            "After generating the items, use the update_grammar tool to add any "
            "particularly good item names/prefixes to the data tables for future use:\n"
            "- New prefixes: update_grammar('tables/item_affixes', 'prefixes.<rarity>', '<prefix>')\n"
            "- New suffixes: update_grammar('tables/item_affixes', 'suffixes.<slot>', '<suffix>')\n"
            "- New item names: update_grammar('grammars/item_names', '<rarity>_prefix', '<name>')"
        ),
        tools=[update_grammar],
        llm=LLM(model=model),
    )

    design_task = Task(
        description=(
            f"Design {num_items} themed items for '{location_name}'.\n\n"
            f"Theme: {theme or 'dark fantasy'}\n"
            f"Rarity budget: {rarity_budget}\n\n"
            f"SCAFFOLD (use as starting point, modify freely):\n{scaffold_text}\n\n"
            f"Rename these items to match the location theme. Add lore and effects.\n"
            f"Output a JSON array of the final items.\n\n"
            f"After outputting the items, use the update_grammar tool to save "
            f"any new prefixes, suffixes, or names you invented."
        ),
        expected_output="JSON array of themed items with name, rarity, slot, damage, defense, weight, lore, effects",
        agent=designer,
    )

    return Crew(
        agents=[designer],
        tasks=[design_task],
        process=Process.sequential,
    )
