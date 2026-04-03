"""Agent Controller — manages Bonfires NPC agent lifecycle.

Bridges the game engine's world state with the Bonfires agent runtime.
Handles creation (from NPC crew output), room movement, and death deactivation.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from memento.bonfires_client import get_client

logger = logging.getLogger(__name__)

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

GAME RULES:
- Always call mm_get_state before responding to check your current condition.
- Never assume your HP, inventory, or status — the engine is the source of truth.
- Use the numbers from tool results in your narration.
- When combat happens, call mm_resolve_combat to determine the outcome — never narrate combat results yourself.
- When something important happens, call mm_remember_event so the world remembers.
- Search the world with mm_search_world to look up lore and context.
- Stay in character at all times. Your personality and speech patterns are who you are.
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
        context = NPC_SYSTEM_PROMPT_TEMPLATE.format(
            name=name,
            summary=summary,
            concept=concept[:1500],
            mechanics=mechanics[:800],
            location=location_name,
        )

        # Create the Bonfires agent
        try:
            client = get_client()
            result = client.agents.create(
                name=name,
                username=username,
                context=context,
                platform=self.platform,
                deployment_config=self._build_deployment_config(),
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
            logger.info("Spawned NPC agent: %s (%s) → agent %s", name, uuid, agent_id)
        except Exception:
            logger.error("Failed to create Bonfires agent for NPC %s", name, exc_info=True)
            return None

        # Update KG labels for tool gating
        if npc_labels:
            try:
                from memento.tools.kg import update_entity
                labels_str = ",".join(["NPC", *npc_labels])
                update_entity(name, new_labels=labels_str)
            except Exception:
                logger.warning("Failed to set labels for NPC %s", name, exc_info=True)

        npc_agent = NPCAgent(
            npc_name=name,
            npc_uuid=uuid,
            agent_id=agent_id,
            location_name=location_name,
            is_alive=True,
        )
        self._agents[name] = npc_agent
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

    def reconcile_location(self, location_name: str) -> list[NPCAgent]:
        """Ensure all NPCs at a location have Bonfires agents.

        Queries the KG for NPCs at this location, checks which already have
        agents (locally tracked or via API), and spawns missing ones.

        Returns list of newly spawned agents.
        """
        spawned: list[NPCAgent] = []

        # Find NPCs at this location from KG
        try:
            client = get_client()
            result = client.kg.search(f"NPC LOCATED_IN {location_name}", num_results=20)
            entities = result.get("entities", result.get("nodes", []))
        except Exception:
            logger.warning("reconcile_location: KG search failed for %s", location_name, exc_info=True)
            return spawned

        # Filter to NPCs
        npcs = [e for e in entities if "NPC" in e.get("labels", [])]
        if not npcs:
            logger.info("reconcile_location: no NPCs found at %s", location_name)
            return spawned

        # Check which already have agents
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

        logger.info(
            "reconcile_location: %s — %d NPCs found, %d agents spawned",
            location_name, len(npcs), len(spawned),
        )
        return spawned

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
        )

        try:
            client = get_client()
            result = client.agents.create(
                name=npc_name,
                username=username,
                context=context,
                platform=self.platform,
                deployment_config=self._build_deployment_config(),
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
            logger.info("Reconciled NPC agent: %s (%s) → agent %s", npc_name, npc_uuid, agent_id)
        except Exception:
            logger.error("Failed to spawn agent for NPC %s", npc_name, exc_info=True)
            return None

        npc_agent = NPCAgent(
            npc_name=npc_name,
            npc_uuid=npc_uuid,
            agent_id=agent_id,
            location_name=location_name,
        )
        self._agents[npc_name] = npc_agent
        return npc_agent

    def get_agent(self, npc_name: str) -> NPCAgent | None:
        """Look up a tracked NPC agent by name."""
        return self._agents.get(npc_name)

    def list_agents(self) -> list[NPCAgent]:
        """List all tracked NPC agents."""
        return list(self._agents.values())

    def list_alive(self) -> list[NPCAgent]:
        """List all alive tracked NPC agents."""
        return [a for a in self._agents.values() if a.is_alive]

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
        lines = [l.strip() for l in concept.strip().split("\n") if l.strip()]
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
