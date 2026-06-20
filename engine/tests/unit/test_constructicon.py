"""Unit tests for C3 — arithmetic, conditions, definitions, constructicon.

All tests are deterministic, no I/O, no LLM, no RNG.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# arithmetic.py
# ---------------------------------------------------------------------------


class TestArithmetic:
    def test_damage_normal(self):
        from memento.cxn.arithmetic import damage

        # Kael str=3, Iron Sword dmg=8, Goblin armor=2 → 9
        assert damage(8, 3, 2) == 9

    def test_damage_floor_zero(self):
        from memento.cxn.arithmetic import damage

        # weapon=1, strength=0, armor=50 → max(0, -49) = 0
        assert damage(1, 0, 50) == 0

    def test_damage_zero_armor(self):
        from memento.cxn.arithmetic import damage

        assert damage(5, 4, 0) == 9

    def test_clamp_hp_survives(self):
        from memento.cxn.arithmetic import clamp_hp

        assert clamp_hp(10, 3) == 7

    def test_clamp_hp_exact_zero(self):
        from memento.cxn.arithmetic import clamp_hp

        # Goblin hp=9, dmg=9 → 0
        assert clamp_hp(9, 9) == 0

    def test_clamp_hp_overdamage(self):
        from memento.cxn.arithmetic import clamp_hp

        # Never goes negative
        assert clamp_hp(5, 100) == 0

    def test_damage_returns_int(self):
        from memento.cxn.arithmetic import damage

        result = damage(8, 3, 2)
        assert isinstance(result, int)

    def test_clamp_hp_returns_int(self):
        from memento.cxn.arithmetic import clamp_hp

        result = clamp_hp(9, 9)
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# definitions.py — registry validity
# ---------------------------------------------------------------------------


class TestDefinitions:
    def test_registry_has_three_entries(self):
        from memento.cxn.definitions import CONSTRUCTION_REGISTRY

        assert len(CONSTRUCTION_REGISTRY) == 3

    def test_registry_keys(self):
        from memento.cxn.definitions import CONSTRUCTION_REGISTRY

        assert set(CONSTRUCTION_REGISTRY.keys()) == {"MOVE", "ATTACK", "TAKE"}

    def test_move_cxn_shape(self):
        from memento.cxn.definitions import MOVE_CXN

        assert MOVE_CXN["name"] == "MOVE"
        assert MOVE_CXN["predicate"] == "move"
        assert MOVE_CXN["mcp_tool_name"] == "mm_move"
        assert MOVE_CXN["chain_mirror"] is False
        assert MOVE_CXN["semantic_roles"] == ["agent", "location"]
        assert MOVE_CXN["guards"] == ["exit_exists"]

    def test_attack_cxn_shape(self):
        from memento.cxn.definitions import ATTACK_CXN

        assert ATTACK_CXN["name"] == "ATTACK"
        assert ATTACK_CXN["predicate"] == "attack"
        assert ATTACK_CXN["mcp_tool_name"] == "mm_attack"
        assert ATTACK_CXN["chain_mirror"] is True
        assert ATTACK_CXN["semantic_roles"] == ["agent", "patient", "instrument", "location"]
        assert ATTACK_CXN["guards"] == ["agent_armed", "target_damageable", "same_room"]

    def test_take_cxn_shape(self):
        from memento.cxn.definitions import TAKE_CXN

        assert TAKE_CXN["name"] == "TAKE"
        assert TAKE_CXN["predicate"] == "take"
        assert TAKE_CXN["mcp_tool_name"] == "mm_take"
        assert TAKE_CXN["chain_mirror"] is True
        assert TAKE_CXN["semantic_roles"] == ["agent", "patient", "location"]
        assert TAKE_CXN["guards"] == ["item_carryable", "same_room", "capacity_ok"]

    def test_move_restrictions(self):
        from memento.cxn.definitions import MOVE_CXN

        roles = {r["role"]: r for r in MOVE_CXN["restrictions"]}
        assert roles["agent"]["required_labels"] == ["Character"]
        assert roles["agent"]["forbidden_labels"] == ["Dead"]
        assert roles["location"]["required_labels"] == ["Location"]
        assert roles["location"]["forbidden_labels"] == []

    def test_attack_restrictions(self):
        from memento.cxn.definitions import ATTACK_CXN

        roles = {r["role"]: r for r in ATTACK_CXN["restrictions"]}
        assert roles["agent"]["required_labels"] == ["Character"]
        assert roles["agent"]["forbidden_labels"] == ["Dead"]
        assert roles["patient"]["required_labels"] == ["Character"]
        assert roles["patient"]["forbidden_labels"] == ["Dead"]
        assert roles["instrument"]["required_labels"] == ["Weapon"]
        assert roles["instrument"]["forbidden_labels"] == []

    def test_take_restrictions(self):
        from memento.cxn.definitions import TAKE_CXN

        roles = {r["role"]: r for r in TAKE_CXN["restrictions"]}
        assert roles["agent"]["required_labels"] == ["Character"]
        assert roles["agent"]["forbidden_labels"] == ["Dead"]
        assert roles["patient"]["required_labels"] == ["Item"]
        assert roles["patient"]["forbidden_labels"] == []
        assert roles["location"]["required_labels"] == ["Location"]
        assert roles["location"]["forbidden_labels"] == []

    def test_if_conditions_are_valid(self):
        """Every if_condition across all three CxnDefs must be None or a key in CONDITIONS."""
        from memento.cxn.conditions import CONDITIONS
        from memento.cxn.definitions import CONSTRUCTION_REGISTRY

        for cxn in CONSTRUCTION_REGISTRY.values():
            for prim in cxn["effect_template"]:
                cond = prim["if_condition"]
                assert cond is None or cond in CONDITIONS, (
                    f"CxnDef '{cxn['name']}' has primitive with unknown "
                    f"if_condition={cond!r}; valid keys: {list(CONDITIONS)}"
                )

    def test_attack_effect_template_length(self):
        from memento.cxn.definitions import ATTACK_CXN

        # spec §3.4 shows 5 steps for ATTACK
        assert len(ATTACK_CXN["effect_template"]) == 5

    def test_move_effect_template_length(self):
        from memento.cxn.definitions import MOVE_CXN

        # spec §3.4 shows 2 steps for MOVE
        assert len(MOVE_CXN["effect_template"]) == 2

    def test_take_effect_template_length(self):
        from memento.cxn.definitions import TAKE_CXN

        # spec §3.4 shows 3 steps for TAKE
        assert len(TAKE_CXN["effect_template"]) == 3


# ---------------------------------------------------------------------------
# conditions.py
# ---------------------------------------------------------------------------


def _make_ctx(
    bound_roles: dict[str, str],
    entities: dict[str, dict],
    transients: dict,
    world_tick: int = 0,
) -> "dict":
    """Build a minimal ExecutionContext dict (TypedDict uses subscript access)."""
    return {
        "bound_roles": bound_roles,
        "entities": entities,
        "transients": transients,
        "world_tick": world_tick,
    }


class TestConditions:
    def test_both_keys_present(self):
        from memento.cxn.conditions import CONDITIONS

        assert "hp_depleted" in CONDITIONS
        assert "patient_onchain" in CONDITIONS
        assert len(CONDITIONS) == 2, "Exactly two conditions on Day 1"

    def test_hp_depleted_true(self):
        from memento.cxn.conditions import CONDITIONS

        ctx = _make_ctx({}, {}, {"computed_hp": 0})
        assert CONDITIONS["hp_depleted"](ctx) is True

    def test_hp_depleted_negative(self):
        from memento.cxn.conditions import CONDITIONS

        # Overshoot — still depleted
        ctx = _make_ctx({}, {}, {"computed_hp": -5})
        assert CONDITIONS["hp_depleted"](ctx) is True

    def test_hp_depleted_false(self):
        from memento.cxn.conditions import CONDITIONS

        ctx = _make_ctx({}, {}, {"computed_hp": 1})
        assert CONDITIONS["hp_depleted"](ctx) is False

    def test_patient_onchain_true(self):
        from memento.cxn.conditions import CONDITIONS

        patient_uuid = "item-uuid-001"
        ctx = _make_ctx(
            bound_roles={"patient": patient_uuid},
            entities={patient_uuid: {"attrs": {"onchain": True}}},
            transients={},
        )
        assert CONDITIONS["patient_onchain"](ctx) is True

    def test_patient_onchain_false(self):
        from memento.cxn.conditions import CONDITIONS

        patient_uuid = "item-uuid-002"
        ctx = _make_ctx(
            bound_roles={"patient": patient_uuid},
            entities={patient_uuid: {"attrs": {"onchain": False}}},
            transients={},
        )
        assert CONDITIONS["patient_onchain"](ctx) is False

    def test_patient_onchain_missing_attr(self):
        from memento.cxn.conditions import CONDITIONS

        patient_uuid = "item-uuid-003"
        ctx = _make_ctx(
            bound_roles={"patient": patient_uuid},
            entities={patient_uuid: {"attrs": {}}},
            transients={},
        )
        assert CONDITIONS["patient_onchain"](ctx) is False

    def test_patient_onchain_no_attrs(self):
        from memento.cxn.conditions import CONDITIONS

        patient_uuid = "item-uuid-004"
        ctx = _make_ctx(
            bound_roles={"patient": patient_uuid},
            entities={patient_uuid: {}},
            transients={},
        )
        assert CONDITIONS["patient_onchain"](ctx) is False


# ---------------------------------------------------------------------------
# constructicon.py — match / all_cxns
# ---------------------------------------------------------------------------


class TestConstructicon:
    def _registry(self):
        from memento.cxn.constructicon import ConstructiconRegistry

        return ConstructiconRegistry()

    def _frame(self, predicate: str, roles: dict) -> dict:
        return {
            "predicate": predicate,
            "roles": roles,
            "confidence": 1.0,
            "raw_text": "",
        }

    def test_match_move(self):
        reg = self._registry()
        frame = self._frame("move", {"agent": "a1b2", "location": "r002"})
        result = reg.match(frame)

        assert result is not None
        assert result["cxn"]["name"] == "MOVE"
        assert result["bound_roles"] == {"agent": "a1b2", "location": "r002"}

    def test_match_attack(self):
        reg = self._registry()
        frame = self._frame(
            "attack",
            {"agent": "a1b2", "patient": "goblin-001", "instrument": "sword-001", "location": "r002"},
        )
        result = reg.match(frame)

        assert result is not None
        assert result["cxn"]["name"] == "ATTACK"
        assert result["bound_roles"]["patient"] == "goblin-001"
        assert result["bound_roles"]["instrument"] == "sword-001"

    def test_match_take(self):
        reg = self._registry()
        frame = self._frame(
            "take",
            {"agent": "a1b2", "patient": "item-scroll-001", "location": "r002"},
        )
        result = reg.match(frame)

        assert result is not None
        assert result["cxn"]["name"] == "TAKE"
        assert result["bound_roles"]["patient"] == "item-scroll-001"

    def test_match_unknown_predicate_returns_none(self):
        reg = self._registry()
        frame = self._frame("fly", {"agent": "a1b2", "location": "r002"})
        result = reg.match(frame)
        assert result is None

    def test_match_empty_predicate_returns_none(self):
        reg = self._registry()
        frame = self._frame("", {})
        result = reg.match(frame)
        assert result is None

    def test_all_cxns_returns_three(self):
        reg = self._registry()
        cxns = reg.all_cxns()
        assert len(cxns) == 3

    def test_all_cxns_names(self):
        reg = self._registry()
        names = {c["name"] for c in reg.all_cxns()}
        assert names == {"MOVE", "ATTACK", "TAKE"}

    def test_bound_roles_is_copy(self):
        """Mutating the returned bound_roles must not affect a subsequent call."""
        reg = self._registry()
        frame = self._frame("move", {"agent": "a1b2", "location": "r002"})
        result1 = reg.match(frame)
        assert result1 is not None
        result1["bound_roles"]["injected"] = "evil"

        result2 = reg.match(frame)
        assert result2 is not None
        assert "injected" not in result2["bound_roles"]

    def test_matched_cxn_predicate_matches_frame(self):
        """The returned cxn's predicate must equal the frame's predicate."""
        reg = self._registry()
        for pred in ("move", "attack", "take"):
            frame = self._frame(pred, {})
            result = reg.match(frame)
            assert result is not None
            assert result["cxn"]["predicate"] == pred
