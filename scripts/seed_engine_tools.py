#!/usr/bin/env python3
"""Seed the memento-engine McpTool configuration in MongoDB.

Replaces the old HttpToolProvider seed with an McpTool document that
bonfires-ai consumes via MultiServerMCPClient.  Also deletes the legacy
HttpToolProvider doc so tools aren't loaded twice.

Usage:
    python scripts/seed_engine_tools.py [--dry-run]

Requires MONGO_URI env var pointing to the Bonfires MongoDB.
"""

import os
import sys
import json
import argparse
from pymongo import MongoClient

MCP_TOOL = {
    "id": "memento-engine",
    "name": "Memento Mori Game Engine",
    "description": "Game mechanics tools for NPC agents — combat, skill checks, world queries, world building",
    "type": "http",
    "url": "{{env:MEMENTO_GATEWAY_URL}}/mcp",
    "apiKey": "{{env:ENGINE_API_TOKEN}}",
    "enabled": True,
    "toolSettings": {
        "allowedTools": [
            # --- read / neutral tools ---
            "mm_get_state",
            "mm_get_world_time",
            "mm_search_world",
            "mm_get_entity",
            "mm_skill_check",
            "mm_calculate_damage",
            "mm_evaluate_disposition",
            "mm_assess_combat",
            "mm_check_plausibility",
            "mm_inventory",
            "mm_npc_response",
            # --- write tools ---
            "mm_remember_event",
            "mm_update_entity",
            "mm_give_item",
            "mm_give_quest",
            "mm_create_npc",
            "mm_create_item",
            "mm_create_location",
            "mm_move_to",
            "mm_send_gossip",
            "mm_resolve_combat",
            "mm_design_quest",
            "mm_design_item",
            "mm_design_npc",
            "mm_design_location",
            "mm_design_region",
            "mm_npc_memory",
            "mm_inventory_transfer",
            "mm_heartbeat",
            "mm_world_reaction",
            "mm_narrate",
            "mm_trigger_npc",
            "mm_move_within",
            # --- new MCP-only tools (read-only stubs) ---
            "mm_room_manifest",
            "mm_reputation",
            "mm_detect_events",
        ],
        "contextMappings": {
            "*": {"npc_id": "agentId"},
        },
        "writeTools": [
            "mm_remember_event",
            "mm_update_entity",
            "mm_give_item",
            "mm_give_quest",
            "mm_create_npc",
            "mm_create_item",
            "mm_create_location",
            "mm_move_to",
            "mm_send_gossip",
            "mm_resolve_combat",
            "mm_design_quest",
            "mm_design_item",
            "mm_design_npc",
            "mm_design_location",
            "mm_design_region",
            "mm_npc_memory",
            "mm_inventory_transfer",
            "mm_heartbeat",
            "mm_world_reaction",
            "mm_narrate",
            "mm_trigger_npc",
            "mm_move_within",
        ],
        "defaultTimeout": 60000,
    },
}

OLD_PROVIDER_ID = "memento-engine"


def main():
    parser = argparse.ArgumentParser(
        description="Seed memento-engine McpTool config in MongoDB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the McpTool document to stdout instead of writing to Mongo",
    )
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps(MCP_TOOL, indent=2))
        return

    uri = os.getenv("MONGO_URI")
    if not uri:
        print("Error: MONGO_URI env var not set", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(uri)
    db = client.get_default_database()

    # Delete old HttpToolProvider doc so bonfires-ai doesn't load tools twice
    result = db.httptoolproviders.delete_many({"providerId": OLD_PROVIDER_ID})
    print(
        f"Deleted {result.deleted_count} HttpToolProvider doc(s) "
        f"with providerId={OLD_PROVIDER_ID!r}"
    )

    # Upsert new McpTool doc
    result = db.mcptools.replace_one(
        {"id": MCP_TOOL["id"]}, MCP_TOOL, upsert=True
    )
    if result.upserted_id:
        print(f"Inserted McpTool doc: id={MCP_TOOL['id']!r}")
    else:
        print(
            f"Updated McpTool doc: id={MCP_TOOL['id']!r} "
            f"(matched={result.matched_count})"
        )

    client.close()


if __name__ == "__main__":
    main()
