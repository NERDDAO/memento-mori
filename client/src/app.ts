// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, UnifiedCanvas, and message handling together.
 */

import { type GameState } from './state/game-state';
import { getSession, sendAction, setMessageHandler, setConnectionHandler, setErrorHandler, GATEWAY_URL } from './state/session';
import { getRoundState } from './state/round-state';
import { setKnownEntities } from './renderer/text-renderer';
import { createMessageHandler, getLastNpcMessage } from './message-handler';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { updateMap, setViewportCallback, initMapPanel } from './panels/map';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderWorldMapPanel } from './panels/worldmap';
import { renderPresentPanel } from './panels/present';
import { renderQuestLogPanel } from './panels/questlog';
import { renderFactionsPanel } from './panels/factions';
import { renderViewport } from './panels/viewport';
import { renderHeader, type WorldTime } from './ui/header';
import { renderStatusBar, type StatusState } from './ui/status';
import { UnifiedCanvas } from './canvas/unified-canvas';
import { createDialog } from './ui/dialog';
import { createInventoryModal } from './ui/inventory-modal';
import { createCodexModal } from './ui/codex-modal';
import { createArtViewer } from './ui/art-viewer';
import { type OverlayManager, createOverlayManager } from './ui/overlay';
import { startGame } from './flows/session-flow';
import { initInventoryApi } from './state/inventory-api';
import { initInput } from './panels/input';
import { setManageInventoryCallback } from './panels/inventory';
import { initHotkeys } from './hotkeys';
import { initCharCreation } from './char-creation';
import type { CardContent } from './map/card-renderer';

let gameState: GameState;
let narrative: NarrativeController;
let eventsFeed: NarrativeController;
let uc: UnifiedCanvas;

let npcDialog: ReturnType<typeof createDialog>;
let codex: ReturnType<typeof createCodexModal>;
let artViewer: ReturnType<typeof createArtViewer>;
let invModal: ReturnType<typeof createInventoryModal>;
let overlays: OverlayManager;

// --- Header / status state for CharCell renderers ---
let headerState = { title: 'MEMENTO MORI', worldTime: undefined as WorldTime | undefined };
let statusState: StatusState = { phase: 'ready', tick: 0, chain: false, activity: '', location: '' };

// --- Viewport state ---
let currentCard: CardContent | null = null;
let currentScene: string[] | null = null;

// --- Entity registration for narrative highlighting ---
function registerMapEntities(map: import('./map/types').RoomMap | null): void {
  if (!map) return;
  const entities: Array<{ name: string; id: string; type: string }> = [];
  for (const npc of map.npcs) entities.push({ name: npc.name, id: npc.id, type: 'npc' });
  for (const item of map.items) entities.push({ name: item.name, id: item.id, type: 'item' });
  for (const exit of map.exits) entities.push({ name: exit.target, id: exit.target, type: 'location' });
  entities.push({ name: map.name, id: map.id, type: 'location' });
  setKnownEntities(entities);
}

// --- Fetch player world map ---
async function fetchPlayerWorldMap(): Promise<void> {
  try {
    const pid = getSession().playerId;
    if (!pid || !gameState) return;
    const resp = await fetch(`${GATEWAY_URL}/api/worldmap/${pid}`);
    if (resp.ok) {
      gameState.worldMap = await resp.json();
      renderAllPanels();
    }
  } catch {
    // Non-fatal
  }
}

