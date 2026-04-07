"""World Heartbeat — processes accumulated events and triggers Room NPC.

Processes the Room NPC's stack (if non-empty), then triggers the Room NPC
agent via /graph/invoke so it can narrate, enrich lore stubs, and evolve
the world using its MCP tools.

Idempotent — skips if stack is empty or already processing.
"""

from __future__ import annotations

import os
from typing import Any

import requests as _requests

from memento.log import get_logger

logger = get_logger(__name__)


class HeartbeatRunner:
    """Processes Room NPC stack and triggers the agent to narrate/evolve."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = agent_id

    def _get_agent_id(self) -> str:
        """Resolve agent ID from config or explicit parameter."""
        if self._agent_id:
            return self._agent_id
        from memento.bonfires_client import get_client
        return get_client().config.agent_id

    def run(self) -> dict[str, Any]:
        """Check stack, process if non-empty, trigger Room NPC. Returns summary.

        Returns:
            {"skipped": True} if stack is empty
            {"processed": True, "episode_uuid": ..., "triggered": True} on success
            {"error": str} on failure
        """
        try:
            return self._run_inner()
        except Exception:
            logger.error("Heartbeat failed", exc_info=True)
            return {"error": "heartbeat_failed"}

    def _run_inner(self) -> dict[str, Any]:
        from memento.bonfires_client import get_client
        client = get_client()
        agent_id = self._get_agent_id()

        # 1. Check stack — skip if empty
        try:
            status = client.kg.get_stack_status(agent_id)
            message_count = status.get("message_count", 0)
            if message_count == 0:
                logger.debug("Heartbeat: stack empty, skipping")
                return {"skipped": True, "reason": "stack_empty"}
        except Exception:
            logger.warning("Heartbeat: could not check stack status", exc_info=True)
            return {"skipped": True, "reason": "status_check_failed"}

        logger.info("Heartbeat: %d messages in stack, processing", message_count)

        # 2. Trigger stack processing and wait for completion
        try:
            process_result = client.kg.process_stack(agent_id)
            task_id = process_result.get("task_id")

            if process_result.get("already_processing"):
                logger.info("Heartbeat: stack already processing, skipping")
                return {"skipped": True, "reason": "already_processing"}

            if task_id:
                job_result = client.kg.wait_for_job(task_id, timeout=120.0, poll_interval=3.0)
                job_status = job_result.get("status", "")

                if job_status == "timeout":
                    logger.warning("Heartbeat: job timed out after 120s")
                    return {"error": "job_timeout", "task_id": task_id}

                if job_status in ("failed", "FAILED"):
                    logger.warning("Heartbeat: job failed: %s", job_result)
                    return {"error": "job_failed", "task_id": task_id}
            else:
                logger.info("Heartbeat: processing completed inline (no task queue)")

        except Exception:
            logger.warning("Heartbeat: stack processing failed", exc_info=True)
            return {"error": "processing_failed"}

        # 3. Read latest episode for the trigger message
        episode_uuid = ""
        episode_content = ""
        try:
            episode = client.kg.get_latest_episode(agent_id)
            if episode:
                episode_uuid = episode.get("uuid", "")
                episode_content = episode.get("content", "") or episode.get("summary", "") or ""
                logger.info("Heartbeat: episode %s — %s", episode_uuid, episode_content[:100])
        except Exception:
            logger.warning("Heartbeat: could not read episode", exc_info=True)

        # 4. Trigger Room NPC via /graph/invoke
        # The Room NPC has the episode in its memory from stack processing.
        # We send a trigger message so it wakes up and runs its workflow:
        # mm_search_world → mm_narrate → mm_world_reaction
        triggered = self._trigger_room_npc(agent_id, episode_content)

        return {
            "processed": True,
            "episode_uuid": episode_uuid,
            "message_count": message_count,
            "triggered": triggered,
        }

    def _trigger_room_npc(self, agent_id: str, episode_summary: str) -> bool:
        """Tag the Room NPC narrator in the Matrix room via the engine agent.

        Sends a Matrix message as the global engine agent (@bonfires-engine)
        mentioning the narrator (@bonfires-narrator_{slug}). The bonfires-ai
        runtime sees the tag and wakes up the narrator to run its workflow.
        """
        import re
        import uuid as _uuid

        homeserver = os.getenv("MATRIX_HOMESERVER", "http://localhost:8008")
        as_token = os.getenv("MATRIX_AS_TOKEN", "")
        domain = os.getenv("MATRIX_DOMAIN", "localhost")

        if not as_token:
            logger.warning("Heartbeat: no MATRIX_AS_TOKEN, cannot trigger narrator")
            return False

        # Resolve location and usernames from the agent_id
        # The agent_id maps to a narrator agent — look up its location
        try:
            from memento.bonfires_client import get_client
            client = get_client()
            agent_info = client.agents.get(agent_id)
            agent_name = agent_info.get("name", "")
            # "Narrator: The Threshold" → "The Threshold"
            location_name = agent_name.replace("Narrator: ", "") if agent_name.startswith("Narrator:") else ""
        except Exception:
            logger.warning("Heartbeat: could not resolve agent info for %s", agent_id)
            return False

        if not location_name:
            logger.warning("Heartbeat: could not determine location for agent %s", agent_id)
            return False

        slug = re.sub(r"[^a-z0-9]", "_", location_name.lower())
        slug = re.sub(r"_+", "_", slug).strip("_")[:30]

        engine_user = f"@bonfires-engine:{domain}"
        narrator_tag = f"@bonfires-narrator_{slug}"

        # Find the Matrix room for this location
        gateway_url = os.getenv("MEMENTO_GATEWAY_URL", "http://localhost:8080")
        try:
            resp = _requests.get(f"{gateway_url}/api/room-id/{location_name}", timeout=10)
            if resp.status_code != 200:
                logger.warning("Heartbeat: room lookup failed for %s", location_name)
                return False
            room_id = resp.json().get("room_id", "")
        except Exception:
            logger.warning("Heartbeat: room lookup failed for %s", location_name, exc_info=True)
            return False

        if not room_id:
            logger.warning("Heartbeat: no room_id for %s", location_name)
            return False

        # Send message as engine agent, tagging the narrator
        trigger_text = (
            f"{narrator_tag} New episode processed. Narrate and evolve the world.\n\n"
            f"Episode summary:\n{episode_summary[:2000]}"
        ) if episode_summary else f"{narrator_tag} Heartbeat — process your stack and narrate."

        txn_id = str(_uuid.uuid4())
        try:
            resp = _requests.put(
                f"{homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                params={"access_token": as_token, "user_id": engine_user},
                json={
                    "msgtype": "m.text",
                    "body": trigger_text,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Heartbeat: engine tagged narrator at %s", location_name)
                return True
            else:
                logger.warning("Heartbeat: Matrix send failed (HTTP %d): %s", resp.status_code, resp.text[:200])
                return False
        except Exception:
            logger.warning("Heartbeat: failed to send trigger to Matrix", exc_info=True)
            return False
