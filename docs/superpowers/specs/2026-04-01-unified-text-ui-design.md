# Unified Text UI Redesign

## Overview

Replace the current HTML side panel and mixed rendering with a unified text-based UI where every panel is an independent bordered window (tmux-style). Add a floating NPC dialog system and an engine-driven in-game time system displayed in a persistent header.

## Current State

- Left column: canvas ASCII map (top) + narrative pane with virtual scrolling (bottom)
- Right column: HTML panels (CHARACTER, INVENTORY, ACTIONS) with CSS styling
- Bottom: text input bar
- Entity cards: floating DOM elements positioned near the map
- NPC conversations flow inline into the narrative

## Design

### Layout: Independent Windows

Every UI element becomes a bordered window with a title bar, rendered in the DOM but styled to look like a TUI. The viewport is a tiling arrangement of these windows.

```
┌─ ☽ Waning Crescent · 3rd of Ashfall · Dusk ──── MEMENTO MORI ─┐
│                                                                 │
│  ┌─ Narrative ──────────────┐  ┌─ Character ──────────┐        │
│  │                          │  │ HP ████░░ 42/50      │        │
│  │  (scrolling story text)  │  │ XP ██░░░░ 120        │        │
│  │                          │  ├─ Inventory ──────────┤        │
│  │                          │  │ · Tattered Journal   │        │
│  │                          │  │ · Dull Iron Dagger E │        │
│  │                          │  ├─ Exits ──────────────┤        │
│  │                          │  │ → East  Fog Road     │        │
│  │                          │  ├─ Present ────────────┤        │
│  │                          │  │ ◆ Roric — Barkeep   │        │
│  └──────────────────────────┘  └──────────────────────┘        │
│  ┌─ Map ──────────────┐                                        │
│  │  (toggleable)      │                                        │
│  └────────────────────┘                                        │
│  ┌─ Command ───────────────────────────────────────────┐       │
│  │ > talk to roric▌                                    │       │
│  └─────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Rendering: DOM + Pretext Hybrid

The UI uses a hybrid rendering approach:

- **DOM** handles window chrome (borders, title bars, grid layout, scroll, click events, text selection)
- **Pretext** handles text content inside windows — precise monospace measurement and line breaking
- **Animations** — Pretext's `layoutNextLine` drives character-by-character typewriter reveals in the NPC dialog; sidebar panels fade in on update

Pretext API used:
- `prepare(text, font)` → PreparedText (measures character widths)
- `layout(prepared, maxWidth, lineHeight)` → `{ lineCount, height }` (for virtual scroll measurement)
- `prepareWithSegments(text, font)` → adds segment tracking
- `layoutWithLines(prepared, maxWidth, lineHeight)` → `{ lines: LayoutLine[] }` (for rendering line-broken text)
- `layoutNextLine(prepared, start, maxWidth)` → single line (for incremental/streaming typewriter)

### Window Component

A reusable `Window` component that all panels use:

- 1px solid border (`#2a2a38`)
- Title bar: background `#16161f`, dim text with `─ Title ─` format
- Body: `#0a0a0f` background, monospace font throughout
- Windows are DOM elements (divs) — CSS handles the TUI look
- Text content inside windows is measured by Pretext for precise monospace layout

### Header Bar

- Spans the full width at the top
- Left: in-game time — moon phase icon, fantasy date, time of day
- Right: "MEMENTO MORI" in accent color
- Thin border separating it from content below
- Data comes from the engine's time tool (see Time System below)

### Sidebar Panels

Replace the current HTML panels with window-styled equivalents. The right column stacks these windows:

1. **Character** — name, level, HP bar (█/░), XP bar. Title shows player name.
2. **Inventory** — bullet list with rarity colors, equipped marker. Same color scheme as current.
3. **Exits** — arrow + direction + destination name. Clickable (triggers `go {direction}`).
4. **Present** — diamond + NPC name + role. Clickable (triggers `talk to {npc}`).

Each is a Window with its own title bar. They stack vertically, separated by the 4px gap.

### Narrative Window

- The existing narrative pane becomes a Window
- Keeps virtual scrolling (NarrativeStore + Pretext measurement)
- Keeps entity link highlighting, player action styling, all existing text rendering
- Title bar shows `─ Narrative ─` (or current location name)
- Serif font (Georgia) for narrative body text preserved — only the window chrome is monospace

### Map Window

