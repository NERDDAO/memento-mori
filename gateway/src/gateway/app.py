"""FastAPI gateway — thin bridge between web client and engine via Matrix."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from gateway.matrix_bridge import MatrixBridge
from gateway.ws import WebSocketHub


bridge: MatrixBridge | None = None
ws_hub: WebSocketHub | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, ws_hub
    ws_hub = WebSocketHub()
    # Matrix bridge connects on startup if env vars are set
    import os
    homeserver = os.getenv("MATRIX_HOMESERVER", "")
    token = os.getenv("MATRIX_BOT_TOKEN", "")
    if homeserver and token:
        bridge = MatrixBridge(homeserver, token, ws_hub)
        await bridge.connect()
    yield
    if bridge:
        await bridge.disconnect()


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
from gateway.routes import action, session, state, entity
app.include_router(action.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(entity.router, prefix="/api")

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
        ws_hub.disconnect(player_id)


# Static file serving — must be last (mounts at "/")
client_dir = Path(__file__).parent.parent.parent.parent / "client"
if client_dir.exists():
    app.mount("/", StaticFiles(directory=str(client_dir), html=True), name="client")
