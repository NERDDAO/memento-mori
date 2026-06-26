"""FastAPI gateway — thin bridge between web client and engine via Matrix."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from gateway.log import get_logger
from gateway.matrix_bridge import MatrixBridge
from gateway.mcp_server import build_mcp_app
from gateway.ws import WebSocketHub
from memento.round_manager import RoundManager
from gateway.round_callback import make_round_callback, make_action_callback
from gateway.room_driver import build_agent_runtime_client

logger = get_logger(__name__)


bridge: MatrixBridge | None = None
ws_hub: WebSocketHub | None = None
round_manager: RoundManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, ws_hub, round_manager
    ws_hub = WebSocketHub()
    app.state.ws_hub = ws_hub
    round_manager = RoundManager(window_seconds=20)
    # Matrix bridge connects on startup if env vars are set
    import os

    homeserver = os.getenv("MATRIX_HOMESERVER", "")
    token = os.getenv("MATRIX_BOT_TOKEN", "")
    if homeserver and token:
        bridge = MatrixBridge(homeserver, token, ws_hub)
        await bridge.connect()
        app.state.bridge = bridge
        app.state.narrator_registry = bridge._narrator_agents
        round_manager.on_round_close(make_round_callback(bridge, ws_hub))
        round_manager.on_action(make_action_callback(ws_hub))
    else:
        bridge = None
        app.state.bridge = None
        app.state.narrator_registry = {}

    mcp_asgi = build_mcp_app(
        ws_hub=ws_hub,
        bridge=bridge,
        narrator_registry=app.state.narrator_registry,
    )
    app.mount("/mcp", mcp_asgi)
    # app.mount() appends after the catch-all StaticFiles("") mount, which
    # would swallow all requests before /mcp is checked. Swap the last two
    # routes so /mcp is tried before the catch-all.
    app.router.routes[-2], app.router.routes[-1] = (
        app.router.routes[-1],
        app.router.routes[-2],
    )
    logger.info("mcp_server: mounted at /mcp")

    # Expose the shared cxn repo + executor on app.state so the HTTP
    # tool-exec route (POST /v1/tools/{tool}) can dispatch through the SAME
    # EffectExecutor instance as the MCP handlers — no divergent fork (G1).
    app.state.cxn_repo = mcp_asgi.cxn_repo  # type: ignore[attr-defined]
    app.state.cxn_executor = mcp_asgi.cxn_executor  # type: ignore[attr-defined]
    app.state.agent_runtime_client = build_agent_runtime_client()
    app.state.scene_registry = {}
    app.state.scene_locations = {}  # location name -> uuid cache (LocationResolver)
    from gateway.world_identity import resolve_bonfire_id

    app.state.bonfire_id = resolve_bonfire_id()
    if os.environ.get("PERSONA_LOCAL_SEED"):
        from gateway.persona_seed import seed_local_personas

        await seed_local_personas(app.state.cxn_repo, app.state.scene_locations)

    if os.environ.get("PERSONA_KG_SEED"):
        from gateway.persona_seed import provision_kg_personas

        try:
            await provision_kg_personas(app.state.cxn_repo, app.state.scene_locations)
        except Exception:
            logger.warning("KG persona provisioning failed (non-fatal)", exc_info=True)

    if os.environ.get("PERSONA_OPENING_SEED"):
        from gateway.persona_seed import seed_opening_persona

        try:
            await seed_opening_persona(app.state.cxn_repo, app.state.scene_locations)
        except Exception:
            logger.warning("opening persona seed failed (non-fatal)", exc_info=True)

    # Seed NPC registry from MongoDB + world.json
    from gateway.npc_registry import seed_from_db, register_npc, update_npc_location

    npc_count = seed_from_db()
    logger.info("NPC registry seeded: %d agents", npc_count)

    # Wire engine → gateway registry hooks (breaks the circular import)
    from memento.agent_controller import set_registry_hooks

    set_registry_hooks(on_register=register_npc, on_move=update_npc_location)

    # Seed ontology types on Delve for this bonfire
    _seed_ontology()

    # Start the MCP session manager's task group — streamable_http_app()'s
    # inner Starlette lifespan won't fire because the mount was added during
    # the outer app's lifespan (after inner lifespan dispatch already passed).
    async with mcp_asgi.session_manager.run():
        yield

    await app.state.agent_runtime_client.aclose()
    if bridge:
        await bridge.disconnect()


def _seed_ontology() -> None:
    """Register world seed extraction types on the bonfire's Delve ontology."""
    try:
        from memento.bonfires_client import get_client
        from memento.rpg_types import RPG_ENTITY_TYPES

        client = get_client()

        # Convert Pydantic models to OntologyLabel format for Delve
        entity_labels = []
        for name, model in RPG_ENTITY_TYPES.items():
            schema = model.model_json_schema()
            fields = {}
            properties = schema.get("properties", {})
            required_fields = set(schema.get("required", []))
            for fname, fprop in properties.items():
                ftype = fprop.get("type", "string")
                # Map JSON Schema types to OntologyField types
                type_map = {
                    "string": "str",
                    "integer": "int",
                    "number": "float",
                    "boolean": "bool",
                }
                if ftype == "array" and fprop.get("items", {}).get("type") == "string":
                    resolved_type = "list[str]"
                else:
                    resolved_type = type_map.get(ftype, "str")
                fields[fname] = {
                    "type": resolved_type,
                    "description": fprop.get("description", ""),
                    "required": fname in required_fields,
                }
            entity_labels.append(
                {
                    "name": name,
                    "description": model.__doc__ or "",
                    "labels": [name],
                    "fields": fields,
                }
            )

        client.ontology.set_extraction_types(entity_labels)
        logger.info("Seeded ontology types: %s", [l["name"] for l in entity_labels])
    except Exception:
        logger.warning("Failed to seed ontology types (non-fatal)", exc_info=True)


