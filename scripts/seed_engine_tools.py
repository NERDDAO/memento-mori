#!/usr/bin/env python3
"""Seed the memento-engine HttpToolProvider in MongoDB.

Usage:
    python scripts/seed_engine_tools.py

Requires MONGO_URI env var pointing to the Bonfires MongoDB.
"""

import os
import sys
from pymongo import MongoClient

PROVIDER = {
    "providerId": "memento-engine",
    "providerName": "Memento Mori Game Engine",
    "description": "Game mechanics tools for NPC agents — combat, skill checks, world queries, world building",
    "enabled": True,
    "baseConfig": {
        "baseUrl": "{{env:MEMENTO_GATEWAY_URL}}",
        "headers": {"Content-Type": "application/json"},
        "auth": {
            "type": "bearer",
            "keyName": "Authorization",
            "valueTemplate": "Bearer {{env:ENGINE_API_TOKEN}}",
        },
        "defaultTimeout": 60000,
    },
    "tools": [
        # Tier 1 — State & Knowledge
        {
            "id": "mm_get_state", "name": "Get Entity State",
            "description": "Get an entity's current state from the knowledge graph — HP, inventory, labels, edges, recent events. Call this before responding to check your current condition.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/state", "method": "POST",
                           "bodyTemplate": {"entity_name": "{{entity_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "entity_name": {"type": "string", "description": "Entity name to look up"}
            }, "required": ["entity_name"]},
        },
        {
            "id": "mm_get_world_time", "name": "Get World Time",
            "description": "Get current in-game time — moon phase, date, time of day, season.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/time", "method": "GET"},
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "id": "mm_search_world", "name": "Search World",
            "description": "Search the game world's knowledge graph for entities, locations, NPCs, items, relationships, and lore.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/search", "method": "POST",
                           "bodyTemplate": {"query": "{{query}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"}
            }, "required": ["query"]},
        },
        {
            "id": "mm_get_entity", "name": "Get Entity Details",
            "description": "Get detailed information about a specific game entity by name.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/world/entity", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string", "description": "Entity name"}
            }, "required": ["name"]},
        },
        {
            "id": "mm_skill_check", "name": "Roll Skill Check",
            "description": "Roll a d20 skill check. Returns PASS or FAIL with margin. Use for persuasion, stealth, lockpicking, any non-combat check.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/skill-check", "method": "POST",
                           "bodyTemplate": {"skill_level": "{{skill_level}}", "difficulty": "{{difficulty}}", "modifiers": "{{modifiers}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "skill_level": {"type": "number", "description": "Skill level (0-30)"},
                "difficulty": {"type": "number", "description": "Difficulty class (1-40)"},
                "modifiers": {"type": "number", "description": "Situational modifier", "default": 0},
            }, "required": ["skill_level", "difficulty"]},
        },
        {
            "id": "mm_calculate_damage", "name": "Calculate Damage",
            "description": "Calculate final damage from weapon damage, strength, and armor.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/damage", "method": "POST",
                           "bodyTemplate": {"weapon_damage": "{{weapon_damage}}", "attacker_strength": "{{attacker_strength}}", "defender_armor": "{{defender_armor}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "weapon_damage": {"type": "number"}, "attacker_strength": {"type": "number"}, "defender_armor": {"type": "number"},
            }, "required": ["weapon_damage", "attacker_strength", "defender_armor"]},
        },
        {
            "id": "mm_evaluate_disposition", "name": "Evaluate Disposition",
            "description": "Calculate how an interaction shifts friendship and trust.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/disposition", "method": "POST",
                           "bodyTemplate": {"current_friendship": "{{current_friendship}}", "current_trust": "{{current_trust}}", "interaction_type": "{{interaction_type}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "current_friendship": {"type": "number"}, "current_trust": {"type": "number"},
                "interaction_type": {"type": "string", "enum": ["friendly_conversation", "hostile_action", "gift", "betrayal", "help_in_combat", "theft", "trade"]},
            }, "required": ["current_friendship", "current_trust", "interaction_type"]},
        },
        # Tier 2 — World Mutation
        {
            "id": "mm_remember_event", "name": "Remember Event",
            "description": "Record a significant event in the world's memory. Use for deaths, discoveries, betrayals, victories. The world will remember this.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/remember", "method": "POST",
                           "bodyTemplate": {"summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "What happened"}
            }, "required": ["summary"]},
        },
        {
            "id": "mm_update_entity", "name": "Update Entity",
            "description": "Update an entity's summary or labels in the knowledge graph.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/update-entity", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "new_summary": "{{new_summary}}", "new_labels": "{{new_labels}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "new_summary": {"type": "string"}, "new_labels": {"type": "string"},
            }, "required": ["name"]},
        },
        {
            "id": "mm_give_item", "name": "Give Item",
            "description": "Transfer an item from one entity to another. Use for quest rewards, trades, theft.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/give-item", "method": "POST",
                           "bodyTemplate": {"item_name": "{{item_name}}", "from_entity": "{{from_entity}}", "to_entity": "{{to_entity}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "item_name": {"type": "string"}, "from_entity": {"type": "string"}, "to_entity": {"type": "string"},
            }, "required": ["item_name", "from_entity", "to_entity"]},
        },
        {
            "id": "mm_give_quest", "name": "Give Quest",
            "description": "Create a quest and assign it to a player.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/give-quest", "method": "POST",
                           "bodyTemplate": {"quest_name": "{{quest_name}}", "description": "{{description}}", "giver_name": "{{giver_name}}", "player_name": "{{player_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "quest_name": {"type": "string"}, "description": {"type": "string"},
                "giver_name": {"type": "string"}, "player_name": {"type": "string"},
            }, "required": ["quest_name", "description", "giver_name", "player_name"]},
        },
        {
            "id": "mm_create_npc", "name": "Create NPC",
            "description": "Create a new NPC entity in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-npc", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "NPC", "summary": "{{summary}}", "location_name": "{{location_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"}, "location_name": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_create_item", "name": "Create Item",
            "description": "Create a new item in the world. Use for crafting, forging, finding.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-item", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "Item", "summary": "{{summary}}", "location_name": "{{location_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"}, "location_name": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_create_location", "name": "Create Location",
            "description": "Discover or build a new location in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/create-location", "method": "POST",
                           "bodyTemplate": {"name": "{{name}}", "entity_type": "Location", "summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "name": {"type": "string"}, "summary": {"type": "string"},
            }, "required": ["name", "summary"]},
        },
        {
            "id": "mm_move_to", "name": "Move To Location",
            "description": "Move to a different location in the world.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/move", "method": "POST",
                           "bodyTemplate": {"entity_name": "{{entity_name}}", "destination": "{{destination}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "entity_name": {"type": "string"}, "destination": {"type": "string"},
            }, "required": ["entity_name", "destination"]},
        },
        {
            "id": "mm_send_gossip", "name": "Send Gossip",
            "description": "Send a message to another NPC. Creates organic information flow between NPCs.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/world/gossip", "method": "POST",
                           "bodyTemplate": {"from_npc": "{{from_npc}}", "to_npc": "{{to_npc}}", "message": "{{message}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "from_npc": {"type": "string"}, "to_npc": {"type": "string"}, "message": {"type": "string"},
            }, "required": ["from_npc", "to_npc", "message"]},
        },
        # Tier 3 — Crew-Powered
        {
            "id": "mm_resolve_combat", "name": "Resolve Combat",
            "description": "Execute full combat resolution: assess, resolve attack/ability, apply consequences, check death. Returns complete outcome with authoritative entity states.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/combat/resolve", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "attacker": "{{attacker}}", "target": "{{target}}", "location": "{{location}}", "context": "{{context}}", "attacker_stats": "{{attacker_stats}}", "target_stats": "{{target_stats}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "attacker": {"type": "string"}, "target": {"type": "string"},
                "location": {"type": "string"}, "context": {"type": "string"},
                "attacker_stats": {"type": "string"}, "target_stats": {"type": "string"},
            }, "required": ["action", "attacker", "target", "location"]},
        },
        {
            "id": "mm_assess_combat", "name": "Assess Combat",
            "description": "Evaluate a combat situation without resolving it.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/combat/assess", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "attacker": "{{attacker}}", "target": "{{target}}", "location": "{{location}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "attacker": {"type": "string"},
                "target": {"type": "string"}, "location": {"type": "string"},
            }, "required": ["action", "attacker", "target", "location"]},
        },
        {
            "id": "mm_check_plausibility", "name": "Check Plausibility",
            "description": "Check if an action is physically plausible in the current scene.",
            "enabled": True,
            "httpConfig": {"endpoint": "/api/engine/plausibility", "method": "POST",
                           "bodyTemplate": {"action": "{{action}}", "context": "{{context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "action": {"type": "string"}, "context": {"type": "string"},
            }, "required": ["action", "context"]},
        },
        {
            "id": "mm_design_quest", "name": "Design Quest",
            "description": "Design a morally complex quest with choices, rewards, and consequences.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/quest", "method": "POST",
                           "bodyTemplate": {"location": "{{location}}", "npc_name": "{{npc_name}}", "player_level": "{{player_level}}", "active_quests": "{{active_quests}}", "faction_context": "{{faction_context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location": {"type": "string"}, "npc_name": {"type": "string"},
                "player_level": {"type": "number", "default": 1},
                "active_quests": {"type": "string"}, "faction_context": {"type": "string"},
            }, "required": ["location", "npc_name"]},
        },
        {
            "id": "mm_design_item", "name": "Design Item",
            "description": "Design thematically appropriate items with stats and lore.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/item", "method": "POST",
                           "bodyTemplate": {"location_name": "{{location_name}}", "rarity_budget": "{{rarity_budget}}", "num_items": "{{num_items}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location_name": {"type": "string"}, "rarity_budget": {"type": "string", "default": "common"},
                "num_items": {"type": "number", "default": 1},
            }, "required": ["location_name"]},
        },
        {
            "id": "mm_design_npc", "name": "Design NPC",
            "description": "Design a full NPC with personality, stats, and backstory.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/npc", "method": "POST",
                           "bodyTemplate": {"role": "{{role}}", "location_name": "{{location_name}}", "region_context": "{{region_context}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "role": {"type": "string"}, "location_name": {"type": "string"}, "region_context": {"type": "string"},
            }, "required": ["role", "location_name"]},
        },
        {
            "id": "mm_design_location", "name": "Design Location",
            "description": "Design a full location with tile map, secrets, and atmosphere.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/location", "method": "POST",
                           "bodyTemplate": {"location_plan": "{{location_plan}}", "region_name": "{{region_name}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "location_plan": {"type": "string"}, "region_name": {"type": "string"},
            }, "required": ["location_plan", "region_name"]},
        },
        {
            "id": "mm_design_region", "name": "Design Region",
            "description": "Design an entire region with biome, culture, threats, and locations.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/design/region", "method": "POST",
                           "bodyTemplate": {"theme": "{{theme}}", "adjacent_regions": "{{adjacent_regions}}", "player_level": "{{player_level}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "theme": {"type": "string"}, "adjacent_regions": {"type": "string"},
                "player_level": {"type": "number", "default": 1},
            }, "required": ["theme"]},
        },
        {
            "id": "mm_npc_memory", "name": "NPC Memory",
            "description": "Record a first-person memory of a scene from your perspective.",
            "enabled": True, "accessCategory": "write",
            "httpConfig": {"endpoint": "/api/engine/npc-memory", "method": "POST",
                           "bodyTemplate": {"summary": "{{summary}}", "npc_id": "{{context:agentId}}"}},
            "inputSchema": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "Your first-person memory of what happened"},
            }, "required": ["summary"]},
        },
    ],
}


def main():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "bonfires_staging")
    if not mongo_uri:
        print("Error: MONGO_URI not set")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["httptoolproviders"]

    # Upsert by providerId
    result = collection.update_one(
        {"providerId": PROVIDER["providerId"]},
        {"$set": PROVIDER},
        upsert=True,
    )

    if result.upserted_id:
        print(f"Created HttpToolProvider: {PROVIDER['providerId']} ({len(PROVIDER['tools'])} tools)")
    else:
        print(f"Updated HttpToolProvider: {PROVIDER['providerId']} ({len(PROVIDER['tools'])} tools)")

    client.close()


if __name__ == "__main__":
    main()
