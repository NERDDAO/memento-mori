"""Opening arc routes — director-backed engine surface for the immersive opening.

Two endpoints:

  POST /api/opening/start  — create a fresh per-player opening-arc stack seeded
                             with the Deep Roads opening room; register a
                             director-backed TurnRouter; return initial room state.

  POST /api/opening/act   — drive a turn through the registered TurnRouter;
                            on win drop the registry entry; return the TurnOutcome.

DI hooks (module-level callables)
----------------------------------
All builder hooks have real default implementations but can be replaced by tests
via monkeypatch without touching mcp_server.py:

  build_comprehension() -> ComprehensionClient
      Real default: HttpComprehensionClient if KERNEL_BASE_URL+GM_INTERNAL_TOKEN
      are set, else NullComprehensionClient (matching mcp_server.py logic).

  build_memory() -> MemoryClient-compatible
      Real default: NullMemoryClient (no kernel required for Day-1 opening arc).

  build_mirror() -> ChainMirror
      Real default: LiveChainMirror (no-ops when chain is disabled).

  build_projection() -> KgProjectionProtocol
      Real default: KgProjection wrapping the live Bonfires KG SDK.

  create_player(player_name, wallet_address, archetype) -> str (player_uuid)
      Real default: SessionManager.create_player via asyncio.to_thread (same
      path as routes/session.py:create_session).
      NOTE: create_player is defined for future full-onboarding integration
      (user/archetype edges etc.) but is NOT called by /start.  The opening
      arc creates the player identity exclusively via repo.seed_entity so that
      there is exactly ONE player entity per session (C3b fix).  Full player
      onboarding (wallet linkage, archetype edges) is a deferred follow-up.

Tests replace these hooks with fakes (KgProjectionFake, FakeComprehensionClient,
NoopChainMirror, NullMemoryClient) so the suite runs with zero network I/O.
"""

from __future__ import annotations

import asyncio
import os
import uuid as _uuid_mod

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.log import get_logger
from gateway.world_identity import resolve_bonfire_id

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Per-player TurnRouter registry (mirrors gm_room_registry in room_driver.py)
# ---------------------------------------------------------------------------

opening_registry: dict[str, object] = {}  # player_uuid → TurnRouter

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

BONFIRE_ID = resolve_bonfire_id()


class StartOpeningRequest(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=30)
    wallet_address: str = Field(
        ..., min_length=42, max_length=42, pattern=r"^0x[a-fA-F0-9]{40}$"
    )
    archetype: str = Field("", max_length=20)


class StartOpeningResponse(BaseModel):
    player_id: str
    epigraph: str
    location_id: str
    location_name: str
    description: str
    exits: list[dict] = []


class ActRequest(BaseModel):
    player_id: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# DI builder hooks — replaced by tests via monkeypatch
# ---------------------------------------------------------------------------


def build_comprehension() -> object:
    """Return the ComprehensionClient to use for opening sessions.

    Replicates the env-gated logic in mcp_server.py:1267-1270.
    """
    from memento.cxn.kernel_client import HttpComprehensionClient
    from memento.cxn.null_comprehension_client import NullComprehensionClient

    if os.environ.get("KERNEL_BASE_URL") and os.environ.get("GM_INTERNAL_TOKEN"):
        return HttpComprehensionClient(bonfire_id=BONFIRE_ID)
    return NullComprehensionClient()


def build_memory() -> object:
    """Return a MemoryClient for the opening session."""
    from memento.memory.null_client import NullMemoryClient

    return NullMemoryClient()


def build_mirror() -> object:
    """Return a ChainMirror for the opening session."""
    from memento.state.chain_mirror import LiveChainMirror

    return LiveChainMirror()


def build_projection() -> object:
    """Return a KgProjectionProtocol for the opening session."""
    from memento.bonfires_client import get_client
    from memento.state.kg_projection import KgProjection

    return KgProjection(kg=get_client().kg)


