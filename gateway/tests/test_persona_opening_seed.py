import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

from gateway.persona_seed import (
    seed_opening_persona,
    _OPENING_LOC_UUID,
    _OPENING_LOC_NAME,
    _OPENING_NPC_UUID,
)


@pytest.mark.asyncio
async def test_seeds_opening_npc_at_deep_roads_and_primes_cache():
    repo = InMemoryStateRepository()
    cache: dict[str, str] = {}
    assert await seed_opening_persona(repo, cache) is True
    entities = await repo.get_entities_at_location(_OPENING_LOC_UUID)
    npc = next((e for e in entities if e.get("kind") == "character"), None)
    assert npc is not None and npc["uuid"] == _OPENING_NPC_UUID
    assert "NPC" in npc["labels"]
    assert cache[_OPENING_LOC_NAME] == _OPENING_LOC_UUID
    assert _OPENING_LOC_UUID == "507f1f77bcf86cd799439011"
    assert _OPENING_LOC_NAME == "the deep roads"


@pytest.mark.asyncio
async def test_noop_on_non_in_memory_repo():
    repo = EventSourcedStateRepository(
        InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror()
    )
    cache: dict[str, str] = {}
    assert await seed_opening_persona(repo, cache) is False
    assert cache == {}
