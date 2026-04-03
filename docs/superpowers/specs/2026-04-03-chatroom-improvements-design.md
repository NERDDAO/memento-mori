# Chatroom Improvements Design

Three interconnected features improving how Memento Mori handles chatrooms: structured message channels via Matrix threads, a full terminal-aesthetic UI powered by Pretext canvas rendering, and a CrewAI crew that generates ASCII art for scenes and entities.

## Context

The game currently sends all message types (narrative prose, phase markers, player actions, NPC dialogue, event summaries) into a single flat Matrix room per location. The client renders panels as HTML DOM with Pretext used only for text measurement. There is no visual illustration — the game is pure text. These three features address those gaps and interact: the channel structure determines what content goes where, the terminal surface renders it all as monospace text, and the ASCII art crew feeds visual content into that surface.

## Feature 1: Matrix Room Topics (Metadata Channels → MSC3440 Threads)

### Phase 1 — Metadata Channels

Add a `channel` field to all `com.bonfires.rpg` custom metadata on Matrix messages. Three channels: `narrative`, `events`, `ooc`.

**Message routing:**

| Source | Channel | Examples |
|--------|---------|----------|
| Narration crew | `narrative` | GM prose, scene descriptions |
| NPC agents (`@bonfires-*`) | `narrative` | NPC dialogue, reactions |
| ASCII art crew | `narrative` | Scene/entity art |
| `emit_phase()` | `events` | Phase markers (resolving, npc_response, ready) |
| Engine event resolution | `events` | Combat damage, item pickups, quest updates, faction changes |
| `player-action-batch` | `events` | Batched player actions |
| Player chat (no IC prefix) | `ooc` | Out-of-character messages |

**Key rule:** NPC agents (Bonfires AI) only post to `narrative`. When their MCP tool calls produce mechanical results (damage, item transfers, reputation changes), the engine writes those to `events`. Agents never write to `events` directly.

**Files to modify:**

- `engine/src/memento/round_controller.py` — add `channel: "events"` to `emit_phase()` content dict, `channel: "narrative"` to narrative output
- `engine/src/memento/matrix_listener.py` — add `channel: "narrative"` when posting narration crew output, `channel: "events"` when posting event resolution results
- `gateway/src/gateway/matrix_bridge.py` — extract `channel` from `rpg_meta` and include in WebSocket broadcast payload. Tag `@bonfires-*` NPC messages with `channel: "narrative"`
- `gateway/src/gateway/round_callback.py` — add `channel: "events"` to `player-action-batch` metadata
- `client/src/app.ts` — route `msg.channel` to appropriate panel (narrative panel, event feed, OOC overlay)

### Phase 2 — MSC3440 Threads (future)

Upgrade to real Matrix threads for persistence and native Matrix client visibility.

- On room creation, send 3 thread root events with `com.bonfires.rpg.type: "thread_root"` and `thread_name` field
- Store thread root event IDs in `MatrixBridge.location_threads: dict[str, dict[str, str]]`
- All subsequent messages include `m.relates_to: {"rel_type": "m.thread", "event_id": thread_root_id}`
- Room discovery (`_discover_rooms`) scans timeline for `thread_root` markers to repopulate cache
- The `channel` metadata field determines which thread a message belongs to — both systems compose

## Feature 2: Full Pretext Terminal Surface (Hybrid Canvas Panels)

Convert all client panels below the header into canvas-rendered monospace text. CSS grid handles layout, each panel's `<canvas>` handles rendering. The header bar, input element, and status bar remain as HTML.

### Architecture

**New abstraction — `TerminalPanel`:**
- Wraps a `<canvas>` inside a `createWindow()` body
- Provides `paint(cells: CharCell[][])` for rendering a 2D character grid
- Maintains a hit-test map for clickable regions: `{x, y, w, h, entityId, entityType}[]`
- Diffs against previous frame, only repaints changed cells

**`CharCell` type:**
```typescript
interface CharCell {
  char: string;    // single character
  fg: string;      // foreground color
  bg?: string;     // optional background color
  attrs?: number;  // bitmask: bold, italic, underline
}
```

