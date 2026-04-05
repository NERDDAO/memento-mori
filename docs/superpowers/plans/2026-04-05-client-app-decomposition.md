# Client app.ts Decomposition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 718-line `app.ts` monolith into 4 focused modules with zero behavior changes.

**Architecture:** Pure extraction refactor. `app.ts` becomes a thin orchestrator (~250 lines) that calls `initPanels()`, `createMessageHandler()`, and `initHotkeys()`. Each module takes an `AppRefs` object for shared state access. No new features, no behavior changes.

**Tech Stack:** TypeScript, Bun bundler

**Spec:** `docs/superpowers/specs/2026-04-05-client-app-decomposition-design.md`

---

### Task 1: Create `message-handler.ts` — Extract WS Message Routing

This is the largest extraction (~230 lines). The `handleMessage` switch (lines 124-356) moves to its own module. It needs access to shared state via a refs object.

**Files:**
- Create: `client/src/message-handler.ts`
- Modify: `client/src/app.ts`

- [ ] **Step 1: Create `message-handler.ts` with the AppRefs type and handler factory**

Create `client/src/message-handler.ts` with this content — it's the `handleMessage` function extracted verbatim, with all shared state accessed through `refs`:

```typescript
// src/message-handler.ts
/**
 * WebSocket message routing — handles all incoming game messages.
 */

import { applyStateUpdate, type GameState } from './state/game-state';
import { getSession } from './state/session';
import { getRoundState, updateRoundState, type PhaseMessage as RoundPhaseMessage } from './state/round-state';
import type { WsMessage } from './types/ws-messages';
import type { NarrativeController } from './panels/narrative';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderWorldMapPanel } from './panels/worldmap';
import { renderPresentPanel } from './panels/present';
import { renderQuestLogPanel } from './panels/questlog';
import { renderFactionsPanel } from './panels/factions';
import { updateMap } from './panels/map';
import type { WorldTime } from './ui/header';

/** Shared references passed from the orchestrator. */
export interface AppRefs {
  getGameState: () => GameState | null;
  setGameState: (gs: GameState) => void;
  narrative: NarrativeController;
  eventsFeed: NarrativeController;
  characterWin: { panel: any; setTitle: (t: string) => void };
  inventoryWin: { panel: any };
  exitsWin: { panel: any };
  presentWin: { panel: any };
  questWin: { panel: any };
  factionWin: { panel: any };
  codex: { active: boolean; refreshEntityArt: (id: string, lines: string[]) => void };
  invModal: { active: boolean; refresh: () => void };
  statusBar: { setTick: (t: number) => void; setChain: (c: boolean) => void; setActivity: (a: string) => void };
  header: { updateTime: (t: WorldTime) => void };
  overlays: { show: (id: string) => void };
  handleAction: (action: string) => void;
  registerMapEntities: (map: any) => void;
  fetchPlayerWorldMap: () => void;
  showDeathScreen: (cause: string) => void;
}

export function createMessageHandler(refs: AppRefs): (msg: WsMessage) => void {

  function renderAllPanels(): void {
    const gameState = refs.getGameState();
    if (!gameState) return;
    refs.characterWin.setTitle(gameState.player.name || 'Character');
    renderCharacterPanel(refs.characterWin.panel!, gameState);
    renderInventoryPanel(refs.inventoryWin.panel!, gameState);
    renderWorldMapPanel(refs.exitsWin.panel!, gameState, refs.handleAction);
    renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
    renderQuestLogPanel(refs.questWin.panel!, gameState.quests);
    renderFactionsPanel(refs.factionWin.panel!, gameState.factions);
    updateMap(gameState, refs.handleAction);
  }

  return function handleMessage(msg: WsMessage): void {
    const gameState = refs.getGameState();

    switch (msg.type) {
      // --- Paste the ENTIRE switch body from app.ts lines 126-355 here ---
      // Replace all bare `gameState` references with `gameState` (already a local const)
      // Replace `narrative.` with `refs.narrative.`
      // Replace `eventsFeed.` with `refs.eventsFeed.`
      // Replace `codex.` with `refs.codex.`
      // Replace `invModal.` with `refs.invModal.`
      // Replace `statusBar.` with `refs.statusBar.`
      // Replace `header.` with `refs.header.`
      // Replace `overlays.` with `refs.overlays.`
      // Replace `renderAllPanels()` calls with the local `renderAllPanels()`
      // Replace `fetchPlayerWorldMap()` with `refs.fetchPlayerWorldMap()`
      // Replace `registerMapEntities(...)` with `refs.registerMapEntities(...)`
      // Replace `showDeathScreen(...)` with `refs.showDeathScreen(...)`
      // Replace `handleAction` with `refs.handleAction`
      // Replace `renderPresentPanel(presentWin.panel!, ...)` with `renderPresentPanel(refs.presentWin.panel!, ...)`
      // (and similarly for other panel references)
    }
  };
}
```

