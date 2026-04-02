"""Combat assessment crew — evaluates the combat situation before resolution."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.sanitize import sanitize_for_prompt
from memento.tools.kg import search_world, get_entity


def make_combat_assessment_crew(
    action: str, attacker: str, target: str, location: str
) -> Crew:
    """Build a combat assessment crew for the current encounter."""
    model = get_model_for_crew("combat_assessment")
    action = sanitize_for_prompt(action, max_length=500)
    attacker = sanitize_for_prompt(attacker, max_length=100)
    target = sanitize_for_prompt(target, max_length=100)
    location = sanitize_for_prompt(location, max_length=200)

    combat_assessor = Agent(
        role="Combat Assessor",
        goal="Evaluate the combat situation and classify the incoming action",
        backstory=(
            "You are a tactical analyst for a dark fantasy permadeath RPG. "
            "You assess combat situations by examining who is fighting, what they "
            "are capable of, and what type of action is being attempted. "
            "Classify actions as: attack, ability, or flee. Be precise — misclassification "
            "leads to wrong resolution paths and player frustration."
        ),
        tools=[search_world, get_entity],
        llm=LLM(model=model),
    )

    assess_task = Task(
        description=(
            f"Assess the following combat situation:\n\n"
            f"Attacker: {attacker}\n"
            f"Target: {target}\n"
            f"Location: {location}\n"
            f"Action: {action}\n\n"
            "Perform the following steps:\n"
            "1. Retrieve entity data for both the attacker and target\n"
            "2. Search the location for environmental factors (terrain, obstacles, exits)\n"
            "3. Classify the action as: attack, ability, or flee\n"
            "4. Assess the target's apparent threat level\n"
            "5. Note any relevant environmental factors that affect the encounter\n\n"
            "Be explicit about the action type classification in your output."
        ),
        expected_output=(
            "A structured combat assessment with: Action Type (attack/ability/flee), "
            "Attacker summary, Target summary and threat level, Environmental factors, "
            "and any special conditions affecting the encounter."
        ),
        agent=combat_assessor,
    )

    return Crew(
        agents=[combat_assessor],
        tasks=[assess_task],
        process=Process.sequential,
    )
