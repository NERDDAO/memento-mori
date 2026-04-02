"""Episodic memory flow — consolidates a scene into an episode and writes NPC memories."""

import logging
import uuid as _uuid

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.narrative.memory.crew import make_memory_consolidation_crew, make_npc_memory_crew

logger = logging.getLogger(__name__)


class MemoryState(BaseModel):
    narrative: str = ""
    events: str = ""
    npcs: list[str] = []
    player: str = ""
    session_id: str = ""
    episode_summary: str = ""
    tick: int = 0


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
    def pin_and_record(self, episode_summary):
        """Pin episode content to IPFS and write hash onchain."""
        from memento.tools.ipfs import pin_json
        from memento.tools.chain import record_episode, is_enabled

        episode_id = _uuid.uuid4().hex

        episode_data = {
            "version": 1,
            "episodeId": episode_id,
            "tick": self.state.tick,
            "name": episode_summary[:80],
            "summary": episode_summary,
            "entities": self.state.events,
            "edges": "",
        }

        cid, content_hash = pin_json(episode_data)

        if cid and content_hash and is_enabled():
            record_episode(episode_id, content_hash, self.state.tick)
            logger.info(f"Episode recorded: {episode_id} -> IPFS {cid}")
        elif not cid:
            logger.warning(f"Episode {episode_id} not pinned — IPFS upload failed or disabled")

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
