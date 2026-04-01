#!/bin/bash
# Start Memento Mori services

set -e

cd "$(dirname "$0")"

echo "=== Memento Mori ==="

# Load env
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)
    echo "Loaded .env"
else
    echo "Warning: no .env file found"
fi

# Build client
echo "Building client..."
(cd client && ~/.bun/bin/bun build src/app.ts --outdir . 2>&1) || echo "Client build skipped"

# Start gateway (serves client + API)
echo "Starting gateway on :8080..."
(cd gateway && /home/at0x/miniconda3/bin/uvicorn gateway.app:app --host 0.0.0.0 --port 8080) &
GATEWAY_PID=$!

# Start engine listener (if Matrix env vars set)
if [ -n "$MATRIX_HOMESERVER" ] && [ -n "$MATRIX_BOT_TOKEN" ]; then
    echo "Starting engine Matrix listener..."
    (cd engine && /home/at0x/miniconda3/bin/python -m memento.matrix_listener) &
    ENGINE_PID=$!
    echo "Engine PID: $ENGINE_PID"
else
    echo "Skipping engine listener (MATRIX_HOMESERVER not set)"
fi

echo "Gateway PID: $GATEWAY_PID"
echo ""
echo "Open http://localhost:8080"
echo "Press Ctrl+C to stop"

wait
