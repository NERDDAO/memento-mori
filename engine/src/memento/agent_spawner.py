"""Agent Spawner — handles the full lifecycle of creating a Bonfires agent.

Encapsulates: API create → encrypted env vars → Matrix user registration → room join → registry hook.

Usage:
    from memento.agent_spawner import AgentSpawner
    spawner = AgentSpawner()
    agent_id = spawner.spawn(
        name="Grumlock",
        username="bonfires-grumlock",
        context="You are Grumlock...",
        labels=["NPC"],
        location="The Threshold",
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests as _requests

from memento.bonfires_client import get_client

logger = logging.getLogger(__name__)


class AgentSpawner:
    """Handles the full agent creation lifecycle."""

    def __init__(self) -> None:
        self.matrix_homeserver = os.getenv("MATRIX_HOMESERVER", "http://localhost:8008")
        self.matrix_as_token = os.getenv("MATRIX_AS_TOKEN", "")
        self.matrix_hs_token = os.getenv("MATRIX_HS_TOKEN", "")
        self.matrix_domain = os.getenv("MATRIX_DOMAIN", "localhost")
        self.gateway_url = os.getenv("MEMENTO_GATEWAY_URL", "http://localhost:8081")
        self.engine_api_token = os.getenv("ENGINE_API_TOKEN", "")

    def spawn(
        self,
        *,
        name: str,
        username: str,
        context: str,
        labels: list[str],
        location: str = "",
        kg_uuid: str = "",
        platform: str = "matrix",
        max_tool_iterations: int = 5,
        max_parallel_tool_calls: int = 3,
        chat_config: dict[str, Any] | None = None,
        extra_env_vars: dict[str, str] | None = None,
    ) -> str:
        """Spawn a fully configured Bonfires agent.

        Steps:
        1. Create agent via Bonfires API (includes Matrix deployment config)
        2. Set encrypted env vars via PUT /agents/{id}/env-vars
        3. Register Matrix user via appservice API
        4. Register in gateway npc_registry via hook

        Args:
            name: Display name (e.g. "Grumlock Stonebrow")
            username: Matrix username (must start with "bonfires-")
            context: System prompt
            labels: KG labels for tool gating (e.g. ["NPC"], ["Engine"], ["Room"])
            location: Location name (empty for global agents like Engine)
            kg_uuid: KG entity UUID (if already created)
            platform: Deployment platform (default "matrix")
            max_tool_iterations: Max tool call iterations
            max_parallel_tool_calls: Max parallel tool calls
            chat_config: Optional chat config overrides (e.g. disableStoring)
            extra_env_vars: Additional env vars beyond the defaults

        Returns:
            Agent ID on success, empty string on failure.
        """
        client = get_client()

        # 1. Create agent via API
        deployment_config: dict[str, Any] = {
            "bonfireId": client.config.bonfire_id,
        }
        if platform == "matrix":
            deployment_config["matrixHomeserverUrl"] = self.matrix_homeserver
            deployment_config["matrixAsToken"] = self.matrix_as_token
            deployment_config["matrixHsToken"] = self.matrix_hs_token

        # Default chat config: NPCs disable group storing (room stack is the narrator's),
        # keep DM storing for personal episodic memory from player conversations.
        if chat_config is None and "NPC" in labels:
            chat_config = {"disableStoringGroups": True, "disableStoringDMs": False}

        try:
            result = client.agents.create(
                name=name,
                username=username,
                context=context,
                platform=platform,
                deployment_config=deployment_config,
                enabled_mcp_tools=["memento-engine"],
                agent_features={
                    "maxToolIterations": max_tool_iterations,
                    "maxParallelToolCalls": max_parallel_tool_calls,
                },
                chat_config=chat_config,
                agent_env_vars={
                    "MEMENTO_GATEWAY_URL": self.gateway_url,
                    "ENGINE_API_TOKEN": self.engine_api_token,
                    **(extra_env_vars or {}),
                },
            )
            agent_id = result.get("_id", result.get("id", ""))
            if not agent_id:
                logger.error("Agent create returned no ID for %s", name)
                return ""
            logger.info("Created agent: %s (%s) → %s", name, username, agent_id)
        except Exception:
            logger.error("Failed to create agent %s", name, exc_info=True)
            return ""

        # 2. Set encrypted env vars via proper API endpoint
        # The agents.create() puts env vars in agentconfigs.agentEnvVars,
        # but bonfires-ai reads from the separate encrypted agentenvvars collection.
        env_vars = {
            "MEMENTO_GATEWAY_URL": self.gateway_url,
            "ENGINE_API_TOKEN": self.engine_api_token,
            **(extra_env_vars or {}),
        }
        try:
            api_url = client.config.api_url
            api_key = client.config.api_key
            bonfire_id = client.config.bonfire_id
            resp = _requests.put(
                f"{api_url}/agents/{agent_id}/env-vars",
                json={"vars": env_vars},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Bonfire-Id": bonfire_id,
                },
                timeout=15,
            )
            if resp.ok:
                logger.info("Set encrypted env vars for %s: %s", name, list(env_vars.keys()))
            else:
                logger.warning("Failed to set env vars for %s (HTTP %d)", name, resp.status_code)
        except Exception:
            logger.warning("Failed to set env vars for %s", name, exc_info=True)

        # 3. Register Matrix user (if matrix platform)
        if platform == "matrix" and self.matrix_as_token:
            try:
                resp = _requests.post(
                    f"{self.matrix_homeserver}/_matrix/client/v3/register",
                    params={"access_token": self.matrix_as_token},
                    json={"type": "m.login.application_service", "username": username},
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info("Registered Matrix user: @%s:%s", username, self.matrix_domain)
                elif resp.status_code == 400 and "already" in resp.text.lower():
                    logger.debug("Matrix user @%s already registered", username)
                else:
                    logger.warning("Matrix register for %s: HTTP %d", username, resp.status_code)
            except Exception:
                logger.warning("Failed to register Matrix user %s", username, exc_info=True)

        # 4. Register in gateway npc_registry via hook
        from memento.agent_controller import _register_npc
        _register_npc(agent_id, name, location, kg_uuid)

        logger.info("Agent fully spawned: %s (%s) at %s", name, username, location or "(global)")
        return agent_id

    def join_room(self, username: str, room_id: str) -> bool:
        """Join an agent to a Matrix room (invite + join).

        Args:
            username: Agent's Matrix username (e.g. "bonfires-engine")
            room_id: Matrix room ID

        Returns:
            True if successful.
        """
        if not self.matrix_as_token:
            logger.warning("Cannot join room — no MATRIX_AS_TOKEN")
            return False

        user_id = f"@{username}:{self.matrix_domain}"
        narrator_token = os.getenv("MATRIX_BOT_TOKEN", self.matrix_as_token)

        try:
            # Invite
            _requests.post(
                f"{self.matrix_homeserver}/_matrix/client/v3/rooms/{room_id}/invite",
                headers={"Authorization": f"Bearer {narrator_token}"},
                json={"user_id": user_id},
                timeout=10,
            )
            # Join
            resp = _requests.post(
                f"{self.matrix_homeserver}/_matrix/client/v3/join/{room_id}",
                params={"access_token": self.matrix_as_token, "user_id": user_id},
                json={},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Joined %s to room %s", user_id, room_id)
                return True
            else:
                logger.warning("Join failed for %s: HTTP %d", user_id, resp.status_code)
                return False
        except Exception:
            logger.warning("Failed to join %s to room", user_id, exc_info=True)
            return False
