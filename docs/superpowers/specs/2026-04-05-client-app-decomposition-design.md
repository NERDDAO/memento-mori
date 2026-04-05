# Client app.ts Decomposition

## Context

`client/src/app.ts` is a 705-line monolith handling session flow, WS message routing, panel initialization, hotkeys, and shared state. This makes it hard to navigate, test, or modify individual concerns. Before the UI rework, we need to split it into focused modules.

## Approach

Pure extraction refactor — no behavior changes. Move code into modules along natural seams. `app.ts` becomes a thin orchestrator.

## Modules

### `app.ts` — Orchestrator (~80 lines)

Entry point. Holds shared refs, calls module init functions, wires session flow.

- Defines `AppRefs` interface (all shared state: `gameState`, `narrative`, `eventsFeed`, panel windows, codex, statusBar, etc.)
- On DOMContentLoaded: calls `initPanels()` → `initHotkeys()` → session flow → passes `createMessageHandler(refs)` to WS connection
- No business logic — just glue

### `message-handler.ts` — WS Message Routing (~220 lines)

The `handleMessage` switch extracted verbatim.

- Exports `createMessageHandler(refs: AppRefs): (msg: WsMessage) => void`
- All shared state accessed via `refs.` prefix
- Each case block stays identical — just moved

### `panel-setup.ts` — Panel Initialization (~150 lines)

Creates all windows, TerminalPanels, NarrativeControllers.

- Exports `initPanels(): PanelRefs`
- `PanelRefs` contains: `narrative`, `eventsFeed`, `mapRenderer`, `characterWin`, `inventoryWin`, `presentWin`, `questWin`, `factionWin`, `exitsWin`, `codex`, `invModal`, `npcDialog`, `artViewer`, `statusBar`, `actionInput`
- Current panel init block (lines ~482-560) extracted here
- Each panel's `createWindow` + `TerminalPanel` or `NarrativeController` creation

### `hotkeys.ts` — Keyboard Bindings (~60 lines)

All keyboard event listeners.

- Exports `initHotkeys(refs: AppRefs): void`
- Registers: `m` (map toggle), `i` (inventory modal), `k` (codex modal), `Escape` (close modals)
- Also registers the `narrative-entity-click` document listener that opens codex

## AppRefs Interface

Defined in `app.ts`:

```typescript
export interface AppRefs {
  gameState: GameState | null;
  narrative: NarrativeController;
  eventsFeed: NarrativeController;
  // Panel windows
  characterWin: { panel: TerminalPanel };
  inventoryWin: { panel: TerminalPanel };
  presentWin: { panel: TerminalPanel };
  questWin: { panel: TerminalPanel };
  factionWin: { panel: TerminalPanel };
  exitsWin: { panel: TerminalPanel };
  mapWin: { panel: any };
  // Modals & UI
  codex: CodexModal;
  invModal: InventoryModal;
  npcDialog: NpcDialog;
  artViewer: ArtViewer;
  statusBar: StatusBar;
  // Callbacks
  handleAction: (action: string) => void;
  renderAllPanels: () => void;
}
```

The exact shape will be determined during extraction — this is indicative.

## Constraints

- **No behavior changes** — every handler, panel, and hotkey works identically after the split
- **No new dependencies** — modules import from existing types, not from each other (except AppRefs)
- **gameState stays mutable** — refs hold a reference to the mutable gameState object; modules mutate it in place as before
- **File locations** — all new files in `client/src/` alongside `app.ts`

## Files

| File | Action |
|------|--------|
| `client/src/app.ts` | Modify — reduce to orchestrator |
| `client/src/message-handler.ts` | Create — WS message routing |
| `client/src/panel-setup.ts` | Create — panel initialization |
| `client/src/hotkeys.ts` | Create — keyboard bindings |

## Verification

1. Build client with `bun build` — no compile errors
2. All panels render identically (narrative, map, character, inventory, etc.)
3. WS messages route correctly (narrative, phase, NPC, episode_feed, etc.)
4. Hotkeys work (m, i, k, Escape)
5. Session flow works (create, join, reconnect)
6. No behavior regressions — pure move refactor
