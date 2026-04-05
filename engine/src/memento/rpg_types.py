"""World seed custom types for Graphiti episode extraction.

These are NOT action replays — combat/movement/trade are handled inline by NPC
tool calls. These types represent world consequences: new entities, quests,
location changes, and lore that should exist as a result of what happened.

Each type's docstring is used as the matching corpus for the TypeSelector.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NewEntitySeed(BaseModel):
    """Extracted when conversation implies a new NPC, creature, or item should exist in the world that doesn't already."""

    entity_name: str = Field(..., description="Name of the new entity")
    entity_type: str = Field("", description="One of: npc, item, creature")
    location: str = Field("", description="Where the entity should appear")
    description: str = Field("", description="Brief description of the entity")
    source_context: str = Field("", description="What in the conversation implied this entity")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["NewEntitySeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"entity_name": self.entity_name}
        if self.entity_type:
            out["entity_type"] = self.entity_type
        if self.location:
            out["location"] = self.location
        if self.description:
            out["description"] = self.description
        if self.source_context:
            out["source_context"] = self.source_context
        return out


class QuestSeed(BaseModel):
    """Extracted when interaction suggests a quest opportunity, quest progression, or quest-related discovery."""

    quest_name: str = Field("", description="Name or short title of the quest")
    giver_name: str = Field("", description="NPC who triggered or gave the quest")
    objective_hint: str = Field("", description="What needs to be done")
    trigger_context: str = Field("", description="What in the conversation triggered this")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["QuestSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.quest_name:
            out["quest_name"] = self.quest_name
        if self.giver_name:
            out["giver_name"] = self.giver_name
        if self.objective_hint:
            out["objective_hint"] = self.objective_hint
        if self.trigger_context:
            out["trigger_context"] = self.trigger_context
        return out


class LocationChange(BaseModel):
    """Extracted when the room state should change as a consequence of what happened — doors opened, fires started, structures collapsed."""

    location: str = Field("", description="Location being changed")
    change_description: str = Field("", description="What changed")
    new_exits: list[str] = Field(default_factory=list, description="New exits or passages revealed")
    removed_features: list[str] = Field(default_factory=list, description="Features destroyed or removed")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LocationChange"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.location:
            out["location"] = self.location
        if self.change_description:
            out["change_description"] = self.change_description
        if self.new_exits:
            out["new_exits"] = self.new_exits
        if self.removed_features:
            out["removed_features"] = self.removed_features
        return out


class LoreSeed(BaseModel):
    """Extracted when new world lore, history, or mythology is revealed or created during conversation."""

    lore_topic: str = Field("", description="Topic or title of the lore")
    content: str = Field("", description="The lore content")
    source_npc: str = Field("", description="NPC who revealed it")
    related_locations: list[str] = Field(default_factory=list, description="Locations related to this lore")

    @classmethod
    def get_graphiti_labels(cls) -> list[str]:
        return ["LoreSeed"]

    def to_entity_attributes(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.lore_topic:
            out["lore_topic"] = self.lore_topic
        if self.content:
            out["content"] = self.content
        if self.source_npc:
            out["source_npc"] = self.source_npc
        if self.related_locations:
            out["related_locations"] = self.related_locations
        return out


# Registry of all world seed types — used by TypeSelector and Delve type registration
RPG_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "NewEntitySeed": NewEntitySeed,
    "QuestSeed": QuestSeed,
    "LocationChange": LocationChange,
    "LoreSeed": LoreSeed,
}
