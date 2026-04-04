"""Entity enrichment crew -- fills missing structured attributes on KG entities.

Lightweight single-agent crew that takes an entity's existing data (name, labels,
summary, current attributes) and generates missing fields to match the attribute schema.
Triggered on room load for entities with incomplete data.
"""

from memento.core import Agent, Crew, Task, Process, LLM
from memento.config import get_model_for_crew
from memento.models.attributes import (
    NPC_ATTRIBUTE_FIELDS,
    ITEM_ATTRIBUTE_FIELDS,
    LOCATION_ATTRIBUTE_FIELDS,
)

_FIELD_GUIDES: dict[str, dict[str, str]] = {
    "npc": NPC_ATTRIBUTE_FIELDS,
    "item": ITEM_ATTRIBUTE_FIELDS,
    "location": LOCATION_ATTRIBUTE_FIELDS,
}


def make_enrichment_crew(
    entity_name: str,
    entity_type: str,  # 'npc' | 'item' | 'location'
    existing_summary: str,
    existing_attributes: dict,
    missing_fields: list[str],
) -> Crew:
    """Build a crew that generates missing attribute fields for an entity."""
    model = get_model_for_crew("enrichment")

    enricher = Agent(
        role="Entity Data Enricher",
        goal=f"Generate missing structured data for {entity_type} '{entity_name}'",
        backstory=(
            "You enrich game entities with structured data for a dark fantasy MUD. "
            "Given an entity's name, type, summary, and existing attributes, you infer "
            "the missing fields. Stay consistent with existing data. Be concise but flavorful."
        ),
        llm=LLM(model=model),
    )

    field_guide = _FIELD_GUIDES.get(entity_type, {})
    fields_desc = "\n".join(
        f"- {f}: {field_guide.get(f, 'fill appropriately')}"
        for f in missing_fields
    )

    task = Task(
        description=(
            f"Generate missing attribute fields for this {entity_type}.\n\n"
            f"Entity: {entity_name}\n"
            f"Summary: {existing_summary}\n"
            f"Existing attributes: {existing_attributes}\n\n"
            f"Generate ONLY these missing fields:\n{fields_desc}\n\n"
            f"Output as a valid JSON object with only the missing fields. "
            f"No markdown, no explanation, just the JSON."
        ),
        expected_output="JSON object with the missing fields filled in",
        agent=enricher,
    )

    return Crew(
        agents=[enricher],
        tasks=[task],
        process=Process.sequential,
    )
