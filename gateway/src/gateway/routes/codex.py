"""Codex endpoint — assembles manifest-scoped entities with onchain data."""

import asyncio
import json as _json
from fastapi import APIRouter, HTTPException

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def _get_location_uuid(player_id: str) -> str | None:
    """Resolve a player's current location UUID via ws_hub then KG search."""
    from gateway.app import ws_hub

    location_name = ws_hub.player_locations.get(player_id) if ws_hub else None
    if not location_name:
        return None

    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        result = await asyncio.to_thread(client.kg.search, location_name, 5)
        entities = result.get("entities", result.get("nodes", []))
        for entity in entities:
            if "Location" in entity.get("labels", []):
                return entity.get("uuid", entity.get("id", ""))
    except Exception:
        logger.debug("KG search failed for location %s", location_name)

    # Fallback: world.json threshold UUID
    try:
        import json
        from pathlib import Path
        world_json = Path(__file__).parent.parent.parent.parent / "world.json"
        if world_json.exists():
            data = json.loads(world_json.read_text())
            if location_name == "The Threshold" and data.get("threshold_uuid"):
                return data["threshold_uuid"]
    except Exception:
        pass

    return None


async def _fetch_chain_for_entity(entity_id: str, labels: list[str]) -> dict | None:
    """Fetch onchain record for an entity based on its labels. Returns None on miss."""
    from gateway.chain_client import fetch_chain_record, table_for_labels

    table = table_for_labels(labels)
    if table is None:
        return None
    try:
        return await fetch_chain_record(table, entity_id)
    except Exception:
        logger.debug("Chain fetch failed for %s in %s", entity_id, table)
        return None


