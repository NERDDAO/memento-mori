from pydantic import BaseModel

from .refs import EntityRef


class Item(BaseModel):
    ref: EntityRef
    description: str = ""
    rarity: str = "common"
    slot_type: str = ""
    effects: list[str] = []
    is_consumable: bool = False
    is_quest_item: bool = False
    stackable: bool = False
