"""Item mechanics crew — assigns mechanical stats to a designed item concept."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew


def make_item_mechanics_crew(item_concept: str) -> Crew:
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
            "Assign mechanical stats to this item: damage/defense values, weight, any status "
            "effects it applies, and whether it's consumable or a quest item."
        ),
        expected_output=(
            "A structured stat block with: damage or defense value (as appropriate), weight, "
            "status effects (if any), consumable flag, quest item flag, and any special mechanics."
        ),
        agent=item_mechanic,
    )

    return Crew(
        agents=[item_mechanic],
        tasks=[mechanics_task],
        process=Process.sequential,
    )
