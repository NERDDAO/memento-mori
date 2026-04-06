"""RoundController — stoplight orchestrator replacing GameTurnFlow.

Drives crew execution step by step (no @start/@listen decorators).
Emits phase messages to Matrix at each crew boundary.
Waits for NPC responses before narrating so narration can incorporate NPC dialogue.
Gates narration on a 30s cooldown per location to prevent world-event stacking.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import nio

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
    InventoryEvent,
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


# ---------------------------------------------------------------------------
# NPC response tracker — shared between gateway bridge and round controller
# ---------------------------------------------------------------------------
_npc_responses: dict[str, set[str]] = {}
_npc_lock = threading.Lock()


def record_npc_responded(location: str, npc_username: str) -> None:
    """Record that an NPC sent a message at a location during the current round."""
    with _npc_lock:
        _npc_responses.setdefault(location, set()).add(npc_username)


def clear_npc_responses(location: str) -> None:
    """Reset response tracking for a new round at this location."""
    with _npc_lock:
        _npc_responses.pop(location, None)


def npc_response_count(location: str) -> int:
    """Return how many unique NPCs have responded at this location."""
    with _npc_lock:
        return len(_npc_responses.get(location, set()))


# ---------------------------------------------------------------------------
# Proximity helpers — room-level position cache and interaction gate
# ---------------------------------------------------------------------------
INTERACTION_RADIUS = 3


def _build_position_cache(room_map: dict) -> dict[str, tuple[int, int]]:
    """Build name→(x,y) lookup from room map. One dict, O(1) per entity."""
    cache: dict[str, tuple[int, int]] = {}
    for npc in room_map.get("npcs", []):
        cache[npc.get("name", "").lower()] = (npc.get("x", 0), npc.get("y", 0))
    for item in room_map.get("items", []):
        cache[item.get("name", "").lower()] = (item.get("x", 0), item.get("y", 0))
    return cache


def check_proximity(
    player_pos: tuple[int, int],
    target_pos: tuple[int, int],
    max_distance: int = INTERACTION_RADIUS,
) -> bool:
    """Check if player is within interaction range (Manhattan distance)."""
    return (
        abs(player_pos[0] - target_pos[0]) + abs(player_pos[1] - target_pos[1])
        <= max_distance
    )


def query_active_quests(player_uuid: str) -> list[dict]:
    """Query KG for player's active quests via edge traversal (UUID-based)."""
    if not player_uuid:
        return []
    try:
        from memento.bonfires_client import get_client

        client = get_client()

        # Use edge traversal — HAS_QUEST edges from player to quest entities
        edges = client.kg.get_edges(
            player_uuid, direction="outgoing", edge_type="HAS_QUEST"
        )
        quests = []
        for edge in edges:
            target = edge.get("target", {})
            if "Quest" in target.get("labels", []):
                quests.append(
                    {
                        "name": target.get("name", "Unknown Quest"),
                        "description": target.get("summary", ""),
                        "giver": target.get("giver", ""),
                        "current_stage": 0,
                        "total_stages": 3,
                        "completed": False,
                    }
                )
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
    matrix_client : nio.AsyncClient | None
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
        matrix_client: nio.AsyncClient | None = None,
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
        self.player_name: str = (
            actions[0].get("player_name", "unknown") if actions else "unknown"
        )
        self.player_id: str = actions[0].get("player_id", "") if actions else ""
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
            logger.debug(
                "emit_phase(%s:%s) skipped — no matrix client/room/loop", phase, crew
            )
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
        """Wait for NPC responses — event-driven with timeout.

        Skips entirely if no NPCs are present. Otherwise polls the shared
        response tracker and exits early once at least one NPC has responded.
        """
        from memento.agent_controller import get_agent_controller

        controller = get_agent_controller()
        npcs_here = controller.get_npc_user_ids(self.location)

        if not npcs_here:
            return  # No NPCs at this location — skip the phase

        self.emit_phase("npc_response")
        clear_npc_responses(self.location)

        # Fixed wait — NPC responses land in Matrix room history during this window.
        # The narration crew reads them via room context.
        # Keep short since NPCs typically respond within 5-10s.
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

        if "inventory" in categories:
            self.emit_phase("resolving", "inventory")
            try:
                self._resolve_inventory()
            except Exception:
                logger.warning("Inventory resolution failed", exc_info=True)
                self.subsystem_warnings.append("inventory_unavailable")

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

    def _resolve_inventory(self) -> None:
        """Execute detected inventory events (pickup/drop) against the KG."""
        from memento.inventory_actions import pickup, get_inventory_manifest
        from memento.room_manifest import get_room_manifest

        if not self.player_id or not self.location_uuid:
            logger.warning("Cannot resolve inventory: missing player_id or location_uuid")
            return

        # Get room items to match names from the LLM event detection
        room = get_room_manifest(self.location_uuid)
        room_items = {i["name"].lower(): i for i in room.get("items", [])}

        action_lower = self.combined_action.lower()

        # Match any room item mentioned in the action text
        picked_up = []
        for item_name, item_data in room_items.items():
            if item_name in action_lower:
                item_id = item_data.get("id", "")
                if not item_id:
                    continue
                try:
                    pickup(self.player_id, item_id, self.location_uuid)
                    picked_up.append(item_data.get("name", item_name))
                    logger.info("Inventory pickup: %s → %s", item_name, self.player_id)
                except Exception as e:
                    logger.warning("Pickup failed for %s: %s", item_name, e)

        if picked_up:
            self.events["inventory_changes"] = [
                {"event_type": "PICKUP", "item_name": name} for name in picked_up
            ]
            # Cache updated manifest for state_update
            self.events["inventory_manifest"] = get_inventory_manifest(self.player_id)

    def narrate(self, mode: str = "action") -> str:
        self.emit_phase("resolving", "narrating")
        events_str = (
            str(self.events)
            if mode == "action"
            else f"Action rejected: {self.rejection_reason}"
        )
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

        # 5b. Fire-and-forget scene art
        if self.narrative:
            import threading

            threading.Thread(
                target=self.request_art,
                args=(self.context[:500],),
                daemon=True,
            ).start()

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
                    target_dead="dead"
                    in str(self.events.get("combat_consequences", "")).lower(),
                )
            events_summary = EventSummary(
                categories=categories,
                combat=combat,
            )

        # Query active quests for primary player
        active_quests = None
        raw_quests = query_active_quests(self.player_id or self.player_name)
        if raw_quests:
            active_quests = [QuestSummary(**q) for q in raw_quests]

        # Include inventory if it was updated this turn
        inventory_items = None
        inv_manifest = self.events.get("inventory_manifest") if self.events else None
        if inv_manifest:
            from memento.models.state_update import InventoryItemUpdate
            inventory_items = []
            for slot in ["weapon", "armor", "accessory", "ring"]:
                eq = inv_manifest.get(slot)
                if eq:
                    inventory_items.append(InventoryItemUpdate(
                        id=eq.get("id", ""), name=eq.get("name", ""),
                        rarity=eq.get("rarity", "common"), slot_type=slot,
                        equipped=True, quantity=1,
                    ))
            for bp_item in inv_manifest.get("backpack", []):
                inventory_items.append(InventoryItemUpdate(
                    id=bp_item.get("id", ""), name=bp_item.get("name", ""),
                    rarity=bp_item.get("rarity", "common"),
                    slot_type=bp_item.get("slot_type", ""),
                    equipped=False, quantity=bp_item.get("quantity", 1),
                ))

        # Include inventory events in EventSummary
        inv_changes = self.events.get("inventory_changes", []) if self.events else []
        if inv_changes and events_summary:
            events_summary.inventory_changes = [
                InventoryEvent(**c) for c in inv_changes
            ]

        state_update = StateUpdate(
            location=self.location,
            world_time=WorldTimeDisplay(**self.world_time)
            if isinstance(self.world_time, dict) and self.world_time
            else None,
            events=events_summary,
            active_quests=active_quests,
            inventory=inventory_items,
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
                lines = art_text.split("\n")
                content = {
                    "msgtype": "m.text",
                    "body": art_text,
                    "com.bonfires.rpg": {
                        "type": "scene_art",
                        "location": self.location,
                        "lines": lines,
                        "width": max(len(ln) for ln in lines) if lines else 0,
                        "height": len(lines),
                        "channel": "narrative",
                    },
                }
                coro = self.matrix_client.room_send(
                    self.room_id, "m.room.message", content
                )
                future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                future.add_done_callback(
                    lambda f: f.exception()
                    and logger.debug("Art post failed", exc_info=f.exception())
                )
        except Exception:
            logger.warning("Art generation failed for %s", self.location, exc_info=True)

    # ------------------------------------------------------------------
    # Quest persistence (ported from GameTurnFlow)
    # ------------------------------------------------------------------

    def _persist_quest(self, quest_flow: QuestFlow) -> None:
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

            # Link quest to player for restoration
            if self.player_id:
                client.kg.create_edge(self.player_id, quest_uuid, "HAS_QUEST", "")

            logger.info("Persisted quest: %s (%s)", quest_name, quest_uuid)
        except Exception:
            logger.warning("Failed to persist quest", exc_info=True)
