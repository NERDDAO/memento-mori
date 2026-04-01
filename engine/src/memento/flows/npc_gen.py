"""NPC generation flow — creates NPCs for a location."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from memento.crews.npc_gen.planning import make_npc_planning_crew
from memento.crews.npc_gen.concept import make_concept_crew
from memento.crews.npc_gen.mechanics import make_mechanics_crew
from memento.crews.npc_gen.finalization import make_finalization_crew


class NPCGenState(BaseModel):
    location_name: str = ""
    location_description: str = ""
    region_context: str = ""
    npc_roles: str = ""
    npcs_created: list[str] = []


class NPCGenerationFlow(Flow[NPCGenState]):
    @start()
    def plan_npcs(self):
        crew = make_npc_planning_crew(
            location_name=self.state.location_name,
            location_description=self.state.location_description,
            existing_npcs="",
        )
        result = crew.kickoff()
        self.state.npc_roles = result.raw
        return result.raw

    @listen(plan_npcs)
    def generate_npcs(self, roles):
        # Process each NPC sequentially
        # The roles output is free-form text listing NPC roles
        # We'll generate 2 NPCs from the plan
        for i in range(2):
            # Concept
            concept_crew = make_concept_crew(
                npc_role=f"NPC {i+1} from this plan:\n{roles}",
                location_name=self.state.location_name,
                region_context=self.state.region_context,
            )
            concept = concept_crew.kickoff().raw

            # Mechanics
            mech_crew = make_mechanics_crew(npc_concept=concept)
            mechanized = mech_crew.kickoff().raw

            # Finalization — write to KG
            final_crew = make_finalization_crew(
                npc_full=f"{concept}\n\nMechanics:\n{mechanized}",
                location_name=self.state.location_name,
            )
            result = final_crew.kickoff()
            self.state.npcs_created.append(result.raw[:200])

        return self.state.npcs_created
