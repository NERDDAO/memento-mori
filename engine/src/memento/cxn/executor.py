"""EffectExecutor — the 3-phase deterministic construction executor (C4).

Single entry point: ``execute(cxn, caller_id, bindings) -> dict``.

Three strictly ordered phases (spec §7.2), NO LLM / NO NLP / NO RNG anywhere:

  Phase 1   — selection-restriction + guard validation (reads only).
  Phase 1.5 — pure transient compute (arithmetic.py, never mechanics.py).
  Phase 2   — transactional primitives, all-or-nothing with reverse-order
              compensation (§3.3).
  Phase 3   — memory ingest (best-effort) + optional chain mirror
              (fire-and-forget). Neither rolls back.

The executor then builds a ``StateUpdate`` (the existing v1 model — schema
unchanged) from ``get_actor_snapshot`` and returns ``model_dump(exclude_none=True)``.

Determinism is a hard guarantee: ATTACK damage is exactly
``max(0, weapon + strength - armor)`` via ``cxn/arithmetic.py``.
"""
from __future__ import annotations

import logging
from typing import Any

from memento.cxn import arithmetic
from memento.cxn.conditions import CONDITIONS
from memento.cxn.types import (
    ConstructionError,
    CxnDef,
    EpisodeIn,
    ExecutionContext,
    StateDelta,
    StatePrimitive,
)
from memento.memory.client import MemoryClient
from memento.models.state_update import (
    CombatEvent,
    EventSummary,
    InventoryEvent,
    StateUpdate,
)
from memento.state.chain_mirror import ChainMirror
from memento.state.repository import StateRepository

logger = logging.getLogger(__name__)

# Inventory capacity ceiling for the capacity_ok guard (§4.1).
DEFAULT_CAPACITY = 20

# Fixed world-namespace for episode writes (§5.1). The skeleton ships a single
# world; a real deployment injects this. Kept as a constructor default.
DEFAULT_BONFIRE_ID = "mm-world-v1"


# ---------------------------------------------------------------------------
# Guard predicates — deterministic, read-only, no LLM (§4.1).
# Each takes the executor's loaded-doc context and returns bool.
# ---------------------------------------------------------------------------


def _equipped_main_hand(agent_doc: dict[str, Any]) -> str | None:
    """Return the agent's equipped main-hand weapon UUID, or None."""
    equipped = agent_doc.get("attrs", {}).get("equipped", {}) or {}
    return equipped.get("main_hand")


def _guard_exit_exists(ctx: "_GuardCtx") -> bool:
    """The agent's current location has an exit whose target is the destination."""
    agent_loc = ctx.docs.get(ctx.agent_location_uuid or "")
    if agent_loc is None:
        return False
    dest_uuid = ctx.roles.get("location")
    exits = agent_loc.get("attrs", {}).get("exits", []) or []
    return any(e.get("target_uuid") == dest_uuid for e in exits)


def _guard_agent_armed(ctx: "_GuardCtx") -> bool:
    """Agent has a weapon: the bound instrument doc carries the Weapon label."""
    instrument_uuid = ctx.roles.get("instrument")
    if not instrument_uuid:
        return False
    instr = ctx.docs.get(instrument_uuid)
    if instr is None:
        return False
    return "Weapon" in (instr.get("labels", []) or [])


def _guard_target_damageable(ctx: "_GuardCtx") -> bool:
    """Patient has an hp attr and is not Dead."""
    patient = ctx.docs.get(ctx.roles.get("patient", ""))
    if patient is None:
        return False
    if patient.get("is_dead"):
        return False
    if "Dead" in (patient.get("labels", []) or []):
        return False
    return patient.get("attrs", {}).get("hp") is not None


def _guard_same_room(ctx: "_GuardCtx") -> bool:
    """Patient/item location_uuid matches the agent's current location."""
    target = ctx.docs.get(ctx.roles.get("patient", ""))
    if target is None:
        return False
    return target.get("location_uuid") == ctx.agent_location_uuid


