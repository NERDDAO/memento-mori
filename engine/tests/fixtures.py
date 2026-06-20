"""Shared test fixtures (UUIDs, entity docs) for the cxn control system.

UUIDs are valid 24-hex ObjectId shapes so they round-trip through the same
id validation graph-memory uses for bonfire/actor ids.
"""

from __future__ import annotations

from typing import Any

# Characters
KAEL = "6650000000000000000000a1"        # player-agent
GOBLIN = "6650000000000000000000a2"      # NPC patient

# Items
IRON_SWORD = "6650000000000000000000b1"  # instrument (Weapon, damage attr)
SCROLL = "6650000000000000000000b2"      # carryable floor item (onchain=False)

# Locations
ASH_MARKET = "6650000000000000000000c1"  # starting room
RIVER_GATE = "6650000000000000000000c2"  # MOVE destination (exit of ASH_MARKET)

BONFIRE_ID = "6650000000000000000000f1"  # mm-world-v1 namespace


# ---------------------------------------------------------------------------
# Entity-doc builder helpers (match the §6.1 EntityDoc / ItemDoc shapes).
# These produce plain dicts ready for InMemoryStateRepository.seed_entity /
# seed_item — no behaviour, just literal docs the worked examples need.
# ---------------------------------------------------------------------------


def character_doc(
    uuid: str,
    name: str,
    location_uuid: str | None,
    *,
    labels: list[str] | None = None,
    is_dead: bool = False,
    **attrs: Any,
) -> dict[str, Any]:
    """A character EntityDoc.  Extra kwargs land in attrs (hp, strength, …)."""
    return {
        "uuid": uuid,
        "name": name,
        "kind": "character",
        "labels": labels if labels is not None else ["Character"],
        "location_uuid": location_uuid,
        "attrs": dict(attrs),
        "is_dead": is_dead,
    }


def location_doc(
    uuid: str,
    name: str,
    *,
    exits: list[dict[str, Any]] | None = None,
    **attrs: Any,
) -> dict[str, Any]:
    """A location EntityDoc.  exits is a list of {direction, target_uuid} dicts."""
    a: dict[str, Any] = dict(attrs)
    a["exits"] = exits if exits is not None else []
    return {
        "uuid": uuid,
        "name": name,
        "kind": "location",
        "labels": ["Location"],
        "location_uuid": None,
        "attrs": a,
        "is_dead": False,
    }


def item_doc(
    uuid: str,
    name: str,
    *,
    labels: list[str] | None = None,
    owner_uuid: str | None = None,
    location_uuid: str | None = None,
    **attrs: Any,
) -> dict[str, Any]:
    """An ItemDoc (kind=='item').  Extra kwargs land in attrs (damage, carryable, …)."""
    return {
        "uuid": uuid,
        "name": name,
        "kind": "item",
        "labels": labels if labels is not None else ["Item"],
        "owner_uuid": owner_uuid,
        "location_uuid": location_uuid,
        "attrs": dict(attrs),
    }
