# Client Remaining Fixes — C2, C3, C4

## Context

Three remaining items from Workstream C after the app.ts decomposition.

## C2: Entity Sync Helper

**Problem:** Position updates, entity art caching, and NPC join/leave all manually sync data between `gameState.location` entities and `gameState.roomMap` entities. Three copy-paste dual-write blocks in message-handler.ts.

**Fix:** Add a `syncEntityField(gameState, entityId, field, value)` utility in `state/game-state.ts`. The three dual-write sites call this instead of hand-rolling the sync. Each call updates both `location.npcs/items` and `roomMap.npcs/items` in one place.

**Files:** `client/src/state/game-state.ts`, `client/src/message-handler.ts`

## C3: Error Display for Failed Actions

**Problem:** `sendAction` in `session.ts` is fire-and-forget — no response check, no error handling. Failed actions are silently dropped.

**Fix:** Add try/catch and response status check to `sendAction`. Accept an optional `onError` callback set via `setErrorHandler`. On failure, call it with a user-facing message. `app.ts` wires the handler to `eventsFeed.addBlock(msg, 'error')`.

**Files:** `client/src/state/session.ts`, `client/src/app.ts`

## C4: NPC Name Click Opens Dialogue

**Problem:** The dialogue modal (`createDialog`) exists and works for quests but is never triggered from NPC narrative messages.

**Fix:** NPC names in the narrative are already styled as `npc-name` blocks. When the message-handler processes an NPC message, store the last message per NPC in a map. Add a click handler on the narrative canvas: when a user clicks an NPC name block, dispatch `npc-dialogue-click` event. `app.ts` (or hotkeys.ts) handles it by calling `npcDialog.show(npcName, '', lastMessage)`.

**Files:** `client/src/message-handler.ts` (store last NPC message), `client/src/panels/narrative.ts` (NPC name click detection), `client/src/app.ts` or `client/src/hotkeys.ts` (wire dialog)

## Verification

1. **C2:** Position update, entity art, and NPC join messages update both location and roomMap entities via the sync helper
2. **C3:** Submit an action when gateway is down → error message appears in events feed
3. **C4:** Click an NPC name in the narrative → dialog opens with their last message