def _guard_item_carryable(ctx: "_GuardCtx") -> bool:
    """The item's carryable attr is not False (absent => carryable)."""
    item = ctx.docs.get(ctx.roles.get("patient", ""))
    if item is None:
        return False
    return item.get("attrs", {}).get("carryable", True) is not False


def _guard_capacity_ok(ctx: "_GuardCtx") -> bool:
    """The agent's inventory count is below DEFAULT_CAPACITY."""
    agent = ctx.docs.get(ctx.roles.get("agent", ""))
    if agent is None:
        return False
    inv = agent.get("attrs", {}).get("inventory", []) or []
    return len(inv) < DEFAULT_CAPACITY


class _GuardCtx:
    """Read-only bundle passed to guard predicates (loaded docs + bound roles)."""

    __slots__ = ("docs", "roles", "agent_location_uuid")

    def __init__(
        self,
        docs: dict[str, dict[str, Any]],
        roles: dict[str, str],
        agent_location_uuid: str | None,
    ) -> None:
        self.docs = docs
        self.roles = roles
        self.agent_location_uuid = agent_location_uuid


GUARDS = {
    "exit_exists": _guard_exit_exists,
    "agent_armed": _guard_agent_armed,
    "target_damageable": _guard_target_damageable,
    "same_room": _guard_same_room,
    "item_carryable": _guard_item_carryable,
    "capacity_ok": _guard_capacity_ok,
}


