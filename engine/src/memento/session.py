"""Session manager — handles player lifecycle in the game world."""

from __future__ import annotations

import json

from memento.bonfires_client import get_client
from memento.config.archetypes import get_archetype
from memento.crews.narrative.narration import make_narration_crew
from memento.log import get_logger

logger = get_logger(__name__)


def _extract_entity_attr(entity: dict, key: str) -> str | dict | None:
    """Extract an attribute from a KG entity.

    KG stores attributes as a JSON blob inside the summary field.
    This checks both direct entity keys and parsed summary JSON.
    """
    # Direct attribute
    val = entity.get(key)
    if val is not None:
        return val
    # Try parsing summary as JSON
    summary = entity.get("summary", "")
    if isinstance(summary, str) and summary.startswith("{"):
        try:
            parsed = json.loads(summary)
            return parsed.get(key)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


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

        # 1b. Link player to user (wallet owner)
        if wallet_address:
            try:
                user_uuid = self.get_or_create_user(wallet_address)
                client.kg.create_edge(user_uuid, player_uuid, "OWNS", "")
            except Exception:
                logger.warning("Failed to link player to user", exc_info=True)

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
        location_name, loc_uuid = self._find_starting_location()

        # 4. Place player at location and get room_map
        room_map = None
        try:
            if not loc_uuid:
                from memento.tools.kg import _resolve_entity_uuid
                loc_uuid = _resolve_entity_uuid(location_name)
            if loc_uuid:
                client.kg.create_edge(player_uuid, loc_uuid, "LOCATED_IN", "")
                # Fetch room_map from location entity
                try:
                    loc_entity = client.kg.get_entity(loc_uuid)
                    rm_raw = _extract_entity_attr(loc_entity, "room_map")
                    if rm_raw:
                        room_map = json.loads(rm_raw) if isinstance(rm_raw, str) else rm_raw
                except Exception:
                    logger.debug("Could not fetch room_map for %s", location_name)
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
            "room_map": room_map,
        }

    def get_or_create_user(self, wallet_address: str) -> str:
        """Find or create a User entity for this wallet. Returns user_uuid."""
        client = get_client()
        try:
            result = client.kg.search(f"User {wallet_address[:10]}", num_results=10)
            for entity in result.get("entities", result.get("nodes", [])):
                if "User" in entity.get("labels", []):
                    wallet = _extract_entity_attr(entity, "wallet") or entity.get("wallet")
                    if wallet == wallet_address:
                        return entity.get("uuid", entity.get("id", ""))
        except Exception:
            logger.debug("User search failed", exc_info=True)

        user_uuid = client.kg.create_entity(
            f"User:{wallet_address[:10]}",
            ["User"],
            {"wallet": wallet_address, "userId": wallet_address, "summary": f"Player account {wallet_address[:10]}..."},
        )
        logger.info("Created User entity %s for wallet %s", user_uuid, wallet_address[:10])
        return user_uuid

    def get_user_characters(self, wallet_address: str) -> list[dict]:
        """Return all Player characters owned by this wallet."""
        client = get_client()
        try:
            result = client.kg.search(f"User {wallet_address[:10]}", num_results=10)
            entities = result.get("entities", result.get("nodes", []))
            user_uuid = None
            for entity in entities:
                if "User" in entity.get("labels", []):
                    wallet = _extract_entity_attr(entity, "wallet") or entity.get("wallet")
                    if wallet == wallet_address:
                        user_uuid = entity.get("uuid", entity.get("id", ""))
                        break
            if not user_uuid:
                return []

            edges = client.kg.get_edges(user_uuid, direction="outgoing", edge_type="OWNS")
            characters = []
            for edge in edges:
                target = edge.get("target", {})
                if "Player" in target.get("labels", []):
                    player_id = target.get("uuid", target.get("id", ""))
                    char_info = {
                        "player_id": player_id,
                        "player_name": target.get("name", "Unknown"),
                        "archetype": str(_extract_entity_attr(target, "archetype") or ""),
                        "health": int(str(_extract_entity_attr(target, "health") or 100)),
                        "is_dead": False,
                        "death_cause": "",
                        "death_location": "",
                    }

                    # Check for death status
                    try:
                        status_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="HAS_STATUS")
                        for se in status_edges:
                            label = se.get("label", "")
                            if "DEAD" in label:
                                char_info["is_dead"] = True
                                char_info["death_cause"] = label.replace("DEAD. ", "")
                                break
                        if char_info["is_dead"]:
                            died_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="DIED_AT")
                            for de in died_edges:
                                death_target = de.get("target", {})
                                char_info["death_location"] = death_target.get("name", "unknown")
                                break
                    except Exception:
                        logger.debug("Death check failed for %s", player_id)

                    characters.append(char_info)
            return characters
        except Exception:
            logger.warning("Failed to query user characters", exc_info=True)
            return []

    def restore_player_state(self, player_id: str) -> dict:
        """Restore full game state for a returning player.

        Returns: {player_id, player_name, location_name, health, max_health, skills, inventory, room_map}
        """
        client = get_client()

        # Get player entity
        try:
            entity = client.kg.get_entity(player_id)
        except Exception:
            logger.warning("Failed to get player entity %s, using Threshold fallback", player_id)
            # Player entity missing from KG — return Threshold with map
            try:
                from memento.seed import seed_threshold, THRESHOLD_MAP
                seed_result = seed_threshold()
                THRESHOLD_MAP["id"] = seed_result.get("uuid", "")
                return {
                    "player_id": player_id,
                    "location_name": "The Threshold",
                    "room_map": dict(THRESHOLD_MAP),
                    "health": 100, "max_health": 100,
                    "skills": {}, "inventory": [],
                }
            except Exception:
                return {"player_id": player_id, "location_name": "The Threshold"}

        player_name = entity.get("name", "Unknown")
        health = int(str(_extract_entity_attr(entity, "health") or 100))
        max_health = int(str(_extract_entity_attr(entity, "max_health") or 100))
        archetype = str(_extract_entity_attr(entity, "archetype") or "")
        skills = {}
        try:
            skills_raw = _extract_entity_attr(entity, "skills") or "{}"
            skills = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
        except (json.JSONDecodeError, TypeError):
            pass

        # Get location
        location_name = "The Threshold"
        room_map = None
        try:
            loc_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="LOCATED_IN")
            for le in loc_edges:
                loc_target = le.get("target", {})
                if "Location" in loc_target.get("labels", []):
                    location_name = loc_target.get("name", "The Threshold")
                    loc_uuid = loc_target.get("uuid", loc_target.get("id", ""))
                    # Try to get room_map from location entity
                    if loc_uuid:
                        try:
                            loc_entity = client.kg.get_entity(loc_uuid)
                            rm_raw = _extract_entity_attr(loc_entity, "room_map")
                            if rm_raw:
                                room_map = json.loads(rm_raw) if isinstance(rm_raw, str) else rm_raw
                        except Exception:
                            pass
                    break
        except Exception:
            logger.debug("Location lookup failed for %s", player_id)

        # Fallback: if no room_map found, use The Threshold's map
        if not room_map:
            try:
                from memento.seed import seed_threshold, THRESHOLD_MAP
                seed_result = seed_threshold()
                threshold_uuid = seed_result.get("uuid", "")
                if threshold_uuid:
                    THRESHOLD_MAP["id"] = threshold_uuid
                    room_map = dict(THRESHOLD_MAP)
                    location_name = "The Threshold"
            except Exception:
                logger.debug("Threshold map fallback failed")

        # Get inventory
        inventory = []
        try:
            carry_edges = client.kg.get_edges(player_id, direction="outgoing", edge_type="CARRIES")
            for ce in carry_edges:
                item = ce.get("target", {})
                inventory.append(item.get("name", "Unknown Item"))
        except Exception:
            logger.debug("Inventory lookup failed for %s", player_id)

        return {
            "player_id": player_id,
            "player_name": player_name,
            "location_name": location_name,
            "health": health,
            "max_health": max_health,
            "archetype": archetype,
            "skills": skills,
            "inventory": inventory,
            "room_map": room_map,
        }

    def _find_starting_location(self) -> tuple[str, str | None]:
        """Ensure The Threshold exists and return its name and UUID.

        Uses seed_threshold() which is idempotent — creates if missing,
        returns existing UUID if found. No KG text search needed.
        """
        try:
            from memento.seed import seed_threshold
            seed_result = seed_threshold()
            uuid = seed_result.get("uuid", "")
            if uuid:
                logger.info("Starting location: The Threshold (%s)", uuid)
                return "The Threshold", uuid
        except Exception:
            logger.warning("seed_threshold failed", exc_info=True)

        return "The Threshold", None

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
