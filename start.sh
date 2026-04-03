#!/bin/bash
# Start Memento Mori services

set -e

cd "$(dirname "$0")"

echo "=== Memento Mori ==="

# Load env (--dev uses .env.dev for local Bonfires stack)
ENV_FILE=".env"
if [ "$1" = "--dev" ]; then
    ENV_FILE=".env.dev"
    shift
fi
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^\s*$' | xargs)
    echo "Loaded $ENV_FILE"
else
    echo "Warning: $ENV_FILE not found"
fi

# Seed world if requested
if [ "$1" = "--seed" ]; then
    echo "Seeding world (this will take several minutes)..."
    python -m memento.seed --world ${@:2}
    echo "Seeding complete."
fi

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

# --- Wait for Bonfires backend (if --dev) ---
if [ "$ENV_FILE" = ".env.dev" ]; then
    wait_for_port 8000 "delve backend" 10 || echo "Warning: delve not reachable"
fi

# --- Start engine listener ---
if [ -n "$MATRIX_HOMESERVER" ] && [ -n "$MATRIX_BOT_TOKEN" ]; then
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
