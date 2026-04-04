"""Inventory routes — structured actions for equip/unequip/drop/use/pickup.

These bypass the narrative crew pipeline for instant feedback.
Each action validates deterministically, writes to KG (+ chain in background),
and broadcasts state_update via WebSocket.
"""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/inventory")


class EquipRequest(BaseModel):
    player_id: str
    item_id: str
    slot: str


class UnequipRequest(BaseModel):
    player_id: str
    slot: str


class DropRequest(BaseModel):
    player_id: str
    item_id: str
    quantity: int | None = None


class UseRequest(BaseModel):
    player_id: str
    item_id: str


class PickupRequest(BaseModel):
    player_id: str
    item_id: str


async def _broadcast_inventory_update(player_id: str, manifest: dict) -> None:
    """Broadcast inventory + room state updates via WebSocket."""
    from gateway.app import ws_hub
    if not ws_hub:
        return

    from memento.inventory_manifest import get_inventory_as_state_update
    inventory_items = await asyncio.to_thread(get_inventory_as_state_update, player_id)

    await ws_hub.send_to_player(player_id, {
        "type": "state_update",
        "state_update": {"inventory": inventory_items},
    })

    # Also broadcast room_map update to all players in the same location
    # (items on ground may have changed)
    location = ws_hub.player_locations.get(player_id)
    if location:
        from memento.room_manifest import get_room_manifest
        # We need the location UUID, not name — get from session
        # For now, broadcast a lightweight item list refresh
        await ws_hub.broadcast_to_location(location, {
            "type": "room_items_changed",
            "location": location,
        })


@router.get("/{player_id}")
async def get_inventory(player_id: str):
    """Get full inventory manifest for a player."""
    from memento.inventory_manifest import get_inventory_manifest
    try:
        manifest = await asyncio.to_thread(get_inventory_manifest, player_id)
        return manifest
    except Exception:
        logger.error("Inventory query failed for %s", player_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch inventory")


@router.post("/equip")
async def equip_item(req: EquipRequest):
    """Equip an item to a slot. Instant — no LLM round-trip."""
    from memento.inventory_actions import equip, InventoryError
    try:
        manifest = await asyncio.to_thread(equip, req.player_id, req.item_id, req.slot)
        await _broadcast_inventory_update(req.player_id, manifest)
        return {"status": "ok", "action": "equip", "item_id": req.item_id, "slot": req.slot}
    except InventoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("Equip failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Equip failed")


@router.post("/unequip")
async def unequip_item(req: UnequipRequest):
    """Unequip an item from a slot. Instant."""
    from memento.inventory_actions import unequip, InventoryError
    try:
        manifest = await asyncio.to_thread(unequip, req.player_id, req.slot)
        await _broadcast_inventory_update(req.player_id, manifest)
        return {"status": "ok", "action": "unequip", "slot": req.slot}
    except InventoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("Unequip failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Unequip failed")


@router.post("/drop")
async def drop_item(req: DropRequest):
    """Drop an item into the current room. Chain tx fires in background."""
    from memento.inventory_actions import drop, InventoryError

    # Get player's current location
    from gateway.app import ws_hub
    location = ws_hub.player_locations.get(req.player_id) if ws_hub else None
    if not location:
        raise HTTPException(status_code=400, detail="Player location unknown")

    # Resolve location UUID from session
    location_uuid = await _get_location_uuid(req.player_id)
    if not location_uuid:
        raise HTTPException(status_code=400, detail="Cannot resolve location")

    try:
        manifest = await asyncio.to_thread(
            drop, req.player_id, req.item_id, location_uuid, req.quantity,
        )
        await _broadcast_inventory_update(req.player_id, manifest)
        return {"status": "ok", "action": "drop", "item_id": req.item_id}
    except InventoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("Drop failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Drop failed")


@router.post("/use")
async def use_item(req: UseRequest):
    """Use a consumable item. Applies effects instantly."""
    from memento.inventory_actions import use, InventoryError
    try:
        manifest = await asyncio.to_thread(use, req.player_id, req.item_id)
        await _broadcast_inventory_update(req.player_id, manifest)
        return {"status": "ok", "action": "use", "item_id": req.item_id}
    except InventoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("Use failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Use failed")


@router.post("/pickup")
async def pickup_item(req: PickupRequest):
    """Pick up an item from the current room."""
    from memento.inventory_actions import pickup, InventoryError

    location_uuid = await _get_location_uuid(req.player_id)
    if not location_uuid:
        raise HTTPException(status_code=400, detail="Cannot resolve location")

    try:
        manifest = await asyncio.to_thread(
            pickup, req.player_id, req.item_id, location_uuid,
        )
        await _broadcast_inventory_update(req.player_id, manifest)
        return {"status": "ok", "action": "pickup", "item_id": req.item_id}
    except InventoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error("Pickup failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Pickup failed")


async def _get_location_uuid(player_id: str) -> str | None:
    """Resolve a player's current location UUID from the session."""
    try:
        from memento.bonfires_client import get_client
        client = await asyncio.to_thread(get_client)
        entity = await asyncio.to_thread(client.kg.get_entity, player_id)
        # Get outgoing LOCATED_IN edge from player to location
        edges = await asyncio.to_thread(
            client.kg.get_edges, player_id,
            direction="outgoing", edge_type="LOCATED_IN",
        )
        for edge in edges:
            if not (edge.get("expired_at") or edge.get("invalid_at")):
                target = edge.get("target", {})
                return target.get("uuid", target.get("id", ""))
        return None
    except Exception:
        logger.debug("Failed to resolve location for %s", player_id)
        return None