The implementer must copy the ENTIRE switch body from `app.ts` lines 126-355 and apply the `refs.` prefix substitutions listed above. Every `presentWin`, `characterWin`, etc. becomes `refs.presentWin`, etc. The `gameState` local const is already correct since it's derived from `refs.getGameState()` at the top of the handler.

- [ ] **Step 2: Update `app.ts` to use the new module**

In `app.ts`:
1. Add import: `import { createMessageHandler, type AppRefs } from './message-handler';`
2. Remove the `handleMessage` function (lines 124-356)
3. Remove imports that are now only used by message-handler.ts (check each: `applyStateUpdate`, `updateRoundState`, `RoundPhaseMessage`, panel render functions — keep only what app.ts still needs)
4. In the DOMContentLoaded handler, after panels are initialized, create the handler:

```typescript
  const refs: AppRefs = {
    getGameState: () => gameState,
    setGameState: (gs) => { gameState = gs; },
    narrative,
    eventsFeed,
    characterWin: { panel: characterWin.panel, setTitle: (t) => characterWin.setTitle(t) },
    inventoryWin: { panel: inventoryWin.panel },
    exitsWin: { panel: exitsWin.panel },
    presentWin: { panel: presentWin.panel },
    questWin: { panel: questWin.panel },
    factionWin: { panel: factionWin.panel },
    codex,
    invModal,
    statusBar,
    header,
    overlays,
    handleAction,
    registerMapEntities,
    fetchPlayerWorldMap,
    showDeathScreen,
  };
  const handleMessage = createMessageHandler(refs);
  setMessageHandler(handleMessage);
```

