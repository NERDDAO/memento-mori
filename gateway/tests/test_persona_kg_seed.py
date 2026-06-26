import pytest

from memento.state.chain_mirror import NoopChainMirror
from memento.state.event_sourced import EventSourcedStateRepository
from memento.state.in_memory import InMemoryStateRepository
from memento.state.kg_projection import KgProjectionFake
from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog

from gateway.persona_seed import provision_kg_personas, _LOC_UUID, _LOC_NAME, _NPC_UUID


def _event_sourced_repo():
    return EventSourcedStateRepository(
        InMemoryTxLog(), InMemoryActivationLog(), KgProjectionFake(), NoopChainMirror()
    )


@pytest.mark.asyncio
async def test_provisions_kg_repo_with_located_npc_and_cache():
    repo = _event_sourced_repo()
    cache: dict[str, str] = {}
    seeded = await provision_kg_personas(repo, cache)
    assert seeded is True
    entities = await repo.get_entities_at_location(_LOC_UUID)
    npc = next((e for e in entities if e.get("kind") == "character"), None)
    assert npc is not None and npc["uuid"] == _NPC_UUID  # LOCATED_IN resolved
    assert "NPC" in npc["labels"]  # satisfies room_manifest too
    assert cache[_LOC_NAME] == _LOC_UUID  # resolvable without a KG search


@pytest.mark.asyncio
async def test_noop_for_in_memory_repo():
    cache: dict[str, str] = {}
    assert await provision_kg_personas(InMemoryStateRepository(), cache) is False
    assert cache == {}
