#!/bin/bash
# Start Memento Mori services

set -e

cd "$(dirname "$0")"

echo "=== Memento Mori ==="

# Load env
if [ -f ".env" ]; then
    export $(grep -v '^#' ".env" | grep -v '^\s*$' | xargs)
    echo "Loaded .env"
else
    echo "Error: .env not found. Copy example.env to .env and fill in values."
    exit 1
fi

# Seed world if requested
if [ "$1" = "--seed" ]; then
    echo "Seeding world (this will take several minutes)..."
    python -m memento.seed --world ${@:2}
    echo "Seeding complete."
fi

# Seed engine MCP tools (idempotent)
MONGO_URI=mongodb://localhost:27017 python scripts/seed_engine_tools.py 2>/dev/null || true

# Build client
echo "Building client..."
(cd client && bun build src/app.ts --outdir . 2>&1) || echo "Client build skipped"

# --- Wait helpers ---
wait_for_port() {
    local port=$1 name=$2 timeout=${3:-30}
    echo -n "Waiting for $name on :$port"
    for i in $(seq 1 $timeout); do
        if curl -s "http://localhost:$port/health" >/dev/null 2>&1 || \
           curl -s "http://localhost:$port/" >/dev/null 2>&1; then
            echo " ✓"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo " timeout!"
    return 1
}

# --- Start gateway ---
GATEWAY_PORT="${GATEWAY_PORT:-8081}"
echo "Starting gateway on :$GATEWAY_PORT..."
(cd gateway && PYTHONPATH=../engine/src:src uvicorn gateway.app:app --host 0.0.0.0 --port "$GATEWAY_PORT") &
GATEWAY_PID=$!

wait_for_port "$GATEWAY_PORT" "gateway"

# --- Wait for local Bonfires backend if pointing at localhost ---
if echo "${BONFIRE_BASE_URL:-}" | grep -q "localhost"; then
    wait_for_port 8000 "delve backend" 10 || echo "Warning: delve not reachable"
fi

# --- Start engine listener ---
if [ -n "$MATRIX_HOMESERVER" ] && [ -n "$MATRIX_BOT_TOKEN" ]; then
    # Kill any stale engine listeners from previous runs
    pkill -f "python.*memento.matrix_listener" 2>/dev/null && sleep 1
    echo "Starting engine Matrix listener..."
    (cd engine && PYTHONPATH=src python -m memento.matrix_listener) &
    ENGINE_PID=$!
    echo "Engine PID: $ENGINE_PID"
else
    echo "Skipping engine listener (MATRIX_HOMESERVER not set)"
fi

echo "Gateway PID: $GATEWAY_PID"
echo ""
echo "Open http://localhost:$GATEWAY_PORT"
echo "Press Ctrl+C to stop"

wait
