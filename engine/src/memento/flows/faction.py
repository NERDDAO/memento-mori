"""Faction flow — generates factions and their relationships for a region."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.faction.generation import make_faction_generation_crew


class FactionState(BaseModel):
    region: str = ""
    num_factions: int = 2
    factions: str = ""


class FactionFlow(Flow[FactionState]):
    @start()
    def generate(self):
        crew = make_faction_generation_crew(
            region=self.state.region,
            num_factions=self.state.num_factions,
        )
        result = crew.kickoff()
        self.state.factions = result.raw
        return result.raw
