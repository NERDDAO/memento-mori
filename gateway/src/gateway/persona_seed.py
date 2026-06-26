"""Flag-gated persona-NPC seeds, one per repo backend.

Two parallel, opt-in paths let a developer test the persona dialogue loop:
  - ``seed_local_personas`` — in-memory cxn_repo only (no KG stack needed);
    a no-op on KG-backed repos.
  - ``provision_kg_personas`` — the KG-backed (EventSourced) counterpart;
    seeds the intended game NPC into graph-memory via the projection, and a
    no-op on the in-memory repo.

Each helper writes only when its own backend matches, so neither path ever
seeds the wrong store.
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


async def provision_kg_personas(repo: Any, cache: Any) -> bool:
    """Seed the persona location + NPC into a KG-backed (EventSourced) repo so a
    real deployment has a reachable persona scene. Each seed flows through
    KgProjection.create() -> a KG entity + a LOCATED_IN edge. No-op (returns
    False) on the in-memory repo (that path uses seed_local_personas).

    Order matters: the location is seeded first so its engine->kg uuid is mapped
    before the NPC's LOCATED_IN edge resolves. The name->engine-uuid cache entry
    lets LocationResolver resolve the location without a KG search, keeping the
    cxn path on the engine-uuid identity the EventSourced repo expects.
    """
    from memento.state.event_sourced import EventSourcedStateRepository

    if not isinstance(repo, EventSourcedStateRepository):
        return False  # in-memory play uses seed_local_personas
    await repo.seed_entity(
        _location_doc()
    )  # EventSourcedStateRepository.seed_entity is async
    await repo.seed_entity(_npc_doc())
    if cache is not None:
        cache[_LOC_NAME] = (
            _LOC_UUID  # resolve without a KG search -> engine-uuid identity
        )
    logger.info("provisioned KG persona NPC %s at %s", _NPC_UUID, _LOC_NAME)
    return True


# --- Opening-arc persona (typewriter UI) ------------------------------------
# The Deep Roads opening room (engine/src/memento/opening/deep_roads.py).
_OPENING_LOC_UUID = "507f1f77bcf86cd799439011"
_OPENING_LOC_NAME = "the deep roads"
_OPENING_NPC_UUID = "opening-wanderer"


def _opening_location_doc() -> dict[str, Any]:
    return {
        "uuid": _OPENING_LOC_UUID,
        "kind": "location",
        "name": _OPENING_LOC_NAME,
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": {"exits": [], "item_ids": []},
        "is_dead": False,
    }


def _opening_npc_doc() -> dict[str, Any]:
    return {
        "uuid": _OPENING_NPC_UUID,
        "kind": "character",
        "name": "a dying adventurer",
        "labels": ["Character", "NPC"],
        "location_uuid": _OPENING_LOC_UUID,
        "attrs": {"hp": 3, "max_hp": 10, "inventory": []},
        "is_dead": False,
    }


async def seed_opening_persona(repo: Any, cache: Any) -> bool:
    """Seed a persona NPC at the Deep Roads opening room into the in-memory
    ``app.state.cxn_repo`` so the typewriter opening UI can reach a live
    agent-runtime NPC. Gated by ``PERSONA_OPENING_SEED``. A no-op (returns
    False) on any non-in-memory repo — the opening demo path runs the in-memory
    cxn_repo. Writes only to ``app.state.cxn_repo`` (never the opening's own
    per-player repo, never the production KG). The cache entry lets
    LocationResolver resolve "the deep roads" without a KG search.
    """
    from memento.state.in_memory import InMemoryStateRepository

    if not isinstance(repo, InMemoryStateRepository):
        return False
    repo.seed_entity(
        _opening_location_doc()
    )  # InMemoryStateRepository.seed_entity is sync
    repo.seed_entity(_opening_npc_doc())
    if cache is not None:
        cache[_OPENING_LOC_NAME] = _OPENING_LOC_UUID
    logger.info(
        "seeded opening persona NPC %s at %s", _OPENING_NPC_UUID, _OPENING_LOC_NAME
    )
    return True