**Shared canvas utilities** — extract from `card-renderer.ts` into new `renderer/canvas-text.ts`:
- `drawText(ctx, text, x, y, style)` — draw styled text at character coordinates
- `drawBox(ctx, x, y, w, h, style)` — draw box-drawing character frame
- `measureChar(ctx)` — get monospace character cell dimensions
- Box-drawing character constants and color palette mapping from theme

**Window chrome:**
- Title bars rendered as box-drawing characters on the canvas: `┌─ INVENTORY ─┐`
- Matches existing `card-renderer` aesthetic

**Entity interaction:**
- Per-panel hit-test map updated on each paint
- Canvas click handler does point-in-rect lookup
- Opens wiki panel same as current `entity-link` click delegation

**Narrative panel (hardest):**
- Virtual scroll stays conceptually the same — `NarrativeStore` provides block positions via Pretext measurement
- Instead of inserting DOM nodes, visible blocks are painted to canvas
- `StyledSegment[]` from `text-renderer.ts` map to `CharCell` fg colors
- Mouse wheel adjusts `scrollOffset`, triggers repaint

**Input:** Stays as a real HTML `<input>` element below the canvas grid. Status bar stays as HTML.

**Scroll:** Mouse wheel events on a panel's canvas region adjust that panel's `scrollOffset` and trigger repaint. Keyboard PageUp/PageDown scroll the focused panel.

### Migration Order

1. Character panel (simplest — static text, health bar)
2. Inventory panel (list rendering with rarity colors)
3. Exits panel (clickable direction list)
4. Present panel (NPC + player list)
5. Quest panel (list with stages)
6. Factions panel (reputation bars)
7. Narrative panel (virtual scroll + styled segments + entity links)

### Key Files

- `client/src/map/card-renderer.ts` — reference pattern, extract shared utilities
- `client/src/ui/window.ts` — modify to support canvas-backed window bodies
- `client/src/renderer/line-cache.ts` — adapt `NarrativeStore` for canvas rendering
- `client/src/renderer/text-renderer.ts` — output stays as `StyledSegment[]`, consumed by canvas painter instead of `renderSegments()` HTML
- New: `client/src/renderer/canvas-text.ts` — shared canvas text drawing utilities
- New: `client/src/ui/terminal-panel.ts` — `TerminalPanel` abstraction

## Feature 3: ASCII Art CrewAI Crew

A new CrewAI crew that generates ASCII art for location scenes and entity portraits. Art is cached in the KG, generated asynchronously, and delivered to the client via WebSocket.

### Crew Structure

**Directory:** `engine/src/memento/crews/ascii_art/`

**Two factory functions:**

- `make_scene_art_crew(location_name, description, mood, width=35, height=20)` — large atmospheric scene art for location headers
- `make_entity_art_crew(entity_name, entity_type, description, width=20, height=12)` — compact character portraits and item art

**Agents (adversarial pair):**

1. **ASCII Artist** — generates the art. System prompt specifies:
   - Exact dimension constraints ("exactly N characters wide, exactly M lines tall")
   - Allowed character palette: `#.:|/\-_~^*@!?+'"` and box-drawing characters
   - Composition rules (border lines, title banner placement)
   - 2-3 inline examples of dark fantasy ASCII art
   - Style direction from `config.yaml` game tone

2. **Art Critic** — reviews and rejects/requests revision. Evaluates:
   - Dimensional compliance (correct width/height)
   - Atmospheric quality (does it evoke the scene/entity?)
   - Readability (can you tell what it is at a glance?)
   - Character palette discipline (no out-of-set chars)
   - Provides specific, actionable feedback for revision

**Tasks (sequential CrewAI process):**

1. `generate_task` — Artist generates ASCII art from the description/mood
2. `critique_task` — Critic evaluates the art, returns "approved" or specific revision feedback (context: `generate_task`)
3. `revise_task` — Artist revises based on Critic feedback (context: `critique_task`). Skipped if Critic approved on first pass
4. `final_review_task` — Critic does final evaluation (context: `revise_task`)

