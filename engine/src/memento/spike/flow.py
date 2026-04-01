"""Spike flow — validates CrewAI Flow state passing with KG data."""

from crewai import LLM
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.spike.crew import make_spike_crew


class SpikeState(BaseModel):
    location_name: str = ""
    location_description: str = ""
    npc_name: str = ""


class SpikeFlow(Flow[SpikeState]):
    @start()
    def create_location(self):
        crew = make_spike_crew()
        result = crew.kickoff()
        self.state.location_description = result.raw
        self.state.location_name = "The Spike Tavern"
        return result.raw

    @listen(create_location)
    def add_npc(self, location_desc: str):
        llm = LLM(model="openrouter/anthropic/claude-sonnet-4")
        response = llm.call(
            f"Given this location:\n{location_desc[:500]}\n\n"
            "Name one NPC who would be found here. Just the name, nothing else."
        )
        self.state.npc_name = response.strip()
        return self.state.npc_name


def main():
    flow = SpikeFlow()
    result = flow.kickoff()
    print(f"\nFlow state: location={flow.state.location_name}, npc={flow.state.npc_name}")
    print(f"Flow result: {result}")


if __name__ == "__main__":
    main()
