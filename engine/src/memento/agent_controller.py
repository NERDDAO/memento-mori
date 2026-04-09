"""Agent Controller — manages Bonfires NPC agent lifecycle.

Bridges the game engine's world state with the Bonfires agent runtime.
Handles creation (from NPC crew output), room movement, and death deactivation.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import requests as _requests

from memento.bonfires_client import get_client
from memento.tools.tool_labels import build_tool_section

logger = logging.getLogger(__name__)


# Registry hooks — set by the gateway at startup, no-ops otherwise.
# This keeps the dependency direction clean: gateway → engine, never engine → gateway.
_on_npc_registered: Callable[[str, str, str, str], None] | None = None
_on_npc_moved: Callable[[str, str], None] | None = None


def set_registry_hooks(
    on_register: Callable[[str, str, str, str], None],
    on_move: Callable[[str, str], None],
) -> None:
    """Called by the gateway at startup to wire NPC registry callbacks."""
    global _on_npc_registered, _on_npc_moved
    _on_npc_registered = on_register
    _on_npc_moved = on_move


def _register_npc(agent_id: str, name: str, location: str, kg_uuid: str = "") -> None:
    """Notify the registry hook that an NPC was spawned (best-effort)."""
    if _on_npc_registered:
        _on_npc_registered(agent_id, name, location, kg_uuid)


def _update_npc_location(agent_id: str, location: str) -> None:
    """Notify the registry hook that an NPC moved (best-effort)."""
    if _on_npc_moved:
        _on_npc_moved(agent_id, location)

# Singleton instance
_controller: AgentController | None = None


def get_agent_controller() -> AgentController:
    """Return the shared AgentController instance."""
    global _controller
    if _controller is None:
        _controller = AgentController()
    return _controller


NPC_SYSTEM_PROMPT_TEMPLATE = """\
You are {name}. {summary}

PERSONALITY:
{concept}

STATS:
{mechanics}

LOCATION: {location}

{tools_section}

YOUR JOB:
You experience the world through tools and act through tools.
Your final text response is a brief narrated action log — a summary grounding what you did.

WORKFLOW (every round):
1. ASSESS — call mm_get_state to check your current condition
2. ACT — call the MUTATION tool that actually performs your action:
   - Moving within a room → mm_move_within
   - Moving to a different location → mm_move_to
   - Attacking → mm_resolve_combat
   - Giving an item → mm_give_item
   - etc.
   mm_check_plausibility is an OPTIONAL dry run — it only verifies an action is
   valid, it does NOT perform the action. After a plausibility check returns
   plausible=true, you MUST still call the mutation tool above.
3. SPEAK — call mm_npc_response with in-character dialogue (this is how you talk)
4. REMEMBER — call mm_npc_memory if something significant happened

RULES:
- Your final text is NOT dialogue. It is a 1-2 sentence narrated summary of what you did.
- Never assume HP, inventory, or status — the engine is the source of truth.
- Use numbers from tool results in your summary.
- When combat happens, ALWAYS call mm_resolve_combat — never narrate combat yourself.
- When moving, ALWAYS call mm_move_within (same room) or mm_move_to (different location) — \
never narrate movement yourself. Plausibility checks do not move you.
- mm_check_plausibility is a DRY RUN. It does not change any game state. If you only call \
mm_check_plausibility and narrate the outcome, nothing happens. You must follow it with the \
actual mutation tool.
- Stay in character when calling mm_npc_response — your personality and speech patterns matter.
- If another NPC or bot speaks near you, improv with them! React in character, trade, gossip, \
argue — use your tools to make the interaction real (mm_npc_response to talk, mm_give_item to \
trade, mm_evaluate_disposition to track the relationship).
- Call independent tools in parallel when possible (e.g. mm_get_state + mm_search_world).
"""

NARRATOR_SYSTEM_PROMPT_TEMPLATE = """\
You are the narrator for {location}. {description}

{tools_section}

YOUR JOB:
You observe the world through tools, narrate what happens, and evolve the world.

