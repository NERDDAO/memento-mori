"""NPC mechanics crew — assigns stats and abilities."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.mechanics import roll_skill_check


def make_mechanics_crew(npc_concept: str) -> Crew:
    """Build a crew that assigns balanced attributes, skills, and abilities to an NPC."""
    model = get_model_for_crew("npc_mechanics")

    stat_builder = Agent(
        role="NPC Stat Builder",
        goal="Assign balanced attributes and skills that reflect the NPC's concept",
        backstory=(
            "You are a game balance expert for a dark fantasy RPG. You translate an NPC's "
            "background and role into concrete mechanical values — attributes and skills — "
            "and verify they are balanced by testing them against difficulty thresholds."
        ),
        tools=[roll_skill_check],
        llm=LLM(model=model),
    )

    ability_designer = Agent(
        role="NPC Ability Designer",
        goal="Select abilities that authentically reflect the NPC's combat style and background",
        backstory=(
            "You curate the special abilities that make each NPC distinct in combat and "
            "social encounters. You ensure abilities are thematically coherent with the "
            "NPC's story and do not unbalance their mechanical profile."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    stat_task = Task(
        description=(
            f"NPC concept:\n{npc_concept}\n\n"
            "Assign attributes (strength, dexterity, constitution, intelligence, wisdom, "
            "charisma) and 3-5 skills with levels 1-10 for this NPC."
        ),
        expected_output=(
            "A stat block with: six attribute scores (1-20), and 3-5 named skills each "
            "with a level between 1 and 10. Include a brief note justifying the choices."
        ),
        agent=stat_builder,
    )

    ability_task = Task(
        description=(
            "Select 1-3 abilities that reflect this NPC's combat style and background."
        ),
        expected_output=(
            "A list of 1-3 abilities, each with a name, one-sentence description, "
            "and how it connects to the NPC's background or role."
        ),
        agent=ability_designer,
        context=[stat_task],
    )

    return Crew(
        agents=[stat_builder, ability_designer],
        tasks=[stat_task, ability_task],
        process=Process.sequential,
    )
