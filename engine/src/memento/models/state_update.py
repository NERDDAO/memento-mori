"""Canonical state update schema — the contract between engine, gateway, and client.

This is the single source of truth for the shape of state updates sent
from the engine through the gateway to the client via WebSocket.
"""

from __future__ import annotations

from pydantic import BaseModel


class ExitUpdate(BaseModel):
    direction: str = ""
    name: str = ""


class EntityRefUpdate(BaseModel):
    name: str = ""
    id: str = ""
    role: str = ""


class InventoryItemUpdate(BaseModel):
    name: str = ""
    rarity: str = "common"
    equipped: bool = False


class WorldTimeDisplay(BaseModel):
    moon_phase: str = ""
    moon_icon: str = ""
    day_name: str = ""
    day_number: int = 0
    month: str = ""
    season: str = ""
    time_of_day: str = ""
    tick: int = 0


class RoomMapUpdate(BaseModel):
    id: str = ""
    name: str = ""
    width: int = 0
    height: int = 0
    tiles: list[str] = []
    npcs: list[dict] = []
    items: list[dict] = []
    exits: list[dict] = []
    spawn: dict = {}


class StateUpdate(BaseModel):
    """State update sent from engine to client after each turn.

    All fields are optional — only changed fields are included.
    The client applies these on top of its current state.
    """
    schema_version: int = 1
    location: str | None = None
    health: int | None = None
    max_health: int | None = None
    level: int | None = None
    xp: int | None = None
    exits: list[ExitUpdate] | None = None
    npcs: list[EntityRefUpdate] | None = None
    items: list[EntityRefUpdate] | None = None
    inventory: list[InventoryItemUpdate] | None = None
    room_map: RoomMapUpdate | None = None
    world_time: WorldTimeDisplay | None = None
    skills: dict[str, int] | None = None
    status: str | None = None
    cause: str | None = None
    subsystem_warnings: list[str] = []
