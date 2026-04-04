"""RoundController — stoplight orchestrator replacing GameTurnFlow.

Drives crew execution step by step (no @start/@listen decorators).
Emits phase messages to Matrix at each crew boundary.
Waits for NPC responses before narrating so narration can incorporate NPC dialogue.
Gates narration on a 30s cooldown per location to prevent world-event stacking.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from memento.config import load_config
from memento.core import LLM
from memento.crews.context import make_context_crew
from memento.crews.faction.reputation import make_reputation_crew
from memento.crews.narrative.narration import make_narration_crew
from memento.flows.combat import CombatFlow
from memento.flows.episodic_memory import EpisodicMemoryFlow
from memento.flows.event_detection import EventDetectionFlow
from memento.flows.quest import QuestFlow
from memento.log import get_logger
from memento.models.state_update import (
    CombatEvent,
    EventSummary,
    QuestSummary,
    StateUpdate,
    WorldTimeDisplay,
)
from memento.tools.time import advance_time

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Narration cooldown — prevents world -> world -> world stacking
# ---------------------------------------------------------------------------
NARRATION_COOLDOWN = 30.0  # seconds

# Module-level dict: location_name -> last narration timestamp
_last_narration: dict[str, float] = {}


def should_narrate(location: str) -> bool:
    """Return True if enough time has elapsed since the last narration at *location*."""
    last = _last_narration.get(location, 0.0)
    return (time.monotonic() - last) >= NARRATION_COOLDOWN


def _record_narration(location: str) -> None:
    """Record that narration just happened at *location*."""
    _last_narration[location] = time.monotonic()


def query_active_quests(player_uuid: str) -> list[dict]:
    """Query KG for player's active quests via edge traversal (UUID-based)."""
    if not player_uuid:
        return []
    try:
        from memento.bonfires_client import get_client
        client = get_client()

        # Use edge traversal — HAS_QUEST edges from player to quest entities
        edges = client.kg.get_edges(player_uuid, direction="outgoing", edge_type="HAS_QUEST")
        quests = []
        for edge in edges:
            target = edge.get("target", {})
            if "Quest" in target.get("labels", []):
                quests.append({
                    "name": target.get("name", "Unknown Quest"),
                    "description": target.get("summary", ""),
                    "giver": target.get("giver", ""),
                    "current_stage": 0,
                    "total_stages": 3,
                    "completed": False,
                })
        return quests
    except Exception:
        logger.warning("Failed to query active quests", exc_info=True)
        return []


