"""FastAPI gateway — thin bridge between web client and engine via Matrix."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from gateway.log import get_logger
from gateway.matrix_bridge import MatrixBridge
from gateway.ws import WebSocketHub
from memento.round_manager import RoundManager
from gateway.round_callback import make_round_callback, make_action_callback

logger = get_logger(__name__)


bridge: MatrixBridge | None = None
ws_hub: WebSocketHub | None = None
round_manager: RoundManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, ws_hub, round_manager
    ws_hub = WebSocketHub()
    round_manager = RoundManager(window_seconds=20)
    # Matrix bridge connects on startup if env vars are set
    import os
    homeserver = os.getenv("MATRIX_HOMESERVER", "")
    token = os.getenv("MATRIX_BOT_TOKEN", "")
    if homeserver and token:
        bridge = MatrixBridge(homeserver, token, ws_hub)
        await bridge.connect()
        round_manager.on_round_close(make_round_callback(bridge, ws_hub))
        round_manager.on_action(make_action_callback(ws_hub))

    # Seed ontology types on Delve for this bonfire
    _seed_ontology()

    yield
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
                type_map = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
                if ftype == "array" and fprop.get("items", {}).get("type") == "string":
                    resolved_type = "list[str]"
                else:
                    resolved_type = type_map.get(ftype, "str")
                fields[fname] = {
                    "type": resolved_type,
                    "description": fprop.get("description", ""),
                    "required": fname in required_fields,
                }
            entity_labels.append({
                "name": name,
                "description": model.__doc__ or "",
                "labels": [name],
                "fields": fields,
            })

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


# Include routes
from gateway.routes import action, session, state, entity, chain, engine, inventory, codex, chronicle
app.include_router(action.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(entity.router, prefix="/api")
app.include_router(chain.router, prefix="/api")
app.include_router(engine.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(codex.router, prefix="/api")
app.include_router(chronicle.router, prefix="/api")

# WebSocket endpoint
from fastapi import WebSocket, WebSocketDisconnect

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
        await ws_hub.disconnect(player_id)
    except Exception:
        logger.warning("WebSocket error for %s, disconnecting", player_id, exc_info=True)
        await ws_hub.disconnect(player_id)


# Static file serving — must be last (mounts at "/")
client_dir = Path(__file__).parent.parent.parent.parent / "client"
if client_dir.exists():
    app.mount("/", StaticFiles(directory=str(client_dir), html=True), name="client")
