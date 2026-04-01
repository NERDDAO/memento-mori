from pydantic import BaseModel

from .refs import EntityRef


class Quest(BaseModel):
    ref: EntityRef
    description: str = ""
    giver: EntityRef | None = None
    stages: list[str] = []
    current_stage: int = 0
    completed: bool = False
    rewards: list[str] = []
