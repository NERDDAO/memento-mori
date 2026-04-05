"""NPC generation flow — creates NPCs for a location."""

import json
import logging
import re

from memento.core import Flow, listen, start
from pydantic import BaseModel

from memento.crews.npc_gen.planning import make_npc_planning_crew
from memento.crews.npc_gen.concept import make_concept_crew
from memento.crews.npc_gen.mechanics import make_mechanics_crew
from memento.crews.npc_gen.finalization import make_finalization_crew

_logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> dict | None:
    """Extract the first JSON object from text, handling optional ```json fences."""
    # Try fenced block first
    m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    # Try bare JSON object
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _persist_npc_attributes(finalization_result: str, entity_name: str) -> None:
    """Parse structured attributes from finalization output and write to KG."""
    attrs = _extract_json_block(finalization_result)
    if not attrs:
        _logger.debug("No JSON attributes found in finalization output for %s", entity_name)
        return

    # Extract UUID from the finalization result text
    uuid_match = re.search(r"UUID:\s*([a-f0-9-]+)", finalization_result, re.IGNORECASE)
    if not uuid_match:
        _logger.debug("No UUID found in finalization output for %s", entity_name)
        return

    uuid = uuid_match.group(1)
    try:
        from memento.bonfires_client import get_client
        client = get_client()
        client.kg.update_entity(uuid, entity_name, [], "", attributes=attrs)
        _logger.info("Persisted structured attributes for NPC '%s' (%s)", entity_name, uuid)
    except Exception:
        _logger.warning("Failed to persist attributes for NPC '%s'", entity_name, exc_info=True)


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

            # Persist structured attributes extracted from the finalization output
            try:
                _persist_npc_attributes(result.raw, concept[:50])
            except Exception:
                _logger.debug("Attribute persistence skipped for NPC at %s", self.state.location_name)

            # Generate ASCII art for the new NPC in background
            try:
                npc_uuid = re.search(r"UUID:\s*([a-f0-9-]+)", result.raw, re.IGNORECASE)
                if npc_uuid:
                    import threading
                    from memento.flows.enrichment import enrich_entity_art
                    _uid = npc_uuid.group(1)
                    _name = concept[:50]
                    _desc = concept[:500]
                    threading.Thread(
                        target=enrich_entity_art,
                        args=(_uid, _name, "npc", _desc, {}),
                        daemon=True,
                    ).start()
            except Exception:
                _logger.debug("Art generation skipped for NPC at %s", self.state.location_name)

            # Spawn Bonfires agent for this NPC
            try:
                from memento.agent_controller import get_agent_controller
                controller = get_agent_controller()
                controller.spawn_npc_agent(
                    concept=concept,
                    mechanics=mechanized,
                    finalization_result=result.raw,
                    location_name=self.state.location_name,
                    npc_labels=["Combat", "Memory", "Trade"],
                )
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Agent spawn failed for NPC at %s", self.state.location_name, exc_info=True,
                )

        return self.state.npcs_created
