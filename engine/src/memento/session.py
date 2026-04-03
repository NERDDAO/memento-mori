"""Session manager — handles player lifecycle in the game world."""

from __future__ import annotations

import json

from memento.bonfires_client import get_client
from memento.config.archetypes import get_archetype
from memento.crews.narrative.narration import make_narration_crew
from memento.log import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages game sessions — player creation, placement, and cleanup."""

    def create_player(self, player_name: str, wallet_address: str = "", archetype: str = "") -> dict:
        """Create a new player in the KG and return session info.

        Returns: {player_id, session_id, location_name, opening_narrative, archetype, stats, skills, inventory}
        """
        client = get_client()

        # 0. Load archetype config (if specified)
        arch_config = get_archetype(archetype) if archetype else {}
        arch_stats = arch_config.get("stats", {})
        arch_skills = arch_config.get("skills", {})
        arch_items = arch_config.get("starting_items", [])

        health = arch_stats.get("health", 100)
        max_health = arch_stats.get("max_health", 100)

        summary_parts = [f"A new soul enters the world. {player_name} stands at the threshold."]
        if archetype:
            summary_parts.append(f"Archetype: {archetype}. {arch_config.get('description', '')}")

        # 1. Create player entity in KG
        player_uuid = client.kg.create_entity(
            player_name,
            ["Player"],
            {
                "summary": " ".join(summary_parts),
                "archetype": archetype,
                "health": str(health),
                "max_health": str(max_health),
                "skills": json.dumps(arch_skills),
            },
        )

        # 2. Create session kEngram
        session_id = f"session-{player_uuid[:8]}"
        try:
            kengram = client.kengrams.create(
                f"{player_name} - session",
                type="session",
            )
            client.kengrams.pin(kengram.id, player_uuid)
        except Exception as e:
            logger.warning("kEngram creation failed", exc_info=True)

        # 3. Find or create starting location
        location_name = self._find_starting_location()

        # 4. Place player at location
        try:
            from memento.tools.kg import _resolve_entity_uuid
            loc_uuid = _resolve_entity_uuid(location_name)
            if loc_uuid:
                client.kg.create_edge(player_uuid, loc_uuid, "LOCATED_IN", "")
        except Exception as e:
            logger.warning("Failed to place player at location", exc_info=True)

        # 5. Register character on-chain (non-fatal)
        try:
            from memento.tools import chain as _chain
            if _chain.is_enabled():
                _chain.register_character(player_uuid, player_name, wallet_address)
        except Exception as e:
            logger.warning("Chain register_character failed", exc_info=True)

        # 6. Create starting items from archetype
        inventory_names = []
        for item_def in arch_items:
            try:
                item_uuid = client.kg.create_entity(
                    item_def["name"],
                    item_def.get("labels", ["Item"]),
                    {"summary": item_def.get("summary", "")},
                )
                client.kg.create_edge(player_uuid, item_uuid, "CARRIES", "")
                inventory_names.append(item_def["name"])
            except Exception:
                logger.warning("Failed to create starting item: %s", item_def.get("name"), exc_info=True)

        # 7. Generate opening narration
        opening = self._generate_opening(player_name, location_name)

        return {
            "player_id": player_uuid,
            "session_id": session_id,
            "location_name": location_name,
            "opening_narrative": opening,
            "archetype": archetype,
            "health": health,
            "max_health": max_health,
            "skills": arch_skills,
            "inventory": inventory_names,
        }

    def _find_starting_location(self) -> str:
        """Find an existing location or return a default.

        Searches KG for locations, preferring ones with room_map data.
        Falls back to The Threshold.
        """
        client = get_client()
        try:
            result = client.kg.search("tavern inn starting location", num_results=5)
            entities = result.get("entities", result.get("nodes", []))
            for entity in entities:
                labels = entity.get("labels", [])
                if "Location" in labels:
                    return entity.get("name", "The Threshold")
            return "The Threshold"
        except Exception:
            return "The Threshold"

    def _generate_opening(self, player_name: str, location_name: str) -> str:
        """Generate opening narration for a new player."""
        try:
            crew = make_narration_crew(
                action="arrive for the first time",
                context=f"Player '{player_name}' is entering '{location_name}' for the first time.",
                events="New player arrival. First moments in the world.",
                mode="intro",
            )
            result = crew.kickoff()
            return result.raw
        except Exception as e:
            logger.warning("Opening narration failed", exc_info=True)
            return f"You stand at {location_name}. The air is heavy with foreboding. Your journey begins."

    def end_session(self, player_id: str) -> dict:
        """End a session — verify kEngram, sync context, commit epoch."""
        client = get_client()
        try:
            client.agents.sync(
                f"Session ended for player {player_id}",
                chat_id=f"rpg:session-{player_id[:8]}",
            )
        except Exception as e:
            logger.warning("Session sync failed", exc_info=True)

        # Commit epoch snapshot at session boundary
        try:
            from memento.epoch import run_epoch
            run_epoch(tick=0)
        except Exception as e:
            logger.warning("Epoch commit on session end failed", exc_info=True)

        return {"status": "ended", "player_id": player_id}

    def handle_death(self, player_id: str, cause: str, location: str) -> dict:
        """Handle permadeath — the session is over forever."""
        client = get_client()
        # Mark player dead (append-only)
        try:
            client.kg.create_edge(player_id, player_id, "HAS_STATUS", f"DEAD. {cause}")
            from memento.tools.kg import _resolve_entity_uuid
            loc_uuid = _resolve_entity_uuid(location)
            if loc_uuid:
                client.kg.create_edge(player_id, loc_uuid, "DIED_AT", f"Fell here. {cause}")
        except Exception as e:
            logger.error("Death marking failed", exc_info=True)

        # Record death on-chain (non-fatal)
        try:
            from memento.tools import chain as _chain
            if _chain.is_enabled():
                _chain.record_death(player_id, cause, location, 0)
        except Exception as e:
            logger.warning("Chain record_death failed", exc_info=True)

        # Deactivate NPC agent if the dead entity is an NPC (non-fatal)
        try:
            from memento.agent_controller import get_agent_controller
            controller = get_agent_controller()
            controller.kill_npc_agent(player_id, cause=cause, location=location)
        except Exception:
            logger.debug("Agent deactivation skipped for %s", player_id)

        # Commit epoch snapshot on permadeath
        try:
            from memento.epoch import run_epoch
            run_epoch(tick=0)
        except Exception:
            logger.warning("Epoch commit on death failed", exc_info=True)

        return {
            "status": "dead",
            "player_id": player_id,
            "cause": cause,
            "location": location,
        }