async def _get_kg_entity(entity_id: str) -> dict | None:
    """Fetch a single entity from the KG. Returns None on failure."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, entity_id)
        if isinstance(entity, dict) and "entity" in entity:
            entity = entity["entity"]
        return entity
    except Exception:
        logger.debug("KG entity fetch failed for %s", entity_id)
        return None


def _parse_attributes(entity: dict | None) -> dict:
    """Parse attributes from a KG entity. Handles JSON string or dict."""
    raw = (entity or {}).get("attributes", {})
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return raw


def _extract_summary(entity: dict) -> str:
    """Extract plain-text summary from a KG entity (handles JSON blob summaries)."""
    import json
    summary = entity.get("summary", "")
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            parsed = json.loads(summary)
            return parsed.get("summary", summary)
        except (json.JSONDecodeError, TypeError):
            pass
    return summary


@router.get("/codex/{player_id}")
async def get_codex(player_id: str, location_uuid: str | None = None):
    """Get all manifest entities for a player, grouped by type, with inline chain data."""
    from memento.room_manifest import get_room_manifest
    from memento.inventory_manifest import get_inventory_manifest

    # 1. Resolve player location (client can provide, otherwise look up)
    if not location_uuid:
        location_uuid = await _get_location_uuid(player_id)

    # 2. Fetch room manifest + inventory manifest in parallel
    room_task = (
        asyncio.to_thread(get_room_manifest, location_uuid)
        if location_uuid else None
    )
    inv_task = asyncio.to_thread(get_inventory_manifest, player_id)

    try:
        if room_task:
            room_manifest, inv_manifest = await asyncio.gather(room_task, inv_task)
        else:
            inv_manifest = await inv_task
            room_manifest = None
    except Exception:
        logger.error("Failed to fetch manifests for %s", player_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch codex data")

    # 3. Build NPC list from room manifest
    raw_npcs = room_manifest.get("npcs", []) if room_manifest else []
    # Fetch KG entity details + chain data for each NPC in parallel
    npc_entity_tasks = [_get_kg_entity(n["id"]) for n in raw_npcs if n.get("id")]
    npc_chain_tasks = [
        _fetch_chain_for_entity(n["id"], ["Character", "NPC"])
        for n in raw_npcs if n.get("id")
    ]
    npc_entities = await asyncio.gather(*npc_entity_tasks) if npc_entity_tasks else []
    npc_chains = await asyncio.gather(*npc_chain_tasks) if npc_chain_tasks else []

    npcs = []
    for raw, kg_entity, chain in zip(raw_npcs, npc_entities, npc_chains):
        labels = (kg_entity or {}).get("labels", [])
        summary = _extract_summary(kg_entity) if kg_entity else ""
        npcs.append({
            "id": raw.get("id", ""),
            "name": raw.get("name", "Unknown"),
            "labels": labels,
            "summary": summary,
            "chain": chain,
            "attributes": _parse_attributes(kg_entity),
        })

    # 4. Build ground items from room manifest
    raw_ground = room_manifest.get("items", []) if room_manifest else []
    ground_entity_tasks = [_get_kg_entity(i["id"]) for i in raw_ground if i.get("id")]
    ground_chain_tasks = [
        _fetch_chain_for_entity(i["id"], ["Item"])
        for i in raw_ground if i.get("id")
    ]
    ground_entities = await asyncio.gather(*ground_entity_tasks) if ground_entity_tasks else []
    ground_chains = await asyncio.gather(*ground_chain_tasks) if ground_chain_tasks else []

    ground_items = []
    for raw, kg_entity, chain in zip(raw_ground, ground_entities, ground_chains):
        summary = _extract_summary(kg_entity) if kg_entity else ""
        ground_items.append({
            "id": raw.get("id", ""),
            "name": raw.get("name", "Unknown"),
            "labels": ["Item"],
            "summary": summary,
            "chain": chain,
            "attributes": _parse_attributes(kg_entity),
        })

    # 5. Build inventory items (backpack + equipped)
    all_inv_items = []
    for slot, item in inv_manifest.get("equipped", {}).items():
        if item:
            all_inv_items.append(item)
    all_inv_items.extend(inv_manifest.get("backpack", []))

    inv_chain_tasks = [
        _fetch_chain_for_entity(item["id"], ["Item"])
        for item in all_inv_items if item.get("id")
    ]
    inv_chains = await asyncio.gather(*inv_chain_tasks) if inv_chain_tasks else []

    inventory = []
    for item, chain in zip(all_inv_items, inv_chains):
        inventory.append({
            "id": item.get("id", ""),
            "name": item.get("name", "Unknown"),
            "rarity": item.get("rarity", "common"),
            "slot_type": item.get("slot_type", ""),
            "equipped": item.get("equipped", False),
            "effects": item.get("effects", []),
            "chain": chain,
        })

    # 6. Build location section — current room + exit destinations
    locations = []
    if room_manifest:
        loc_kg_entity = await _get_kg_entity(
            room_manifest.get("id", location_uuid or "")
        ) if room_manifest.get("id") or location_uuid else None

        exits = []
        for ex in room_manifest.get("exits", []):
            exits.append({
                "direction": ex.get("direction", "unknown"),
                "target": ex.get("target", "unknown"),
                "target_id": ex.get("target_id", ""),
            })
        locations.append({
            "id": room_manifest.get("id", location_uuid or ""),
            "name": room_manifest.get("name", "Unknown"),
            "summary": room_manifest.get("summary", ""),
            "exits": exits,
            "current": True,
            "attributes": _parse_attributes(loc_kg_entity),
        })
        # Add exit destinations as separate location entries
        for ex in exits:
            if ex.get("target_id"):
                locations.append({
                    "id": ex["target_id"],
                    "name": ex["target"],
                    "summary": "",
                    "exits": [],
                    "current": False,
                    "direction": ex["direction"],
                })

    # 7. Build player section
    player_entity = await _get_kg_entity(player_id)
    player_chain = await _fetch_chain_for_entity(player_id, ["Player", "Character"])

    player_info = {
        "id": player_id,
        "name": (player_entity or {}).get("name", "Unknown"),
        "level": 1,
        "health": 100,
        "archetype": "",
        "chain": player_chain,
    }
    # Enrich from chain data if available
    if player_chain and isinstance(player_chain, dict):
        player_info["level"] = player_chain.get("level", player_info["level"])
        player_info["health"] = player_chain.get("health", player_info["health"])
        player_info["archetype"] = player_chain.get("archetype", player_info["archetype"])

    # Trigger background enrichment for entities missing attributes
    import threading

    def _bg_enrich():
        import asyncio as _aio
        try:
            from memento.flows.enrichment import enrich_room_entities
            from gateway.app import ws_hub as _hub
            if not location_uuid:
                return

            # Notify client that enrichment is starting
            if _hub:
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    _hub.send_to_player(player_id, {
                        "type": "status",
                        "activity": "Enriching entities...",
                    })
                )
                loop.close()

            enrich_room_entities(location_uuid)

            # Notify client that enrichment is done
            if _hub:
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    _hub.send_to_player(player_id, {
                        "type": "status",
                        "activity": "Codex updated",
                    })
                )
                loop.close()
        except Exception:
            logger.debug("Background enrichment failed", exc_info=True)

    threading.Thread(target=_bg_enrich, daemon=True).start()

    return {
        "npcs": npcs,
        "ground_items": ground_items,
        "inventory": inventory,
        "locations": locations,
        "player": player_info,
    }
