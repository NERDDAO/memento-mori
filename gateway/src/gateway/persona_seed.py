"""Minimal, flag-gated persona-NPC seed for LOCAL play (in-memory cxn_repo only).
Lets a developer test the persona dialogue loop without standing up the KG stack.
KG-backed deployments seed NPCs through the world bootstrap / KG (P3 provisioning),
so this is a no-op there. Never writes to the production KG.
"""

from __future__ import annotations

from typing import Any

from gateway.log import get_logger

logger = get_logger(__name__)

# Deterministic local-only uuids (clearly non-production).
_LOC_UUID = "local-threshold"
_LOC_NAME = "The Threshold"
_NPC_UUID = "local-gareth"


def _location_doc() -> dict[str, Any]:
    return {
        "uuid": _LOC_UUID,
        "kind": "location",
        "name": _LOC_NAME,
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {"exits": [], "item_ids": []},
        "is_dead": False,
    }


def _npc_doc() -> dict[str, Any]:
    return {
        "uuid": _NPC_UUID,
        "kind": "character",
        "name": "Gareth the Guard",
        "labels": ["Character", "NPC", "Guard"],
        "location_uuid": _LOC_UUID,
        "attrs": {"hp": 10, "max_hp": 10, "inventory": []},
        "is_dead": False,
    }


async def seed_local_personas(repo: Any, cache: Any) -> bool:
    from memento.state.in_memory import InMemoryStateRepository

    if not isinstance(repo, InMemoryStateRepository):
        return False  # KG-backed deployment seeds via the world bootstrap (P3)
    repo.seed_entity(_location_doc())  # InMemoryStateRepository.seed_entity is sync
    repo.seed_entity(_npc_doc())
    if cache is not None:
        cache[_LOC_NAME] = _LOC_UUID  # so LocationResolver resolves it without KG
    logger.info("seeded local persona NPC %s at %s", _NPC_UUID, _LOC_NAME)
    return True
