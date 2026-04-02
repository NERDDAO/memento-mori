"""Session manager — handles player lifecycle in the game world."""

from __future__ import annotations

from memento.bonfires_client import get_client
from memento.crews.narrative.narration import make_narration_crew


class SessionManager:
    """Manages game sessions — player creation, placement, and cleanup."""

    def create_player(self, player_name: str, wallet_address: str = "") -> dict:
        """Create a new player in the KG and return session info.

        Returns: {player_id, session_id, location_name, opening_narrative}
        """
        client = get_client()

        # 1. Create player entity in KG
        player_uuid = client.kg.create_entity(
            player_name,
            ["Player"],
            {"summary": f"A new soul enters the world. {player_name} stands at the threshold."},
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
            print(f"[session] kEngram creation failed (non-fatal): {e}")

        # 3. Find or create starting location
        location_name = self._find_starting_location()

        # 4. Place player at location
        try:
            from memento.tools.kg import _resolve_entity_uuid
            loc_uuid = _resolve_entity_uuid(location_name)
            if loc_uuid:
                client.kg.create_edge(player_uuid, loc_uuid, "LOCATED_IN", "")
        except Exception as e:
            print(f"[session] Failed to place player (non-fatal): {e}")

        # 5. Register character on-chain (non-fatal)
        try:
            from memento.tools import chain as _chain
            if _chain.is_enabled():
                _chain.register_character(player_uuid, player_name, wallet_address, 1)
        except Exception as e:
            print(f"[session] Chain register_character failed (non-fatal): {e}")

        # 6. Generate opening narration
        opening = self._generate_opening(player_name, location_name)

        return {
            "player_id": player_uuid,
            "session_id": session_id,
            "location_name": location_name,
            "opening_narrative": opening,
        }

    def _find_starting_location(self) -> str:
        """Find an existing location or return a default."""
        client = get_client()
        try:
            result = client.kg.search("tavern inn starting location", num_results=3)
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
            print(f"[session] Opening narration failed: {e}")
            return f"You stand at {location_name}. The air is heavy with foreboding. Your journey begins."

    def end_session(self, player_id: str) -> dict:
        """End a session — verify kEngram, sync context."""
        client = get_client()
        try:
            client.agents.sync(
                f"Session ended for player {player_id}",
                chat_id=f"rpg:session-{player_id[:8]}",
            )
        except Exception as e:
            print(f"[session] Sync failed (non-fatal): {e}")
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
            print(f"[session] Death marking failed: {e}")

        # Record death on-chain (non-fatal)
        try:
            from memento.tools import chain as _chain
            if _chain.is_enabled():
                _chain.record_death(player_id, cause, location, 0, 0)
        except Exception as e:
            print(f"[session] Chain record_death failed (non-fatal): {e}")

        return {
            "status": "dead",
            "player_id": player_id,
            "cause": cause,
            "location": location,
        }
