"""Attack resolution crew — resolves combat exchanges with dice and narrative."""

from crewai import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world
from memento.tools.mechanics import roll_skill_check, calculate_damage


def make_attack_resolution_crew(
    action: str, attacker_stats: str, target_stats: str, environment: str
) -> Crew:
    """Build an attack resolution crew for a combat exchange."""
    model = get_model_for_crew("attack_resolution")

    tactician = Agent(
        role="Combat Tactician",
        goal="Evaluate positioning, weapon matchups, and tactical advantage",
        backstory=(
            "You analyze the mechanics of a combat exchange in a dark fantasy RPG. "
            "You evaluate weapon ranges, attacker positioning, armor types, and any "
            "tactical advantages or disadvantages. Your analysis feeds directly into "
            "the dice resolution — accuracy matters."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    dice_master = Agent(
        role="Dice Master",
        goal="Execute skill checks and damage calculations with mechanical precision",
        backstory=(
            "You run the numbers. Given a tactical situation, you call the appropriate "
            "skill checks and damage calculations to determine what actually happened. "
            "You record results faithfully — no fudging. This is a permadeath game. "
            "A bad roll has consequences."
        ),
        tools=[roll_skill_check, calculate_damage],
        llm=LLM(model=model),
    )

    combat_narrator = Agent(
        role="Combat Narrator",
        goal="Translate mechanical outcomes into visceral, atmospheric combat prose",
        backstory=(
            "You write combat sequences for a dark fantasy permadeath RPG. "
            "Given mechanical results (hit/miss, damage dealt, status effects), "
            "you render them as tight, tense prose. No flowery language. "
            "Every blow lands with weight. Death is real here."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    tactical_task = Task(
        description=(
            f"Analyze this combat exchange:\n\n"
            f"Action: {action}\n\n"
            f"Attacker stats:\n{attacker_stats}\n\n"
            f"Target stats:\n{target_stats}\n\n"
            f"Environment:\n{environment}\n\n"
            "Evaluate:\n"
            "1. Weapon or attack type being used\n"
            "2. Target's armor or defense type and how it interacts with the attack\n"
            "3. Positional advantage/disadvantage (flanking, elevation, cover)\n"
            "4. Any special conditions that modify the roll (darkness, rage, wounds)\n\n"
            "Provide a tactical breakdown for the dice master."
        ),
        expected_output=(
            "Tactical analysis: attack type, defense matchup, modifiers (+/-), "
            "and recommended skill check parameters."
        ),
        agent=tactician,
    )

    dice_task = Task(
        description=(
            "Using the tactical analysis provided, resolve the combat exchange:\n\n"
            "1. Run a skill check for the attack (use the recommended parameters)\n"
            "2. If the attack hits, calculate damage\n"
            "3. Account for any defensive rolls or saves the target makes\n"
            "4. Report: hit/miss, damage dealt, any status effects triggered\n\n"
            "Record exact numbers — the narrator needs them."
        ),
        expected_output=(
            "Mechanical resolution: hit/miss result, damage dealt (if any), "
            "critical/fumble flags, status effects triggered, target HP remaining (if known)."
        ),
        agent=dice_master,
        context=[tactical_task],
    )

    narrate_task = Task(
        description=(
            "Write the combat narrative for this exchange.\n\n"
            "Use the tactical analysis and mechanical resolution to write 2-3 sentences "
            "of tight, atmospheric combat prose. Describe what the attacker does, "
            "what the target does in response, and what the outcome looks like. "
            "Match the tone to the result — a miss should feel different from a killing blow."
        ),
        expected_output=(
            "2-3 sentences of atmospheric combat prose describing the exchange, "
            "grounded in the mechanical outcome."
        ),
        agent=combat_narrator,
        context=[tactical_task, dice_task],
    )

    return Crew(
        agents=[tactician, dice_master, combat_narrator],
        tasks=[tactical_task, dice_task, narrate_task],
        process=Process.sequential,
    )
