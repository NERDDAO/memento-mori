"""Quest design crew — creates morally complex quests with consequences."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import search_world, create_entity


def make_quest_design_crew(
    location: str,
    npc: str,
    player_level: int,
    active_quests: str = "",
    faction_context: str = "",
) -> Crew:
    """Build a quest design crew for a given location and NPC."""
    model = get_model_for_crew("quest_design")

    quest_writer = Agent(
        role="Quest Writer",
        goal="Create compelling quests with moral ambiguity, genuine choices, and clear motivation",
        backstory=(
            "You design quests for a permadeath dark fantasy RPG. Every quest you create "
            "has a human motivation behind it — greed, grief, desperation, vengeance. You "
            "avoid generic fetch quests. Each quest has at least two meaningful choices with "
            "no clear 'right' answer. You search the world for existing lore to root quests "
            "in the setting, then create the quest entity in the knowledge graph."
        ),
        tools=[search_world, create_entity],
        llm=LLM(model=model),
    )

    reward_balancer = Agent(
        role="Reward Balancer",
        goal="Design balanced rewards appropriate to player level and quest difficulty",
        backstory=(
            "You balance RPG economies. Given a player's level and quest difficulty, you "
            "design reward packages that feel earned without breaking game balance. You consider "
            "XP, gold, items, and non-material rewards like reputation or information. "
            "In a permadeath game, rewards must feel meaningful — each run has finite time."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    consequence_designer = Agent(
        role="Consequence Designer",
        goal="Design how quest outcomes ripple through the world — no choice is consequence-free",
        backstory=(
            "You design the downstream effects of player choices in a living world. For each "
            "quest outcome, you map what changes: NPCs who react, factions that shift, world "
            "states that update. You search the world graph to understand what entities will "
            "be affected. In a permadeath game, consequences outlast the player's run."
        ),
        tools=[search_world],
        llm=LLM(model=model),
    )

    quest_task = Task(
        description=(
            f"Design a quest given by '{npc}' at '{location}'.\n\n"
            f"Player level: {player_level}\n"
            f"Active quests (avoid conflicts): {active_quests or 'None'}\n"
            f"Faction context: {faction_context or 'None'}\n\n"
            "Search the world for relevant lore, then create the quest entity. "
            "Include: quest name, the NPC's motivation, the core moral dilemma, "
            "2-3 distinct choices the player can make, and what triggers completion."
        ),
        expected_output=(
            "A quest design with: name, NPC motivation, moral dilemma, "
            "2-3 player choices with different implications, and completion triggers."
        ),
        agent=quest_writer,
    )

    reward_task = Task(
        description=(
            f"Design balanced rewards for this quest at player level {player_level}.\n\n"
            "Consider rewards for different completion paths — a 'good' path and a "
            "'pragmatic' path should both feel worth doing. Include XP, gold, and any "
            "special rewards."
        ),
        expected_output=(
            "Reward packages for each quest path: XP amount, gold range, "
            "and any special rewards (items, reputation, information)."
        ),
        agent=reward_balancer,
        context=[quest_task],
    )

    consequence_task = Task(
        description=(
            "Design the world ripple effects for each quest outcome path. "
            "Search the world graph to find entities that will be affected. "
            "What changes? Who reacts? Which factions shift? "
            "Be specific about which world state changes persist."
        ),
        expected_output=(
            "For each quest path: a list of world consequences — NPCs affected, "
            "faction shifts, world state changes that persist after the quest."
        ),
        agent=consequence_designer,
        context=[quest_task, reward_task],
    )

    return Crew(
        agents=[quest_writer, reward_balancer, consequence_designer],
        tasks=[quest_task, reward_task, consequence_task],
        process=Process.sequential,
    )
