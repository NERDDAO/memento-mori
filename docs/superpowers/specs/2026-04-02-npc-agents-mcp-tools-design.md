# NPC Agents as Autonomous Actors — Engine Crews as MCP Tools

## Overview

Transform NPCs from engine-puppeted voices into autonomous Bonfires AI agents on Matrix. The engine's CrewAI crews become MCP tools that NPC agents call when they need game mechanics resolved. The engine focuses on environment narration and world generation only.

## Architecture

NPCs are Bonfires agents on Matrix. They read every message in their room, respond when tagged, and call engine tools for mechanics. The engine posts environment narration and tags NPCs to cue reactions. It never speaks as an NPC.

## Key Design Decisions

### State Consistency
- Tool results return authoritative entity state (HP, effects, inventory) — NPCs never cache state
- `mm_get_state` tool lets NPCs check their own condition from the KG before responding
- NPC system prompt: "Always call mm_get_state first. Never assume numbers."

### Turn Flow (Matrix Room as Turn System)
- Players post actions, some tagging NPCs
- Tagged NPCs respond (calling tools as needed)
- Engine posts environment narration, tagging relevant NPCs as cues
- Cued NPCs respond to environment
- Engine waits for next player message (ignores bot messages)

### Onchain Capability Gating
- Capabilities table onchain (MUD) gates which tools each NPC can call
- Capabilities earned through quests, events, narrative progression
- Gateway checks chain before executing Tier 2/3 tools
- Anyone reconstructing from chain gets same capability set

### Tool Set (30 tools)
- Tier 1 (innate, 8): reads, pure functions — no check
- Tier 2 (basic capabilities, 9): KG writes — checked onchain
- Tier 3 (advanced, 12): crew-powered — checked onchain + rate limited
- Plus `mm_grant_capability` for the engine to unlock tools

### Chain + KG Dual-Write
- Every world mutation dual-writes to KG and Redstone
- Chain write is fire-and-forget (existing `tools/chain.py`)
- NPC world-building (forge items, discover locations) flows to chain automatically

### Files Changed
- `gateway/src/gateway/routes/engine.py` — new, 30 endpoints
- `gateway/src/gateway/app.py` — register engine router
- `contracts/packages/contracts/mud.config.ts` — add Capabilities table
- `contracts/packages/contracts/src/systems/CapabilitySystem.sol` — new system
- `engine/src/memento/matrix_listener.py` — environment-only narration
- `engine/src/memento/crews/narrative/narration/crew.py` — exclude NPC dialogue
- `scripts/seed-engine-tools.py` — MongoDB HttpToolProvider seed

See full plan at `/home/at0x/.claude/plans/fancy-seeking-plum.md`