app = FastAPI(title="Memento Mori Gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "matrix_connected": bridge is not None and bridge.connected}


@app.get("/api/room-id/{location_name}")
async def get_room_id(location_name: str):
    """Look up Matrix room_id for a location name."""
    if bridge and location_name in bridge.location_to_room:
        return {"room_id": bridge.location_to_room[location_name]}
    return {"room_id": ""}


# Include routes
from gateway.routes import (
    action,
    session,
    state,
    entity,
    chain,
    inventory,
    codex,
    chronicle,
    admin,
    player_signup,
    tools_http,
    opening,
    scenes,
)

app.include_router(action.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(entity.router, prefix="/api")
app.include_router(chain.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(codex.router, prefix="/api")
app.include_router(chronicle.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(player_signup.router, prefix="/api")
app.include_router(tools_http.router)
app.include_router(opening.router, prefix="/api")
app.include_router(scenes.router, prefix="/api")

# WebSocket endpoint
from fastapi import WebSocket, WebSocketDisconnect


async def _evict_scene_on_disconnect(player_id: str) -> None:
    """On WS disconnect, close the player's scene if they were the last one there.
    Best-effort: never raises into the WS teardown path."""
    if ws_hub is None:
        return
    departed = ws_hub.player_locations.get(
        player_id, ""
    )  # read before disconnect pops it
    await ws_hub.disconnect(player_id)
    if not departed:
        return
    try:
        from gateway.scene_coordinator import SceneCoordinator

        coordinator = SceneCoordinator.from_app_state(app.state)
        await coordinator.maybe_close(departed)
    except Exception:
        logger.warning(
            "scene eviction on disconnect failed for %s", player_id, exc_info=True
        )


@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    if ws_hub is None:
        await websocket.close()
        return
    await ws_hub.connect(player_id, websocket)
    try:
        while True:
            # Keep connection alive, receive pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        await _evict_scene_on_disconnect(player_id)
    except Exception:
        logger.warning(
            "WebSocket error for %s, disconnecting", player_id, exc_info=True
        )
        await _evict_scene_on_disconnect(player_id)


# Static file serving — must be last (mounts at "/")
client_dir = Path(__file__).parent.parent.parent.parent / "client"
if client_dir.exists():
    app.mount("/", StaticFiles(directory=str(client_dir), html=True), name="client")
