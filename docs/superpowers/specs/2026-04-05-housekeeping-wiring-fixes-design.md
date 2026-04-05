# Housekeeping: Type Safety & Wiring Fixes

## Context

Comprehensive audit of all memento-mori components revealed 16 issues across engine, gateway, and client. This spec addresses 6 surgical fixes in the "type safety & wiring" category — small scope, high impact, no architectural changes. These unblock the subsequent client decomposition (Workstream C) and UI rework.

## Fix 1: StatusMessage Missing `activity` Field

**Problem:** `ws-messages.ts:50` defines `StatusMessage` without an `activity` field, but `app.ts:250` accesses `msg.activity` and passes it to `setActivity()`. TypeScript doesn't catch this because the message handler uses a loose type.

**Fix:** Add `activity?: string` to the `StatusMessage` interface in `client/src/types/ws-messages.ts`.

**Files:** `client/src/types/ws-messages.ts`

## Fix 2: Map Card → Codex Click

**Problem:** Clicking an entity in the narrative panel opens the codex (via `narrative-entity-click` custom event dispatched in `text-renderer.ts`, handled in `app.ts:564-567`). But clicking an entity card in the map proximity panel does nothing — the card renderer doesn't dispatch the same event.

**Fix:** In the map card click handler, dispatch `narrative-entity-click` with the entity name/id. The existing codex handler in `app.ts` picks it up — no new wiring needed.

**Files:** `client/src/map/card-renderer.ts` or `client/src/map/renderer.ts` (whichever handles card click)

## Fix 3: Quest Persistence — player_name → UUID

**Problem:** Quest lookup uses `player_name` for KG text search instead of player UUID. This violates the project convention ("always use UUIDs, never names") and can return wrong results on name collisions.

**Fix:** Find `query_active_quests` (or equivalent) in the engine, change to UUID-based lookup using `get_entity(uuid)` or edge traversal from the player entity UUID.

**Files:** Engine quest-related code (likely `engine/src/memento/` quest flow or state restoration)

## Fix 4: Entity Art Cache Initialization

**Problem:** When a player enters a location, `state_update` delivers `location.items` but ground items may not have `ascii_art` populated. The `roomMap.items` may have art from prior scene_art messages, but this isn't merged into `location.items`.

**Fix:** In the `app.ts` state_update handler, after updating `gameState.location.items`, cross-reference with `gameState.roomMap.items` (or the art cache) and copy any cached `ascii_art` to matching items by UUID.

**Files:** `client/src/app.ts` (state_update handler)

## Fix 5: Wire `episode_feed` WebSocket Type

**Problem:** The chronicle system (just implemented) sends `episode_feed` WS messages, but the client doesn't define the type or handle it.

**Fix:**
1. Add `EpisodeFeedMessage` to the discriminated union in `ws-messages.ts`:
   ```typescript
   interface EpisodeFeedMessage {
     type: 'episode_feed';
     episode_uuid: string;
     agent_id: string;
     name: string;
     summary: string;
     location: string;
     timestamp: string;
   }
   ```
2. Add handler in `app.ts` `handleMessage()` — route to events feed panel as a system-style block:
   ```typescript
   case 'episode_feed':
     eventsFeed.addBlock(`[Chronicle] ${msg.name}: ${msg.summary}`, 'event');
     break;
   ```

**Files:** `client/src/types/ws-messages.ts`, `client/src/app.ts`

## Fix 6: Codex Relationships

**Problem:** The codex modal has a CONNECTIONS section (lines 636-691 of `codex-modal.ts`) that renders relationships, but the API never populates the `relationships` field. The `CodexRelationship` type is defined, the rendering code exists, but no data flows through.

**Fix:** In `gateway/routes/codex.py`, when assembling entity data for the codex response, fetch edges for each entity from the KG. Populate the `relationships` field as:
```python
relationships = []
for edge in entity_edges:
    relationships.append({
        "source": edge.get("source_name", ""),
        "target": edge.get("target_name", ""),
        "relationship": edge.get("name", ""),
        "fact": edge.get("fact", ""),
    })
```

Use the existing KG neighbor/edge query that the `/api/entity/{id}/neighbors` endpoint already uses. Keep it lightweight — limit to 10 relationships per entity to avoid slow responses.

**Files:** `gateway/src/gateway/routes/codex.py`

## Verification

1. **StatusMessage:** TypeScript compiles without errors on `msg.activity` access
2. **Map card click:** Click entity in map proximity → codex opens with that entity selected
3. **Quest UUID:** Active quests load correctly after session join (no false matches)
4. **Entity art:** Enter a location with items → items show cached art immediately
5. **Episode feed:** Trigger a narrator cycle → `[Chronicle]` message appears in events feed
6. **Codex relationships:** Open codex → select entity → CONNECTIONS section shows edges from KG