class RoundController:
    """Explicit stoplight controller that replaces GameTurnFlow's auto-chaining.

    Designed to run in a worker thread via ``asyncio.to_thread`` while the
    Matrix client lives on the main asyncio loop.

    Parameters
    ----------
    location : str
        The location name (room display name).
    actions : list[dict]
        List of ``{"player_name": str, "action": str}`` dicts collected by the
        RoundManager batch window.
    loop : asyncio.AbstractEventLoop
        The *running* asyncio loop (used by ``emit_phase`` to schedule async
        calls from the worker thread).
    room_id : str
        Matrix room ID for phase emissions.
    matrix_client : Any
        The ``nio.AsyncClient`` instance (or None during tests).
    npc_wait : float
        Seconds to wait for NPC responses before narrating (default 15).
    """

    def __init__(
        self,
        location: str,
        actions: list[dict],
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        room_id: str = "",
        matrix_client: Any = None,
        npc_wait: float = 15.0,
        location_uuid: str = "",
    ) -> None:
        self.location = location
        self.location_uuid = location_uuid
        self.actions = actions
        self.loop = loop
        self.room_id = room_id
        self.matrix_client = matrix_client
        self.npc_wait = npc_wait

        # Derived convenience fields
        self.player_name: str = actions[0].get("player_name", "unknown") if actions else "unknown"
        self.combined_action: str = "; ".join(
            f"{a.get('player_name', '?')}: {a.get('action', '?')}" for a in actions
        )

        # Mutable state built up during run()
        self.context: str = ""
        self.plausible: bool = True
        self.rejection_reason: str = ""
        self.events: dict = {}
        self.narrative: str = ""
        self.world_time: dict = {}
        self.subsystem_warnings: list[str] = []

    # ------------------------------------------------------------------
    # Phase emission — sends status to Matrix from the worker thread
    # ------------------------------------------------------------------

    def emit_phase(self, phase: str, crew: str | None = None) -> None:
        """Emit a phase marker message to the Matrix room.

        Runs ``room_send`` on the main loop via ``run_coroutine_threadsafe``
        because *this* code executes in a worker thread.

        Parameters
        ----------
        phase : str
            One of "resolving", "npc_response", "ready".
        crew : str | None
            Sub-step label during "resolving" (e.g. "context", "plausibility").
        """
        if not self.matrix_client or not self.room_id or not self.loop:
            logger.debug("emit_phase(%s:%s) skipped — no matrix client/room/loop", phase, crew)
            return

        body = f"[phase] {phase}" + (f":{crew}" if crew else "")

        rpg_meta: dict[str, Any] = {
            "type": "phase",
            "phase": phase,
            "location": self.location,
            "channel": "events",
        }
        if crew:
            rpg_meta["crew"] = crew

        content = {
            "msgtype": "m.text",
            "body": body,
            "com.bonfires.rpg": rpg_meta,
        }

        coro = self.matrix_client.room_send(self.room_id, "m.room.message", content)
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            future.result(timeout=5)
        except Exception:
            logger.debug("emit_phase(%s:%s) send failed", phase, crew, exc_info=True)

    # ------------------------------------------------------------------
    # NPC response window
    # ------------------------------------------------------------------

    def await_npc_responses(self) -> None:
        """Block the worker thread to give NPCs time to respond.

        The NPC responses end up in room history; the narration crew reads
        them via context.  Future improvement: actively poll room messages
        and return early once all expected NPCs have replied.
        """
        self.emit_phase("npc_response")
        time.sleep(self.npc_wait)

    # ------------------------------------------------------------------
    # Individual crew steps
    # ------------------------------------------------------------------

    def gather_context(self) -> str:
        self.emit_phase("resolving", "context")
        crew = make_context_crew(
            self.player_name,
            self.location,
            self.combined_action,
        )
        result = crew.kickoff()
        self.context = result.raw
        return self.context

    def plausibility_check(self) -> bool:
        self.emit_phase("resolving", "plausibility")
        config = load_config()
        llm = LLM(model=config["llm"]["default_model"])
        response = llm.call(
            f"You are a plausibility checker for a dark fantasy RPG.\n\n"
            f"Scene context:\n{self.context[:1500]}\n\n"
            f"Player action: '{self.combined_action}'\n\n"
            f"Is this action physically plausible in this scene? "
            f"Answer ONLY 'yes' or 'no: [brief reason]'."
        )
        raw = response.strip().lower()
        if raw.startswith("no"):
            self.plausible = False
            self.rejection_reason = raw
        return self.plausible

    def detect_events(self) -> dict:
        self.emit_phase("resolving", "events")
        flow = EventDetectionFlow()
        flow.state.action = self.combined_action
        flow.state.context = self.context
        flow.kickoff()
        self.events = flow.state.events
        return self.events

    def resolve_events(self) -> dict:
        """Route to combat, quest, and social sub-flows based on detected categories."""
        categories = self.events.get("categories", [])

        if "combat" in categories:
            self.emit_phase("resolving", "combat")
            combat_flow = CombatFlow()
            combat_flow.state.action = self.combined_action
            combat_flow.state.attacker = self.player_name
            combat_flow.state.target = "unknown"
            combat_flow.state.location = self.location
            combat_flow.state.context = self.context
            combat_flow.kickoff()
            self.events["combat_result"] = combat_flow.state.resolution
            self.events["combat_consequences"] = combat_flow.state.consequences

        if "quest" in categories:
            self.emit_phase("resolving", "quest")
            try:
                quest_flow = QuestFlow()
                quest_flow.state.location = self.location
                quest_flow.state.npc = "unknown"
                quest_flow.state.player_level = 1
                quest_flow.kickoff()
                self.events["quest_result"] = quest_flow.state.quest_concept
                self._persist_quest(quest_flow)
            except Exception:
                logger.warning("Quest flow failed", exc_info=True)
                self.subsystem_warnings.append("quest_unavailable")

        if "social" in categories:
            self.emit_phase("resolving", "social")
            try:
                rep_crew = make_reputation_crew(
                    player=self.player_name,
                    faction="unknown",
                    action=self.combined_action,
                )
                rep_result = rep_crew.kickoff()
                self.events["reputation"] = rep_result.raw
            except Exception:
                logger.warning("Reputation flow failed", exc_info=True)
                self.subsystem_warnings.append("reputation_unavailable")

        return self.events

    def narrate(self, mode: str = "action") -> str:
        self.emit_phase("resolving", "narrating")
        events_str = str(self.events) if mode == "action" else f"Action rejected: {self.rejection_reason}"
        crew = make_narration_crew(
            action=self.combined_action,
            context=self.context,
            events=events_str,
            mode=mode,
        )
        result = crew.kickoff()
        self.narrative = result.raw
        _record_narration(self.location)
        return self.narrative

    def post_turn(self) -> None:
        """Store episodic memories and advance world time."""
        self.emit_phase("resolving", "post_turn")
        try:
            memory_flow = EpisodicMemoryFlow()
            memory_flow.state.narrative = self.narrative
            memory_flow.state.events = str(self.events)
            memory_flow.state.player = self.player_name
            memory_flow.state.session_id = ""
            memory_flow.kickoff()
        except Exception:
            logger.warning("Memory flow failed", exc_info=True)
            self.subsystem_warnings.append("memory_unavailable")

        world_time = advance_time(1)
        self.world_time = world_time.to_display()

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    def run(self) -> tuple[str, dict]:
        """Execute the full round. Returns ``(narrative, state_update_dict)``.

        This method is designed to be called from a worker thread via
        ``asyncio.to_thread``.  Wraps the entire flow in a try/except so a
        hung crew or unexpected error always emits ``ready`` and never leaves
        the client locked.
        """
        try:
            return self._run_inner()
        except Exception:
            logger.error("RoundController.run() failed", exc_info=True)
            self.subsystem_warnings.append("round_failed")
            self.emit_phase("ready")
            return "", self._build_state_update()

    def _run_inner(self) -> tuple[str, dict]:
        """Core round logic — called by run() inside a safety wrapper."""
        # 1. Context
        self.gather_context()

        # 2. Plausibility gate
        if not self.plausibility_check():
            self.narrate(mode="rejection")
            self.emit_phase("ready")
            return self.narrative, self._build_state_update()

        # 3. Event detection & resolution
        self.detect_events()
        self.resolve_events()

        # 4. NPC wait — block so NPC replies land in room history before narration
        self.await_npc_responses()

        # 5. Narration gate — skip if location was narrated too recently
        if should_narrate(self.location):
            self.narrate(mode="action")
        else:
            logger.info(
                "Narration suppressed at %s (cooldown %.0fs)",
                self.location,
                NARRATION_COOLDOWN,
            )
            self.narrative = ""

        # 5b. Fire-and-forget scene art (disabled until KG caching is fixed)
        # if self.narrative:
        #     import threading
        #     threading.Thread(
        #         target=self.request_art,
        #         args=(self.context[:500],),
        #         daemon=True,
        #     ).start()

        # 6. Post-turn bookkeeping (memory, time advance)
        if self.narrative:
            self.post_turn()

        self.emit_phase("ready")
        return self.narrative, self._build_state_update()

    # ------------------------------------------------------------------
    # State update builder
    # ------------------------------------------------------------------

    def _build_state_update(self) -> dict:
        """Build a StateUpdate dict compatible with matrix_listener output."""
        events_summary = None
        if self.events and isinstance(self.events, dict):
            categories = self.events.get("categories", [])
            combat = None
            if "combat" in categories and "combat_result" in self.events:
                combat = CombatEvent(
                    action_type=self.events.get("action_type", "attack"),
                    target_name=self.events.get("combat_target", ""),
                    target_dead="dead" in str(self.events.get("combat_consequences", "")).lower(),
                )
            events_summary = EventSummary(
                categories=categories,
                combat=combat,
            )

        # Query active quests for primary player
        active_quests = None
        raw_quests = query_active_quests(self.player_name)
        if raw_quests:
            active_quests = [QuestSummary(**q) for q in raw_quests]

        state_update = StateUpdate(
            location=self.location,
            world_time=WorldTimeDisplay(**self.world_time) if isinstance(self.world_time, dict) and self.world_time else None,
            events=events_summary,
            active_quests=active_quests,
            subsystem_warnings=self.subsystem_warnings,
        )
        return state_update.model_dump(exclude_none=True)

    # ------------------------------------------------------------------
    # ASCII art generation (fire-and-forget)
    # ------------------------------------------------------------------

    def request_art(self, description: str) -> None:
        """Fire-and-forget: generate scene art if not cached."""
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            # Check KG for cached art — use stored UUID, no text search
            loc_uuid = self.location_uuid
            if loc_uuid:
                entity = client.kg.get_entity(loc_uuid)
                if entity and entity.get("properties", {}).get("ascii_art"):
                    return  # Already cached

            # Generate in background
            from memento.crews.ascii_art.crew import make_scene_art_crew
            crew = make_scene_art_crew(self.location, description, "dark fantasy")
            result = crew.kickoff()
            art_text = result.raw.strip()

            # Cache in KG
            if loc_uuid and art_text:
                client.kg.update_entity(loc_uuid, {"ascii_art": art_text})

            # Post to Matrix
            if art_text and self.matrix_client and self.room_id and self.loop:
                lines = art_text.split('\n')
                content = {
                    "msgtype": "m.text",
                    "body": art_text,
                    "com.bonfires.rpg": {
                        "type": "scene_art",
                        "location": self.location,
                        "lines": lines,
                        "width": max(len(l) for l in lines) if lines else 0,
                        "height": len(lines),
                        "channel": "narrative",
                    },
                }
                coro = self.matrix_client.room_send(self.room_id, "m.room.message", content)
                future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                future.add_done_callback(lambda f: f.exception() and logger.debug("Art post failed", exc_info=f.exception()))
        except Exception:
            logger.warning("Art generation failed for %s", self.location, exc_info=True)

    # ------------------------------------------------------------------
    # Quest persistence (ported from GameTurnFlow)
    # ------------------------------------------------------------------

    def _persist_quest(self, quest_flow: Any) -> None:
        """Persist quest data to KG and link to player."""
        try:
            from memento.bonfires_client import get_client
            client = get_client()

            quest_name = quest_flow.state.quest_concept[:100].split("\n")[0].strip()
            if not quest_name:
                return

            quest_uuid = client.kg.create_entity(
                quest_name,
                ["Quest"],
                {
                    "summary": quest_flow.state.quest_concept[:500],
                    "stages": quest_flow.state.quest_stages[:500],
                    "dialogue": quest_flow.state.quest_dialogue[:500],
                    "location": quest_flow.state.location,
                    "giver": quest_flow.state.npc,
                },
            )

            # Link quest to location — use stored UUID, no text search
            loc_uuid = self.location_uuid
            if loc_uuid:
                client.kg.create_edge(quest_uuid, loc_uuid, "AVAILABLE_AT", "")

            logger.info("Persisted quest: %s (%s)", quest_name, quest_uuid)
        except Exception:
            logger.warning("Failed to persist quest", exc_info=True)
