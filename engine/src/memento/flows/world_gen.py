"""World generation flow — creates regions with locations, NPCs, and items."""

import json

from memento.core import Flow, listen, start
from pydantic import BaseModel

from memento.crews.world_gen.region_design import make_region_design_crew
from memento.crews.world_gen.location_planning import make_location_planning_crew
from memento.crews.world_gen.location import make_location_crew
from memento.crews.world_gen.exit_connection import make_exit_connection_crew
from memento.flows.npc_gen import NPCGenerationFlow
from memento.flows.item_gen import ItemGenerationFlow
from memento.log import get_logger
from memento.room_map import extract_room_map, generate_fallback_map

logger = get_logger(__name__)


class LocationInfo(BaseModel):
    name: str = ""
    uuid: str = ""
    description: str = ""
    room_map: dict = {}


class WorldGenState(BaseModel):
    theme: str = ""
    player_level: int = 1
    num_locations: int = 5
    region_concept: str = ""
    location_plans: str = ""
    locations: list[LocationInfo] = []
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
        location_descriptions = []
        for i in range(self.state.num_locations):
            crew = make_location_crew(
                location_plan=f"Location {i+1} from this plan:\n{plans}",
                region_name=self.state.region_name,
            )
            result = crew.kickoff()
            raw = result.raw

            # Extract room_map JSON from crew output
            loc_name = f"Location {i+1}"
            room_map = extract_room_map(raw, loc_name)
            if not room_map:
                logger.warning("Using fallback map for %s", loc_name)
                room_map = generate_fallback_map(loc_name)

            # Try to extract location name and UUID from crew output
            # The architect crew creates entities and includes UUIDs in output
            loc_info = LocationInfo(
                name=room_map.get("name", loc_name),
                description=raw[:500],
                room_map=room_map,
            )
            self.state.locations.append(loc_info)

            location_descriptions.append(raw)
            self.state.locations_created.append(raw[:200])

        return "\n---\n".join(location_descriptions)

    @listen(generate_locations)
    def populate_locations(self, location_descriptions):
        """Generate NPCs and items for each location, and merge into room_maps."""
        for loc_info in self.state.locations:
            # NPCs
            npc_flow = NPCGenerationFlow()
            npc_flow.state.location_name = loc_info.name
            npc_flow.state.location_description = loc_info.description
            npc_flow.state.region_context = self.state.region_concept
            npc_flow.kickoff()

            # Items
            item_flow = ItemGenerationFlow()
            item_flow.state.location_name = loc_info.name
            item_flow.kickoff()

        return "populated"

    @listen(populate_locations)
    def connect_exits(self, _):
        locations_summary = "\n".join(
            f"- {loc.name}" for loc in self.state.locations
        )
        crew = make_exit_connection_crew(
            locations=locations_summary,
            region_name=self.state.region_name,
        )
        result = crew.kickoff()
        return result.raw

    @listen(connect_exits)
    def persist_room_maps(self, _):
        """Store room_map JSON on each location entity in the KG."""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            for loc_info in self.state.locations:
                if loc_info.uuid and loc_info.room_map:
                    client.kg.update_entity(
                        loc_info.uuid,
                        loc_info.name,
                        ["Location"],
                        json.dumps({"room_map": json.dumps(loc_info.room_map)}),
                    )
                    logger.info("Persisted room_map for %s", loc_info.name)
        except Exception:
            logger.warning("Failed to persist room_maps", exc_info=True)
        return "done"
