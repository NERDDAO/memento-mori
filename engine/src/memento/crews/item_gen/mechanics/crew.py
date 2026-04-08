"""Item mechanics crew — assigns mechanical stats to a designed item concept."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_item_mechanics_crew(item_concept: str, scaffold: str = "") -> Crew:
    """Build an item mechanics crew for a given item concept."""
    model = get_model_for_crew("item_mechanics")

    item_mechanic = Agent(
        role="Item Mechanic",
        goal="Assign balanced mechanical stats to item concepts for a dark fantasy RPG",
        backstory=(
            "You translate item concepts into concrete mechanical values for a dark fantasy RPG. "
            "Given an item description and rarity, you assign appropriate damage or defense values, "
            "weight, status effects, and flags like consumable or quest item. You ensure stats "
            "feel right for the item's theme and rarity without external reference — pure stat craft."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    mechanics_task = Task(
        description=(
            f"Assign mechanical stats to this item: {item_concept}\n\n"
            "Output a JSON object (or array of objects if multiple items) with these fields:\n"
            '- "name": item name (from the concept)\n'
            '- "damage": integer damage value (0 for non-weapons)\n'
            '- "defense": integer defense value (0 for non-armor)\n'
            '- "weight": integer weight (1-20)\n'
            '- "effects": array of effect description strings\n'
            '- "is_consumable": boolean\n'
            '- "is_quest_item": boolean\n'
            "Include a brief balance note after the JSON."
        ),
        expected_output=(
            "A JSON object (or array) with name, damage, defense, weight, effects, "
            "is_consumable, and is_quest_item fields, followed by a brief balance note."
        ),
        agent=item_mechanic,
    )
    if scaffold:
        mechanics_task.description += (
            "\n\nSCAFFOLD (use as starting point, modify freely, or discard if it doesn't fit):\n"
            + scaffold
        )

    return Crew(
        agents=[item_mechanic],
        tasks=[mechanics_task],
        process=Process.sequential,
    )
