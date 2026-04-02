"""Memory crews — consolidate episode summaries and write NPC memories."""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.tools.kg import remember_event


def make_memory_consolidation_crew(
    narrative: str,
    events: str,
    npcs: str,
    player: str,
) -> Crew:
    """Build a crew that summarizes a scene into a concise episode."""
    model = get_model_for_crew("memory_consolidation")

    memory_consolidator = Agent(
        role="Memory Consolidator",
        goal="Distill a game scene into a clear, concise episode summary",
        backstory=(
            "You are the keeper of the world's memory. You take raw narrative and event "
            "data and produce clean, factual episode summaries — what happened, who was "
            "involved, and what changed. You write in past tense, briefly and without "
            "embellishment. Your summaries are used for long-term memory retrieval."
        ),
        tools=[],
        llm=LLM(model=model),
    )

    consolidate_task = Task(
        description=(
            f"Summarize this scene into a concise episode memory.\n\n"
            f"Player: {player}\n\n"
            f"NPCs involved: {npcs}\n\n"
            f"Narrative:\n{narrative[:2000]}\n\n"
            f"Events detected:\n{events}\n\n"
            "Write 2-4 sentences capturing: what happened, who was involved, "
            "and what changed in the world as a result."
        ),
        expected_output=(
            "2-4 sentence episode summary in past tense covering what happened, "
            "who was involved, and what changed."
        ),
        agent=memory_consolidator,
    )

    return Crew(
        agents=[memory_consolidator],
        tasks=[consolidate_task],
        process=Process.sequential,
    )


def make_npc_memory_crew(
    npc_name: str,
    scene: str,
    npc_perspective: str,
) -> Crew:
    """Build a crew that writes and records an NPC's memory of a scene."""
    model = get_model_for_crew("npc_memory")

    npc_memory_writer = Agent(
        role="NPC Memory Writer",
        goal="Write a first-person memory of a scene from an NPC's perspective and record it",
        backstory=(
            "You give NPCs their inner life by writing their memories. You take a scene "
            "summary and write how the NPC experienced it — their feelings, observations, "
            "and what they'll remember. You then record this memory using the Remember Event "
            "tool so it persists in the world's knowledge graph."
        ),
        tools=[remember_event],
        llm=LLM(model=model),
    )

    memory_task = Task(
        description=(
            f"Write a memory of this scene from {npc_name}'s perspective, then record it.\n\n"
            f"Scene summary:\n{scene[:1500]}\n\n"
            f"NPC perspective context: {npc_perspective}\n\n"
            "Write 2-3 sentences from the NPC's point of view — what they noticed, "
            "felt, or decided. Then use the Remember Event tool to record the memory."
        ),
        expected_output=(
            "A 2-3 sentence first-person NPC memory, followed by confirmation that "
            "the memory was recorded."
        ),
        agent=npc_memory_writer,
    )

    return Crew(
        agents=[npc_memory_writer],
        tasks=[memory_task],
        process=Process.sequential,
    )
