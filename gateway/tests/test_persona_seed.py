import pytest

from memento.state.in_memory import InMemoryStateRepository
from gateway.persona_seed import seed_local_personas, _LOC_UUID, _LOC_NAME, _NPC_UUID


@pytest.mark.asyncio
async def test_seeds_inmemory_repo_and_cache():
    repo = InMemoryStateRepository()
    cache: dict[str, str] = {}
    seeded = await seed_local_personas(repo, cache)
    assert seeded is True
    entities = await repo.get_entities_at_location(_LOC_UUID)
    npc_uuids = {e["uuid"] for e in entities if e.get("kind") == "character"}
    assert _NPC_UUID in npc_uuids  # discoverable by ensure_scene
    assert cache[_LOC_NAME] == _LOC_UUID  # resolvable without KG


class _NotInMemory:
    def seed_entity(self, doc):  # would raise if called
        raise AssertionError("must not seed a KG-backed repo")


@pytest.mark.asyncio
async def test_noop_for_non_inmemory_repo():
    cache: dict[str, str] = {}
    assert await seed_local_personas(_NotInMemory(), cache) is False
    assert cache == {}
