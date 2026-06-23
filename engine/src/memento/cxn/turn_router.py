"""TurnRouter — comprehend → clarify-or-execute orchestrator (Task 3, M2).

Pipeline per utterance:
  1. ComprehensionClient.comprehend(utterance, actor_id)
     - frame.matched==False          → clarify("no_match")
  2. Find CxnDef by predicate in CONSTRUCTION_REGISTRY
     - no cxn                        → clarify("unknown_predicate")
  3. EntityResolver.resolve(frame, actor_id, cxn)
     - ResolutionFailure              → clarify(failure.reason)
  4. Build SemanticFrame{predicate, roles=resolved, confidence=1.0, raw_text}
  5. constructicon.match(frame)       → MatchedCxn
  6. executor.execute(cxn, caller_id=actor_id, bindings=bound_roles)
     - ConstructionError              → propagate (caller handles rejection)
     → TurnOutcome(status="executed", update=result)

Clarify outcomes never write to the store; the executor is never called.

See spec §8 for the full state machine.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from uuid import uuid4

from memento.cxn.constructicon import ConstructiconRegistry
from memento.cxn.entity_resolver import EntityResolver
from memento.cxn.executor import EffectExecutor
from memento.cxn.types import (
    SemanticFrame,
    TurnOutcome,
)
from memento.state.tx_log import ActivationRecord

if TYPE_CHECKING:
    from memento.cxn.kernel_client import ComprehensionClient
    from memento.opening.describe import DescribeClient
    from memento.opening.director import SceneDirector
    from memento.state.repository import StateRepository
    from memento.state.tx_log import ActivationLog

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize_filler(s: str) -> str:
    """Lowercase, strip leading article, collapse whitespace."""
    s = s.strip().lower()
    s = _ARTICLE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


logger = logging.getLogger(__name__)


class TurnRouter:
    """Route a free-text utterance through comprehension → resolution → execution.

    Args:
        comprehension:   ComprehensionClient (real HTTP or FakeComprehensionClient).
        constructicon:   ConstructiconRegistry for predicate → CxnDef lookup and matching.
        resolver:        EntityResolver for role-filler → UUID resolution.
        executor:        EffectExecutor for the 3-phase deterministic execution.
        bonfire_id:      Fixed world identifier ("mm-world-v1" for Day-1).
        director:        SceneDirector for the active opening scene (optional).
        describe_client: DescribeClient for the read-only narration branch (optional).
    """

    _comprehension: "ComprehensionClient"
    _constructicon: ConstructiconRegistry
    _resolver: EntityResolver
    _executor: EffectExecutor
    _bonfire_id: str
    _director: "SceneDirector | None"
    _describe: "DescribeClient | None"
    _repo: "StateRepository | None"
    _activation_log: "ActivationLog | None"

    def __init__(
        self,
        comprehension: "ComprehensionClient",
        constructicon: ConstructiconRegistry,
        resolver: EntityResolver,
        executor: EffectExecutor,
        bonfire_id: str,
        director: "SceneDirector | None" = None,
        describe_client: "DescribeClient | None" = None,
        repo: "StateRepository | None" = None,
        activation_log: "ActivationLog | None" = None,
    ) -> None:
        self._comprehension = comprehension
        self._constructicon = constructicon
        self._resolver = resolver
        self._executor = executor
        self._bonfire_id = bonfire_id
        self._director = director
        self._describe = describe_client
        self._repo = repo
        self._activation_log = activation_log

    async def _resolve_exit(self, actor_id: str, filler: str) -> str | None:
        """Resolve a direction filler to a target_uuid via the actor's room exits.

        Returns the target_uuid string if the filler matches an exit direction,
        or None if repo is not set or no matching exit is found.
        """
        if self._repo is None:
            return None
        snap = await self._repo.get_actor_snapshot(actor_id)
        loc = snap.get("location")
        if loc is None:
            return None
        room = await self._repo.get_entity(loc)
        exits = (room["attrs"].get("exits") or []) if room else []
        norm = _normalize_filler(filler)
        for exit_rec in exits:
            if _normalize_filler(exit_rec.get("direction", "")) == norm:
                return exit_rec.get("target_uuid")
            # also match on exit name/target field if present
            if _normalize_filler(exit_rec.get("name", "")) == norm:
                return exit_rec.get("target_uuid")
        return None

    async def handle(self, utterance: str, actor_id: str) -> TurnOutcome:
        """Comprehend utterance and route to execute or clarify.

        Returns:
            TurnOutcome with status=="executed" (update filled, message/reason None)
            or status=="clarify" (update None, message = player-facing string, reason = machine tag).

        Raises:
            ConstructionError: if execution fails a guard or transactional phase
                               (the store is left untouched; the caller decides how
                               to surface this — see gateway mm_act handler).
            ComprehendError:   if the kernel returns a non-200 response.
        """
        # ── Per-turn identifiers ─────────────────────────────────────────────
        activation_id = uuid4().hex
        message_id = uuid4().hex

        # ── Step 1: comprehend ───────────────────────────────────────────────
        frame = await self._comprehension.comprehend(utterance, actor_id)

        if not frame["matched"]:
            return TurnOutcome(
                status="clarify",
                update=None,
                message="I didn't understand that. Try something like 'attack the goblin'.",
                reason="no_match",
            )

        # ── Step 2: find cxn by predicate ────────────────────────────────────
        predicate = frame["predicate"]
        cxn = next(
            (c for c in self._constructicon.all_cxns() if c["predicate"] == predicate),
            None,
        )
        if cxn is None:
            return TurnOutcome(
                status="clarify",
                update=None,
                message=f"I understood '{predicate}' but that action isn't available here.",
                reason="unknown_predicate",
            )

        # ── Step 2b: read-only branch (LOOK) ─────────────────────────────────
        if cxn.get("read_only"):
            if self._director is None or self._describe is None:
                return TurnOutcome(
                    status="clarify",
                    update=None,
                    message="There is nothing to perceive.",
                    reason="no_scene",
                )
            from memento.opening.describe import DescribeRequest

            # Set activation context so any state writes (die beat) are stamped.
            if self._repo is not None and hasattr(self._repo, "set_activation"):
                self._repo.set_activation(activation_id, cxn["mcp_tool_name"])
            try:
                # Write activation record before any state writes.
                if self._activation_log is not None:
                    self._activation_log.append(
                        ActivationRecord(
                            activation_id=activation_id,
                            message_id=message_id,
                            actor_id=actor_id,
                            cxn_id=cxn["name"],
                            tool=cxn["mcp_tool_name"],
                            roles=[],
                        )
                    )

                director = self._director
                fact = director.next_to_surface()
                if fact is not None:
                    director.mark_surfaced(fact.key)
                    await director.apply_surface_beats(fact)
                req = DescribeRequest(
                    room_name=director.room_name,
                    room_description=director.room_description,
                    focus=fact,
                    surfaced=(),
                    candidates=director.candidates(),
                )
                result = await self._describe.describe(req)
                return TurnOutcome(
                    status="narrated",
                    update=None,
                    message=None,
                    reason=None,
                    narration=result.prose,
                )
            finally:
                if self._repo is not None and hasattr(self._repo, "set_activation"):
                    self._repo.set_activation("", "")

        # ── Step 3: resolve role fillers → UUIDs ─────────────────────────────
        # EntityResolver.resolve returns dict[str, str] (clean roles) OR
        # ResolutionFailure (a TypedDict with a single "reason" key).
        # Both are plain dicts at runtime; we discriminate on the "reason" key.
        resolution = await self._resolver.resolve(frame, actor_id, cxn)

        if "reason" in resolution:
            # ResolutionFailure path — reason is the machine tag verbatim.
            reason_str: str = resolution["reason"]  # type: ignore[typeddict-item]
            return TurnOutcome(
                status="clarify",
                update=None,
                message=_clarify_message_for(reason_str),
                reason=reason_str,
            )

        # Clean resolution: dict[str, str] role → UUID (no "reason" key).
        resolved: dict[str, str] = resolution  # type: ignore[assignment]

        # ── Step 3b: MOVE exit-resolution ────────────────────────────────────
        # EntityResolver skips the location role for MOVE (it's a direction, not
        # an entity name).  If we have a repo, resolve the filler against the
        # actor's room exits and inject the target UUID.
        if cxn["predicate"] == "move":
            filler = next(
                (r["filler"] for r in frame["roles"] if r["role"] == "location"),
                None,
            )
            if filler is not None:
                target = await self._resolve_exit(actor_id, filler)
                if target is not None:
                    resolved["location"] = target

        # ── Step 4: build SemanticFrame ───────────────────────────────────────
        semantic_frame = SemanticFrame(
            predicate=predicate,
            roles=resolved,
            confidence=1.0,
            raw_text=utterance,
        )

        # ── Step 5: constructicon.match ───────────────────────────────────────
        matched = self._constructicon.match(semantic_frame)
        if matched is None:
            # Should not happen given step 2 found the cxn, but be safe.
            return TurnOutcome(
                status="clarify",
                update=None,
                message=f"The action '{predicate}' couldn't be matched to a construction.",
                reason="unknown_predicate",
            )

        # ── Step 6: execute ───────────────────────────────────────────────────
        # Set activation context so all repo writes in this turn are stamped.
        if self._repo is not None and hasattr(self._repo, "set_activation"):
            self._repo.set_activation(activation_id, matched["cxn"]["mcp_tool_name"])
        try:
            # Write activation record before any state writes.
            if self._activation_log is not None:
                self._activation_log.append(
                    ActivationRecord(
                        activation_id=activation_id,
                        message_id=message_id,
                        actor_id=actor_id,
                        cxn_id=matched["cxn"]["name"],
                        tool=matched["cxn"]["mcp_tool_name"],
                        roles=list(matched["bound_roles"].keys()),
                    )
                )

            # ConstructionError propagates — the gateway handler catches it.
            update = await self._executor.execute(
                matched["cxn"],
                caller_id=actor_id,
                bindings=matched["bound_roles"],
            )
        finally:
            if self._repo is not None and hasattr(self._repo, "set_activation"):
                self._repo.set_activation("", "")

        outcome = TurnOutcome(
            status="executed",
            update=update,
            message=None,
            reason=None,
        )

        # ── Step 7: win check ─────────────────────────────────────────────────
        # Only MOVE changes location; checking on every verb is redundant.
        if (
            cxn["predicate"] == "move"
            and self._director is not None
            and await self._director.is_won()
        ):
            outcome["won"] = True
            outcome["narration"] = "The road goes on, into the dark."

        return outcome


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clarify_message_for(reason: str) -> str:
    """Return a player-facing clarification string for a ResolutionFailure reason."""
    if reason.startswith("unresolved_role:"):
        role = reason.split(":", 1)[1]
        return f"I couldn't find '{role}' here. Please be more specific."
    if reason.startswith("ambiguous_role:"):
        role = reason.split(":", 1)[1]
        return f"There are multiple targets for '{role}'. Please be more specific."
    return "I couldn't understand the target of that action."
