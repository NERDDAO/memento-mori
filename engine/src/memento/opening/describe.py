from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from memento.opening.seed_types import SeedFact


@dataclass(frozen=True)
class DescribeRequest:
    room_name: str
    room_description: str
    focus: SeedFact | None
    surfaced: tuple[SeedFact, ...]
    candidates: tuple[SeedFact, ...]


@dataclass(frozen=True)
class DescribeResult:
    prose: str
    candidates: tuple[str, ...]


class DescribeClient(Protocol):
    async def describe(self, request: DescribeRequest) -> DescribeResult: ...


class TemplateDescribeClient:
    async def describe(self, request: DescribeRequest) -> DescribeResult:
        prose = f"{request.room_name}. {request.room_description}"
        if request.focus:
            prose = f"{prose} Before you, {request.focus.name}."
        candidates = tuple(c.name for c in request.candidates)
        return DescribeResult(prose=prose, candidates=candidates)


class FakeDescribeClient:
    def __init__(self, canned: dict[str, str]) -> None:
        self._canned = canned

    async def describe(self, request: DescribeRequest) -> DescribeResult:
        focus_key = request.focus.key if request.focus else ""
        prose = self._canned.get(focus_key, request.room_description)
        candidates = tuple(c.name for c in request.candidates)
        return DescribeResult(prose=prose, candidates=candidates)
