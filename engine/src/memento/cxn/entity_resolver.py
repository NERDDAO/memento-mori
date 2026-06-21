"""EntityResolver — deterministic role-filler → UUID resolution (Task 2, M2).

Resolution is scoped:
  patient   → entities at actor's current room, excluding the actor itself
  instrument→ items in actor's inventory (resolved only when the frame
              supplies an instrument filler; otherwise left unbound for the
              executor to default from equipped main_hand)

No NLP, no LLM, no kernel calls.  Matching is:
  1. Exact match on normalised name  (case-fold, strip leading article)
  2. Unique substring match over entity name + labels

Returns:
  dict[str, str]      — role → UUID for every text-supplied role that resolved
  ResolutionFailure   — on the first failure (unresolved or ambiguous)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import uuid4

from memento.cxn.types import ComprehendedFrame, CxnDef, ResolutionFailure
from memento.state.repository import EntityDoc, StateRepository

if TYPE_CHECKING:
    from memento.opening.director import SceneDirector

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize(s: str) -> str:
    """Lowercase, strip leading article, collapse internal whitespace."""
    s = s.strip().lower()
    s = _ARTICLE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(doc: EntityDoc) -> list[str]:
    """Return the normalised name plus normalised label strings for a doc."""
    parts: list[str] = [_normalize(doc["name"])]
    for lbl in doc["labels"]:
        parts.append(_normalize(lbl))
    return [p for p in parts if p]


def _match_filler(filler: str, candidates: Sequence[EntityDoc]) -> list[str]:
    """Return UUIDs of candidates that match the normalised filler.

    Match order (first wins per candidate):
      1. Exact match on normalised name.
      2. Substring of any normalised token (name or label).
    """
    norm = _normalize(filler)
    matched: list[str] = []
    for doc in candidates:
        toks = _tokens(doc)
        if norm in toks:
            matched.append(doc["uuid"])
        elif any(norm in t for t in toks):
            matched.append(doc["uuid"])
    return matched


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _new_object_id() -> str:
    """Return a 24-hex string suitable as an entity UUID."""
    return uuid4().hex[:24]


_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _strip_article(s: str) -> str:
    """Remove a leading article (the/a/an) from a name string."""
    return _LEADING_ARTICLE_RE.sub("", s).strip()


# ---------------------------------------------------------------------------
# EntityResolver
# ---------------------------------------------------------------------------


class EntityResolver:
    """Resolve ComprehendedFrame role-fillers to entity UUIDs.

    Only the roles present in the frame's ``roles`` list are resolved.
    The caller (TurnRouter) is responsible for binding ``agent`` and
    ``location``, and for defaulting ``instrument`` from equipped main_hand
    when it is absent from the frame.

    Parameters
    ----------
    state:
        The authoritative transactional store (StateRepository Protocol).
    director:
        Optional SceneDirector for the opening sequence.  When supplied,
        a resolve-miss on patient or instrument attempts lazy materialization
        of the matching latent SeedFact before returning a ResolutionFailure.
        When None (default), behaviour is unchanged from the original resolver.
    """

    _state: StateRepository
    _director: SceneDirector | None

    def __init__(
        self,
        state: StateRepository,
        director: SceneDirector | None = None,
    ) -> None:
        self._state = state
        self._director = director

    async def resolve(
        self,
        frame: ComprehendedFrame,
        actor_id: str,
        cxn: CxnDef,  # noqa: ARG002 — kept for API symmetry with TurnRouter
    ) -> dict[str, str] | ResolutionFailure:
        """Resolve each role in the frame; return role→UUID dict or a failure.

        Roles resolved here:
          patient    — entity in actor's room (excluding actor)
          instrument — item in actor's inventory

        ``agent`` and ``location`` are intentionally excluded; the executor
        derives them from the caller_id and the actor's snapshot.
        """
        # Build role→filler map from the frame (skip agent/location)
        role_fillers: dict[str, str] = {}
        for fr in frame["roles"]:
            role = fr["role"]
            if role in ("agent", "location"):
                continue
            role_fillers[role] = fr["filler"]

        if not role_fillers:
            return {}

        # Fetch actor snapshot (location + inventory)
        snapshot = await self._state.get_actor_snapshot(actor_id)
        location_uuid: str | None = snapshot.get("location")

        resolved: dict[str, str] = {}

        # ---- patient -------------------------------------------------------
        if "patient" in role_fillers:
            patient_result = await self._resolve_patient(
                role_fillers["patient"], actor_id, location_uuid
            )
            if isinstance(patient_result, str):
                resolved["patient"] = patient_result
            else:
                return patient_result  # ResolutionFailure

        # ---- instrument ----------------------------------------------------
        if "instrument" in role_fillers:
            inventory: list[str] = snapshot.get("inventory", [])
            instrument_result = await self._resolve_instrument(
                role_fillers["instrument"], inventory, location_uuid
            )
            if isinstance(instrument_result, str):
                resolved["instrument"] = instrument_result
            else:
                return instrument_result  # ResolutionFailure

        return resolved

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_patient(
        self,
        filler: str,
        actor_id: str,
        location_uuid: str | None,
    ) -> str | ResolutionFailure:
        if not location_uuid:
            return ResolutionFailure(reason="unresolved_role:patient")

        entities = await self._state.get_entities_at_location(location_uuid)
        # Exclude the actor themselves
        candidates = [e for e in entities if e["uuid"] != actor_id]

        matches = _match_filler(filler, candidates)

        if len(matches) == 0:
            # Lazy materialization: promote a latent SeedFact if director is wired
            if self._director is not None:
                fact = self._director.find_latent(filler)
                if fact is not None:
                    uuid = fact.uuid or _new_object_id()
                    if fact.kind == "item":
                        item_doc = {
                            "uuid": uuid,
                            "name": _strip_article(fact.name),
                            "kind": fact.kind,
                            "labels": list(fact.labels),
                            "owner_uuid": None,
                            "location_uuid": location_uuid,
                            "attrs": dict(fact.attrs),
                        }
                        await self._state.materialize(item_doc, is_item=True)
                    else:
                        entity_doc = {
                            "uuid": uuid,
                            "name": _strip_article(fact.name),
                            "kind": fact.kind,
                            "labels": list(fact.labels),
                            "location_uuid": location_uuid,
                            "attrs": dict(fact.attrs),
                            "is_dead": False,
                        }
                        await self._state.materialize(entity_doc, is_item=False)
                    self._director.mark_materialized(fact.key, uuid)
                    return uuid
            return ResolutionFailure(reason="unresolved_role:patient")
        if len(matches) > 1:
            return ResolutionFailure(reason="ambiguous_role:patient")
        return matches[0]

    async def _resolve_instrument(
        self,
        filler: str,
        inventory: list[str],
        location_uuid: str | None,
    ) -> str | ResolutionFailure:
        """Match the filler against inventory items by name/labels.

        Uses get_entity(uuid) for each inventory UUID — the Protocol returns
        EntityDoc | None, and ItemDoc shapes share the same fields (name,
        labels, uuid) as EntityDoc, so this lookup works correctly for items
        stored in the _entities dict by InMemoryStateRepository.

        ``location_uuid`` is threaded in so that the promote-on-miss branch
        can place materialised items at the actor's current location.
        """
        item_docs: list[EntityDoc] = []
        for uuid in inventory:
            doc = await self._state.get_entity(uuid)
            if doc is not None:
                item_docs.append(doc)

        matches = _match_filler(filler, item_docs)

        if len(matches) == 0:
            # Lazy materialization: promote a latent SeedFact if director is wired
            if self._director is not None:
                fact = self._director.find_latent(filler)
                if fact is not None:
                    uuid = fact.uuid or _new_object_id()
                    if fact.kind == "item":
                        item_doc = {
                            "uuid": uuid,
                            "name": _strip_article(fact.name),
                            "kind": fact.kind,
                            "labels": list(fact.labels),
                            "owner_uuid": None,
                            "location_uuid": location_uuid,
                            "attrs": dict(fact.attrs),
                        }
                        await self._state.materialize(item_doc, is_item=True)
                    else:
                        entity_doc = {
                            "uuid": uuid,
                            "name": _strip_article(fact.name),
                            "kind": fact.kind,
                            "labels": list(fact.labels),
                            "location_uuid": location_uuid,
                            "attrs": dict(fact.attrs),
                            "is_dead": False,
                        }
                        await self._state.materialize(entity_doc, is_item=False)
                    self._director.mark_materialized(fact.key, uuid)
                    return uuid
            return ResolutionFailure(reason="unresolved_role:instrument")
        if len(matches) > 1:
            return ResolutionFailure(reason="ambiguous_role:instrument")
        return matches[0]
