"""Closed condition evaluator for if_condition keys in effect templates.

Exactly two named conditions on Day 1. No expression parser, no eval, no LLM.
All predicates are read-only — they never mutate ExecutionContext.

ExecutionContext is a TypedDict; all access uses subscript notation.
See spec §4.4 and types.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from memento.cxn.types import ExecutionContext

CONDITIONS: "dict[str, Callable[[ExecutionContext], bool]]" = {
    # True when the computed HP transient is zero or below (patient is dead).
    "hp_depleted": lambda ctx: ctx["transients"]["computed_hp"] <= 0,
    # True when the patient entity doc carries attrs.onchain == True.
    # Defensive: a missing patient role or absent entity returns False rather
    # than raising KeyError (I-7).
    "patient_onchain": lambda ctx: bool(
        ctx["entities"]
        .get(ctx["bound_roles"].get("patient", ""), {})
        .get("attrs", {})
        .get("onchain")
    ),
}
