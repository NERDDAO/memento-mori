#!/bin/bash
# Initialize Synapse homeserver for Memento Mori.
# Run once after first `docker compose up`.
#
# Usage:
#   ./scripts/init-synapse.sh
#
# Requires MATRIX_DOMAIN and a running synapse container.

set -e

DOMAIN="${MATRIX_DOMAIN:-localhost}"
SYNAPSE_CONTAINER="${SYNAPSE_CONTAINER:-memento-mori-synapse-1}"
NARRATOR_PASSWORD="${NARRATOR_PASSWORD:-$(openssl rand -hex 16)}"

echo "=== Memento Mori — Synapse Init ==="
echo "Domain: $DOMAIN"
echo ""

# 1. Generate config if not present
if ! docker exec "$SYNAPSE_CONTAINER" test -f /data/homeserver.yaml 2>/dev/null; then
    echo "Generating Synapse config..."
    docker run --rm \
        -v memento-mori_synapse_data:/data \
        -e SYNAPSE_SERVER_NAME="$DOMAIN" \
        -e SYNAPSE_REPORT_STATS=no \
        matrixdotorg/synapse:latest generate
    echo "Config generated."
fi

# 2. Register narrator bot (admin user)
echo "Registering narrator bot..."
docker exec "$SYNAPSE_CONTAINER" register_new_matrix_user \
    -u narrator \
    -p "$NARRATOR_PASSWORD" \
    -a \
    -c /data/homeserver.yaml 2>/dev/null || echo "Narrator already exists (OK)"

# 3. Get access token for narrator
echo "Getting narrator access token..."
TOKEN=$(curl -s -X POST "http://localhost:8008/_matrix/client/v3/login" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"m.login.password\",\"user\":\"narrator\",\"password\":\"$NARRATOR_PASSWORD\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -n "$TOKEN" ]; then
    echo ""
    echo "=== Add to .env ==="
    echo "MATRIX_BOT_TOKEN=$TOKEN"
    echo "MATRIX_DOMAIN=$DOMAIN"
    echo ""
else
    echo "WARNING: Could not get access token. Synapse may not be running yet."
    echo "Start synapse first: docker compose up synapse -d"
    echo "Then re-run this script."
fi

echo "Done."
