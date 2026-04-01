"""Event detection flow — classify action, dispatch detectors, merge results."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.event_detection.classification import make_classification_crew


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
    def summarize(self, categories):
        # Phase 2 minimal — just pass categories through as events
        # Full detector crews added in Phase 5
        self.state.events = {"categories": categories}
        return self.state.events
