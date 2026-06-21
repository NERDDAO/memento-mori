"""Construction definitions: MOVE_CXN, ATTACK_CXN, TAKE_CXN.

Literals are exactly per spec §4.2. The CONSTRUCTION_REGISTRY maps each
cxn name to its CxnDef. No logic lives here — only data.
"""

from __future__ import annotations

from memento.cxn.types import CxnDef, SelectionRestriction, StatePrimitive

# ---------------------------------------------------------------------------
# CXN.MOVE
# ---------------------------------------------------------------------------

MOVE_CXN: CxnDef = CxnDef(
    name="MOVE",
    predicate="move",
    mcp_tool_name="mm_move",
    description="Move the agent character to an adjacent room (by destination UUID).",
    semantic_roles=["agent", "location"],  # location = destination room
    restrictions=[
        SelectionRestriction(
            role="agent",
            required_labels=["Character"],
            forbidden_labels=["Dead"],
        ),
        SelectionRestriction(
            role="location",
            required_labels=["Location"],
            forbidden_labels=[],
        ),
    ],
    guards=["exit_exists"],
    chain_mirror=False,
    effect_template=[
        StatePrimitive(
            substrate="transactional",
            op="move_entity",
            args={"uuid": "$agent", "to_location_uuid": "$location"},
            if_condition=None,
        ),
        StatePrimitive(
            substrate="memory",
            op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"},
            if_condition=None,
        ),
    ],
    episode_template="{agent_name} moved to {location_name}.",
)

# ---------------------------------------------------------------------------
# CXN.ATTACK
# ---------------------------------------------------------------------------

ATTACK_CXN: CxnDef = CxnDef(
    name="ATTACK",
    predicate="attack",
    mcp_tool_name="mm_attack",
    description=(
        "Agent attacks a target, applying damage; instrument is the weapon "
        "(defaults to equipped main-hand if omitted)."
    ),
    semantic_roles=["agent", "patient", "instrument", "location"],
    restrictions=[
        SelectionRestriction(
            role="agent",
            required_labels=["Character"],
            forbidden_labels=["Dead"],
        ),
        SelectionRestriction(
            role="patient",
            required_labels=["Character"],
            forbidden_labels=["Dead"],
        ),
        SelectionRestriction(
            role="instrument",
            required_labels=["Weapon"],
            forbidden_labels=[],
        ),
    ],
    guards=["agent_armed", "target_damageable", "same_room"],
    chain_mirror=True,  # death = permadeath-critical
    effect_template=[
        StatePrimitive(
            substrate="transactional",
            op="set_attr",
            args={"uuid": "$patient", "field": "hp", "value": "$computed_hp"},
            if_condition=None,
        ),
        StatePrimitive(
            substrate="transactional",
            op="link",
            args={"from_uuid": "$patient", "to_uuid": "$location", "rel": "DIED_IN"},
            if_condition="hp_depleted",
        ),
        StatePrimitive(
            substrate="transactional",
            op="set_attr",
            args={"uuid": "$patient", "field": "is_dead", "value": True},
            if_condition="hp_depleted",
        ),
        # chain death → ChainMirror.on_character_death(character_id, cause, location_id, tick)
        # NOTE: no killer_id — the real chain.py record_death does not take one.
        StatePrimitive(
            substrate="chain",
            op="chain_kill",
            args={
                "character_id": "$patient",
                "cause": "combat",
                "location_id": "$location",
            },
            if_condition="hp_depleted",
        ),
        StatePrimitive(
            substrate="memory",
            op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"},
            if_condition=None,
        ),
    ],
    episode_template=(
        "{agent_name} attacked {patient_name} with {instrument_name}"
        " for {damage} damage{death_suffix}."
    ),
)

# ---------------------------------------------------------------------------
# CXN.TAKE
# ---------------------------------------------------------------------------

TAKE_CXN: CxnDef = CxnDef(
    name="TAKE",
    predicate="take",
    mcp_tool_name="mm_take",
    description="Agent picks up an item from the current room into their inventory.",
    semantic_roles=["agent", "patient", "location"],  # patient = item
    restrictions=[
        SelectionRestriction(
            role="agent",
            required_labels=["Character"],
            forbidden_labels=["Dead"],
        ),
        SelectionRestriction(
            role="patient",
            required_labels=["Item"],
            forbidden_labels=[],
        ),
        SelectionRestriction(
            role="location",
            required_labels=["Location"],
            forbidden_labels=[],
        ),
    ],
    guards=["item_carryable", "same_room", "capacity_ok"],
    chain_mirror=True,  # ownership change → chain transfer
    effect_template=[
        # item moves from the floor (location) to the agent;
        # from_location captured for compensation.
        StatePrimitive(
            substrate="transactional",
            op="transfer_item",
            args={
                "item_uuid": "$patient",
                "from_uuid": "$location",
                "to_uuid": "$agent",
                "to_location_uuid": None,
            },
            if_condition=None,
        ),
        StatePrimitive(
            substrate="chain",
            op="chain_transfer",
            args={"item_id": "$patient", "new_owner_id": "$agent"},
            if_condition="patient_onchain",
        ),
        StatePrimitive(
            substrate="memory",
            op="ingest_episode",
            args={"text": "@episode_template", "actor_id": "$agent"},
            if_condition=None,
        ),
    ],
    episode_template="{agent_name} picked up {patient_name} from {location_name}.",
)

# ---------------------------------------------------------------------------
# CXN.LOOK
# ---------------------------------------------------------------------------

LOOK_CXN: CxnDef = CxnDef(
    name="LOOK",
    predicate="look",
    mcp_tool_name="mm_look",
    description="Look around / examine the scene.",
    semantic_roles=[],
    restrictions=[],
    guards=[],
    chain_mirror=False,
    effect_template=[],
    episode_template="",
    read_only=True,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CONSTRUCTION_REGISTRY: dict[str, CxnDef] = {
    MOVE_CXN["name"]: MOVE_CXN,
    ATTACK_CXN["name"]: ATTACK_CXN,
    TAKE_CXN["name"]: TAKE_CXN,
    LOOK_CXN["name"]: LOOK_CXN,
}


def _validate_conditions() -> None:
    """Registration-time guard (M-5): every ``if_condition`` referenced by any
    effect template must be ``None`` or a known key in ``CONDITIONS``. Raising
    at import time turns a Phase-3 "unknown condition" runtime error into a
    fail-fast startup error (and makes the Phase-3 prefix-mismatch unreachable).
    """
    from memento.cxn.conditions import CONDITIONS

    for cxn in CONSTRUCTION_REGISTRY.values():
        for prim in cxn["effect_template"]:
            cond = prim["if_condition"]
            if cond is not None and cond not in CONDITIONS:
                raise ValueError(
                    f"{cxn['name']}: effect_template references unknown "
                    f"if_condition {cond!r} (not in CONDITIONS)"
                )


_validate_conditions()