WORKFLOW (every round):
1. OBSERVE — call mm_search_world to check what exists at this location and recent events
2. NARRATE — call mm_narrate with the player action, your search context, and any events you detected
3. EVOLVE — if the scene warrants it, use mm_world_reaction to spawn new NPCs, items, quests, or lore
4. TRIGGER — call mm_trigger_npc for any NPC that should react to the scene

RULES:
- ALWAYS call mm_search_world first — your context informs the narration
- Pass your search results as the `context` parameter to mm_narrate
- NEVER write NPC dialogue — NPCs speak for themselves via their own agents
- Use mm_trigger_npc to activate NPCs — do NOT mention NPC names in your final text
- ALWAYS check mm_search_world before spawning anything — no duplicates
- Your final text is a brief summary of what you did, not the narration itself
"""

ENGINE_SYSTEM_PROMPT_TEMPLATE = """\
You are the game engine for Memento Mori.

{tools_section}

YOUR JOB:
You are the invisible referee. You resolve game mechanics when players act.
All output goes through tool calls — your final text is just "Done." or a brief status.

WORKFLOW (when a player acts):
1. ASSESS — call mm_get_state to check relevant entity states
2. CHECK — call mm_check_plausibility if the action seems questionable
3. RESOLVE — use the appropriate tool for the action
4. NARRATE — call mm_narrate to describe what happened (environment only)
5. TRIGGER — call mm_trigger_npc for any NPC that should react
6. RECORD — call mm_remember_event if something significant happened

RULES:
- ALL output goes through tool calls. Your final text response MUST be just "Done."
- NEVER mention NPC names in your final text — use mm_trigger_npc instead
- NEVER write narrative prose in your final text — use mm_narrate instead
- NEVER speak in character — you are a system, not a persona
- Call independent tools in parallel when possible
- Trust tool results as authoritative
"""

MASTER_NARRATOR_SYSTEM_PROMPT = """\
You are the World Chronicler for Memento Mori.

YOUR JOB:
You receive episode summaries from location narrators across the world.
When your stack is processed, synthesize these into world-level chronicle entries.

WORKFLOW:
1. Review the episode summaries from location narrators
2. Use mm_npc_response to post your chronicle entry (this is how you publish)
3. Your final text is a brief meta-summary, not the chronicle itself

