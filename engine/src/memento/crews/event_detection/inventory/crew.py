"""Inventory event detector — tracks item pickups, drops, uses, and transfers."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world
from memento.tools.mechanics import check_carry_capacity


def make_inventory_detector_crew(action: str, context: str) -> Crew:
    """Build a crew that detects inventory events and validates item transfers."""
    model = get_model_for_crew("inventory_detector")

    inventory_tracker = Agent(
        role="Inventory Tracker",
        goal="Detect item pickups, drops, uses, and transfers in player actions",
        backstory=(
            "You monitor inventory events in a dark fantasy RPG. You catch: item pickups, "
            "drops, uses, consumptions, trades, and thefts. You search the world to confirm "
            "items exist. You are thorough — a player saying 'I grab the sword' and "
            "'I take the blade' are both item pickups."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    ownership_arbiter = Agent(
        role="Inventory Ownership Arbiter",
        goal="Validate that inventory transfers are physically possible and legally permissible",
        backstory=(
            "You validate inventory operations. You check carry capacity for pickups and "
            "flag illegal transfers (stealing from sealed containers, picking up quest items "
            "before they're unlocked). Use the Check Carry Capacity tool to verify weight "
            "limits. You are the last gate before inventory state changes are committed."
        ),
        tools=[check_carry_capacity],
        llm=LLM(model=model),
    )

    track_task = Task(
        description=(
            f"Detect inventory events in this player action.\n\n"
            f"Context:\n{context[:1000]}\n\n"
            f"Action: '{action}'\n\n"
            "Identify inventory events:\n"
            "- PICKUP: item acquired\n"
            "- DROP: item discarded\n"
            "- USE: item consumed or activated\n"
            "- EQUIP: item equipped to slot\n"
            "- TRADE: item exchanged with NPC\n"
            "- STEAL: item taken without permission\n\n"
            "For each event, identify: event type, item name, from/to (who had it, who gets it)."
        ),
        expected_output=(
            "List of inventory events: [{type, item, from, to}]. "
            "Empty list if none detected."
        ),
        agent=inventory_tracker,
    )

    validate_task = Task(
        description=(
            "Validate the detected inventory events. For each PICKUP event, "
            "use Check Carry Capacity to verify the player can carry the item "
            "(use weight 5 and capacity 50 as defaults if unknown). "
            "Flag any transfers that seem illegal or impossible. "
            "Approve or reject each event."
        ),
        expected_output=(
            "Validated inventory events: each marked APPROVED or REJECTED with reason."
        ),
        agent=ownership_arbiter,
        context=[track_task],
    )

    return Crew(
        agents=[inventory_tracker, ownership_arbiter],
        tasks=[track_task, validate_task],
        process=Process.sequential,
    )
