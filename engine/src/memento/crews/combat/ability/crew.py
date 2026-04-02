"""Ability resolution crew — resolves special abilities, spells, and skills."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.mechanics import roll_skill_check, apply_status_effect


def make_ability_resolution_crew(
    ability: str, user_stats: str, target_stats: str
) -> Crew:
    """Build an ability resolution crew for a special ability or spell."""
    model = get_model_for_crew("ability_resolution")

    ability_resolver = Agent(
        role="Ability Resolver",
        goal="Resolve ability activation, resource costs, and effects with mechanical accuracy",
        backstory=(
            "You resolve special abilities, spells, and class skills in a dark fantasy RPG. "
            "You check whether the user has the resources to activate the ability, "
            "run any required skill checks, and apply the resulting effects to targets. "
            "Resource costs are real — spending stamina, mana, or health to activate an "
            "ability has consequences in a permadeath game."
        ),
        tools=[roll_skill_check, apply_status_effect],
        llm=LLM(model=model),
    )

    resolve_task = Task(
        description=(
            f"Resolve the following ability use:\n\n"
            f"Ability: {ability}\n\n"
            f"User stats:\n{user_stats}\n\n"
            f"Target stats:\n{target_stats}\n\n"
            "Steps:\n"
            "1. Determine the ability's resource cost (mana, stamina, health, charges)\n"
            "2. Verify the user has sufficient resources to activate it\n"
            "3. If activation requires a skill check, run it now\n"
            "4. Apply any status effects to the target (or user, if self-targeted)\n"
            "5. Report the outcome: activated/failed, resource consumed, effects applied"
        ),
        expected_output=(
            "Ability resolution report: activation success/failure, resource cost deducted, "
            "skill check result (if any), status effects applied to target and/or user, "
            "duration of effects."
        ),
        agent=ability_resolver,
    )

    return Crew(
        agents=[ability_resolver],
        tasks=[resolve_task],
        process=Process.sequential,
    )
