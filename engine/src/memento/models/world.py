from pydantic import BaseModel

from .refs import EntityRef


class Exit(BaseModel):
    target_location: EntityRef
    direction: str = ""
    description: str = ""
    locked: bool = False


class Location(BaseModel):
    ref: EntityRef
    description: str = ""
    region: EntityRef | None = None
    exits: list[Exit] = []
    npc_ids: list[str] = []
    item_ids: list[str] = []
    is_stub: bool = False


class Region(BaseModel):
    ref: EntityRef
    description: str = ""
    biome: str = ""
    controlling_faction: EntityRef | None = None
    locations: list[EntityRef] = []
    danger_level: int = 1
