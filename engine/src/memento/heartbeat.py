"""World Heartbeat — digests accumulated events and generates world content.

Processes the Delve stack (if non-empty), reads the extracted episode,
and runs WorldReactionCrew to create new NPCs, items, locations, quests,
and lore. Runs periodically (background check) and on-demand (MCP tool).

Idempotent — skips if stack is empty or already processing.
"""

from __future__ import annotations

from typing import Any

from memento.log import get_logger
from memento.world_reaction import TurnContext, WorldReactionCrew

logger = get_logger(__name__)


class HeartbeatRunner:
    """Processes accumulated stack events and generates world content."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = agent_id

    def _get_agent_id(self) -> str:
        """Resolve agent ID from config or explicit parameter."""
        if self._agent_id:
            return self._agent_id
        from memento.bonfires_client import get_client
        return get_client().config.agent_id

    def run(self) -> dict[str, Any]:
        """Check stack, process if non-empty, run generation. Returns summary.

        Returns:
            {"skipped": True} if stack is empty
            {"processed": True, "episode_uuid": ..., "reactions": ...} on success
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

            if not task_id:
                logger.warning("Heartbeat: no task_id from process_stack")
                return {"error": "no_task_id"}

            # Poll until complete (120s timeout)
            job_result = client.kg.wait_for_job(task_id, timeout=120.0, poll_interval=3.0)
            job_status = job_result.get("status", "")

            if job_status == "timeout":
                logger.warning("Heartbeat: job timed out after 120s")
                return {"error": "job_timeout", "task_id": task_id}

            if job_status in ("failed", "FAILED"):
                logger.warning("Heartbeat: job failed: %s", job_result)
                return {"error": "job_failed", "task_id": task_id}

        except Exception:
            logger.warning("Heartbeat: stack processing failed", exc_info=True)
            return {"error": "processing_failed"}

        # 3. Read latest episode
        try:
            episode = client.kg.get_latest_episode(agent_id)
            if not episode:
                logger.info("Heartbeat: no episode found after processing")
                return {"processed": True, "episode_uuid": None, "reactions": {}}

            episode_uuid = episode.get("uuid", "")
            episode_content = episode.get("content", "") or episode.get("summary", "") or ""
            logger.info("Heartbeat: episode %s — %s", episode_uuid, episode_content[:100])
        except Exception:
            logger.warning("Heartbeat: could not read episode", exc_info=True)
            return {"processed": True, "episode_uuid": None, "reactions": {}}

        # 4. Run WorldReactionCrew on extracted entities
        # The episode's edges/entities contain the ontology-typed seeds
        entities = episode.get("entities", [])
        if not entities:
            # Try to get entities from edges
            edges = episode.get("edges", [])
            for edge in edges:
                node = edge.get("target", {})
                labels = node.get("labels", [])
                # Check if any label matches our ontology types
                from memento.rpg_types import RPG_ENTITY_TYPES
                for label in labels:
                    if label in RPG_ENTITY_TYPES:
                        entities.append({
                            "type": label,
                            **node.get("attributes", {}),
                        })

        reactions: dict[str, Any] = {}
        if entities:
            ctx = TurnContext(
                location="world",
                location_uuid="",
                player_name="heartbeat",
                combined_action="",
                episode_summary=episode_content,
            )
            crew = WorldReactionCrew()
            reactions = crew.react(entities, ctx)
            logger.info("Heartbeat: created %s", {k: len(v) for k, v in reactions.items()})

        return {
            "processed": True,
            "episode_uuid": episode_uuid,
            "message_count": message_count,
            "entities_found": len(entities),
            "reactions": reactions,
        }
