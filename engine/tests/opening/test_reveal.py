from memento.opening.deep_roads import LOC_DEEP_ROADS, deep_roads_seed
from memento.opening.reveal import reveal_or_deepen, seed_room_ecs
from memento.state.in_memory import InMemoryStateRepository


def _seed_thing(repo, uuid, name, salience, *, kind="character", reveal_level=0):
    repo.seed_entity(
        {
            "uuid": uuid,
            "name": name,
            "kind": kind,
            "labels": ["Character"],
            "location_uuid": "loc-1",
            "attrs": {"salience": salience, "reveal_level": reveal_level},
            "is_dead": False,
        }
    )


async def test_reveals_most_salient_first():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    _seed_thing(repo, "c", "mid", 100)
    d = await reveal_or_deepen(repo, "loc-1")
    assert d.kind == "revealed" and d.entity["name"] == "high" and d.depth == 1
    assert (await repo.get_entity("b"))["attrs"]["reveal_level"] == 1


async def test_reveals_in_descending_salience_order():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    _seed_thing(repo, "c", "mid", 100)
    names = [(await reveal_or_deepen(repo, "loc-1")).entity["name"] for _ in range(3)]
    assert names == ["high", "mid", "low"]


async def test_deepens_after_all_revealed():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "low", 50)
    _seed_thing(repo, "b", "high", 1000)
    for _ in range(2):
        await reveal_or_deepen(repo, "loc-1")
    d = await reveal_or_deepen(repo, "loc-1")
    assert d.kind == "deepened" and d.entity["name"] == "high" and d.depth == 2
    assert (await repo.get_entity("b"))["attrs"]["reveal_level"] == 2


async def test_exhausts_at_max_depth():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "only", 100)
    r = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # reveal -> 1
    d = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # deepen -> 2
    x = await reveal_or_deepen(repo, "loc-1", max_depth=2)  # exhausted
    assert r.kind == "revealed" and d.kind == "deepened" and x.kind == "exhausted"
    assert x.entity is None


async def test_ignores_things_without_reveal_component():
    repo = InMemoryStateRepository()
    repo.seed_entity(
        {
            "uuid": "room",
            "name": "the room",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": "loc-1",
            "attrs": {},  # no reveal_level -> not a candidate
            "is_dead": False,
        }
    )
    _seed_thing(repo, "a", "thing", 100)
    # max_depth=1 so a revealed thing isn't deepenable: the 2nd look is only
    # "exhausted" if the location ("room") was correctly excluded as a candidate.
    d = await reveal_or_deepen(repo, "loc-1", max_depth=1)
    assert d.entity["name"] == "thing"
    assert (await reveal_or_deepen(repo, "loc-1", max_depth=1)).kind == "exhausted"


async def test_reveal_level_is_monotonic_and_capped():
    repo = InMemoryStateRepository()
    _seed_thing(repo, "a", "only", 100)
    levels = []
    for _ in range(5):
        await reveal_or_deepen(repo, "loc-1", max_depth=3)
        levels.append((await repo.get_entity("a"))["attrs"]["reveal_level"])
    assert levels == [1, 2, 3, 3, 3]


async def test_seed_room_ecs_marks_facts_latent_with_salience():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    ents = await repo.get_entities_at_location(LOC_DEEP_ROADS)
    items = await repo.get_items_at_location(LOC_DEEP_ROADS)
    by_name = {t["name"]: t for t in (list(ents) + list(items))}
    assert by_name["a dying adventurer"]["attrs"]["reveal_level"] == 0
    assert by_name["a dying adventurer"]["attrs"]["salience"] == 1_000_000
    # the iron blade is an item, seeded as a floor item, still reveal-tracked
    assert by_name["an iron blade"]["kind"] == "item"
    assert by_name["an iron blade"]["attrs"]["reveal_level"] == 0
    assert by_name["an iron blade"]["attrs"]["damage"] == 4  # original attrs preserved


async def test_deep_roads_reveals_in_authored_order_then_deepens():
    repo = InMemoryStateRepository()
    await seed_room_ecs(repo, deep_roads_seed())
    names = [
        (await reveal_or_deepen(repo, LOC_DEEP_ROADS)).entity["name"] for _ in range(3)
    ]
    assert names == ["a dying adventurer", "something in the dark", "an iron blade"]
    d = await reveal_or_deepen(repo, LOC_DEEP_ROADS)  # 4th look -> deepen most salient
    assert d.kind == "deepened" and d.entity["name"] == "a dying adventurer"
