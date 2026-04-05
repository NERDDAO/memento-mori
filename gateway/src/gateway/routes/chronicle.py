"""Chronicle API — proxies Delve episode endpoints for the client."""

import os

import aiohttp
from fastapi import APIRouter, Query

from gateway.log import get_logger

logger = get_logger(__name__)

router = APIRouter()

DELVE_URL = os.getenv("DELVE_URL", "http://localhost:8000")


@router.get("/episodes")
async def list_episodes(
    agent_id: str = Query(None, description="Filter by narrator agent ID"),
    limit: int = Query(20, ge=1, le=100),
    before: str = Query(None, description="ISO timestamp — return episodes before this time"),
    after: str = Query(None, description="ISO timestamp — return episodes after this time"),
):
    """List episodes, optionally filtered by narrator agent.

    Proxies to Delve's agent episodes search endpoint.
    If no agent_id provided, returns episodes from all narrators.
    """
    if agent_id:
        # Proxy to Delve agent episodes search
        url = f"{DELVE_URL}/knowledge_graph/agents/{agent_id}/episodes/search"
        body = {"limit": limit}
        if before:
            body["before_time"] = before
        if after:
            body["after_time"] = after
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"Delve returned {resp.status}", "episodes": []}
    else:
        # No agent filter — get latest episodes from all narrators
        # Load narrator agent IDs from world.json
        narrator_ids = _get_narrator_ids()
        all_episodes = []
        async with aiohttp.ClientSession() as session:
            for nid in narrator_ids:
                try:
                    url = f"{DELVE_URL}/knowledge_graph/agents/{nid}/episodes/latest"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            episodes = data.get("episodes", [])
                            all_episodes.extend(episodes)
                except Exception:
                    logger.debug("Failed to fetch episodes for agent %s", nid, exc_info=True)
        # Sort by created_at descending, limit
        all_episodes.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return {"episodes": all_episodes[:limit]}


@router.get("/episodes/{episode_uuid}")
async def get_episode(episode_uuid: str):
    """Get a single episode by UUID. Proxies to Delve."""
    url = f"{DELVE_URL}/episodes/by-uuid/{episode_uuid}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"error": f"Episode not found (Delve returned {resp.status})"}


def _get_narrator_ids() -> list[str]:
    """Load narrator agent IDs from world.json."""
    import json
    from pathlib import Path

    world_file = Path(__file__).parent.parent.parent.parent / "world.json"
    try:
        if world_file.exists():
            data = json.loads(world_file.read_text())
            ids = []
            if data.get("threshold_narrator_agent_id"):
                ids.append(data["threshold_narrator_agent_id"])
            if data.get("master_narrator_agent_id"):
                ids.append(data["master_narrator_agent_id"])
            # Generic narrator_agents dict
            for nid in data.get("narrator_agents", {}).values():
                if nid not in ids:
                    ids.append(nid)
            return ids
    except Exception:
        logger.debug("Failed to load narrator IDs", exc_info=True)
    return []
