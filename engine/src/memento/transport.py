"""Transport protocol — decouples TurnController from Matrix."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    import nio

from memento.log import get_logger

logger = get_logger(__name__)


class Transport(Protocol):
    """Interface for phase emission and NPC tracking."""

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None: ...
    def emit_art(self, location: str, art_text: str) -> None: ...
    def get_npc_count(self, location: str) -> int: ...
    def get_npc_response_count(self, location: str) -> int: ...
    def clear_npc_responses(self, location: str) -> None: ...


class NullTransport:
    """No-op transport for tests and headless runs."""

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None:
        pass

    def emit_art(self, location: str, art_text: str) -> None:
        pass

    def get_npc_count(self, location: str) -> int:
        return 0

    def get_npc_response_count(self, location: str) -> int:
        return 0

    def clear_npc_responses(self, location: str) -> None:
        pass


class MatrixTransport:
    """Matrix-backed transport — wraps nio.AsyncClient for thread-safe calls.

    Phase emission and art posting run on the main asyncio loop via
    run_coroutine_threadsafe (the controller runs in a worker thread).
    NPC tracking delegates to the shared round_controller module-level trackers.
    """

    def __init__(
        self,
        client: nio.AsyncClient,
        room_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._client = client
        self._room_id = room_id
        self._loop = loop

    def emit_phase(self, location: str, phase: str, crew: str | None = None) -> None:
        body = f"[phase] {phase}" + (f":{crew}" if crew else "")
        rpg_meta: dict[str, Any] = {
            "type": "phase",
            "phase": phase,
            "location": location,
            "channel": "events",
        }
        if crew:
            rpg_meta["crew"] = crew

        content = {
            "msgtype": "m.text",
            "body": body,
            "com.bonfires.rpg": rpg_meta,
        }
        coro = self._client.room_send(self._room_id, "m.room.message", content)
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            future.result(timeout=5)
        except Exception:
            logger.debug("emit_phase(%s:%s) send failed", phase, crew, exc_info=True)

    def emit_art(self, location: str, art_text: str) -> None:
        lines = art_text.split("\n")
        content = {
            "msgtype": "m.text",
            "body": art_text,
            "com.bonfires.rpg": {
                "type": "scene_art",
                "location": location,
                "lines": lines,
                "width": max(len(line) for line in lines) if lines else 0,
                "height": len(lines),
                "channel": "narrative",
            },
        }
        coro = self._client.room_send(self._room_id, "m.room.message", content)
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(
            lambda f: f.exception() and logger.debug("Art post failed", exc_info=f.exception())
        )

    def get_npc_count(self, location: str) -> int:
        from memento.agent_controller import get_agent_controller
        controller = get_agent_controller()
        return len(controller.get_npc_user_ids(location))

    def get_npc_response_count(self, location: str) -> int:
        from memento.round_controller import npc_response_count
        return npc_response_count(location)

    def clear_npc_responses(self, location: str) -> None:
        from memento.round_controller import clear_npc_responses
        clear_npc_responses(location)
