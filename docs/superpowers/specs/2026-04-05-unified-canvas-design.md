# Unified Canvas Design

Replace the multi-canvas DOM panel layout with a single full-screen `<canvas>` surface. All UI regions rendered as CharCell[][] grids with box-drawing borders, one paint loop, one hit region system. BBS/retro terminal aesthetic — no DOM seams.

## Architecture Overview

One `UnifiedCanvas` class owns a single `<canvas>` filling `#tui-main`. Screen state is a 2D CharCell[][] grid. A `RegionManager` divides the grid into named regions. Panels write CharCell grids into their region. One `requestAnimationFrame` paint loop repaints dirty regions.

Two escape hatches from pure CharCell rendering:
- **Offscreen canvas compositing** for map and ASCII art viewer — they render to their own canvas, `drawImage()`'d into their region's pixel bounds.
- **Pixel-based scrolling** for narrative — Pretext-measured text painted at sub-row pixel offsets within a clipped region.

## Region Layout

```
╔══════════════════════════════════════════════════════════════════╗
║ HEADER (1 row)                                                  ║
╠═══════════╤════════════════════════════╤════════════════════════╣
║ PRESENT   │ VIEWPORT                   │ CHARACTER              ║
║ (~20ch)   │ (flexible)                 │ (~32ch)                ║
║           │ [offscreen canvas]         │                        ║
║           │                            ├────────────────────────╢
║           │                            │ INVENTORY              ║
║           │                            │                        ║
║           │                            ├────────────────────────╢
║           │                            │ QUESTS                 ║
╠═══════════╧════════════════════════════╡                        ║
║ NARRATIVE (pixel-scroll)               │ (continues)            ║
║ spans present + viewport cols          ├────────────────────────╢
║                                        │ EVENTS                 ║
╠════════════════════════════════════════╧════════════════════════╣
║ INPUT (1 row) — DOM <input> overlay                             ║
╠════════════════════════════════════════════════════════════════╣
║ STATUS (1 row)                                                  ║
╚════════════════════════════════════════════════════════════════╝
```

### Border Rules

- **Outer frame:** double-line (`╔═╗║╚╝`)
- **Inner dividers:** single-line (`─│┌┐└┘├┤`)
- **Intersections:** appropriate junction chars where single meets double (`╤╧╞╡╠╣`)

### Regions

| Region | Type | Size | Notes |
|--------|------|------|-------|
| Header | grid | 1 row, full width | Title, round info, chain status |
| Present | grid | ~20 chars wide, top zone height | NPCs, items, exits. Row-based scroll if list overflows. |
| Viewport | offscreen | Flexible width, top zone height | Map + entity cards. Own canvas composited in. |
| Character | grid | ~32 chars wide, weight 2 of sidebar | HP/XP bars, skills, archetype |
| Inventory | grid | ~32 chars wide, weight 3 of sidebar | Equipment + backpack list |
| Quests | grid | ~32 chars wide, weight 2 of sidebar | Quest entries + progress bars |
| Narrative | pixel | Spans present+viewport cols, bottom zone | Pretext-measured, virtual scroll, pixel offsets |
| Events | grid | Sidebar col width, bottom zone | Chronicle/event feed, row-based scroll. Shares the sidebar column — quests end where the bottom zone starts, events fills the rest. |
| Input | grid + DOM | 1 row, full width | Canvas draws prompt + echo, transparent `<input>` overlay |
| Status | grid | 1 row, full width | Phase timer, chain address, location breadcrumb |

## Core Types

```ts
interface Region {
  name: string;
  x: number; y: number;       // char-cell origin (within outer frame)
  w: number; h: number;       // char-cell dimensions
  type: 'grid' | 'pixel';     // grid = CharCell, pixel = offscreen/scroll
  scrollOffset?: number;       // pixels (narrative) or rows (present, events, modals)
}

interface OffscreenSlot {
  canvas: HTMLCanvasElement;
  region: string;              // which region it paints into
}

interface HitEntry {
  region: string;
  col: number; row: number;    // local to region
  width: number; height: number;
  z: number;                   // 0 = panels, 1+ = modals
  data: Record<string, any>;   // entityId, action, etc.
}
```

CharCell, CharSize, ATTR_BOLD/ITALIC/UNDERLINE — unchanged from `canvas-text.ts`.

## UnifiedCanvas Class

