// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { type GameState } from './state/game-state';
import { getSession, sendAction, setMessageHandler, setConnectionHandler, setErrorHandler, GATEWAY_URL } from './state/session';
import { getRoundState } from './state/round-state';
import { setKnownEntities } from './renderer/text-renderer';
import { createMessageHandler } from './message-handler';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { updateMap } from './panels/map';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderWorldMapPanel } from './panels/worldmap';
import { renderPresentPanel } from './panels/present';
import { renderQuestLogPanel } from './panels/questlog';
import { renderFactionsPanel } from './panels/factions';
import { createWindow } from './ui/window';
import { createHeader } from './ui/header';
import { createDialog } from './ui/dialog';
import { createInventoryModal } from './ui/inventory-modal';
import { createCodexModal } from './ui/codex-modal';
import { createArtViewer } from './ui/art-viewer';
import { createStatusBar } from './ui/status';
import { type OverlayManager } from './ui/overlay';
import { startGame } from './flows/session-flow';
import { initInventoryApi } from './state/inventory-api';
import { initPanels } from './panel-setup';
import { initHotkeys } from './hotkeys';
import { initCharCreation } from './char-creation';

let gameState: GameState;
let narrative: NarrativeController;
let eventsFeed: NarrativeController;

let header: ReturnType<typeof createHeader>;
let npcDialog: ReturnType<typeof createDialog>;
let codex: ReturnType<typeof createCodexModal>;
let artViewer: ReturnType<typeof createArtViewer>;
let statusBar: ReturnType<typeof createStatusBar>;
let narrativeWin: ReturnType<typeof createWindow>;
let eventsWin: ReturnType<typeof createWindow>;
let mapWin: ReturnType<typeof createWindow>;
let characterWin: ReturnType<typeof createWindow>;
let inventoryWin: ReturnType<typeof createWindow>;
let exitsWin: ReturnType<typeof createWindow>;
let presentWin: ReturnType<typeof createWindow>;
let questWin: ReturnType<typeof createWindow>;
let factionWin: ReturnType<typeof createWindow>;
let commandWin: ReturnType<typeof createWindow>;
let overlays: OverlayManager;
let invModal: ReturnType<typeof createInventoryModal>;

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
      renderWorldMapPanel(exitsWin.panel!, gameState, handleAction);
    }
  } catch {
    // Non-fatal
  }
}

// --- Panel rendering ---
function renderAllPanels(): void {
  if (!gameState) return;
  characterWin.setTitle(gameState.player.name || 'Character');
  renderCharacterPanel(characterWin.panel!, gameState);
  renderInventoryPanel(inventoryWin.panel!, gameState);
  renderWorldMapPanel(exitsWin.panel!, gameState, handleAction);
  renderPresentPanel(presentWin.panel!, gameState, handleAction);
  renderQuestLogPanel(questWin.panel!, gameState.quests);
  renderFactionsPanel(factionWin.panel!, gameState.factions);
  updateMap(gameState, handleAction);

  // (codex is opened on demand via 'k' key, not auto-shown)
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

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  // Initialize all panels
  const panels = initPanels(() => gameState, handleAction);
  ({
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
  } = panels);

  // Hotkeys: m (map), i (inventory), k (codex), narrative-entity-click, npc-name-click
  initHotkeys({ exitsWin, questWin, factionWin, invModal, codex, npcDialog, narrative });

  // 9. Wire handlers
  const handleMessage = createMessageHandler({
    getGameState: () => gameState,
    narrative,
    eventsFeed,
    header,
    statusBar,
    codex,
    invModal,
    characterWin,
    inventoryWin,
    exitsWin,
    presentWin,
    questWin,
    factionWin,
    handleAction,
    registerMapEntities,
    fetchPlayerWorldMap,
    showDeathScreen,
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

  // 10. Death screen — new character button
  document.getElementById('death-restart-btn')!.addEventListener('click', () => {
    overlays.dismiss('death');
    overlays.show('char-create');
    narrative = initNarrative(narrativeWin.body);
    initHotkeys({ exitsWin, questWin, factionWin, invModal, codex, npcDialog, narrative });
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });

  // Character creation flow (wallet connect, archetype, name input)
  initCharCreation(enterGame, overlays);
});
