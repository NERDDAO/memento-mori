#!/usr/bin/env bash
# scripts/issue_npc_jwts.sh
#
# Mint JWTs for every registered NPC by calling the gateway's admin
# endpoint, and print ready-to-run commands for bonfires-ai's
# seed-agent-env-vars.ts to write them into the field-encrypted
# ``agentenvvars`` collection.
#
# Prerequisites:
#   - Gateway running at $MEMENTO_GATEWAY_URL (default http://localhost:8081)
#   - ENGINE_ADMIN_KEY set in the memento .env
#   - MONGO_URI reachable (for reading the NPC registry)
#
# Usage:
#   source .env
#   ./scripts/issue_npc_jwts.sh > issue_npc_jwts.out
#
# The output file is a sequence of commands you can paste into the
# bonfires-ai repo to provision each NPC's MEMENTO_JWT.

set -euo pipefail

: "${ENGINE_ADMIN_KEY:?ENGINE_ADMIN_KEY must be set (source your .env first)}"
: "${MEMENTO_GATEWAY_URL:=http://localhost:8081}"
: "${MONGO_URI:?MONGO_URI must be set}"
: "${MONGO_DB_NAME:=cannitos}"

python3 - <<'PYEOF'
import json
import os
import sys
import urllib.request
import urllib.error

try:
    from pymongo import MongoClient
except ImportError:
    print("ERROR: pymongo not installed", file=sys.stderr)
    sys.exit(1)

gateway = os.environ["MEMENTO_GATEWAY_URL"]
admin_key = os.environ["ENGINE_ADMIN_KEY"]
mongo_uri = os.environ["MONGO_URI"]
db_name = os.environ.get("MONGO_DB_NAME", "cannitos")

# Find all memento NPC agents in bonfires-ai's agentconfigs.
client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
db = client[db_name]
npcs = []
for doc in db["agentconfigs"].find({}, {"_id": 1, "name": 1, "username": 1}):
    username = doc.get("username", "")
    if username.startswith("bonfires-") or username.startswith("narrator_"):
        npcs.append({
            "agent_id": str(doc["_id"]),
            "name": doc.get("name", ""),
            "username": username,
        })

print(f"# Found {len(npcs)} NPC agents in agentconfigs", file=sys.stderr)

# Mint a JWT for each via the admin endpoint.
for npc in npcs:
    body = json.dumps({
        "npc_id": npc["agent_id"],
        "npc_name": npc["name"],
        "ttl_days": 365,
    }).encode()
    req = urllib.request.Request(
        f"{gateway}/api/admin/npc-jwt",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Api-Key": admin_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"# FAILED {npc['name']}: {e.code} {e.read().decode()}", file=sys.stderr)
        continue
    npc["jwt"] = payload["jwt"]
    # Print a bonfires-ai CLI command that sets MEMENTO_JWT for this agent.
    print(
        f"AGENT_ID={npc['agent_id']} ENV_VAR_MEMENTO_JWT={payload['jwt']} "
        f"pnpm run seed:env-vars  # {npc['name']}"
    )

client.close()
PYEOF
