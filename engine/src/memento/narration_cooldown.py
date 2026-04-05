"""Persistent narration cooldown — survives engine restarts."""

from __future__ import annotations

import json
import time
from pathlib import Path

from memento.log import get_logger

logger = get_logger(__name__)

_DEFAULT_PATH = Path("data/narration_cooldowns.json")


class NarrationCooldown:
    """JSON file-backed per-location narration gating."""

    def __init__(
        self,
        *,
        path: Path = _DEFAULT_PATH,
        cooldown: float = 30.0,
    ) -> None:
        self._path = path
        self._cooldown = cooldown

    def should_narrate(self, location: str) -> bool:
        state = self._load()
        last = state.get(location, 0.0)
        return (time.time() - last) >= self._cooldown

    def record(self, location: str) -> None:
        state = self._load()
        state[location] = time.time()
        self._save(state)

    def _load(self) -> dict[str, float]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read narration cooldowns from %s", self._path)
            return {}

    def _save(self, state: dict[str, float]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state))
