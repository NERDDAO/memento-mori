"""Main game turn flow — the core gameplay loop."""

from crewai import LLM
from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel
from memento.config import load_config
from memento.crews.context import make_context_crew
from memento.crews.narrative.narration import make_narration_crew
from memento.flows.event_detection import EventDetectionFlow
from memento.flows.combat import CombatFlow


class TurnState(BaseModel):
    player_name: str = ""
    player_uuid: str = ""
    location_name: str = ""
    action: str = ""
    context: str = ""
    events: dict = {}
    narrative: str = ""
    plausible: bool = True
    rejection_reason: str = ""


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
        """Route to combat if combat events detected."""
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
