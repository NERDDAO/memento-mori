"""SceneDirector — opening beat orchestrator for the deterministic immersive-opening engine.

Holds the seed's facts, tracks surfaced/materialized state, picks the next fact
to reveal in salience order, runs on_surface beats (e.g. the witnessed-death beat),
resolves latent facts by name (for lazy materialization), and evaluates the win
predicate (actor left the room).
"""

from __future__ import annotations

import re

from memento.opening.seed_types import SeedFact, SeedRoom
from memento.state.repository import StateRepository

# ---------------------------------------------------------------------------
# Normalisation — same logic as cxn.entity_resolver._normalize
# ---------------------------------------------------------------------------

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize(s: str) -> str:
    """Lowercase, strip leading article, collapse internal whitespace."""
    s = s.strip().lower()
    s = _ARTICLE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# SceneDirector
# ---------------------------------------------------------------------------


class SceneDirector:
    """Orchestrates the opening sequence beats for a single SeedRoom.

    Responsibilities:
    - Tracks which facts have been surfaced (revealed to player) and
      which latent facts have been materialised (written to the world state).
    - Returns the next fact to surface in descending salience order.
    - Runs on_surface hooks (currently only "die" is defined).
    - Resolves a latent fact by normalised name for lazy materialisation.
    - Evaluates the win predicate (actor has moved out of the opening room).
    """

    def __init__(self, seed: SeedRoom, repo: StateRepository, actor_id: str) -> None:
        self._seed = seed
        self._repo = repo
        self._actor_id = actor_id
        self._location_id: str = seed.location_id

        # Index all facts by key for O(1) lookup
        self._facts: dict[str, SeedFact] = {f.key: f for f in seed.facts}

        # Tracking sets
        self._surfaced: set[str] = set()
        self._materialized: set[str] = set()

        # Canon UUID registry: key -> uuid (populated by loader via register_canon_uuid)
        self._uuid_by_key: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def location_id(self) -> str:
        return self._location_id

    @property
    def room_name(self) -> str:
        return self._seed.name

    @property
    def room_description(self) -> str:
        return self._seed.description

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def register_canon_uuid(self, key: str, uuid: str) -> None:
        """Record the seeded UUID for a canon fact.  Called by the loader."""
        self._uuid_by_key[key] = uuid

    # ------------------------------------------------------------------
    # Surfacing
    # ------------------------------------------------------------------

    def next_to_surface(self) -> SeedFact | None:
        """Return the highest-salience fact not yet surfaced, or None."""
        candidates = [f for f in self._facts.values() if f.key not in self._surfaced]
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.salience)

    def mark_surfaced(self, key: str) -> None:
        """Record that a fact has been surfaced (revealed to the player)."""
        self._surfaced.add(key)

    # ------------------------------------------------------------------
    # Surface beats
    # ------------------------------------------------------------------

    async def apply_surface_beats(self, fact: SeedFact) -> None:
        """Run on_surface hooks for a fact.

        Currently defined beats:
          "die" — mark the entity dead and record where it died.
                  Idempotent: no-op if is_dead already True.
        """
        if fact.on_surface == "die":
            uuid = self._uuid_by_key[fact.key]
            doc = await self._repo.get_entity(uuid)
            if doc is not None and doc.get("is_dead"):
                # Already dead — idempotent, do not re-trigger
                return
            await self._repo.set_attr(uuid, "is_dead", True)
            await self._repo.link(uuid, self._location_id, "DIED_IN")

    # ------------------------------------------------------------------
    # Latent / materialisation
    # ------------------------------------------------------------------

    def candidates(self) -> tuple[SeedFact, ...]:
        """Return latent (not canon) facts not yet materialised."""
        return tuple(
            f
            for f in self._facts.values()
            if not f.canon and f.key not in self._materialized
        )

    def find_latent(self, filler: str) -> SeedFact | None:
        """Find a latent, unmaterialised fact whose name matches the normalised filler."""
        norm = _normalize(filler)
        for fact in self._facts.values():
            if fact.canon:
                continue
            if fact.key in self._materialized:
                continue
            if _normalize(fact.name) == norm:
                return fact
        return None

    def mark_materialized(self, key: str, uuid: str) -> None:
        """Record that a latent fact has been materialised into the world."""
        self._materialized.add(key)
        self._uuid_by_key[key] = uuid

    # ------------------------------------------------------------------
    # Win predicate
    # ------------------------------------------------------------------

    async def is_won(self) -> bool:
        """Return True when the actor has left the opening location."""
        snap = await self._repo.get_actor_snapshot(self._actor_id)
        return snap.get("location") != self._location_id
