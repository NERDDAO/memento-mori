// src/panel-setup.ts
/**
 * Panel initialization — creates all UI windows, mounts them, wires up
 * event listeners, and returns refs for the rest of the app to use.
 */

import type { GameState } from './state/game-state';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { initInput } from './panels/input';
import { initMapPanel } from './panels/map';
import { createWindow } from './ui/window';
import { createHeader } from './ui/header';
import { createDialog } from './ui/dialog';
import { createInventoryModal } from './ui/inventory-modal';
import { createCodexModal } from './ui/codex-modal';
import { createArtViewer } from './ui/art-viewer';
import { createStatusBar } from './ui/status';
import { createOverlayManager, type OverlayManager } from './ui/overlay';
import { setManageInventoryCallback } from './panels/inventory';
import { getSession } from './state/session';

/** Replace a mount-point div with a component element. */
function mount(mountId: string, el: HTMLElement): void {
  const mountEl = document.getElementById(mountId);
  if (mountEl && mountEl.parentElement) {
    mountEl.parentElement.replaceChild(el, mountEl);
  }
}

export interface PanelRefs {
  header: ReturnType<typeof createHeader>;
  narrative: NarrativeController;
  eventsFeed: NarrativeController;
  narrativeWin: ReturnType<typeof createWindow>;
  eventsWin: ReturnType<typeof createWindow>;
  mapWin: ReturnType<typeof createWindow>;
  characterWin: ReturnType<typeof createWindow>;
  inventoryWin: ReturnType<typeof createWindow>;
  exitsWin: ReturnType<typeof createWindow>;
  presentWin: ReturnType<typeof createWindow>;
  questWin: ReturnType<typeof createWindow>;
  factionWin: ReturnType<typeof createWindow>;
  commandWin: ReturnType<typeof createWindow>;
  statusBar: ReturnType<typeof createStatusBar>;
  overlays: OverlayManager;
  npcDialog: ReturnType<typeof createDialog>;
  invModal: ReturnType<typeof createInventoryModal>;
  codex: ReturnType<typeof createCodexModal>;
  artViewer: ReturnType<typeof createArtViewer>;
  actionInput: HTMLInputElement;
}

export function initPanels(
  getGameState: () => GameState,
  handleAction: (action: string) => Promise<void>,
): PanelRefs {
  // 1. Header
  const header = createHeader();
  mount('tui-header', header.el);

  // 2. Create windows
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

  // 3. Mount windows by replacing mount divs
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

  // Overlay manager
  const overlays = createOverlayManager(['char-create', 'death', 'loading', 'intro']);

  // Wire up panel-click events for interactive panels
  exitsWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.action) handleAction(detail.action);
  });
  presentWin.panel!.canvas.addEventListener('panel-click', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.action) handleAction(detail.action);
  });
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

  // Dialog
  const npcDialog = createDialog();
  mount('dialog-mount', npcDialog.el);

  // Inventory modal
  const invModal = createInventoryModal(getGameState);
  document.body.appendChild(invModal.el);
  setManageInventoryCallback(() => invModal.open());

  // 'i' key toggles inventory modal (when input not focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'i' && document.activeElement?.tagName !== 'INPUT') {
      if (invModal.active) invModal.close();
      else invModal.open();
    }
  });

  // Narrative + Events feed
  const narrative = initNarrative(narrativeWin.body);
  const eventsFeed = initNarrative(eventsWin.body);

  // Art viewer + Codex modal
  const artViewer = createArtViewer();
  document.body.appendChild(artViewer.el);
  const codex = createCodexModal(getGameState, () => getSession().playerId, artViewer.open);
  document.body.appendChild(codex.el);

  // Entity clicks from canvas narrative panel
  narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
    const { entityId } = (e as CustomEvent).detail;
    codex.open(entityId || undefined);
  });

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

  // 'm' key toggles map (when input not focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'm' && document.activeElement?.tagName !== 'INPUT') {
      mapWin.toggle();
    }
  });

  // 'k' key toggles codex modal (when input not focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'k' && document.activeElement?.tagName !== 'INPUT') {
      if (codex.active) codex.close();
      else codex.open();
    }
  });

  return {
    header,
    narrative,
    eventsFeed,
    narrativeWin,
    eventsWin,
    mapWin,
    characterWin,
    inventoryWin,
    exitsWin,
    presentWin,
    questWin,
    factionWin,
    commandWin,
    statusBar,
    overlays,
    npcDialog,
    invModal,
    codex,
    artViewer,
    actionInput,
  };
}