```
UnifiedCanvas
├── canvas: HTMLCanvasElement
├── ctx: CanvasRenderingContext2D
├── grid: CharCell[][]                 // full-screen character grid
├── regions: Map<string, Region>
├── dirtyRegions: Set<string>
├── hitRegistry: HitRegistry
├── offscreenSlots: Map<string, OffscreenSlot>
├── modalStack: ModalState[]
│
├── resize()                           // recalc grid dims + region bounds
├── setRegionContent(name, cells[][])  // panel pushes CharCell grid
├── compositeOffscreen(name, canvas)   // blit offscreen canvas into region
├── drawBorders()                      // box-drawing chars between regions
├── paint()                            // rAF: dirty regions → canvas
├── pointToRegion(x, y)               // pixel → region + local offset
│
├── openModal(name, renderFn, opts)    // push z-layer overlay
├── closeModal(name)                   // pop z-layer
└── scrollRegion(name, delta)          // adjust scroll offset
```

## RegionManager & Layout Algorithm

Layout is declarative. The RegionManager computes char-cell bounds from grid dimensions.

### Layout Definition

```ts
const LAYOUT = {
  header:     { rows: 1 },
  status:     { rows: 1 },
  input:      { rows: 1 },
  topZone:    { weight: 2 },     // 2/3 of remaining rows
  bottomZone: { weight: 1 },     // 1/3 of remaining rows
  present:    { chars: 20, min: 14 },
  viewport:   { weight: 1 },     // flexible, takes remaining width
  sidebar:    { chars: 32, min: 24 },
  character:  { weight: 2 },     // sidebar sub-region
  inventory:  { weight: 3 },
  quests:     { weight: 2 },
  narrative:  { cols: 2 },       // spans present + viewport
  events:     { cols: 1 },       // spans sidebar
};
```

### Reflow Algorithm

1. Subtract border chars: 2 for outer frame horizontally, 2 vertically, 1 per inner divider
2. Fixed rows: header(1) + input(1) + status(1) = 3, plus horizontal border rows between zones
3. Remaining rows split by weight between topZone and bottomZone
4. Fixed columns: present(20) + sidebar(32) + inner vertical dividers. Viewport gets the rest.
5. Sidebar rows split by weight among character/inventory/quests
6. All values clamped to minimums

Example at 120x40: usable ~118x38 after outer frame. Top zone ~20 rows, bottom ~10 rows. Viewport ~64 chars wide.

### Resize Flow

`ResizeObserver` on container → recalculate cols/rows → `RegionManager.reflow()` → all panels get new dimensions → mark all dirty → full repaint.

## Paint Pipeline

Runs on `requestAnimationFrame`, only touches dirty regions.

### Frame Sequence

1. Check `dirtyRegions` — skip frame if empty
2. For each dirty region:
   - **grid type:** clear region pixel bounds, `fillCell()` each CharCell at `(regionX + col, regionY + row)`
   - **pixel type (narrative):** `ctx.save()`, clip to region bounds, run `drawTextAtPixel()` with scroll offset, `ctx.restore()`
   - **offscreen slot (viewport):** `ctx.drawImage(offscreenCanvas, pixelX, pixelY, pixelW, pixelH)`
3. If borders dirty (resize only): draw all box-drawing chars
4. If modal open:
   - Dim backdrop (darken fg, set bg on cells outside modal)
   - Draw modal border (double-line)
   - Render modal CharCell[][] content
5. Render hover highlights (brighten fg + underline on hovered hit region)
6. Clear `dirtyRegions`

### Performance Notes

- Start with full region repaint. Optimize to cell-level diffing only if profiling shows need.
- Borders are static between resizes — paint once, skip on subsequent frames.
- 120x40 = 4,800 cells. Full repaint is trivial at 60fps.
- Device pixel ratio: canvas dims * dpr, `ctx.setTransform(dpr, 0, 0, dpr, 0, 0)`.

## Hit Registry

Global z-ordered hit region system replacing per-panel hit regions.

### Registration

Panels call `hitRegistry.register(region, col, row, w, h, z, data)` after rendering. Local region coords are stored; the registry translates to global canvas coords for hit testing.

### Mouse Routing

1. `click`/`mousemove` on canvas
2. Convert pixel coords to global char-cell `(col, row)`
3. Check hit registry from highest z-layer down — first match wins
4. Dispatch `CustomEvent` with `{ region, action, entityId, ... }`
5. On hover: brighten fg + add underline on hovered hit region, set `cursor: pointer`

### Wheel Events

`wheel` on canvas → `pointToRegion()` → if region is scrollable, adjust scroll offset and mark dirty.

## Modal System

Modals render as CharCell[][] overlays at z-layer 1+.

### Lifecycle

```
openModal(name, renderFn, { width: 0.7, height: 0.8 })
  → allocate centered overlay region (% of grid)
  → push to modalStack
  → dim underlying regions
  → render content + double-line border
  → register hit regions at z = modalStack.length

closeModal(name)
  → remove from modalStack
  → clear hit regions for that layer
  → mark all regions dirty
```

