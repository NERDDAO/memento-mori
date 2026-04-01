"""Event detection flow — classify action, dispatch detectors, merge results."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.event_detection.classification import make_classification_crew
from memento.crews.event_detection.combat import make_combat_detector_crew
from memento.crews.event_detection.inventory import make_inventory_detector_crew
from memento.crews.event_detection.quest import make_quest_detector_crew
from memento.crews.event_detection.world_change import make_world_change_detector_crew
from memento.crews.event_detection.merge import make_event_merge_crew


class EventState(BaseModel):
    action: str = ""
    context: str = ""
    categories: list[str] = []
    events: dict = {}


class EventDetectionFlow(Flow[EventState]):
    @start()
    def classify(self):
        crew = make_classification_crew(self.state.action, self.state.context)
        result = crew.kickoff()
        raw = result.raw.strip()
        self.state.categories = [c.strip().lower() for c in raw.split(",") if c.strip()]
        return self.state.categories

    @listen(classify)
    def dispatch_detectors(self, categories):
        detected = []
        if "combat" in categories:
            crew = make_combat_detector_crew(self.state.action, self.state.context)
            detected.append(crew.kickoff().raw)
        if "inventory" in categories:
            crew = make_inventory_detector_crew(self.state.action, self.state.context)
            detected.append(crew.kickoff().raw)
        if "quest" in categories:
            crew = make_quest_detector_crew(self.state.action, self.state.context)
            detected.append(crew.kickoff().raw)
        if "world_change" in categories:
            crew = make_world_change_detector_crew(
                self.state.action, self.state.context
            )
            detected.append(crew.kickoff().raw)

        if detected:
            merge_crew = make_event_merge_crew("\n---\n".join(detected))
            merged = merge_crew.kickoff().raw
            self.state.events = {"categories": categories, "details": merged}
        else:
            self.state.events = {"categories": categories, "details": ""}
        return self.state.events
