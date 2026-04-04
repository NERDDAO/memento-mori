"""Archetype configuration — load character class definitions from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_ARCHETYPES: dict[str, Any] | None = None


def load_archetypes() -> dict[str, Any]:
    """Load archetype definitions from defs/archetypes.yaml."""
    global _ARCHETYPES
    if _ARCHETYPES is not None:
        return _ARCHETYPES

    # defs/ is at repo root: engine/src/memento/config -> up 4 levels to repo root
    path = Path(__file__).parent.parent.parent.parent.parent / "defs" / "archetypes.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)

    result = data.get("archetypes")
    _ARCHETYPES = result if isinstance(result, dict) else {}
    return _ARCHETYPES


def get_archetype(name: str) -> dict[str, Any]:
    """Get a specific archetype config. Returns empty dict if not found."""
    archetypes = load_archetypes()
    return archetypes.get(name, {})


def list_archetypes() -> list[dict[str, Any]]:
    """List all available archetypes with their configs."""
    archetypes = load_archetypes()
    return [
        {"name": name, **config}
        for name, config in archetypes.items()
    ]
