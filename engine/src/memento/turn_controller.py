"""TurnController — fast turn orchestration.

Pipeline: NPC wait → narrate → time advance.
World evolution (episode processing, entity generation) is handled by the
heartbeat system, not the turn. Messages accumulate in the Delve stack
naturally and are processed by the heartbeat on a periodic + on-demand basis.
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

logger = get_logger(__name__)

_narration_cooldown = NarrationCooldown()


class TurnController:
    """Fast turn orchestrator — NPC wait, narrate, time advance.

    Designed to run in a worker thread via asyncio.to_thread.
    World evolution is handled separately by the heartbeat system.
    """

    def __init__(
        self,
        location: str,
        location_uuid: str,
        actions: list[dict],
        transport: Transport,
        npc_wait: float = 15.0,
    ) -> None:
        self.location = location
        self.location_uuid = location_uuid
        self.actions = actions
        self.transport = transport
        self.npc_wait = npc_wait

        self.player_name: str = actions[0].get("player_name", "unknown") if actions else "unknown"
        self.combined_action: str = "; ".join(
            f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
        )

        # Mutable state built up during run()
        self.narrative: str = ""
        self.world_time: dict = {}
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
        # 1. NPC wait (event-driven) — NPCs respond to actions in Matrix
        self._await_npcs()

        # 2. Narrate (cooldown-gated)
        if _narration_cooldown.should_narrate(self.location):
            self.transport.emit_phase(self.location, "resolving", "narrating")
            self.narrative = self._narrate()
            _narration_cooldown.record(self.location)
        else:
            logger.info("Narration suppressed at %s (cooldown)", self.location)
            self.narrative = ""

        # 3. Post-turn (time advance + scene art)
        if self.narrative:
            self._post_turn()

        self.transport.emit_phase(self.location, "ready", None)
        return self.narrative, self._build_state_update()

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

    def _narrate(self) -> str:
        """Run narration crew with latest episode as context (no extraction)."""
        self.transport.emit_phase(self.location, "resolving", "narrating")

        # Read latest episode for context — already processed by heartbeat
        context = ""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            episode = client.kg.get_latest_episode()
            if episode:
                raw = episode.get("content") or episode.get("summary") or ""
                context = str(raw) if not isinstance(raw, str) else raw
        except Exception:
            logger.debug("Could not read latest episode for narration context", exc_info=True)

        from memento.crews.narrative.narration import make_narration_crew
        from memento.tools.procgen.text_gen import generate_narration_scaffold
        narr_scaffold = generate_narration_scaffold()
        crew = make_narration_crew(
            action=self.combined_action,
            context=context,
            events="",
            mode="action",
            scaffold=narr_scaffold,
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
                # Get current entity to preserve name/labels
                entity = client.kg.get_entity(self.location_uuid)
                client.kg.update_entity(
                    self.location_uuid,
                    entity.get("name", self.location),
                    entity.get("labels", ["Location"]),
                    entity.get("summary", ""),
                    attributes={"ascii_art": art},
                )
                self.transport.emit_art(self.location, art)
        except Exception:
            logger.warning("Art generation failed for %s", self.location, exc_info=True)

    def _build_state_update(self) -> dict:
        """Build StateUpdate dict."""
        warning_details = None
        if self.subsystem_warnings:
            detail_map = {
                "round_failed": "Turn processing encountered an error",
                "time_unavailable": "World time advance failed",
            }
            warning_details = {w: detail_map.get(w, w) for w in self.subsystem_warnings}

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
