from pydantic import BaseModel

from .refs import EntityRef


class Faction(BaseModel):
    ref: EntityRef
    description: str = ""
    reputation: dict[str, float] = {}
    relationships: dict[str, str] = {}
