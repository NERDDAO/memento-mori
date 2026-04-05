"""WorldReactionCrew — creates KG entities from episode-extracted world seeds.

Does NOT re-resolve inline actions (combat, movement, trade) — those are
handled by NPC MCP tool calls during the round. This crew creates NEW things
in the world as consequences of what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memento.log import get_logger

logger = get_logger(__name__)


@dataclass
class TurnContext:
    """Context passed to reaction handlers."""
    location: str
    location_uuid: str
    player_name: str
    combined_action: str = ""
    episode_summary: str = ""


class WorldReactionCrew:
    """Orchestrates entity creation from episode-extracted world seeds."""

    def react(self, extracted_entities: list[dict], ctx: TurnContext) -> dict[str, Any]:
        """Process all extracted seeds. Returns summary of what was created."""
        results: dict[str, Any] = {}

        for entity in extracted_entities:
            entity_type = entity.get("type", "")
            try:
                if entity_type == "NewEntitySeed":
                    results.setdefault("new_entities", []).append(
                        self._create_entity(entity, ctx)
                    )
                elif entity_type == "QuestSeed":
                    results.setdefault("new_quests", []).append(
                        self._create_quest(entity, ctx)
                    )
                elif entity_type == "LocationChange":
                    results.setdefault("location_changes", []).append(
                        self._apply_location_change(entity, ctx)
                    )
                elif entity_type == "LoreSeed":
                    results.setdefault("lore", []).append(
                        self._persist_lore(entity, ctx)
                    )
            except Exception:
                logger.warning("World reaction failed for %s", entity_type, exc_info=True)

        return results

    def _resolve_uuid(self, name: str) -> str:
        """Resolve an entity name to UUID via KG search."""
        if not name:
            return ""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            result = client.kg.search(name, num_results=3)
            entities = result.get("entities", result.get("nodes", []))
            for e in entities:
                if e.get("name", "").lower() == name.lower():
                    return e.get("uuid", "")
        except Exception:
            logger.debug("UUID resolution failed for %s", name)
        return ""

    def _create_entity(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a new entity in the KG from a NewEntitySeed."""
        entity_name = seed.get("entity_name", "")
        entity_type = seed.get("entity_type", "npc")
        description = seed.get("description", "")

        if not entity_name:
            return {"error": "no entity_name"}

        label_map = {"npc": "NPC", "item": "Item", "creature": "Creature"}
        labels = [label_map.get(entity_type, "Entity")]

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                entity_name,
                labels,
                {"description": description, "source": "world_reaction", "location": ctx.location},
            )

            if ctx.location_uuid:
                edge_type = "LOCATED_IN" if entity_type in ("npc", "creature") else "FOUND_AT"
                client.kg.create_edge(uuid, ctx.location_uuid, edge_type, "")

            logger.info("Created %s entity: %s (%s)", entity_type, entity_name, uuid)
            return {"uuid": uuid, "name": entity_name, "type": entity_type}
        except Exception:
            logger.warning("Failed to create entity %s", entity_name, exc_info=True)
            return {"error": f"creation_failed: {entity_name}"}

    def _create_quest(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a quest entity in the KG from a QuestSeed."""
        quest_name = seed.get("quest_name", "")
        giver_name = seed.get("giver_name", "")
        objective = seed.get("objective_hint", "")

        if not quest_name:
            return {"error": "no quest_name"}

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                quest_name,
                ["Quest"],
                {"objective": objective, "giver": giver_name, "location": ctx.location, "source": "world_reaction"},
            )

            if ctx.location_uuid:
                client.kg.create_edge(uuid, ctx.location_uuid, "AVAILABLE_AT", "")

            giver_uuid = self._resolve_uuid(giver_name)
            if giver_uuid:
                client.kg.create_edge(uuid, giver_uuid, "GIVEN_BY", "")

            logger.info("Created quest: %s (%s)", quest_name, uuid)
            return {"uuid": uuid, "name": quest_name, "giver": giver_name}
        except Exception:
            logger.warning("Failed to create quest %s", quest_name, exc_info=True)
            return {"error": f"creation_failed: {quest_name}"}

    def _apply_location_change(self, seed: dict, ctx: TurnContext) -> dict:
        """Update location state in KG from a LocationChange seed."""
        change = seed.get("change_description", "")
        new_exits = seed.get("new_exits", [])

        if not change and not new_exits:
            return {"error": "no change specified"}

        try:
            if ctx.location_uuid:
                from memento.bonfires_client import get_client
                client = get_client()
                updates: dict[str, Any] = {}
                if change:
                    updates["recent_change"] = change
                if new_exits:
                    updates["new_exits"] = new_exits
                client.kg.update_entity(ctx.location_uuid, updates)

            logger.info("Location change at %s: %s", ctx.location, change)
            return {"location": ctx.location, "change": change, "new_exits": new_exits}
        except Exception:
            logger.warning("Failed to apply location change at %s", ctx.location, exc_info=True)
            return {"error": f"location_change_failed: {ctx.location}"}

    def _persist_lore(self, seed: dict, ctx: TurnContext) -> dict:
        """Create a lore entity in the KG from a LoreSeed."""
        topic = seed.get("lore_topic", "")
        content = seed.get("content", "")
        source_npc = seed.get("source_npc", "")

        if not topic:
            return {"error": "no lore_topic"}

        try:
            from memento.bonfires_client import get_client
            client = get_client()
            uuid = client.kg.create_entity(
                topic,
                ["Lore"],
                {"content": content, "source_npc": source_npc, "location": ctx.location, "source": "world_reaction"},
            )

            for loc_name in seed.get("related_locations", []):
                loc_uuid = self._resolve_uuid(loc_name)
                if loc_uuid:
                    client.kg.create_edge(uuid, loc_uuid, "RELATES_TO", "")

            logger.info("Created lore: %s (%s)", topic, uuid)
            return {"uuid": uuid, "topic": topic}
        except Exception:
            logger.warning("Failed to persist lore %s", topic, exc_info=True)
            return {"error": f"lore_failed: {topic}"}
