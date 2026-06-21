from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Mapping

FORCED_FIRST: int = 1_000_000


@dataclass(frozen=True)
class SeedFact:
    key: str
    name: str
    kind: str
    salience: int
    canon: bool
    uuid: str | None = None
    labels: tuple[str, ...] = ()
    attrs: Mapping[str, Any] = field(default_factory=dict)
    on_surface: str | None = None


@dataclass(frozen=True)
class SeedRoom:
    location_id: str
    name: str
    description: str
    facts: tuple[SeedFact, ...]
    exits: tuple[Mapping[str, Any], ...]
    win_exit: str