class EffectExecutor:
    """Deterministic 3-phase executor for the construction control system."""

    def __init__(
        self,
        repo: StateRepository,
        memory: MemoryClient,
        chain: ChainMirror,
        bonfire_id: str = DEFAULT_BONFIRE_ID,
    ) -> None:
        self._repo = repo
        self._memory = memory
        self._chain = chain
        self._bonfire_id = bonfire_id
        # Simple monotonic world tick (§6.3). Starts at 0; a constant 0 is
        # acceptable per spec, but we increment once per resolved action so a
        # live chain mirror gets sequencing for free.
        self._world_tick = 0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def execute(
        self, cxn: CxnDef, caller_id: str, bindings: dict[str, str]
    ) -> dict[str, Any]:
        """Run the 3 phases for ``cxn`` with ``caller_id`` as the agent.

        ``bindings`` is the role→UUID map the MCP handler built from tool args
        (e.g. {"patient": ..., "instrument": ...}); ``agent`` and ``location``
        are derived here (agent = caller JWT sub; location = agent's room).
        Returns ``StateUpdate.model_dump(exclude_none=True)``.
        """
        roles: dict[str, str] = dict(bindings)
        roles["agent"] = caller_id  # agent always comes from the caller, never a param

        # --- Phase 1: reads + restriction + guard validation (no writes) ---
        docs = await self._phase1_resolve_and_validate(cxn, roles)

        # --- Phase 1.5: build context + compute transients (pure) ---
        ctx = self._phase1_5_transients(cxn, roles, docs)

        # --- Phase 2: transactional primitives (all-or-nothing) ---
        deltas = await self._phase2_transactional(cxn, roles, ctx)

        # --- Phase 3: memory + optional chain (non-fatal, no rollback) ---
        await self._phase3_memory_and_chain(cxn, roles, ctx)

        self._world_tick += 1

        return await self._build_state_update(cxn, roles, ctx, deltas)

    # ------------------------------------------------------------------
    # Phase 1 — reads, restriction + guard validation
    # ------------------------------------------------------------------

    async def _phase1_resolve_and_validate(
        self, cxn: CxnDef, roles: dict[str, str]
    ) -> dict[str, dict[str, Any]]:
        # location role = the agent's current room (one read of the agent doc).
        agent_doc = await self._repo.get_entity(roles["agent"])
        if agent_doc is None:
            raise ConstructionError(f"selection_restriction: agent {roles['agent']!r} not found")
        agent_location_uuid = agent_doc.get("location_uuid")
        # location role defaults to the agent's current room (§7.1 M1) — but only
        # when the handler did not bind it explicitly. MOVE binds location to the
        # destination room; ATTACK/TAKE leave it for us to fill from the agent.
        if not roles.get("location") and agent_location_uuid is not None:
            roles["location"] = agent_location_uuid

        # ATTACK: default instrument from equipped main-hand BEFORE the Weapon
        # restriction check (§7.1 M2).
        if cxn["name"] == "ATTACK" and not roles.get("instrument"):
            resolved = _equipped_main_hand(agent_doc)
            if resolved:
                roles["instrument"] = resolved

        # Load every bound role's doc once (reads only).
        docs: dict[str, dict[str, Any]] = {roles["agent"]: agent_doc}
        for role, uuid in roles.items():
            if uuid not in docs:
                doc = await self._repo.get_entity(uuid)
                if doc is not None:
                    docs[uuid] = doc

        # The agent's CURRENT room may not be a bound role (MOVE binds location to
        # the destination). Load it so exit_exists can read its exits.
        if agent_location_uuid and agent_location_uuid not in docs:
            cur_room = await self._repo.get_entity(agent_location_uuid)
            if cur_room is not None:
                docs[agent_location_uuid] = cur_room

        # Selection restrictions: required present, forbidden absent.
        for restriction in cxn["restrictions"]:
            role = restriction["role"]
            uuid = roles.get(role)
            if not uuid:
                # The instrument role is optionally resolved (equipped main-hand).
                # When unresolved, let the agent_armed guard produce the clean
                # failure (§7.1 M2) rather than a restriction error here.
                if role == "instrument":
                    continue
                raise ConstructionError(
                    f"selection_restriction: role {role!r} unbound"
                )
            labels = await self._repo.get_labels(uuid)
            for req in restriction["required_labels"]:
                if req not in labels:
                    raise ConstructionError(
                        f"selection_restriction: {role} missing required label {req!r}"
                    )
            for forb in restriction["forbidden_labels"]:
                if forb in labels:
                    raise ConstructionError(
                        f"selection_restriction: {role} carries forbidden label {forb!r}"
                    )

        # Named guards (closed dict of read-only predicates).
        gctx = _GuardCtx(docs=docs, roles=roles, agent_location_uuid=agent_location_uuid)
        for guard_name in cxn["guards"]:
            predicate = GUARDS.get(guard_name)
            if predicate is None:
                raise ConstructionError(f"selection_restriction: unknown guard {guard_name!r}")
            if not predicate(gctx):
                raise ConstructionError(guard_name)

        return docs

    # ------------------------------------------------------------------
    # Phase 1.5 — build ExecutionContext + compute transients (pure)
    # ------------------------------------------------------------------

    def _phase1_5_transients(
        self,
        cxn: CxnDef,
        roles: dict[str, str],
        docs: dict[str, dict[str, Any]],
    ) -> ExecutionContext:
        entities: dict[str, dict] = {
            uuid: docs[uuid] for uuid in roles.values() if uuid in docs
        }
        transients: dict[str, Any] = {}

        if cxn["name"] == "ATTACK":
            instrument = docs.get(roles.get("instrument", ""), {})
            agent = docs.get(roles["agent"], {})
            patient = docs.get(roles.get("patient", ""), {})
            weapon_dmg = int(instrument.get("attrs", {}).get("damage", 0) or 0)
            strength = int(agent.get("attrs", {}).get("strength", 0) or 0)
            armor = int(patient.get("attrs", {}).get("armor", 0) or 0)
            current_hp = int(patient.get("attrs", {}).get("hp", 0) or 0)

            dmg = arithmetic.damage(weapon_dmg, strength, armor)
            computed_hp = arithmetic.clamp_hp(current_hp, dmg)
            transients["damage"] = dmg
            transients["computed_hp"] = computed_hp
            patient_name = patient.get("name", "")
            transients["death_suffix"] = (
                f" — {patient_name} has died." if computed_hp <= 0 else ""
            )

        return ExecutionContext(
            bound_roles=dict(roles),
            entities=entities,
            transients=transients,
            world_tick=self._world_tick,
        )

    # ------------------------------------------------------------------
    # Phase 2 — transactional primitives (all-or-nothing)
    # ------------------------------------------------------------------

    async def _phase2_transactional(
        self,
        cxn: CxnDef,
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> list[StateDelta]:
        deltas: list[StateDelta] = []
        # Records enough to run the §3.3 compensation table in reverse.
        applied: list[dict[str, Any]] = []

        for prim in cxn["effect_template"]:
            if prim["substrate"] != "transactional":
                continue
            if not self._condition_true(prim, ctx):
                continue
            try:
                delta, comp = await self._apply_transactional(prim, roles, ctx)
            except Exception:
                # Domain/programming failure: roll back applied ops in reverse.
                await self._compensate(applied)
                raise ConstructionError("transactional_failed")
            deltas.append(delta)
            applied.append(comp)

        return deltas

    async def _apply_transactional(
        self,
        prim: StatePrimitive,
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> tuple[StateDelta, dict[str, Any]]:
        op = prim["op"]
        args = self._resolve_args(prim["args"], roles, ctx)

        if op == "set_attr":
            uuid = args["uuid"]
            field = args["field"]
            value = args["value"]
            before_doc = await self._repo.get_entity(uuid)
            before = self._read_field(before_doc, field)
            after_doc = await self._repo.set_attr(uuid, field, value)
            after = self._read_field(after_doc, field)
            delta = StateDelta(op=op, target_uuid=uuid, field=field, before=before, after=after)
            comp = {"op": "set_attr", "uuid": uuid, "field": field, "value": before}
            return delta, comp

        if op == "move_entity":
            uuid = args["uuid"]
            to_loc = args["to_location_uuid"]
            before_doc = await self._repo.get_entity(uuid)
            before = before_doc.get("location_uuid") if before_doc else None
            after_doc = await self._repo.move_entity(uuid, to_loc)
            after = after_doc.get("location_uuid")
            delta = StateDelta(
                op=op, target_uuid=uuid, field="location_uuid", before=before, after=after
            )
            comp = {"op": "move_entity", "uuid": uuid, "to_location_uuid": before}
            return delta, comp

        if op == "transfer_item":
            item_uuid = args["item_uuid"]
            from_uuid = args.get("from_uuid")
            to_uuid = args.get("to_uuid")
            to_location_uuid = args.get("to_location_uuid")
            before_doc = await self._repo.get_entity(item_uuid)
            before = before_doc.get("owner_uuid") if before_doc else None
            orig_location = before_doc.get("location_uuid") if before_doc else None
            after_doc = await self._repo.transfer_item(
                item_uuid, from_uuid, to_uuid, to_location_uuid
            )
            after = after_doc.get("owner_uuid")
            delta = StateDelta(
                op=op, target_uuid=item_uuid, field="owner_uuid", before=before, after=after
            )
            # Restore: swap from/to and return item to its original floor location.
            comp = {
                "op": "transfer_item",
                "item_uuid": item_uuid,
                "from_uuid": to_uuid,
                "to_uuid": from_uuid,
                "to_location_uuid": orig_location,
            }
            return delta, comp

        if op == "link":
            from_uuid = args["from_uuid"]
            to_uuid = args["to_uuid"]
            rel = args["rel"]
            await self._repo.link(from_uuid, to_uuid, rel)
            delta = StateDelta(
                op=op, target_uuid=from_uuid, field=rel, before=None, after=to_uuid
            )
            comp = {"op": "unlink", "from_uuid": from_uuid, "to_uuid": to_uuid, "rel": rel}
            return delta, comp

        if op == "unlink":
            from_uuid = args["from_uuid"]
            to_uuid = args["to_uuid"]
            rel = args["rel"]
            await self._repo.unlink(from_uuid, to_uuid, rel)
            delta = StateDelta(
                op=op, target_uuid=from_uuid, field=rel, before=to_uuid, after=None
            )
            comp = {"op": "link", "from_uuid": from_uuid, "to_uuid": to_uuid, "rel": rel}
            return delta, comp

        raise ConstructionError(f"transactional_failed: unknown op {op!r}")

    async def _compensate(self, applied: list[dict[str, Any]]) -> None:
        """Run inverse ops (§3.3 table) in reverse order. Never raises."""
        for comp in reversed(applied):
            try:
                op = comp["op"]
                if op == "set_attr":
                    await self._repo.set_attr(comp["uuid"], comp["field"], comp["value"])
                elif op == "move_entity":
                    if comp["to_location_uuid"] is not None:
                        await self._repo.move_entity(comp["uuid"], comp["to_location_uuid"])
                elif op == "transfer_item":
                    await self._repo.transfer_item(
                        comp["item_uuid"],
                        comp["from_uuid"],
                        comp["to_uuid"],
                        comp["to_location_uuid"],
                    )
                elif op == "link":
                    await self._repo.link(comp["from_uuid"], comp["to_uuid"], comp["rel"])
                elif op == "unlink":
                    await self._repo.unlink(comp["from_uuid"], comp["to_uuid"], comp["rel"])
            except Exception:  # pragma: no cover - best-effort rollback
                logger.exception("compensation step failed for %r", comp)

    # ------------------------------------------------------------------
    # Phase 3 — memory ingest + optional chain mirror (non-fatal)
    # ------------------------------------------------------------------

    async def _phase3_memory_and_chain(
        self,
        cxn: CxnDef,
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> None:
        # Memory primitives — best-effort, isolated, non-fatal.
        for prim in cxn["effect_template"]:
            if prim["substrate"] != "memory":
                continue
            if not self._condition_true(prim, ctx):
                continue
            if prim["op"] == "ingest_episode":
                text = self._render_episode(cxn, roles, ctx)
                actor_id = self._resolve_ref(prim["args"].get("actor_id"), roles, ctx)
                episode = EpisodeIn(
                    bonfire_id=self._bonfire_id,
                    actor_id=actor_id,
                    content=text,
                    metadata={"cxn": cxn["name"], "world_tick": ctx["world_tick"]},
                )
                try:
                    await self._memory.ingest_episode(episode)
                except Exception:  # pragma: no cover - non-fatal
                    logger.exception("ingest_episode failed (non-fatal)")

        # Chain primitives — fire-and-forget, never roll back.
        if not cxn["chain_mirror"]:
            return
        for prim in cxn["effect_template"]:
            if prim["substrate"] != "chain":
                continue
            if not self._condition_true(prim, ctx):
                continue
            try:
                self._fire_chain(prim, roles, ctx)
            except Exception:  # pragma: no cover - fire-and-forget
                logger.exception("chain primitive %r failed (non-fatal)", prim.get("op"))

    def _fire_chain(
        self,
        prim: StatePrimitive,
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> None:
        op = prim["op"]
        if op == "chain_kill":
            character_id = self._resolve_ref(prim["args"].get("character_id"), roles, ctx)
            cause = prim["args"].get("cause", "combat")
            location_id = self._resolve_ref(prim["args"].get("location_id"), roles, ctx)
            # NO killer_id (§6.3).
            self._chain.on_character_death(
                character_id, cause, location_id, ctx["world_tick"]
            )
        elif op == "chain_transfer":
            item_id = self._resolve_ref(prim["args"].get("item_id"), roles, ctx)
            new_owner_id = self._resolve_ref(prim["args"].get("new_owner_id"), roles, ctx)
            self._chain.on_item_transferred(item_id, new_owner_id)

    # ------------------------------------------------------------------
    # StateUpdate build
    # ------------------------------------------------------------------

    async def _build_state_update(
        self,
        cxn: CxnDef,
        roles: dict[str, str],
        ctx: ExecutionContext,
        deltas: list[StateDelta],
    ) -> dict[str, Any]:
        snap = await self._repo.get_actor_snapshot(roles["agent"])
        update = StateUpdate(
            location=snap.get("location"),
            health=snap.get("health"),
            max_health=snap.get("max_health"),
            level=snap.get("level"),
            xp=snap.get("xp"),
        )

        if cxn["name"] == "ATTACK":
            patient = ctx["entities"].get(roles.get("patient", ""), {})
            computed_hp = ctx["transients"].get("computed_hp", 0)
            update.events = EventSummary(
                categories=["combat"],
                combat=CombatEvent(
                    action_type="attack",
                    target_name=patient.get("name", ""),
                    damage_dealt=ctx["transients"].get("damage"),
                    target_dead=computed_hp <= 0,
                ),
            )
        elif cxn["name"] == "TAKE":
            patient = ctx["entities"].get(roles.get("patient", ""), {})
            update.events = EventSummary(
                categories=["inventory"],
                inventory_changes=[
                    InventoryEvent(event_type="PICKUP", item_name=patient.get("name", ""))
                ],
            )

        result = update.model_dump(exclude_none=True)
        # state_deltas are the executor's audit payload (not a model field).
        result["state_deltas"] = [dict(d) for d in deltas]
        return result

    # ------------------------------------------------------------------
    # Substitution + condition helpers (no eval, no parser)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_field(doc: dict[str, Any] | None, field: str) -> Any:
        """Read a field for StateDelta — top-level (is_dead) or attrs-level (hp)."""
        if doc is None:
            return None
        if field == "is_dead":
            return doc.get("is_dead")
        return doc.get("attrs", {}).get(field)

    def _condition_true(self, prim: StatePrimitive, ctx: ExecutionContext) -> bool:
        cond = prim["if_condition"]
        if cond is None:
            return True
        predicate = CONDITIONS.get(cond)
        if predicate is None:
            raise ConstructionError(f"transactional_failed: unknown condition {cond!r}")
        return predicate(ctx)

    def _resolve_args(
        self,
        args: dict[str, Any],
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> dict[str, Any]:
        return {k: self._resolve_ref(v, roles, ctx) for k, v in args.items()}

    def _resolve_ref(
        self, value: Any, roles: dict[str, str], ctx: ExecutionContext
    ) -> Any:
        """Resolve a single $role / $computed_* ref; literals pass through."""
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        key = value[1:]
        if key == "computed_hp":
            return ctx["transients"]["computed_hp"]
        if key in roles:
            return roles[key]
        # Unknown $-ref: surface as a programming error within the txn phase.
        raise KeyError(f"unresolved reference {value!r}")

    def _render_episode(
        self,
        cxn: CxnDef,
        roles: dict[str, str],
        ctx: ExecutionContext,
    ) -> str:
        """Resolve {role_name} + {transient} substitutions in episode_template."""
        template = cxn["episode_template"]
        subs: dict[str, Any] = {}
        # {role_name} -> resolved entity name (one doc per bound role).
        for role, uuid in roles.items():
            doc = ctx["entities"].get(uuid, {})
            subs[f"{role}_name"] = doc.get("name", "")
        # transients -> {damage}/{death_suffix}/...
        for k, v in ctx["transients"].items():
            subs[k] = v
        try:
            return template.format_map(_SafeDict(subs))
        except Exception:  # pragma: no cover - defensive; templates are fixed
            return template


class _SafeDict(dict):
    """format_map dict that leaves unknown {keys} untouched instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
