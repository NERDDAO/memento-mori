"""Constructicon: registry + match logic.

match() is O(n) over registered constructions (three in the skeleton):
selects the cxn whose predicate == frame['predicate'] and populates
bound_roles from frame['roles'].

Selection restrictions and named guards are validated later by the executor
(Phase 1), not here.

See spec §4.1, §4.3.
"""
from __future__ import annotations

from memento.cxn.definitions import CONSTRUCTION_REGISTRY
from memento.cxn.types import CxnDef, MatchedCxn, SemanticFrame


class ConstructiconRegistry:
    """Static registry that implements the Constructicon protocol."""

    def match(self, frame: SemanticFrame) -> MatchedCxn | None:
        """Return a MatchedCxn for the first cxn whose predicate matches the frame.

        bound_roles is populated from frame['roles'] (role label → UUID).
        Returns None if no construction matches.
        """
        for cxn in CONSTRUCTION_REGISTRY.values():
            if cxn["predicate"] == frame["predicate"]:
                return MatchedCxn(
                    cxn=cxn,
                    bound_roles=dict(frame["roles"]),
                )
        return None

    def all_cxns(self) -> list[CxnDef]:
        """Return all registered constructions in registry insertion order."""
        return list(CONSTRUCTION_REGISTRY.values())
