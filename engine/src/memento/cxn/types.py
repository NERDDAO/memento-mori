from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict


class StatePrimitive(TypedDict):
    substrate: Literal["transactional", "memory", "chain"]
    op: Literal[
        "set_attr",
        "move_entity",
        "transfer_item",
        "link",
        "unlink",
        "ingest_episode",
        "chain_kill",
        "chain_transfer",
    ]
    args: dict[str, Any]  # "$role" / "$computed_hp" refs, "@episode_template", or literals (§4.4)
    if_condition: str | None  # None, or a key into the closed CONDITIONS dict (§4.4). NO expression parser, NO eval, NO LLM.


RoleTag = Literal["agent", "patient", "instrument", "location"]


class SemanticFrame(TypedDict):
    predicate: str  # from kernel comprehension: "move" | "attack" | "take"
    roles: dict[str, str]  # role label → entity UUID (resolved)
    confidence: float  # 0.0–1.0
    raw_text: str


class SelectionRestriction(TypedDict):
    role: str
    required_labels: list[str]  # entity must carry ALL of these
    forbidden_labels: list[str]  # entity must carry NONE of these


class CxnDef(TypedDict):
    name: str  # "MOVE" | "ATTACK" | "TAKE"
    predicate: str  # frame predicate this cxn matches
    mcp_tool_name: str  # "mm_move" | "mm_attack" | "mm_take"
    description: str  # MCP tool docstring (agent-facing)
    semantic_roles: list[str]  # ordered roles → MCP tool params
    restrictions: list[SelectionRestriction]
    guards: list[str]  # named runtime predicates (e.g. "exit_exists")
    chain_mirror: bool  # whether the cxn fires chain primitives
    effect_template: list[StatePrimitive]
    episode_template: str  # f-string over role labels + computed values


class MatchedCxn(TypedDict):
    cxn: CxnDef
    bound_roles: dict[str, str]  # role label → UUID, fully resolved


class StateDelta(TypedDict):
    op: str
    target_uuid: str
    field: str
    before: Any
    after: Any


class EpisodeIn(TypedDict):
    bonfire_id: str
    actor_id: str
    content: str
    metadata: dict[str, Any]


class ExecutionContext(TypedDict):
    bound_roles: dict[str, str]  # role label → UUID
    entities: dict[str, dict]  # UUID → loaded entity doc
    transients: dict[str, Any]  # computed_hp, damage, etc.
    world_tick: int


class ConstructionError(Exception):
    """Typed failure from binding/guard/transactional phases (see spec §7.4 prefixes)."""


class Constructicon(Protocol):
    def match(self, frame: SemanticFrame) -> MatchedCxn | None: ...

    def all_cxns(self) -> list[CxnDef]: ...