async def create_player(
    player_name: str,
    wallet_address: str,
    archetype: str,
) -> str:
    """Create a player via SessionManager and return the player UUID."""
    from memento.session import SessionManager

    sm = SessionManager()
    result = await asyncio.to_thread(
        sm.create_player,
        player_name,
        wallet_address=wallet_address,
        archetype=archetype,
    )
    return result["player_id"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/opening/start", response_model=StartOpeningResponse)
async def start_opening(req: StartOpeningRequest) -> StartOpeningResponse:
    """Create a fresh per-player opening-arc stack and return initial room state.

    Steps:
    1. Generate a stable player uuid for this opening session.
    2. Build EventSourcedStateRepository with InMemoryTxLog/ActivationLog,
       the DI-injected projection and mirror.
    3. Seed the player entity at the opening room via the projection
       (this is the ONE and ONLY player entity — C3b: no double-creation).
    4. Seed the destination room (so MOVE exit guard can resolve it).
    5. load_seed_room → SceneDirector.
    6. Build director-backed TurnRouter (canonical wiring from test_opening_arc.py).
    7. Register in opening_registry[player_uuid].
    8. Return room manifest.

    Note: full player onboarding (user/archetype edges, wallet linkage) via the
    create_player hook is a deferred follow-up.  The opening arc is self-contained.
    """
    # -- 1. Generate player uuid (single identity — no separate KG create_player call) --
    player_uuid = _uuid_mod.uuid4().hex

    # -- 2. Build per-player stack -----------------------------------------------
    from memento.state.tx_log import InMemoryActivationLog, InMemoryTxLog
    from memento.state.event_sourced import EventSourcedStateRepository

    tx_log = InMemoryTxLog()
    activation_log = InMemoryActivationLog()
    projection = build_projection()
    mirror = build_mirror()
    memory = build_memory()
    comprehension = build_comprehension()

    repo = EventSourcedStateRepository(tx_log, activation_log, projection, mirror)  # type: ignore[arg-type]

    # -- 3. Seed the player at the opening room ----------------------------------
    from memento.opening.deep_roads import LOC_DEEP_ROADS, NEXT_ROOM, deep_roads_seed

    await repo.seed_entity(
        {
            "uuid": player_uuid,
            "name": req.player_name,
            "kind": "character",
            "labels": ["Character"],
            "location_uuid": LOC_DEEP_ROADS,
            "attrs": {"inventory": []},
            "is_dead": False,
        }
    )

    # -- 4. Seed the destination room so exit guard can resolve it ---------------
    await repo.seed_entity(
        {
            "uuid": NEXT_ROOM,
            "name": "the road on",
            "kind": "location",
            "labels": ["Location"],
            "location_uuid": None,
            "attrs": {"exits": []},
            "is_dead": False,
        }
    )

    # -- 5. Seed the opening room + canon facts; get director --------------------
    seed = deep_roads_seed()
    from memento.opening.loader import load_seed_room

    director = await load_seed_room(seed, repo, player_uuid)

    # -- 6. Build director-backed TurnRouter (canonical wiring) ------------------
    from memento.cxn.constructicon import ConstructiconRegistry
    from memento.cxn.entity_resolver import EntityResolver
    from memento.cxn.executor import EffectExecutor
    from memento.cxn.turn_router import TurnRouter
    from memento.opening.describe import TemplateDescribeClient

    resolver = EntityResolver(repo, director)
    executor = EffectExecutor(repo, memory, mirror)  # type: ignore[arg-type]
    turn_router = TurnRouter(
        comprehension,  # type: ignore[arg-type]
        ConstructiconRegistry(),
        resolver,
        executor,
        BONFIRE_ID,
        director=director,
        describe_client=TemplateDescribeClient(),
        repo=repo,
        activation_log=activation_log,
    )

    # -- 7. Register -----------------------------------------------------------
    opening_registry[player_uuid] = turn_router

    # -- 8. Return room manifest -----------------------------------------------
    from memento.opening.deep_roads import OPENING_EPIGRAPH

    manifest = await repo.room_manifest(LOC_DEEP_ROADS)
    return StartOpeningResponse(
        player_id=player_uuid,
        epigraph=OPENING_EPIGRAPH,
        location_id=manifest.location_id,
        location_name=manifest.name,
        description=manifest.description,
        exits=[
            {"direction": e.direction, "target_id": e.target_id} for e in manifest.exits
        ],
    )


@router.post("/opening/act")
async def act_opening(req: ActRequest) -> dict:
    """Drive a single turn through the player's registered TurnRouter.

    Returns the TurnOutcome dict.  On win (outcome["won"] is True), the
    registry entry is dropped so the player can no longer drive this session.

    Raises:
        HTTPException(404): player_id not in opening_registry.
    """
    from memento.cxn.turn_router import TurnRouter

    router_obj = opening_registry.get(req.player_id)
    if router_obj is None:
        raise HTTPException(status_code=404, detail="Opening session not found.")

    turn_router: TurnRouter = router_obj  # type: ignore[assignment]
    outcome = await turn_router.handle(req.text, req.player_id)

    # Drop registry entry on win
    if outcome.get("won"):
        opening_registry.pop(req.player_id, None)

    return dict(outcome)