5. Keep `renderAllPanels()` in app.ts as well (it's still called from `enterGame` and needs to stay accessible). The message-handler has its own copy via the closure.

- [ ] **Step 3: Build and verify**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=dist`
Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/message-handler.ts client/src/app.ts
git commit -m "refactor(client): extract message-handler.ts from app.ts"
```

---

### Task 2: Create `panel-setup.ts` — Extract Panel Initialization

Extract window creation, mounting, and panel event wiring into its own module.

**Files:**
- Create: `client/src/panel-setup.ts`
- Modify: `client/src/app.ts`

- [ ] **Step 1: Create `panel-setup.ts`**

Extract lines 497-604 from the DOMContentLoaded handler (window creation, mounting, panel init, event wiring):

```typescript
// src/panel-setup.ts
/**
 * Panel initialization — creates all windows, terminals, and narrative controllers.
 */

import { createWindow } from './ui/window';
import { createHeader } from './ui/header';
import { createDialog } from './ui/dialog';
import { createInventoryModal } from './ui/inventory-modal';
import { createCodexModal } from './ui/codex-modal';
import { createArtViewer } from './ui/art-viewer';
import { createStatusBar } from './ui/status';
import { createOverlayManager } from './ui/overlay';
import { initNarrative } from './panels/narrative';
import { initMapPanel } from './panels/map';
import { initInput } from './panels/input';
import { setManageInventoryCallback } from './panels/inventory';
import type { GameState } from './state/game-state';
import { getSession } from './state/session';

function mount(mountId: string, el: HTMLElement): void {
  const mountEl = document.getElementById(mountId);
  if (mountEl && mountEl.parentElement) {
    mountEl.parentElement.replaceChild(el, mountEl);
  }
}

export function initPanels(
  getGameState: () => GameState | null,
  handleAction: (action: string) => void,
) {
  // Header
  const header = createHeader();
  mount('tui-header', header.el);

  // Windows
  const narrativeWin = createWindow({ title: 'Narrative', id: 'narrative-win', className: 'resizable' });
  const eventsWin = createWindow({ title: 'Events', id: 'events-win' });
  const mapWin = createWindow({ title: 'Map', id: 'map-win' });
  const characterWin = createWindow({ title: 'Character', id: 'character-win', className: 'sidebar-win resizable', canvas: true });
  const inventoryWin = createWindow({ title: 'Inventory', id: 'inventory-win', className: 'sidebar-win resizable', canvas: true });
  const exitsWin = createWindow({ title: 'World', id: 'exits-win', className: 'sidebar-win resizable', canvas: true });
  const presentWin = createWindow({ title: 'Present', id: 'present-win', className: 'sidebar-win resizable', canvas: true });
  const questWin = createWindow({ title: 'Quests', id: 'quest-win', className: 'sidebar-win resizable', canvas: true });
  const factionWin = createWindow({ title: 'Factions', id: 'faction-win', className: 'sidebar-win resizable', canvas: true });
  const commandWin = createWindow({ title: 'Command', id: 'command-win' });

  // Mount windows
  mount('narrative-mount', narrativeWin.el);
  mount('events-mount', eventsWin.el);
  mount('map-mount', mapWin.el);
  mount('character-mount', characterWin.el);
  mount('inventory-mount', inventoryWin.el);
  mount('exits-mount', exitsWin.el);
  mount('present-mount', presentWin.el);
  mount('quest-mount', questWin.el);
  mount('faction-mount', factionWin.el);
  mount('command-mount', commandWin.el);

  // Status bar
  const statusBar = createStatusBar();
  mount('status-mount', statusBar.el);

  // Overlays
  const overlays = createOverlayManager(['char-create', 'death', 'loading', 'intro']);

  // Panel click events
  exitsWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.action) handleAction(detail.action);
  });
  presentWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.action) handleAction(detail.action);
  });

  // Dialog
  const npcDialog = createDialog();
  mount('dialog-mount', npcDialog.el);

  // Quest click → dialog
  questWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.questName) {
      const gs = getGameState();
      if (gs) {
        const quest = gs.quests.find(q => q.name === detail.questName);
        if (quest) npcDialog.showQuest(quest);
      }
    }
  });

  // Inventory modal
  const invModal = createInventoryModal(getGameState);
  document.body.appendChild(invModal.el);
  setManageInventoryCallback(() => invModal.open());

  // Narrative + Events feed
  const narrative = initNarrative(narrativeWin.body);
  const eventsFeed = initNarrative(eventsWin.body);

  // Command input
  commandWin.body.innerHTML = `
    <span class="prompt-char">&gt;</span>
    <input type="text" id="action-input" placeholder="What do you do?" autocomplete="off" spellcheck="false" />
  `;
  const actionInput = commandWin.body.querySelector('#action-input') as HTMLInputElement;
  initInput(actionInput, handleAction, () => ({
    npcs: getGameState()?.location?.npcs || [],
    players: getGameState()?.location?.players || [],
  }));

  // Map
  const mapCanvasWrap = document.createElement('div');
  mapCanvasWrap.className = 'map-canvas-wrap';
  mapWin.body.appendChild(mapCanvasWrap);
  initMapPanel(mapCanvasWrap, handleAction);

  // Art viewer + Codex
  const artViewer = createArtViewer();
  document.body.appendChild(artViewer.el);
  const codex = createCodexModal(getGameState, () => getSession().playerId, artViewer.open);
  document.body.appendChild(codex.el);

  return {
    header, narrative, eventsFeed,
    narrativeWin, eventsWin, mapWin,
    characterWin, inventoryWin, exitsWin, presentWin, questWin, factionWin, commandWin,
    statusBar, overlays, npcDialog, invModal, codex, artViewer, actionInput,
  };
}
```

- [ ] **Step 2: Update `app.ts` to use `initPanels()`**

Replace the entire panel creation block in DOMContentLoaded (lines 497-604) with:

```typescript
  const panels = initPanels(() => gameState, handleAction);
  // Destructure for local access
  header = panels.header;
  narrative = panels.narrative;
  eventsFeed = panels.eventsFeed;
  narrativeWin = panels.narrativeWin;
  // ... etc for all panel refs
  statusBar = panels.statusBar;
  overlays = panels.overlays;
  codex = panels.codex;
  invModal = panels.invModal;
  npcDialog = panels.npcDialog;
  artViewer = panels.artViewer;
```

Remove the `mount()` helper from app.ts (it's now in panel-setup.ts). Remove imports that moved to panel-setup.ts.

- [ ] **Step 3: Build and verify**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=dist`

- [ ] **Step 4: Commit**

```bash
git add client/src/panel-setup.ts client/src/app.ts
git commit -m "refactor(client): extract panel-setup.ts from app.ts"
```

---

### Task 3: Create `hotkeys.ts` — Extract Keyboard Bindings

Extract all keyboard event listeners into their own module.

**Files:**
- Create: `client/src/hotkeys.ts`
- Modify: `client/src/app.ts`

- [ ] **Step 1: Create `hotkeys.ts`**

```typescript
// src/hotkeys.ts
/**
 * Keyboard bindings — hotkeys for panel toggles and modals.
 */

export interface HotkeyRefs {
  mapWin: { toggle: () => void };
  invModal: { active: boolean; open: () => void; close: () => void };
  codex: { active: boolean; open: (entityId?: string) => void; close: () => void };
  narrative: { canvas: HTMLCanvasElement };
}

export function initHotkeys(refs: HotkeyRefs): void {
  // 'm' — toggle map
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'm' && document.activeElement?.tagName !== 'INPUT') {
      refs.mapWin.toggle();
    }
  });

  // 'i' — toggle inventory modal
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'i' && document.activeElement?.tagName !== 'INPUT') {
      if (refs.invModal.active) refs.invModal.close();
      else refs.invModal.open();
    }
  });

  // 'k' — toggle codex modal
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'k' && document.activeElement?.tagName !== 'INPUT') {
      if (refs.codex.active) refs.codex.close();
      else refs.codex.open();
    }
  });

  // Entity clicks from narrative canvas → open codex
  refs.narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
    const { entityId } = (e as CustomEvent).detail;
    refs.codex.open(entityId || undefined);
  });
}
```

- [ ] **Step 2: Update `app.ts`**

1. Import: `import { initHotkeys } from './hotkeys';`
2. Remove the three `document.addEventListener('keydown', ...)` blocks for m, i, k (lines 550-554, 566-571, 607-612)
3. Remove the `narrative-entity-click` listener (lines 578-581)
4. After panels are initialized, call:

```typescript
  initHotkeys({
    mapWin,
    invModal,
    codex,
    narrative,
  });
