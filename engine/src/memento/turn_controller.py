"""TurnController — episode-driven turn orchestration.

Pipeline: stack ingest -> NPC wait -> world reactions -> narrate -> post-turn.
Replaces RoundController. Types are set per-bonfire in Delve's Ontology,
not per-turn. Combat/movement/trade are handled inline by NPC tool calls.
"""

from __future__ import annotations

import threading
import time
from memento.log import get_logger
from memento.models.state_update import (
    QuestSummary,
    StateUpdate,
    WorldTimeDisplay,
)
from memento.narration_cooldown import NarrationCooldown
from memento.transport import Transport
from memento.world_reaction import WorldReactionCrew, TurnContext

logger = get_logger(__name__)

_narration_cooldown = NarrationCooldown()


class TurnController:
    """Episode-driven turn orchestrator.

    Designed to run in a worker thread via asyncio.to_thread.
    """

    def __init__(
        self,
        location: str,
        location_uuid: str,
        actions: list[dict],
        transport: Transport,
        world_reaction: WorldReactionCrew,
        npc_wait: float = 15.0,
    ) -> None:
        self.location = location
        self.location_uuid = location_uuid
        self.actions = actions
        self.transport = transport
        self.world_reaction = world_reaction
        self.npc_wait = npc_wait

        self.player_name: str = actions[0].get("player_name", "unknown") if actions else "unknown"
        self.combined_action: str = "; ".join(
            f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
        )

        # Mutable state built up during run()
        self.narrative: str = ""
        self.world_time: dict = {}
        self.reaction_results: dict = {}
        self.subsystem_warnings: list[str] = []

    def run(self) -> tuple[str, dict]:
        """Execute the full turn. Returns (narrative, state_update_dict)."""
        try:
            return self._run_inner()
        except Exception:
            logger.error("TurnController.run() failed", exc_info=True)
            self.subsystem_warnings.append("round_failed")
            self.transport.emit_phase(self.location, "ready", None)
            return "", self._build_state_update()

    def _run_inner(self) -> tuple[str, dict]:
        # 1. Ingest to Delve stack + trigger processing
        #    (bonfire's ontology types applied automatically by Delve)
        self.transport.emit_phase(self.location, "resolving", "episode")
        episode = self._ingest_and_extract()

        # 2. NPC wait (event-driven) — NPCs respond to actions in Matrix
        self._await_npcs()

        # 3. World reactions — create new entities/quests/lore from seeds
        self.transport.emit_phase(self.location, "resolving", "world_reaction")
        ctx = TurnContext(
            location=self.location,
            location_uuid=self.location_uuid,
            player_name=self.player_name,
            combined_action=self.combined_action,
            episode_summary=episode.get("content", ""),
        )
        self.reaction_results = self.world_reaction.react(
            episode.get("entities", []),
            ctx,
        )

        # 4. Narrate (episode summary + world reaction results, cooldown-gated)
        if _narration_cooldown.should_narrate(self.location):
            self.transport.emit_phase(self.location, "resolving", "narrating")
            self.narrative = self._narrate(episode, self.reaction_results)
            _narration_cooldown.record(self.location)
        else:
            logger.info("Narration suppressed at %s (cooldown)", self.location)
            self.narrative = ""

        # 5. Post-turn
        if self.narrative:
            self._post_turn()

        self.transport.emit_phase(self.location, "ready", None)
        return self.narrative, self._build_state_update()

    def _ingest_and_extract(self) -> dict:
        """Push messages to Delve stack, trigger processing, read episode."""
        try:
            from memento.bonfires_client import get_client
            from datetime import datetime, UTC

            client = get_client()

            timestamp = datetime.now(UTC).isoformat()
            for action in self.actions:
                client.stack.add(
                    text=action.get("action", ""),
                    user_id=action.get("player_name", "unknown"),
                    chat_id=self.location,
                    timestamp=timestamp,
                )

            # Trigger immediate processing
            result = client.stack.process_now()
            return result if isinstance(result, dict) else {"content": "", "entities": []}
        except Exception:
            logger.warning("Episode ingestion failed", exc_info=True)
            self.subsystem_warnings.append("episode_unavailable")
            return {"content": "", "entities": []}

    def _await_npcs(self) -> None:
        """Event-driven NPC wait with early exit."""
        expected = self.transport.get_npc_count(self.location)
        if expected == 0:
            return

        self.transport.emit_phase(self.location, "npc_response", None)
        self.transport.clear_npc_responses(self.location)

        deadline = time.monotonic() + self.npc_wait
        poll_interval = 1.0

        while time.monotonic() < deadline:
            responded = self.transport.get_npc_response_count(self.location)
            if responded >= expected:
                logger.info("All %d NPCs responded at %s", expected, self.location)
                break
            time.sleep(poll_interval)

    def _narrate(self, episode: dict, reaction_results: dict) -> str:
        """Run narration crew with episode summary + world reaction results."""
        from memento.crews.narrative.narration import make_narration_crew

        events_str = str(reaction_results) if reaction_results else ""
        context = episode.get("content", "")

        crew = make_narration_crew(
            action=self.combined_action,
            context=context,
            events=events_str,
            mode="action",
        )
        result = crew.kickoff()
        return result.raw

    def _post_turn(self) -> None:
        """Post-turn: time advance + scene art (fire-and-forget)."""
        try:
            from memento.tools.time import advance_time

            world_time = advance_time(1)
            self.world_time = world_time.to_display()
        except Exception:
            logger.warning("Time advance failed", exc_info=True)
            self.subsystem_warnings.append("time_unavailable")

        # Scene art — fire-and-forget, cached by location UUID
        if self.narrative and self.location_uuid:
            threading.Thread(
                target=self._request_art,
                daemon=True,
            ).start()

    def _request_art(self) -> None:
        """Generate and cache scene art (runs in background thread)."""
        try:
            from memento.bonfires_client import get_client

            client = get_client()
            entity = client.kg.get_entity_or_none(self.location_uuid)
            if entity and entity.get("properties", {}).get("ascii_art"):
                return  # Already cached

            from memento.crews.ascii_art.crew import make_scene_art_crew

            crew = make_scene_art_crew(self.location, self.narrative[:500], "dark fantasy")
            result = crew.kickoff()
            art = result.raw.strip()

            if art:
                client.kg.update_entity(self.location_uuid, {"ascii_art": art})
                self.transport.emit_art(self.location, art)
        except Exception:
            logger.warning("Art generation failed for %s", self.location, exc_info=True)

    def _build_state_update(self) -> dict:
        """Build StateUpdate dict."""
        warning_details = None
        if self.subsystem_warnings:
            detail_map = {
                "round_failed": "Turn processing encountered an error",
                "episode_unavailable": "Episode extraction timed out — action processed without structured analysis",
                "time_unavailable": "World time advance failed",
            }
            warning_details = {w: detail_map.get(w, w) for w in self.subsystem_warnings}

        # Query active quests by UUID
        active_quests = None
        try:
            from memento.round_controller import query_active_quests

            raw_quests = query_active_quests(self.player_name)
            if raw_quests:
                active_quests = [QuestSummary(**q) for q in raw_quests]
        except Exception:
            pass

        state_update = StateUpdate(
            location=self.location,
            world_time=WorldTimeDisplay(**self.world_time) if isinstance(self.world_time, dict) and self.world_time else None,
            active_quests=active_quests,
            subsystem_warnings=self.subsystem_warnings,
            warning_details=warning_details,
        )
        return state_update.model_dump(exclude_none=True)