### Scroll Within Modals

Codex and inventory have scrollable content. Track `scrollOffset` in char rows, render only the visible window of the CharCell[][] grid. Wheel events scoped to modal region via z-layer priority.

### Backdrop Dimming

When modal is open, darken fg colors of all cells under the modal. Post-processing pass on the grid before final paint — no extra buffer.

### Stacking

Modals stack: codex (z=1) → art viewer (z=2). Only topmost layer receives mouse events. `Escape` closes topmost.

### Migrated Modals

- **Codex** (`codex-modal.ts`): two-panel entity browser → CharCell overlay with scroll
- **Dialogue** (`dialog.ts`): NPC conversation → CharCell overlay
- **Inventory Modal** (`inventory-modal.ts`): full inventory management → CharCell overlay

## Command Input

Real DOM `<input>` element positioned over the canvas input row.

```ts
input.style.position = 'absolute';
input.style.left = `${inputRegion.x * charSize.width + promptWidth}px`;
input.style.top = `${inputRegion.y * charSize.height}px`;
input.style.background = 'transparent';
input.style.color = 'transparent';
input.style.caretColor = theme.colors.primary;
```

Canvas draws `> ` prompt + input text as CharCells. DOM `<input>` handles typing, cursor, selection, clipboard, IME. On `input` event, canvas repaints input region to match.

Repositioned on resize via the input region's recalculated pixel bounds.

## Panel Migration

Render functions keep their current signatures — they take game state + dimensions, return CharCell[][]. The change is where they paint.

### Migration Map

| Panel | Current | After |
|-------|---------|-------|
| Character, Inventory, Quests, Present, WorldMap | Own `TerminalPanel` instance | `canvas.setRegionContent(name, cells)` |
| Narrative | Own canvas + pixel scroll | `pixel` region, `drawTextAtPixel` into clipped bounds |
| Map | `MapRenderer` with own canvas | Offscreen canvas → `canvas.compositeOffscreen('viewport', mapCanvas)` |
| Art Viewer | DOM overlay | Offscreen canvas composited into viewport slot |
| Codex, Dialogue, Inventory Modal | DOM elements | CharCell[][] at z=1 via `canvas.openModal()` |
| Header, Status | DOM elements | CharCell rows in fixed regions |
| Input | DOM `<input>` in `#command-mount` | Transparent `<input>` positioned over input region |

### Migration Order

1. **UnifiedCanvas + RegionManager + borders** — scaffolding with placeholder content
2. **Grid panels** (character, inventory, quests, present) — simplest, just change paint target
3. **Header + status** — convert from DOM to CharCell rows
4. **Narrative** — pixel scrolling in clipped region, most complex migration
5. **Viewport** (map + entity cards) — offscreen canvas compositing
6. **Events feed** — row-based scroll in sidebar bottom
7. **Input** — DOM overlay positioning
8. **Modals** (codex, dialogue, inventory) — z-layered CharCell overlays
9. **Cleanup** — delete TerminalPanel, createWindow, old DOM mount points, CSS grid layout

### Retirement

Once complete, delete:
- `TerminalPanel` class (`ui/terminal-panel.ts`)
- `createWindow()` (`ui/window.ts`)
- CSS grid layout in `index.html`
- All `*-mount` DOM containers
- `panel-setup.ts` replaced by thin wiring layer calling render functions → `setRegionContent()`

## File Structure (New/Modified)

```
client/src/
├── canvas/
│   ├── unified-canvas.ts      # NEW — UnifiedCanvas class, paint loop
│   ├── region-manager.ts      # NEW — layout algorithm, reflow
│   ├── hit-registry.ts        # NEW — z-ordered global hit regions
│   ├── border-renderer.ts     # NEW — box-drawing char rendering
│   └── modal-manager.ts       # NEW — modal lifecycle, backdrop, scroll
├── panels/                    # MODIFIED — paint to regions, not TerminalPanel
├── renderer/
│   ├── canvas-text.ts         # UNCHANGED
│   ├── theme.ts               # UNCHANGED
│   └── line-cache.ts          # UNCHANGED
├── map/
│   └── renderer.ts            # MODIFIED — render to offscreen canvas
├── ui/
│   ├── codex-modal.ts         # MODIFIED — CharCell rendering instead of DOM
│   ├── dialog.ts              # MODIFIED — CharCell rendering instead of DOM
│   ├── inventory-modal.ts     # MODIFIED — CharCell rendering instead of DOM
│   ├── terminal-panel.ts      # DELETED
│   └── window.ts              # DELETED
└── app.ts                     # MODIFIED — wire UnifiedCanvas instead of panel-setup
```