// --- Panel rendering ---
function renderAllPanels(): void {
  if (!gameState || !uc) return;

  const r = (name: string) => uc.getRegion(name);

  const charRegion = r('character');
  if (charRegion) {
    uc.setRegionContent('character', renderCharacterPanel(charRegion.cols, charRegion.rows, gameState));
  }

  const invRegion = r('inventory');
  if (invRegion) {
    uc.setRegionContent('inventory', renderInventoryPanel(invRegion.cols, invRegion.rows, gameState));
  }

  const questRegion = r('quests');
  if (questRegion) {
    uc.setRegionContent('quests', renderQuestLogPanel(questRegion.cols, questRegion.rows, gameState.quests));
  }

  const presentRegion = r('present');
  if (presentRegion) {
    uc.setRegionContent('present', renderPresentPanel(presentRegion.cols, presentRegion.rows, gameState));
  }

  const vpRegion = r('viewport');
  if (vpRegion) {
    uc.setRegionContent('viewport', renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }

  const headerRegion = r('header');
  if (headerRegion) {
    uc.setRegionContent('header', renderHeader(headerRegion.cols, headerState));
  }

  const statusRegion = r('status');
  if (statusRegion) {
    uc.setRegionContent('status', renderStatusBar(statusRegion.cols, statusState));
  }

  updateMap(gameState, handleAction);
}

// --- Action handling ---
async function handleAction(action: string): Promise<void> {
  if (!action.trim() || action.length > 500) return;
  // Block actions during active round phases (resolving, npc_response)
  const phase = getRoundState().phase;
  if (phase !== 'ready' && phase !== 'collecting') return;
  narrative.addBlock(`> ${action}`, 'player-action');
  await sendAction(action);
}

// --- Death screen ---
function showDeathScreen(cause: string): void {
  const causeEl = document.getElementById('death-cause')!;
  const statsEl = document.getElementById('death-stats')!;

  causeEl.textContent = cause || 'The world continues without you.';
  statsEl.innerHTML = gameState ? `
    <div>Name: ${gameState.player.name}</div>
    <div>Level: ${gameState.player.level}</div>
    <div>Last Location: ${gameState.location.name}</div>
  ` : '';

  overlays.show('death');
}

// --- Viewport setters ---
function setViewportCard(card: CardContent | null): void {
  currentCard = card;
  currentScene = null;
  const vpRegion = uc?.getRegion('viewport');
  if (vpRegion) {
    uc.setRegionContent('viewport', renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }
}

function setViewportScene(lines: string[]): void {
  currentScene = lines;
  currentCard = null;
  const vpRegion = uc?.getRegion('viewport');
  if (vpRegion) {
    uc.setRegionContent('viewport', renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }
}

// --- Enter game (new or returning) ---
function enterGame(config: { playerName: string; walletAddress: string; isReturning: boolean; playerId?: string; archetype?: string }): void {
  startGame(
    { ...config },
    overlays,
    {
      onGameReady(state, openingNarrative) {
        gameState = state;
        // Init optimistic inventory API
        const session = getSession();
        (window as any).__mmPlayerId = session.playerId;
        initInventoryApi(gameState, session.playerId, renderAllPanels, (text, style) => {
          eventsFeed.addBlock(text, style);
        });
        if (gameState.roomMap) registerMapEntities(gameState.roomMap);
        renderAllPanels();
        fetchPlayerWorldMap();
        if (openingNarrative) {
          narrative.addBlock(openingNarrative, config.isReturning ? 'system' : 'narrative');
        }
        (document.getElementById('action-input') as HTMLInputElement).focus();
      },
    },
  ).catch((err) => {
    console.error('startGame failed:', err);
    overlays.dismiss('loading');
    overlays.show('char-create');
  });
}

// --- Position action input over the canvas input region ---
function positionActionInput(inputEl: HTMLInputElement): void {
  const inputRegion = uc.getRegion('input');
  if (!inputRegion) return;
  const cs = uc.getCharSize();
  const canvasRect = uc.canvas.getBoundingClientRect();
  const appRect = uc.canvas.parentElement!.getBoundingClientRect();

  // Position relative to #tui-main (the positioned parent)
  const offsetX = canvasRect.left - appRect.left;
  const offsetY = canvasRect.top - appRect.top;

  // Leave 2 chars for the "> " prompt rendered by the canvas
  const promptCols = 2;
  inputEl.style.left = `${offsetX + (inputRegion.col + promptCols) * cs.width}px`;
  inputEl.style.top = `${offsetY + inputRegion.row * cs.height}px`;
  inputEl.style.width = `${(inputRegion.cols - promptCols) * cs.width}px`;
  inputEl.style.height = `${cs.height}px`;
  inputEl.style.fontSize = `${cs.height - 2}px`;
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  // Create UnifiedCanvas
  const tuiMain = document.getElementById('tui-main')!;
  uc = new UnifiedCanvas(tuiMain);

  // Create offscreen containers for narrative and events
  const narrativeContainer = document.createElement('div');
  narrativeContainer.style.position = 'absolute';
  narrativeContainer.style.left = '-9999px';
  document.body.appendChild(narrativeContainer);

  const eventsContainer = document.createElement('div');
  eventsContainer.style.position = 'absolute';
  eventsContainer.style.left = '-9999px';
  document.body.appendChild(eventsContainer);

  // Size offscreen containers to match regions
  function sizeNarrativeContainers(): void {
    const cs = uc.getCharSize();
    const narRegion = uc.getRegion('narrative');
    if (narRegion) {
      narrativeContainer.style.width = `${narRegion.cols * cs.width}px`;
      narrativeContainer.style.height = `${narRegion.rows * cs.height}px`;
    }
    const evtRegion = uc.getRegion('events');
    if (evtRegion) {
      eventsContainer.style.width = `${evtRegion.cols * cs.width}px`;
      eventsContainer.style.height = `${evtRegion.rows * cs.height}px`;
    }
  }
  sizeNarrativeContainers();

  // Init narrative controllers on the offscreen containers
  narrative = initNarrative(narrativeContainer);
  eventsFeed = initNarrative(eventsContainer);

  // Composite narrative canvases into the UC via pixel renderers
  uc.setPixelRenderer('narrative', (ctx, region, charSize) => {
    const px = region.col * charSize.width;
    const py = region.row * charSize.height;
    const pw = region.cols * charSize.width;
    const ph = region.rows * charSize.height;
    ctx.drawImage(narrative.canvas, 0, 0, narrative.canvas.width, narrative.canvas.height, px, py, pw, ph);
  });

  uc.setPixelRenderer('events', (ctx, region, charSize) => {
    const px = region.col * charSize.width;
    const py = region.row * charSize.height;
    const pw = region.cols * charSize.width;
    const ph = region.rows * charSize.height;
    ctx.drawImage(eventsFeed.canvas, 0, 0, eventsFeed.canvas.width, eventsFeed.canvas.height, px, py, pw, ph);
  });

  // Forward wheel events to narrative/events
  uc.onWheel((region, deltaY) => {
    if (region === 'narrative') {
      narrative.scroll(deltaY);
      uc.markDirty('narrative');
    }
    if (region === 'events') {
      eventsFeed.scroll(deltaY);
      uc.markDirty('events');
    }
  });

  // Wire click handler for interactive panels
  uc.onClick((region, data) => {
    if (data.action) handleAction(data.action as string);
    if (data.questName) {
      const quest = gameState?.quests.find((q: any) => q.name === data.questName);
      if (quest) npcDialog.showQuest(quest);
    }
    if (data.entityId) codex.open(data.entityId as string);
    if (data.npcName) {
      const lastMsg = getLastNpcMessage(data.npcName as string);
      if (lastMsg) npcDialog.show(data.npcName as string, '', lastMsg);
    }
  });

  // Wire viewport callback from map proximity
  setViewportCallback(setViewportCard);

  // Init map into a hidden container (it renders its own canvas)
  const mapContainer = document.createElement('div');
  mapContainer.style.position = 'absolute';
  mapContainer.style.left = '-9999px';
  mapContainer.style.width = '400px';
  mapContainer.style.height = '300px';
  document.body.appendChild(mapContainer);
  initMapPanel(mapContainer, handleAction);

  // Action input positioning and wiring
  const actionInput = document.getElementById('action-input') as HTMLInputElement;
  initInput(actionInput, handleAction, () => ({
    npcs: gameState?.location?.npcs || [],
    players: gameState?.location?.players || [],
  }));
  positionActionInput(actionInput);

  // Reposition input on resize
  const resizeObserver = new ResizeObserver(() => {
    sizeNarrativeContainers();
    positionActionInput(actionInput);
  });
  resizeObserver.observe(tuiMain);

  // Render input prompt into the grid
  function renderInputPrompt(): void {
    const inputRegion = uc.getRegion('input');
    if (!inputRegion) return;
    const cells = [[
      { char: '>', fg: '#6a6a78' },
      { char: ' ', fg: '#6a6a78' },
    ]];
    // Pad to region width
    while (cells[0].length < inputRegion.cols) {
      cells[0].push({ char: ' ', fg: '#6a6a78' });
    }
    uc.setRegionContent('input', { cells });
  }
  renderInputPrompt();

  // Periodically repaint narrative/events (they have their own rAF loops)
  setInterval(() => {
    uc.markDirty('narrative');
    uc.markDirty('events');
  }, 100);

  // Overlay manager
  overlays = createOverlayManager(['char-create', 'death', 'loading', 'intro']);

  // Dialog
  npcDialog = createDialog();
  const dialogMount = document.getElementById('dialog-mount')!;
  dialogMount.parentElement!.replaceChild(npcDialog.el, dialogMount);

  // Inventory modal
  invModal = createInventoryModal(() => gameState);
  document.body.appendChild(invModal.el);
  setManageInventoryCallback(() => invModal.open());

  // Art viewer + Codex modal
  artViewer = createArtViewer();
  document.body.appendChild(artViewer.el);
  codex = createCodexModal(() => gameState, () => getSession().playerId, artViewer.open);
  document.body.appendChild(codex.el);

  // Hotkeys
  initHotkeys({ invModal, codex, npcDialog });

  // Wire message handler
  const handleMessage = createMessageHandler({
    getGameState: () => gameState,
    narrative,
    eventsFeed,
    renderAllPanels,
    header: {
      updateTime(t: WorldTime) {
        headerState.worldTime = t;
        const headerRegion = uc.getRegion('header');
        if (headerRegion) {
          uc.setRegionContent('header', renderHeader(headerRegion.cols, headerState));
        }
      },
    },
    statusBar: {
      setTick(t: number) {
        statusState.tick = t;
        const region = uc.getRegion('status');
        if (region) uc.setRegionContent('status', renderStatusBar(region.cols, statusState));
      },
      setChain(c: boolean) {
        statusState.chain = c;
        const region = uc.getRegion('status');
        if (region) uc.setRegionContent('status', renderStatusBar(region.cols, statusState));
      },
      setActivity(a: string) {
        statusState.activity = a;
        const region = uc.getRegion('status');
        if (region) uc.setRegionContent('status', renderStatusBar(region.cols, statusState));
      },
    },
    codex,
    invModal,
    handleAction,
    registerMapEntities,
    fetchPlayerWorldMap,
    showDeathScreen,
    setViewportScene,
  });
  setMessageHandler(handleMessage);

  setConnectionHandler((connected) => {
    if (connected) {
      narrative.addBlock('Reconnected.', 'system');
    } else {
      narrative.addBlock('Connection lost. Reconnecting...', 'system');
    }
  });

  setErrorHandler((msg) => eventsFeed.addBlock(msg, 'error'));

  // Death screen — new character button
  document.getElementById('death-restart-btn')!.addEventListener('click', () => {
    overlays.dismiss('death');
    overlays.show('char-create');
    // Re-init narrative
    narrativeContainer.innerHTML = '';
    narrative = initNarrative(narrativeContainer);
    // Re-register pixel renderer with new narrative
    uc.setPixelRenderer('narrative', (ctx, region, charSize) => {
      const px = region.col * charSize.width;
      const py = region.row * charSize.height;
      const pw = region.cols * charSize.width;
      const ph = region.rows * charSize.height;
      ctx.drawImage(narrative.canvas, 0, 0, narrative.canvas.width, narrative.canvas.height, px, py, pw, ph);
    });
    initHotkeys({ invModal, codex, npcDialog });
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });

  // Character creation flow (wallet connect, archetype, name input)
  initCharCreation(enterGame, overlays);

  // Initial panel render
  renderAllPanels();
});