Max 2 revision rounds (4 tasks total). The `validate_art()` tool runs after the Critic's final approval as a mechanical dimension/palette check. If validation fails, output is padded/trimmed to fit rather than re-entering the crew loop.

### Validation

**Tool:** `@tool validate_art(art_text, expected_width, expected_height)` in `engine/src/memento/tools/art_validation.py`
- Checks line count matches expected height
- Checks each line width matches expected width (padded or trimmed)
- Validates character palette
- Returns pass/fail with specific errors
- Crew retries once on failure, then accepts best effort

### Caching

Art stored as `ascii_art` property on Location/NPC/Item entities in the KG via existing `kg.py` tools. Once generated, art persists across sessions.

### Generation Timing

Async and non-blocking:
- **Scene art:** When a player enters a location, if no cached art exists on the Location entity, fire a background task. Art arrives as a separate WebSocket message seconds later.
- **Entity art:** On first examine action for an NPC or item, if no cached art exists.
- Art generation does NOT block the round pipeline.

### Integration

- New method `request_art(location, description)` on `RoundController` — spawns the crew in a background thread via `asyncio.to_thread`
- Called after `narrate()` if the location has no cached `ascii_art` property
- Examine actions trigger entity art via a new handler in `matrix_listener.py`
- Model config: add `ascii_art` entry to `models.yaml` (can use a cheaper/faster model)

### Delivery

New WebSocket message types:
- `{"type": "scene_art", "location": "...", "lines": [...], "width": 35, "height": 20}`
- `{"type": "entity_art", "entity_id": "...", "name": "...", "lines": [...], "width": 20, "height": 12}`

Art messages posted to Matrix get `channel: "narrative"` — they're visual content, not mechanical events.

### New Files

- `engine/src/memento/crews/ascii_art/__init__.py`
- `engine/src/memento/crews/ascii_art/crew.py`
- `engine/src/memento/tools/art_validation.py`
- Update `engine/src/memento/config/models.yaml`
- Update `engine/src/memento/round_controller.py`
- Update `engine/src/memento/models/state_update.py` — add art fields

## Delivery Order

1. **Phase 1 — Metadata Channels** (F1 phase 1): Lowest risk, enables client-side routing. ~100 lines across 4 files.
2. **Phase 2 — Terminal Surface** (F2): Incremental panel-by-panel migration. Extract shared canvas utilities, convert panels in order of complexity.
3. **Phase 3 — ASCII Art Crew** (F3): New crew following existing patterns. Renders into the terminal surface built in Phase 2.
4. **Phase 4 — MSC3440 Threads** (F1 phase 2): Matrix-native thread structure. Upgrades metadata channels to real threads.

## Risk Areas

1. **Pretext canvas rendering performance** — narrative panel with hundreds of styled segments needs to stay under 16ms/frame. Existing `line-cache.ts` reports ~0.09ms/500 texts for layout, which is encouraging.
2. **nio thread support** — `matrix-nio` may not have first-class MSC3440 support. Raw `room_send()` with manual `m.relates_to` should work. This is why metadata channels come first.
3. **LLM ASCII art quality** — inconsistent by nature. Validation tool + retry mitigates. Cap retries at 2, accept best effort.
4. **Canvas hit testing** — narrative panel entity links need a spatial index of clickable regions. New infrastructure not in `card-renderer.ts` today.
5. **Keyboard focus routing** — multiple canvas panels need a focus manager for scroll/keyboard events. Currently only one input element exists.

## Verification

- **F1**: Send a player action, verify narrative and phase messages arrive on client with correct `channel` values. Check OOC messages route separately.
- **F2**: For each migrated panel, verify visual parity with current HTML rendering. Test entity clicks open wiki. Test scroll in narrative panel.
- **F3**: Generate scene art for a test location, verify it arrives via WebSocket with correct dimensions. Check KG caching (second visit should use cached art). Verify entity art on examine.
