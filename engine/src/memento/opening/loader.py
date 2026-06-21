"""load_seed_room — seeds canon room entities and returns a ready SceneDirector.

Latent (non-canon) facts are deliberately NOT seeded here; they materialise
later on player intent via SceneDirector.find_latent / mark_materialized.
"""

from __future__ import annotations

from memento.opening.director import SceneDirector
from memento.opening.seed_types import SeedRoom
from memento.state.in_memory import InMemoryStateRepository


async def load_seed_room(
    seed: SeedRoom,
    repo: InMemoryStateRepository,
    actor_id: str,
) -> SceneDirector:
    """Seed the room's canon entities into *repo* and return a ready SceneDirector.

    Steps
    -----
    1. Seed the location EntityDoc.
    2. For each SeedFact where ``fact.canon`` is True:
       - character / threat → seed as an EntityDoc at ``location_uuid=seed.location_id``.
       - item → seed as an ItemDoc at ``location_uuid=seed.location_id``.
       - Call ``director.register_canon_uuid(fact.key, fact.uuid)`` so the director
         can later resolve UUID-dependent beats (e.g. the "die" surface beat).
    3. Latent (``canon=False``) facts are NOT seeded.
    4. Return the constructed SceneDirector.

    Note: ``seed_entity`` and ``seed_item`` are SYNC helpers — do not await them.
    """
    # -- 1. Seed the location ----------------------------------------------------
    repo.seed_entity(
        {
            "uuid": seed.location_id,
            "name": seed.name,
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {
                "description": seed.description,
                "exits": list(seed.exits),
            },
            "is_dead": False,
        }
    )

    # -- 2. Build the director (empty uuid registry so far) ----------------------
    director = SceneDirector(seed, repo, actor_id)

    # -- 3. Seed canon facts and register their UUIDs ----------------------------
    for fact in seed.facts:
        if not fact.canon:
            continue  # latent facts are not seeded

        assert fact.uuid is not None, f"Canon fact {fact.key!r} has no uuid"

        if fact.kind in {"character", "threat"}:
            repo.seed_entity(
                {
                    "uuid": fact.uuid,
                    "name": fact.name,
                    "kind": fact.kind,
                    "labels": list(fact.labels),
                    "location_uuid": seed.location_id,
                    "attrs": dict(fact.attrs),
                    "is_dead": False,
                }
            )
        elif fact.kind == "item":
            repo.seed_item(
                {
                    "uuid": fact.uuid,
                    "name": fact.name,
                    "kind": "item",
                    "labels": list(fact.labels),
                    "owner_uuid": None,
                    "location_uuid": seed.location_id,
                    "attrs": dict(fact.attrs),
                }
            )

        director.register_canon_uuid(fact.key, fact.uuid)

    return director