- The canvas map becomes its own Window, toggleable
- Keyboard shortcut (e.g., `Tab` or `M`) shows/hides it
- When visible, appears below the narrative window in the left column
- The existing canvas renderer draws inside the window body
- Entity cards from the map (card-renderer.ts) continue to render on the canvas

### NPC Dialog Window

When a player talks to an NPC, a floating window appears overlaid on the narrative area:

```
┌─ Roric — Barkeep ─────────────────┐
│                                    │
│  "The Wastes don't give many      │
│   second chances, stranger."       │
│                                    │
│  His eyes narrow as he wipes      │
│  the bar with a stained cloth.    │
│                                    │
└────────────────────────────────────┘
```

- Centered over the narrative pane, semi-transparent backdrop
- Title bar shows NPC name and role
- **Typewriter animation**: text reveals character by character using Pretext's `layoutNextLine` for precise line breaking. Each character appears with a short delay (20-40ms), NPC quoted dialogue in gold, action descriptions in default text color. A blinking cursor tracks the reveal position.
- Dismissed automatically when the next non-NPC narrative arrives, or by pressing Escape
- The conversation also flows into the narrative pane underneath (for scroll history)

### Command Window

- The input bar becomes a Window at the bottom, spanning full width
- Title bar: `─ Command ─`
- Body: prompt character `>` + input field + blinking cursor
- Keeps command history (arrow up/down)

### Time System (Engine)

New CrewAI tool that provides in-game time:

**Tool: `get_world_time`**
- Returns structured data: `{ moon_phase, day_name, day_number, month, season, time_of_day }`
- Called by the engine at the start of each turn
- Time advances based on action type: movement = minutes, conversations = longer, rest = hours
- Fantasy calendar with custom month/season names fitting the dark fantasy theme

**Implementation:**
- New file: `engine/src/memento/tools/time.py` — the CrewAI tool
- New model: `engine/src/memento/models/time.py` — Pydantic model for world time state
- Time state stored in session (not KG — it's ephemeral per-session)
- Gateway passes time data in the state_update payload
- Client reads `state_update.world_time` and renders in the header

### Styling

All windows share the same CSS variables (existing theme extended):

```
--win-border:    #2a2a38
--win-title-bg:  #16161f
--win-title-text:#6a6a78
--win-body-bg:   #0a0a0f
```

Typography:
- Window title bars: monospace, 11px, uppercase
- Sidebar content: monospace, 13px
- Narrative body: Georgia serif, 16px (preserved from current)
- Input: monospace, 14px

Color scheme unchanged — same NPC gold, item purple, exit cyan, location blue, damage red, heal green.

### Pretext-Animated Text (`client/src/ui/typewriter.ts`)

A reusable typewriter animation module powered by Pretext:

- Takes raw text, font, and container width
- Uses `prepareWithSegments` + `layoutNextLine` to break text into lines
- Reveals characters one at a time with configurable delay (default 25ms)
- Renders each character as it appears into the target DOM element
- Returns a controller: `{ start(), skip(), cancel(), onComplete(cb) }`
- Used by the NPC dialog, and optionally by narrative blocks for dramatic moments

## Out of Scope

- Wiki/journal panel (future work)
- Crew status messages in UI
- Responsive/mobile layout
- Drag-to-resize windows

## Files Changed

### Client (new)
- `client/src/ui/window.ts` — reusable Window component
- `client/src/ui/typewriter.ts` — Pretext-powered typewriter animation
- `client/src/ui/dialog.ts` — floating NPC dialog overlay (uses typewriter)
- `client/src/ui/header.ts` — header bar with time display

### Client (modified)
- `client/index.html` — new grid layout, window-based structure, updated CSS
- `client/src/app.ts` — wire up new Window components, handle dialog lifecycle
- `client/src/panels/character.ts` — render inside Window
- `client/src/panels/inventory.ts` — render inside Window
- `client/src/panels/map.ts` — render inside Window, add toggle
- `client/src/panels/actions.ts` — merge into Present/Exits panels or remove
- `client/src/panels/narrative.ts` — render inside Window
- `client/src/panels/input.ts` — render inside Window

### Engine (new)
- `engine/src/memento/tools/time.py` — world time tool
- `engine/src/memento/models/time.py` — WorldTime Pydantic model

### Engine (modified)
- `engine/src/memento/flows/game_turn.py` — call time tool, include in output
- `engine/src/memento/session.py` — store time state

### Gateway (modified)
- `gateway/src/gateway/routes/action.py` or equivalent — pass world_time in state_update
