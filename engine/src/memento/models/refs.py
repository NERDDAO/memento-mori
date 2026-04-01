from pydantic import BaseModel


class EntityRef(BaseModel):
    uuid: str
    name: str
    labels: list[str] = []
