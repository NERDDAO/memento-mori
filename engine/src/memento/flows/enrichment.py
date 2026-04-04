"""Entity enrichment flow -- checks and fills missing attributes on room load."""

import json
import logging
from typing import Any

from memento.bonfires_client import get_client
from memento.crews.enrichment.crew import make_enrichment_crew

logger = logging.getLogger(__name__)

# Track which entities have been enriched this session to avoid re-running
_enriched: set[str] = set()


def enrich_entity(
    entity_uuid: str,
    entity_name: str,
    entity_type: str,
    existing_summary: str,
    existing_attributes: dict,
    missing_fields: list[str],
) -> dict[str, Any] | None:
    """Run enrichment crew for a single entity. Returns updated attributes or None on failure."""
    if entity_uuid in _enriched:
        return None
    _enriched.add(entity_uuid)

    if not missing_fields:
        return None

    logger.info("Enriching %s '%s': missing %s", entity_type, entity_name, missing_fields)

    try:
        crew = make_enrichment_crew(
            entity_name, entity_type, existing_summary, existing_attributes, missing_fields,
        )
        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        # Parse JSON from LLM output — strip markdown code blocks if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        new_attrs = json.loads(raw)

        # Merge with existing
        merged = {**existing_attributes, **new_attrs}

        # Write back to KG
        client = get_client()
        client.kg.update_entity(
            entity_uuid,
            entity_name,
            [],  # don't change labels
            existing_summary,  # don't change summary
            attributes=merged,
        )
        logger.info("Enriched %s '%s' with %d fields", entity_type, entity_name, len(new_attrs))
        return merged

    except Exception:
        logger.warning("Enrichment failed for %s '%s'", entity_type, entity_name, exc_info=True)
        return None


def enrich_room_entities(location_uuid: str) -> None:
    """Check all entities in a room and enrich any with incomplete attributes.

    Called on room load. Non-blocking -- runs enrichment for entities that need it.
    """
    from memento.room_manifest import get_room_manifest
    from memento.models.attributes import needs_enrichment

    manifest = get_room_manifest(location_uuid)
    client = get_client()

    # Check NPCs
    for npc in manifest.get("npcs", []):
        npc_id = npc.get("id", "")
        if not npc_id or npc_id in _enriched:
            continue
        try:
            entity = client.kg.get_entity(npc_id)
            attrs = entity.get("attributes", {})
            if isinstance(attrs, str):
                attrs = json.loads(attrs) if attrs else {}
            summary = entity.get("summary", "")
            missing = needs_enrichment("npc", attrs)
            if missing:
                enrich_entity(npc_id, npc.get("name", ""), "npc", summary, attrs, missing)
        except Exception:
            pass

    # Check items on ground
    for item in manifest.get("items", []):
        item_id = item.get("id", "")
        if not item_id or item_id in _enriched:
            continue
        try:
            entity = client.kg.get_entity(item_id)
            attrs = entity.get("attributes", {})
            if isinstance(attrs, str):
                attrs = json.loads(attrs) if attrs else {}
            summary = entity.get("summary", "")
            missing = needs_enrichment("item", attrs)
            if missing:
                enrich_entity(item_id, item.get("name", ""), "item", summary, attrs, missing)
        except Exception:
            pass
