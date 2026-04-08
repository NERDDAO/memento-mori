"""Item concept crew — designs items for a given location and rarity budget."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world
from memento.tools.mechanics import roll_loot_table


def make_item_concept_crew(
    location_name: str,
    rarity_budget: str = "common",
    num_items: int = 3,
    scaffold: str = "",
) -> Crew:
    """Build an item concept crew for a given location."""
    model = get_model_for_crew("item_concept")

    item_concepter = Agent(
        role="Item Concepter",
        goal="Design thematically appropriate items for a dark fantasy RPG location",
        backstory=(
            "You design items for a dark fantasy RPG. Given a location and a rarity budget, "
            "you search the world knowledge graph for thematic inspiration and roll the loot "
            "table to determine rarities. You produce well-conceived items that feel native "
            "to the location and match the power level implied by their rarity."
        ),
        tools=[search_world, roll_loot_table],
        llm=LLM(model=model),
    )

    concept_task = Task(
        description=(
            f"Design {num_items} items that would be found at '{location_name}'. "
            f"Use the Roll Loot Table tool with rarity budget '{rarity_budget}' to determine rarities. "
            f"For each item, provide a structured JSON array where each element has:\n"
            f'- "name": item name\n'
            f'- "description": 1-2 sentence physical description\n'
            f'- "rarity": one of common/uncommon/rare/epic/legendary\n'
            f'- "slot_type": one of weapon/armor/accessory/ring or empty string\n'
            f'- "effects": array of effect description strings\n'
            f'- "lore": 1-2 sentence historical flavor text\n'
        ),
        expected_output=(
            f"A JSON array of {num_items} item objects, each with name, description, "
            "rarity, slot_type, effects, and lore fields."
        ),
        agent=item_concepter,
    )
    if scaffold:
        concept_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    return Crew(
        agents=[item_concepter],
        tasks=[concept_task],
        process=Process.sequential,
    )