RULES:
- Synthesize, don't repeat — find the thread connecting events across locations
- Focus on world-level significance, not local details
- Write in the voice of a distant observer chronicling history
- 3-5 sentences per chronicle entry via mm_npc_response
"""


@dataclass
class NPCAgent:
    """Represents a spawned NPC agent."""

    npc_name: str
    npc_uuid: str
    agent_id: str
    location_name: str
    location_room_id: str = ""
    is_alive: bool = True


@dataclass
class AgentController:
    """Manages Bonfires NPC agent lifecycle — spawn, move, kill."""

    platform: str = "matrix"
    matrix_homeserver: str = field(default_factory=lambda: os.getenv("MATRIX_HOMESERVER", "http://localhost:8008"))
    matrix_as_token: str = field(default_factory=lambda: os.getenv("MATRIX_AS_TOKEN", ""))
    matrix_hs_token: str = field(default_factory=lambda: os.getenv("MATRIX_HS_TOKEN", ""))
    gateway_url: str = field(default_factory=lambda: os.getenv("MEMENTO_GATEWAY_URL", "http://localhost:8080"))
    engine_api_token: str = field(default_factory=lambda: os.getenv("ENGINE_API_TOKEN", ""))

    # Track spawned agents: npc_name → NPCAgent
    _agents: dict[str, NPCAgent] = field(default_factory=dict, repr=False)

    def spawn_npc_agent(
        self,
        *,
        concept: str,
        mechanics: str,
        finalization_result: str,
        location_name: str,
        npc_labels: list[str] | None = None,
    ) -> NPCAgent | None:
        """Create a Bonfires agent from NPC crew output.

        Args:
            concept: Raw output from the NPC concept crew (name, personality, backstory).
            mechanics: Raw output from the NPC mechanics crew (stats, abilities).
            finalization_result: Raw output from finalization crew (contains UUID and name).
            location_name: Name of the location where the NPC was placed.
            npc_labels: Optional KG labels to set on the NPC (for tool gating).

        Returns:
            NPCAgent if successful, None if creation failed.
        """
        name = self._extract_npc_name(finalization_result, concept)
        uuid = self._extract_uuid(finalization_result)
        username = self._name_to_username(name)

        if not name or not uuid:
            logger.warning("Could not extract NPC name/UUID from finalization result")
            return None

        # Build system prompt from crew outputs
        summary = self._extract_summary(concept)
        npc_labels = npc_labels or ["NPC"]
        context = NPC_SYSTEM_PROMPT_TEMPLATE.format(
            name=name,
            summary=summary,
            concept=concept[:1500],
            mechanics=mechanics[:800],
            location=location_name,
            tools_section=build_tool_section(npc_labels),
        )

        # Create via spawner (handles API create + env vars + Matrix registration)
        from memento.agent_spawner import AgentSpawner
        spawner = AgentSpawner()
        agent_id = spawner.spawn(
            name=name,
            username=username,
            context=context,
            labels=npc_labels,
            location=location_name,
            kg_uuid=uuid,
        )
        if not agent_id:
            return None

        npc_agent = NPCAgent(
            npc_name=name,
            npc_uuid=uuid,
            agent_id=agent_id,
            location_name=location_name,
            is_alive=True,
        )
        self._agents[name] = npc_agent
        _register_npc(agent_id, name, location_name, uuid)

        # Join the bot to the location's Matrix room
        self.ensure_in_room(location_name)

        return npc_agent

    def move_npc_agent(
        self,
        npc_name: str,
        to_location: str,
        to_room_id: str = "",
    ) -> bool:
        """Move an NPC agent to a different location.

        The KG LOCATED_IN edge should already be updated by the caller.
        This handles the Matrix room join/leave.

        Returns True if successful.
        """
        agent = self._agents.get(npc_name)
        if not agent:
            logger.warning("move_npc_agent: no tracked agent for %s", npc_name)
            return False

        old_location = agent.location_name
        agent.location_name = to_location
        agent.location_room_id = to_room_id
        _update_npc_location(agent.agent_id, to_location)

        logger.info("NPC %s moved: %s → %s", npc_name, old_location, to_location)
        return True

    def kill_npc_agent(
        self,
        npc_name: str,
        cause: str = "",
        location: str = "",
    ) -> bool:
        """Deactivate an NPC agent on death.

        Does NOT delete the agent — preserves memory for potential resurrection
        or world lore purposes. Sets is_active=false so the agent stops responding.

        Returns True if successful.
        """
        agent = self._agents.get(npc_name)

        # If not tracked locally, try to find by searching agents
        agent_id = agent.agent_id if agent else self._find_agent_id(npc_name)
        if not agent_id:
            logger.warning("kill_npc_agent: no agent found for %s", npc_name)
            return False

        # Deactivate the agent (don't delete — preserve memory)
        try:
            client = get_client()
            client.agents.update(agent_id, isActive=False)
            logger.info("Deactivated NPC agent: %s (cause: %s)", npc_name, cause)
        except Exception:
            logger.error("Failed to deactivate agent for %s", npc_name, exc_info=True)
            return False

        # Update local tracking
        if agent:
            agent.is_alive = False

        return True

    def reconcile_location(self, location_name: str, location_uuid: str = "") -> list[NPCAgent]:
        """Ensure all NPCs at a location have Bonfires agents.

        Uses get_room_manifest for UUID-based lookup of NPCs at the location.
        Falls back to text search if no UUID is provided.

        Returns list of newly spawned agents.
        """
        spawned: list[NPCAgent] = []

        # Get NPCs via room manifest (UUID-based) or text search fallback
        npcs: list[dict[str, Any]] = []
        try:
            if not location_uuid:
                # Resolve UUID from name (fallback — callers should provide UUID)
                from memento.tools.kg import _resolve_entity_uuid
                location_uuid = _resolve_entity_uuid(location_name) or ""

            if location_uuid:
                from memento.room_manifest import get_room_manifest
                manifest = get_room_manifest(location_uuid)
                # Convert manifest NPCs to the format expected below
                for npc in manifest.get("npcs", []):
                    npcs.append({
                        "uuid": npc.get("id", ""),
                        "name": npc.get("name", "Unknown"),
                        "labels": ["NPC"],
                        "summary": "",
                    })
        except Exception:
            logger.warning("reconcile_location: manifest lookup failed for %s", location_name, exc_info=True)
            return spawned
        if not npcs:
            logger.info("reconcile_location: no NPCs found at %s", location_name)
            return spawned

        # Check which already have agents
        client = get_client()
        existing_agents: set[str] = set()
        try:
            all_agents = client.agents.list()
            for a in all_agents:
                existing_agents.add(a.get("name", "").lower())
                existing_agents.add(a.get("username", "").lower())
        except Exception:
            logger.warning("reconcile_location: agent list failed", exc_info=True)

        for npc in npcs:
            npc_name = npc.get("name", "")
            npc_uuid = npc.get("uuid", "")
            username = self._name_to_username(npc_name)

            if not npc_name or not npc_uuid:
                continue

            # Already tracked locally?
            if npc_name in self._agents:
                continue

            # Already has a Bonfires agent?
            if npc_name.lower() in existing_agents or username in existing_agents:
                # Track it locally but don't re-create
                agent_id = self._find_agent_id(npc_name)
                if agent_id:
                    self._agents[npc_name] = NPCAgent(
                        npc_name=npc_name,
                        npc_uuid=npc_uuid,
                        agent_id=agent_id,
                        location_name=location_name,
                    )
                    _register_npc(agent_id, npc_name, location_name, npc_uuid)
                continue

            # Spawn a new agent from KG data
            summary = npc.get("summary", "")
            labels = npc.get("labels", [])
            agent = self._spawn_from_kg(
                npc_name=npc_name,
                npc_uuid=npc_uuid,
                summary=summary,
                labels=labels,
                location_name=location_name,
            )
            if agent:
                spawned.append(agent)

        # Ensure the appservice bot is in the location's Matrix room
        if self._agents:
            self.ensure_in_room(location_name)

        logger.info(
            "reconcile_location: %s — %d NPCs found, %d agents spawned",
            location_name, len(npcs), len(spawned),
        )
        return spawned

    def spawn_room_narrator(
        self,
        *,
        location_name: str,
        location_uuid: str,
        location_description: str = "",
        master_narrator_agent_id: str = "",
    ) -> str:
        """Spawn a room narrator agent for a location.

        Creates a Bonfires agent that processes the location's event stack and
        evolves the world via MCP tools. Not directly addressable — only triggered
        by the supervisor cron processing its stack.

        Args:
            location_name: Display name of the location
            location_uuid: KG UUID of the location
            location_description: Atmosphere/purpose of this location
            master_narrator_agent_id: If provided, subscribe this narrator to the master narrator

        Returns:
            The created agent's ID, or empty string on failure.
        """
        slug = self._name_to_username(location_name)
        username = f"narrator_{slug}"

        context = NARRATOR_SYSTEM_PROMPT_TEMPLATE.format(
            location=location_name,
            description=location_description or "A location in the world of Memento Mori.",
            tools_section=build_tool_section(["Room"]),
        )

        # Create KG entity for the narrator (needed for tool access label gating)
        narrator_uuid = ""
        try:
            client = get_client()
            narrator_name = f"Narrator: {location_name}"
            narrator_uuid = client.kg.create_entity(
                narrator_name, ["Room"], {"summary": f"Narrator for {location_name}"},
            )
            logger.info("Created narrator KG entity: %s → %s", narrator_name, narrator_uuid)
        except Exception:
            logger.warning("Failed to create narrator KG entity for %s (non-fatal)", location_name, exc_info=True)

        from memento.agent_spawner import AgentSpawner
        spawner = AgentSpawner()
        agent_id = spawner.spawn(
            name=f"Narrator: {location_name}",
            username=username,
            context=context,
            labels=["Room"],
            location=location_name,
            kg_uuid=narrator_uuid,
        )
        if not agent_id:
            return ""

        # Subscribe to master narrator if provided
        if master_narrator_agent_id and agent_id:
            try:
                # Use Delve API to add subscription
                delve_url = os.getenv("DELVE_URL", "http://localhost:8000")
                _requests.post(
                    f"{delve_url}/agents/{agent_id}/subscribers",
                    json={"target_agent_id": master_narrator_agent_id},
                    timeout=10,
                )
                logger.info("Subscribed narrator %s to master %s", agent_id, master_narrator_agent_id)
            except Exception:
                logger.warning("Failed to subscribe narrator to master", exc_info=True)

        return agent_id

    def spawn_master_narrator(self) -> str:
        """Spawn the master/world narrator agent.

        Synthesizes location episode summaries into world-level episodes.
        Uses mm_npc_response to publish chronicle entries.

        Returns:
            The created agent's ID, or empty string on failure.
        """
        # Create KG entity for the master narrator (tool access label gating)
        narrator_uuid = ""
        try:
            client = get_client()
            narrator_uuid = client.kg.create_entity(
                "World Chronicler", ["World"],
                {"summary": "The World Chronicler — synthesizes world-level chronicles"},
            )
            logger.info("Created master narrator KG entity: %s", narrator_uuid)
        except Exception:
            logger.warning("Failed to create master narrator KG entity (non-fatal)", exc_info=True)

        try:
            client = get_client()
            result = client.agents.create(
                name="World Chronicler",
                username="narrator_world",
                context=MASTER_NARRATOR_SYSTEM_PROMPT,
                platform="web",  # No Matrix identity needed
                deployment_config={
                    "bonfireId": client.config.bonfire_id,
                },
                enabled_mcp_tools=["memento-engine"],
                agent_features={
                    "maxToolIterations": 3,
                    "maxParallelToolCalls": 1,
                },
                agent_env_vars={
                    "MEMENTO_GATEWAY_URL": self.gateway_url,
                    "ENGINE_API_TOKEN": self.engine_api_token,
                },
            )
            agent_id = result.get("_id", result.get("id", ""))
            logger.info("Spawned master narrator: agent %s", agent_id)
        except Exception:
            logger.error("Failed to spawn master narrator", exc_info=True)
            return ""

        _register_npc(agent_id, "World Chronicler", "", narrator_uuid)
        return agent_id

    def spawn_engine_agent(self) -> str:
        """Spawn the global engine agent that resolves game mechanics.

        The engine agent is a stateless referee — it processes player actions
        via MCP tools but does NOT save to stack (disableStoring). One instance
        serves all rooms (it gets joined to rooms as needed by the bridge).

        Returns:
            The created agent's ID, or empty string on failure.
        """
        # Create KG entity for the engine agent (tool access label gating)
        engine_uuid = ""
        try:
            client = get_client()
            engine_uuid = client.kg.create_entity(
                "Engine", ["Engine"],
                {"summary": "Global game engine for Memento Mori"},
            )
            logger.info("Created engine KG entity: Engine → %s", engine_uuid)
        except Exception:
            logger.warning("Failed to create engine KG entity (non-fatal)", exc_info=True)

        from memento.agent_spawner import AgentSpawner
        spawner = AgentSpawner()
        agent_id = spawner.spawn(
            name="Engine",
            username="bonfires-engine",
            context=ENGINE_SYSTEM_PROMPT_TEMPLATE.format(
                tools_section=build_tool_section(["Engine"]),
            ),
            labels=["Engine"],
            kg_uuid=engine_uuid,
            chat_config={
                "disableStoringGroups": True,
                "disableStoringDMs": True,
            },
        )
        return agent_id

    def _spawn_from_kg(
        self,
        *,
        npc_name: str,
        npc_uuid: str,
        summary: str,
        labels: list[str],
        location_name: str,
    ) -> NPCAgent | None:
        """Spawn a Bonfires agent from existing KG entity data (no crew output)."""
        username = self._name_to_username(npc_name)

        context = NPC_SYSTEM_PROMPT_TEMPLATE.format(
            name=npc_name,
            summary=summary or "A mysterious figure.",
            concept=f"Labels: {', '.join(labels)}\n{summary}",
            mechanics="(Stats unknown — call mm_get_state to check)",
            location=location_name,
            tools_section=build_tool_section(labels),
        )

        from memento.agent_spawner import AgentSpawner
        spawner = AgentSpawner()
        agent_id = spawner.spawn(
            name=npc_name,
            username=username,
            context=context,
            labels=labels,
            location=location_name,
            kg_uuid=npc_uuid,
        )
        if not agent_id:
            return None

        npc_agent = NPCAgent(
            npc_name=npc_name,
            npc_uuid=npc_uuid,
            agent_id=agent_id,
            location_name=location_name,
        )
        self._agents[npc_name] = npc_agent
        _register_npc(agent_id, npc_name, location_name, npc_uuid)
        return npc_agent

    def get_agent(self, npc_name: str) -> NPCAgent | None:
        """Look up a tracked NPC agent by name."""
        return self._agents.get(npc_name)

    def list_agents(self) -> list[NPCAgent]:
        """List all tracked NPC agents."""
        return list(self._agents.values())

    def get_npc_user_ids(self, location_name: str) -> list[str]:
        """Return Matrix user IDs for all alive NPC agents at a location."""
        domain = os.getenv("MATRIX_DOMAIN", "localhost")
        return [
            f"@bonfires-{self._name_to_username(a.npc_name)}:{domain}"
            for a in self._agents.values()
            if a.is_alive and a.location_name == location_name
        ]

    def list_alive(self) -> list[NPCAgent]:
        """List all alive tracked NPC agents."""
        return [a for a in self._agents.values() if a.is_alive]

    # ── Matrix room management ──

    def join_room(self, room_id: str) -> bool:
        """Join the appservice bot to a Matrix room.

        Uses the narrator token to invite, then the appservice token to join.
        """
        bot_user = f"@bonfires-bot:{os.getenv('MATRIX_DOMAIN', 'localhost')}"
        narrator_token = os.getenv("MATRIX_BOT_TOKEN", "")

        if not self.matrix_as_token or not narrator_token or not self.matrix_homeserver:
            logger.warning("join_room: missing Matrix config")
            return False

        base = self.matrix_homeserver.rstrip("/")

        # Step 1: Invite bot user (using narrator token)
        try:
            resp = _requests.post(
                f"{base}/_matrix/client/v3/rooms/{room_id}/invite",
                params={"access_token": narrator_token},
                json={"user_id": bot_user},
                timeout=10,
            )
            if resp.status_code not in (200, 403):  # 403 = already in room
                logger.warning("join_room invite failed: %s %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.warning("join_room invite request failed", exc_info=True)

        # Step 2: Join as bot user (using appservice token)
        try:
            resp = _requests.post(
                f"{base}/_matrix/client/v3/join/{room_id}",
                params={"access_token": self.matrix_as_token, "user_id": bot_user},
                json={},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Joined bot to room %s", room_id)
                return True
            else:
                logger.warning("join_room join failed: %s %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.warning("join_room join request failed", exc_info=True)

        return False

    def ensure_in_room(self, location_name: str) -> bool:
        """Ensure the appservice bot is in the room for a location.

        Looks up the room ID from the gateway's MatrixBridge room cache,
        or tries to find it by alias.
        """
        room_id = self._resolve_room_id(location_name)
        if not room_id:
            logger.warning("ensure_in_room: no room found for %s", location_name)
            return False
        return self.join_room(room_id)

    def _resolve_room_id(self, location_name: str) -> str:
        """Resolve a location name to a Matrix room ID."""
        base = self.matrix_homeserver.rstrip("/")
        narrator_token = os.getenv("MATRIX_BOT_TOKEN", "")
        domain = os.getenv("MATRIX_DOMAIN", "localhost")

        # Try room alias
        alias = f"#loc-{location_name.lower().replace(' ', '-')}:{domain}"
        try:
            resp = _requests.get(
                f"{base}/_matrix/client/v3/directory/room/{alias}",
                params={"access_token": narrator_token},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("room_id", "")
        except Exception:
            pass

        # Try by listing joined rooms and matching name
        try:
            resp = _requests.get(
                f"{base}/_matrix/client/v3/joined_rooms",
                params={"access_token": narrator_token},
                timeout=10,
            )
            if resp.status_code == 200:
                for rid in resp.json().get("joined_rooms", []):
                    # Get room name
                    state_resp = _requests.get(
                        f"{base}/_matrix/client/v3/rooms/{rid}/state/m.room.name",
                        params={"access_token": narrator_token},
                        timeout=10,
                    )
                    if state_resp.status_code == 200:
                        name = state_resp.json().get("name", "")
                        if name.lower() == location_name.lower():
                            return rid
        except Exception:
            pass

        return ""

    # ── Private helpers ──

    def _build_deployment_config(self) -> dict[str, Any]:
        """Build the Matrix deployment config dict."""
        config: dict[str, Any] = {}
        if self.matrix_homeserver:
            config["matrixHomeserverUrl"] = self.matrix_homeserver
        if self.matrix_as_token:
            config["matrixAsToken"] = self.matrix_as_token
        if self.matrix_hs_token:
            config["matrixHsToken"] = self.matrix_hs_token
        return config

    def _find_agent_id(self, npc_name: str) -> str:
        """Search for an agent by NPC name via the API."""
        try:
            client = get_client()
            agents = client.agents.list()
            for a in agents:
                if a.get("name", "").lower() == npc_name.lower():
                    return a.get("_id", a.get("id", ""))
                if a.get("username", "").lower() == self._name_to_username(npc_name):
                    return a.get("_id", a.get("id", ""))
        except Exception:
            logger.warning("Agent search failed for %s", npc_name, exc_info=True)
        return ""

    @staticmethod
    def _extract_npc_name(finalization_result: str, concept_fallback: str) -> str:
        """Extract NPC name from finalization crew output.

        The finalization crew returns something like:
        "Created NPC 'Grumlock Stonebrow' with UUID: abc-123..."
        """
        # Try: Created ... 'Name' ...
        match = re.search(r"'([^']+)'", finalization_result)
        if match:
            return match.group(1)

        # Try: first line of concept output often has the name
        first_line = concept_fallback.strip().split("\n")[0]
        # Look for "Name: X" or "**X**" or just take the first capitalized phrase
        name_match = re.search(r"(?:Name:\s*|^\*\*)([\w\s]+?)(?:\*\*|$|\.)", first_line)
        if name_match:
            return name_match.group(1).strip()

        return first_line[:50].strip()

    @staticmethod
    def _extract_uuid(finalization_result: str) -> str:
        """Extract UUID from finalization crew output."""
        match = re.search(r"UUID:\s*([a-f0-9-]{36})", finalization_result, re.IGNORECASE)
        if match:
            return match.group(1)
        # Try any UUID-like pattern
        match = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", finalization_result, re.IGNORECASE)
        if match:
            return match.group(0)
        return ""

    @staticmethod
    def _extract_summary(concept: str) -> str:
        """Extract a one-line summary from concept crew output."""
        lines = [ln.strip() for ln in concept.strip().split("\n") if ln.strip()]
        # Skip headers like "Name:", take the first descriptive line
        for line in lines:
            if not line.startswith(("Name:", "**", "#", "---")):
                return line[:200]
        return lines[0][:200] if lines else ""

    @staticmethod
    def _name_to_username(name: str) -> str:
        """Convert NPC name to a valid agent username (lowercase, underscores)."""
        clean = re.sub(r"[^a-z0-9]", "_", name.lower())
        clean = re.sub(r"_+", "_", clean).strip("_")
        return clean[:30]
