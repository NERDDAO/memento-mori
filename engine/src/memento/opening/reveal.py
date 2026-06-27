"""Accretive room reveal-state — the "look adds detail" ECS state machine.

A room's lookable things carry a ``reveal_level`` component in ``attrs``
(0 = latent / unseen, 1 = surfaced, 2+ = deepened) plus a ``salience`` for
ordering.  ``reveal_or_deepen`` advances that state one step per call: it
REVEALS the next most-salient unseen thing, and once the room is fully
surfaced it DEEPENS already-seen things (shallowest first).  Re-looking
accretes; it never resets.

The state lives as components on the entity docs in the StateRepository, so
this is the first real ECS effect (the future ``mm_look``'s effect).  Only the
async StateRepository protocol is used (``get_*_at_location`` + ``set_attr``),
so it is backend-agnostic (in-memory or EventSourced/KG) and headless-testable.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from typing import Any

from memento.opening.seed_types import SeedRoom

DEFAULT_MAX_DEPTH: int = 3


@dataclass(frozen=True)
class RevealDelta:
    """What one look changed.

    kind   : "revealed" | "deepened" | "exhausted"
    entity : {uuid, name, kind, labels} view of the changed thing (None if exhausted)
    depth  : the new reveal_level (0 when exhausted)
    """

    kind: str
    entity: dict[str, Any] | None
    depth: int


def _view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": doc["uuid"],
        "name": doc["name"],
        "kind": doc["kind"],
        "labels": list(doc.get("labels", [])),
    }


async def _lookable_things(repo: Any, location_uuid: str) -> list[dict[str, Any]]:
    """Reveal-tracked things at the location — characters/threats AND items.

    ``get_entities_at_location`` excludes ``kind=="item"``, so items are
    gathered separately and unioned.  A thing is reveal-tracked iff it carries
    a ``reveal_level`` component.
    """
    entities = await repo.get_entities_at_location(location_uuid)
    items = await repo.get_items_at_location(location_uuid)
    things = list(entities) + list(items)
    return [t for t in things if "reveal_level" in t.get("attrs", {})]


async def reveal_or_deepen(
    repo: Any, location_uuid: str, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> RevealDelta:
    """Advance the room's reveal-state by one look.

    REVEAL the next most-salient unseen thing; else DEEPEN the shallowest
    revealed thing (ties -> higher salience -> uuid); else "exhausted".
    ``reveal_level`` is mutated monotonically (only increases, capped at
    ``max_depth``).
    """
    things = await _lookable_things(repo, location_uuid)

    latent = [t for t in things if t["attrs"].get("reveal_level", 0) == 0]
    if latent:
        nxt = max(latent, key=lambda e: (e["attrs"].get("salience", 0), e["uuid"]))
        await repo.set_attr(nxt["uuid"], "reveal_level", 1)
        return RevealDelta(kind="revealed", entity=_view(nxt), depth=1)

    deepenable = [
        t for t in things if 0 < t["attrs"].get("reveal_level", 0) < max_depth
    ]
    if deepenable:
        nxt = min(
            deepenable,
            key=lambda e: (
                e["attrs"]["reveal_level"],
                -e["attrs"].get("salience", 0),
                e["uuid"],
            ),
        )
        new_depth = nxt["attrs"]["reveal_level"] + 1
        await repo.set_attr(nxt["uuid"], "reveal_level", new_depth)
        return RevealDelta(kind="deepened", entity=_view(nxt), depth=new_depth)

    return RevealDelta(kind="exhausted", entity=None, depth=0)


def _stable_uuid(location_id: str, key: str) -> str:
    """Deterministic 24-hex (ObjectId-shaped) id for a uuid-less seed fact."""
    return hashlib.sha1(f"{location_id}:{key}".encode()).hexdigest()[:24]


async def seed_room_ecs(repo: Any, room: SeedRoom) -> None:
    """Seed a SeedRoom's facts as ECS entities carrying reveal components
    (``reveal_level=0``, ``salience``).  Item-kind facts become floor items;
    others become entities.  ``seed_entity``/``seed_item`` may be sync
    (in-memory) or async (EventSourced) — both are handled.
    """
    for fact in room.facts:
        uuid = fact.uuid or _stable_uuid(room.location_id, fact.key)
        attrs = {**dict(fact.attrs), "salience": fact.salience, "reveal_level": 0}
        if fact.kind == "item":
            res = repo.seed_item(
                {
                    "uuid": uuid,
                    "name": fact.name,
                    "kind": "item",
                    "labels": list(fact.labels),
                    "owner_uuid": None,
                    "location_uuid": room.location_id,
                    "attrs": attrs,
                }
            )
        else:
            res = repo.seed_entity(
                {
                    "uuid": uuid,
                    "name": fact.name,
                    "kind": fact.kind,
                    "labels": list(fact.labels),
                    "location_uuid": room.location_id,
                    "attrs": attrs,
                    "is_dead": False,
                }
            )
        if inspect.isawaitable(res):
            await res
