"""Permadeath flow — narrate death, mark dead, create memorial."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from memento.crews.combat.permadeath import make_permadeath_crew


class DeathState(BaseModel):
    player_name: str = ""
    cause: str = ""
    location: str = ""
    context: str = ""
    narrative: str = ""
    memorial: str = ""


class PermadeathFlow(Flow[DeathState]):
    @start()
    def narrate_and_memorialize(self):
        crew = make_permadeath_crew(
            player_name=self.state.player_name,
            cause=self.state.cause,
            location=self.state.location,
            context=self.state.context,
        )
        result = crew.kickoff()
        self.state.narrative = result.raw
        return result.raw
