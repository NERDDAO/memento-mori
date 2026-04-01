"""Consequence crew — applies combat outcomes to the knowledge graph."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import update_entity, create_edge
from memento.tools.mechanics import calculate_xp, evaluate_disposition


def make_consequence_crew(
    resolution: str, attacker: str, target: str
) -> Crew:
    """Build a consequence crew to apply combat outcomes to the world state."""
    model = get_model_for_crew("consequence")

    consequence_applier = Agent(
        role="Consequence Applier",
        goal="Apply all combat outcomes — damage, status effects, XP, disposition changes — to the world state",
        backstory=(
            "You translate combat resolutions into persistent world state changes in a "
            "dark fantasy permadeath RPG. Damage dealt is reflected in entity HP. "
            "Killing a target means marking it dead and awarding XP. Witnesses affect "
            "faction disposition. Every consequence must be written to the knowledge graph "
            "so the world remembers what happened."
        ),
        tools=[update_entity, create_edge, calculate_xp, evaluate_disposition],
        llm=LLM(model=model),
    )

    consequence_task = Task(
        description=(
            f"Apply the consequences of this combat resolution to the world state:\n\n"
            f"Resolution:\n{resolution}\n\n"
            f"Attacker: {attacker}\n"
            f"Target: {target}\n\n"
            "Apply all outcomes:\n"
            "1. Update the target's entity with damage dealt (reduce HP, apply wounds)\n"
            "2. If the target was killed, mark them dead and update their status\n"
            "3. If the attacker gained XP from this exchange, calculate and apply it\n"
            "4. Evaluate how this combat affects disposition of nearby factions or NPCs\n"
            "5. Create any relevant relationship edges (e.g., attacker DEFEATED target)\n\n"
            "Report all changes made. Note explicitly if the target is dead or alive."
        ),
        expected_output=(
            "Consequence report: HP changes applied, death status (dead/alive), "
            "XP awarded (if any), disposition changes, relationship edges created. "
            "State clearly if the target is dead, killed, or slain."
        ),
        agent=consequence_applier,
    )

    return Crew(
        agents=[consequence_applier],
        tasks=[consequence_task],
        process=Process.sequential,
    )
