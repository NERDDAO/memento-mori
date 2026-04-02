"""Main game turn flow — the core gameplay loop."""

from crewai import LLM
from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel
from memento.config import load_config
from memento.crews.context import make_context_crew
from memento.crews.narrative.narration import make_narration_crew
from memento.crews.faction.reputation import make_reputation_crew
from memento.flows.event_detection import EventDetectionFlow
from memento.flows.combat import CombatFlow
from memento.flows.episodic_memory import EpisodicMemoryFlow
from memento.flows.quest import QuestFlow
from memento.log import get_logger
from memento.tools.time import advance_time

logger = get_logger(__name__)


class TurnState(BaseModel):
    player_name: str = ""
    player_uuid: str = ""
    location_name: str = ""
    action: str = ""
    context: str = ""
    events: dict = {}
    narrative: str = ""
    world_time: dict = {}
    plausible: bool = True
    rejection_reason: str = ""
    subsystem_warnings: list[str] = []


class GameTurnFlow(Flow[TurnState]):
    @start()
    def gather_context(self):
        crew = make_context_crew(
            self.state.player_name,
            self.state.location_name,
            self.state.action,
        )
        result = crew.kickoff()
        self.state.context = result.raw
        return self.state.context

    @listen(gather_context)
    def plausibility_check(self, context):
        config = load_config()
        llm = LLM(model=config["llm"]["default_model"])
        response = llm.call(
            f"You are a plausibility checker for a dark fantasy RPG.\n\n"
            f"Scene context:\n{context[:1500]}\n\n"
            f"Player action: '{self.state.action}'\n\n"
            f"Is this action physically plausible in this scene? "
            f"Answer ONLY 'yes' or 'no: [brief reason]'."
        )
        raw = response.strip().lower()
        if raw.startswith("no"):
            self.state.plausible = False
            self.state.rejection_reason = raw
        return self.state.plausible

    @router(plausibility_check)
    def route_plausibility(self):
        return "proceed" if self.state.plausible else "reject"

    @listen("reject")
    def narrate_rejection(self):
        crew = make_narration_crew(
            action=self.state.action,
            context=self.state.context,
            events=f"Action rejected: {self.state.rejection_reason}",
            mode="rejection",
        )
        result = crew.kickoff()
        self.state.narrative = result.raw
        return self.state.narrative

    @listen("proceed")
    def detect_events(self, _):
        flow = EventDetectionFlow()
        flow.state.action = self.state.action
        flow.state.context = self.state.context
        result = flow.kickoff()
        self.state.events = flow.state.events
        return self.state.events

    @listen(detect_events)
    def resolve_events(self, events):
        """Route to combat, quest, and social flows based on detected event categories."""
        categories = events.get("categories", [])
        if "combat" in categories:
            combat_flow = CombatFlow()
            combat_flow.state.action = self.state.action
            combat_flow.state.attacker = self.state.player_name
            combat_flow.state.target = "unknown"  # extracted from context
            combat_flow.state.location = self.state.location_name
            combat_flow.state.context = self.state.context
            combat_flow.kickoff()
            self.state.events["combat_result"] = combat_flow.state.resolution
            self.state.events["combat_consequences"] = combat_flow.state.consequences

        if "quest" in categories:
            try:
                quest_flow = QuestFlow()
                quest_flow.state.location = self.state.location_name
                quest_flow.state.npc = "unknown"
                quest_flow.state.player_level = 1
                quest_flow.kickoff()
                self.state.events["quest_result"] = quest_flow.state.quest_concept
            except Exception as e:
                logger.warning("Quest flow failed", exc_info=True)
                self.state.subsystem_warnings.append("quest_unavailable")

        if "social" in categories:
            try:
                rep_crew = make_reputation_crew(
                    player=self.state.player_name,
                    faction="unknown",
                    action=self.state.action,
                )
                rep_result = rep_crew.kickoff()
                self.state.events["reputation"] = rep_result.raw
            except Exception as e:
                logger.warning("Reputation flow failed", exc_info=True)
                self.state.subsystem_warnings.append("reputation_unavailable")

        return self.state.events

    @listen(resolve_events)
    def narrate(self, events):
        crew = make_narration_crew(
            action=self.state.action,
            context=self.state.context,
            events=str(events),
            mode="action",
        )
        result = crew.kickoff()
        self.state.narrative = result.raw
        return self.state.narrative

    @listen(narrate)
    def post_turn(self, narrative):
        """Store episodic memories after each turn."""
        try:
            memory_flow = EpisodicMemoryFlow()
            memory_flow.state.narrative = narrative
            memory_flow.state.events = str(self.state.events)
            memory_flow.state.player = self.state.player_name
            memory_flow.state.session_id = self.state.player_uuid
            memory_flow.kickoff()
        except Exception as e:
            logger.warning("Memory flow failed", exc_info=True)
            self.state.subsystem_warnings.append("memory_unavailable")
        world_time = advance_time(1)
        self.state.world_time = world_time.to_display()

        # Chain: fetch latest Graphiti episode and push onchain
        from memento.tools import chain as _chain
        if _chain.is_enabled():
            self._sync_episode_to_chain()

        return narrative

    def _sync_episode_to_chain(self) -> None:
        """Poll for the latest Graphiti episode and push to Redstone."""
        import time
        import logging
        from memento.bonfires_client import get_client
        from memento.tools import chain as _chain

        logger = logging.getLogger(__name__)
        try:
            client = get_client()
            # Poll for up to 10 seconds (Graphiti extraction usually <2s)
            latest = None
            episodes = {}
            for attempt in range(5):
                time.sleep(2)
                try:
                    episodes = client.kg.search("", num_results=1)
                    ep_list = episodes.get("episodes", [])
                    if ep_list:
                        latest = ep_list[0]
                        break
                except Exception:
                    continue

            if not latest:
                logger.warning("Episode sync: no episode found after polling")
                return

            # Extract structured data
            ep_uuid = latest.get("uuid", "")
            ep_name = latest.get("name", "")
            content = latest.get("content", {})
            ep_summary = (
                content.get("content", "") if isinstance(content, dict) else str(content)
            )

            # Get entities and edges from search context
            entities = episodes.get("entities", [])
            edges = episodes.get("edges", [])

            entity_list = [
                {"uuid": e.get("uuid", ""), "name": e.get("name", ""), "labels": e.get("labels", [])}
                for e in entities[:20]
            ]
            edge_list = [
                {
                    "source": e.get("source_node_name", e.get("source_name", "")),
                    "target": e.get("target_node_name", e.get("target_name", "")),
                    "relationship": e.get("name", e.get("relationship", "")),
                    "fact": e.get("fact", ""),
                }
                for e in edges[:20]
            ]

            tick = 0
            if isinstance(self.state.world_time, dict):
                tick = self.state.world_time.get("tick", 0)

            _chain.record_episode(ep_uuid, ep_name, ep_summary, entity_list, edge_list, tick)
            logger.info(f"Episode synced to chain: {ep_name}")

        except Exception as e:
            logger.warning(f"Episode chain sync failed: {e}")
