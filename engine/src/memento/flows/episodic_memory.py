"""Episodic memory flow — consolidates a scene into an episode and writes NPC memories."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.narrative.memory.crew import make_memory_consolidation_crew, make_npc_memory_crew


class MemoryState(BaseModel):
    narrative: str = ""
    events: str = ""
    npcs: list[str] = []
    player: str = ""
    session_id: str = ""
    episode_summary: str = ""


class EpisodicMemoryFlow(Flow[MemoryState]):
    @start()
    def consolidate(self):
        crew = make_memory_consolidation_crew(
            narrative=self.state.narrative,
            events=self.state.events,
            npcs=", ".join(self.state.npcs),
            player=self.state.player,
        )
        result = crew.kickoff()
        self.state.episode_summary = result.raw
        return result.raw

    @listen(consolidate)
    def npc_memories(self, episode):
        for npc in self.state.npcs:
            crew = make_npc_memory_crew(
                npc_name=npc,
                scene=episode,
                npc_perspective=npc,
            )
            crew.kickoff()
        return "memories recorded"
