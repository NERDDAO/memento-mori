"""World generation flow — creates regions with locations, NPCs, and items."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from memento.crews.world_gen.region_design import make_region_design_crew
from memento.crews.world_gen.location_planning import make_location_planning_crew
from memento.crews.world_gen.location import make_location_crew
from memento.crews.world_gen.exit_connection import make_exit_connection_crew
from memento.flows.npc_gen import NPCGenerationFlow
from memento.flows.item_gen import ItemGenerationFlow


class WorldGenState(BaseModel):
    theme: str = ""
    player_level: int = 1
    region_concept: str = ""
    location_plans: str = ""
    locations_created: list[str] = []
    region_name: str = ""


class WorldGenFlow(Flow[WorldGenState]):
    @start()
    def design_region(self):
        crew = make_region_design_crew(
            theme=self.state.theme,
            player_level=self.state.player_level,
        )
        result = crew.kickoff()
        self.state.region_concept = result.raw
        # Extract region name from first line or use theme
        self.state.region_name = self.state.theme
        return result.raw

    @listen(design_region)
    def plan_locations(self, region_concept):
        crew = make_location_planning_crew(region_concept=region_concept)
        result = crew.kickoff()
        self.state.location_plans = result.raw
        return result.raw

    @listen(plan_locations)
    def generate_locations(self, plans):
        # Process locations sequentially (no async)
        location_descriptions = []
        # Split plans into individual locations — agent output is free-form,
        # so we pass the full plan to each location crew
        for i in range(3):  # generate 3 locations from the plan
            crew = make_location_crew(
                location_plan=f"Location {i+1} from this plan:\n{plans}",
                region_name=self.state.region_name,
            )
            result = crew.kickoff()
            location_descriptions.append(result.raw)
            self.state.locations_created.append(result.raw[:200])
        return "\n---\n".join(location_descriptions)

    @listen(generate_locations)
    def populate_locations(self, location_descriptions):
        # Generate NPCs and items for each location
        for i, loc_desc in enumerate(self.state.locations_created):
            loc_name = f"Location {i+1}"
            # NPCs
            npc_flow = NPCGenerationFlow()
            npc_flow.state.location_name = loc_name
            npc_flow.state.location_description = loc_desc
            npc_flow.state.region_context = self.state.region_concept
            npc_flow.kickoff()
            # Items
            item_flow = ItemGenerationFlow()
            item_flow.state.location_name = loc_name
            item_flow.kickoff()
        return "populated"

    @listen(populate_locations)
    def connect_exits(self, _):
        locations_summary = "\n".join(
            f"- {desc}" for desc in self.state.locations_created
        )
        crew = make_exit_connection_crew(
            locations=locations_summary,
            region_name=self.state.region_name,
        )
        result = crew.kickoff()
        return result.raw