```

- [ ] **Step 3: Build and verify**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=dist`

- [ ] **Step 4: Commit**

```bash
git add client/src/hotkeys.ts client/src/app.ts
git commit -m "refactor(client): extract hotkeys.ts from app.ts"
```

---

### Task 4: Final Cleanup — Verify `app.ts` is the Thin Orchestrator

After Tasks 1-3, verify `app.ts` only contains: imports, shared state declarations, utility functions (`registerMapEntities`, `fetchPlayerWorldMap`, `renderAllPanels`, `showDeathScreen`, `handleAction`), `enterGame`, character creation flow, and the DOMContentLoaded wiring.

**Files:**
- Modify: `client/src/app.ts`

- [ ] **Step 1: Review and clean up `app.ts`**

Verify the file is ~250 lines. Remove any unused imports. Ensure:
- Shared state (`gameState`, panel refs) is declared at top
- `initPanels()` call returns all refs
- `createMessageHandler(refs)` builds the handler
- `initHotkeys(refs)` registers keybindings
- `enterGame`, `showCharacterPicker`, `loadArchetypes` remain in app.ts (they're UI flow, not structural)
- `setMessageHandler(handleMessage)` + `setConnectionHandler(...)` wiring stays
- Death restart button handler stays (it re-creates narrative + listener)

- [ ] **Step 2: Re-wire death restart handler**

The death restart button (line 626-635) re-creates the narrative and adds the entity-click listener. Since the entity-click listener is now in `initHotkeys`, the death handler should just re-create narrative and re-register:

```typescript
  document.getElementById('death-restart-btn')!.addEventListener('click', () => {
    overlays.dismiss('death');
    overlays.show('char-create');
    narrative = initNarrative(narrativeWin.body);
    // Re-register entity click on new canvas
    narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
      const { entityId } = (e as CustomEvent).detail;
      codex.open(entityId || undefined);
    });
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });
```

This stays in app.ts since it's part of the death/restart flow and needs to mutate the `narrative` ref.

- [ ] **Step 3: Full build + manual verification**

Run: `cd /home/at0x/Vaults/Bonfires/memento-mori/client && bun build src/app.ts --outdir=dist`

Verify:
1. Build succeeds
2. `app.ts` is ~250 lines
3. `message-handler.ts` is ~230 lines
4. `panel-setup.ts` is ~120 lines
5. `hotkeys.ts` is ~40 lines

- [ ] **Step 4: Commit**

```bash
git add client/src/app.ts
git commit -m "refactor(client): finalize app.ts as thin orchestrator (~250 lines)"
```

---

## Verification

After all tasks:

1. `bun build` succeeds with no errors
2. `app.ts` is ~250 lines (down from 718)
3. All panels render correctly
4. WS messages route correctly (narrative, phase, NPC, episode_feed, etc.)
5. Hotkeys work (m, i, k, Escape)
6. Session flow works (create, join, reconnect)
7. Death screen + restart works
8. Character picker works
9. Codex opens from narrative clicks AND map card clicks
10. No behavior regressions — pure extraction
