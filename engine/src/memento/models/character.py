from pydantic import BaseModel

from .refs import EntityRef


class CharacterStats(BaseModel):
    level: int = 1
    health: int = 100
    max_health: int = 100
    experience: int = 0
    currency: int = 0
    attributes: dict[str, int] = {}


class Disposition(BaseModel):
    friendship: float = 0.0
    trust: float = 0.0
    respect: float = 0.0
    romance: float = 0.0


class Character(BaseModel):
    ref: EntityRef
    stats: CharacterStats = CharacterStats()
    personality_type: str = ""
    personality_traits: list[str] = []
    skills: dict[str, int] = {}
    abilities: list[str] = []
    inventory: list[EntityRef] = []
    equipped: dict[str, EntityRef] = {}
    status_effects: list[str] = []
    dispositions: dict[str, Disposition] = {}
    important_memories: list[str] = []
    is_npc: bool = False
    is_dead: bool = False
