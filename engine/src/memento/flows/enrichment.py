"""Entity enrichment flow -- checks and fills missing attributes on room load."""

import json
import logging
from typing import Any, Callable

from memento.bonfires_client import get_client
from memento.crews.enrichment.crew import make_enrichment_crew

logger = logging.getLogger(__name__)

# Track which entities have been enriched this session to avoid re-running
_enriched: set[str] = set()
_art_enriched: set[str] = set()


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

        # Write back to KG — fetch current entity to preserve labels
        client = get_client()
        try:
            current = client.kg.get_entity(entity_uuid)
            labels = current.get("labels", [])
        except Exception:
            labels = []
        client.kg.update_entity(
            entity_uuid,
            entity_name,
            labels,
            existing_summary,
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
            else:
                _enriched.add(npc_id)
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
            else:
                _enriched.add(item_id)
        except Exception:
            pass

    # Check the location itself
    if location_uuid and location_uuid not in _enriched:
        try:
            entity = client.kg.get_entity(location_uuid)
            attrs = entity.get("attributes", {})
            if isinstance(attrs, str):
                attrs = json.loads(attrs) if attrs else {}
            summary = entity.get("summary", "")
            loc_name = entity.get("name", manifest.get("name", "Unknown"))
            missing = needs_enrichment("location", attrs)
            if missing:
                enrich_entity(location_uuid, loc_name, "location", summary, attrs, missing)
            else:
                _enriched.add(location_uuid)
        except Exception:
            pass


def enrich_entity_art(
    entity_uuid: str,
    entity_name: str,
    entity_type: str,
    existing_summary: str,
    existing_attributes: dict,
) -> str | None:
    """Generate ASCII art for a single entity. Returns art text or None on failure."""
    from memento.models.attributes import needs_art

    if entity_uuid in _art_enriched:
        return None
    _art_enriched.add(entity_uuid)

    if not needs_art(existing_attributes):
        return None

    logger.info("Generating art for %s '%s'", entity_type, entity_name)

    # Build a description from summary + key attributes
    desc_parts = [existing_summary or ""]
    for key in ("description", "personality", "atmosphere", "backstory"):
        val = existing_attributes.get(key)
        if val and isinstance(val, str):
            desc_parts.append(val)
    description = " ".join(p for p in desc_parts if p)[:500]

    if not description:
        description = f"A {entity_type} named {entity_name}"

    try:
        if entity_type == "location":
            from memento.crews.ascii_art.crew import make_scene_art_crew
            crew = make_scene_art_crew(entity_name, description, "dark fantasy", 35, 20)
        else:
            from memento.crews.ascii_art.crew import make_entity_art_crew
            crew = make_entity_art_crew(entity_name, entity_type, description, 20, 12)

        result = crew.kickoff()
        art_text = (result.raw if hasattr(result, "raw") else str(result)).strip()

        if not art_text:
            return None

        # Persist to KG
        merged = {**existing_attributes, "ascii_art": art_text}
        client = get_client()
        try:
            current = client.kg.get_entity(entity_uuid)
            labels = current.get("labels", [])
        except Exception:
            labels = []
        client.kg.update_entity(
            entity_uuid, entity_name, labels, existing_summary, attributes=merged,
        )
        logger.info("Generated art for %s '%s'", entity_type, entity_name)
        return art_text

    except Exception:
        logger.warning("Art generation failed for %s '%s'", entity_type, entity_name, exc_info=True)
        return None


def enrich_room_art(
    location_uuid: str,
    on_art_ready: Callable[[str, str], None] | None = None,
) -> None:
    """Generate ASCII art for all entities in a room that are missing it.

    Args:
        location_uuid: The room to process.
        on_art_ready: Optional callback(entity_id, art_text) called as each entity's art completes.
    """
    from memento.room_manifest import get_room_manifest

    manifest = get_room_manifest(location_uuid)
    client = get_client()

    def _process(entity_id: str, entity_name: str, entity_type: str) -> None:
        if not entity_id or entity_id in _art_enriched:
            return
        try:
            entity = client.kg.get_entity(entity_id)
            attrs = entity.get("attributes", {})
            if isinstance(attrs, str):
                attrs = json.loads(attrs) if attrs else {}
            summary = entity.get("summary", "")
            art = enrich_entity_art(entity_id, entity_name, entity_type, summary, attrs)
            if art and on_art_ready:
                on_art_ready(entity_id, art)
        except Exception:
            pass

    # NPCs
    for npc in manifest.get("npcs", []):
        _process(npc.get("id", ""), npc.get("name", ""), "npc")

    # Items
    for item in manifest.get("items", []):
        _process(item.get("id", ""), item.get("name", ""), "item")

    # Location
    if location_uuid and location_uuid not in _art_enriched:
        loc_name = manifest.get("name", "Unknown")
        _process(location_uuid, loc_name, "location")
