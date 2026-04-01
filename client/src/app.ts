// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { createInitialState, applyStateUpdate, type GameState } from './state/game-state';
import { getSession, initSession, sendAction, setMessageHandler, setConnectionHandler } from './state/session';
import { parseNarrative, renderSegments } from './renderer/text-renderer';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { initInput } from './panels/input';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderLocationPanel, initMapPanel, updateMap } from './panels/map';
import { renderActionsPanel } from './panels/actions';
import type { RoomMap } from './map/types';

let gameState: GameState;
let narrative: NarrativeController;

// --- Panel rendering ---
function renderAllPanels(): void {
  if (!gameState) return;
  renderCharacterPanel(document.getElementById('character-panel')!, gameState);
  renderInventoryPanel(document.getElementById('inventory-list')!, gameState);
  renderLocationPanel(
    document.getElementById('location-panel')!,
    gameState,
    handleAction,
  );
  renderActionsPanel(
    document.getElementById('actions-list')!,
    gameState,
    handleAction,
  );
  updateMap(gameState, handleAction);
}

// Temporary test map — remove once engine sends real maps
function getTestMap(): RoomMap {
  const w = 30, h = 15;
  const tiles: string[] = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (y === 0 || y === h-1 || x === 0 || x === w-1) tiles.push('#');
      else if (x === 5 && y >= 3 && y <= 5) tiles.push('B');  // bar
      else if ((x === 10 || x === 20) && (y === 4 || y === 8)) tiles.push('T');  // tables
      else tiles.push('.');
    }
  }
  // Fix exit (overwrite the wall)
  tiles[7 * w + (w-1)] = '+';

  return {
    id: 'test-tavern',
    name: 'The Threshold',
    width: w,
    height: h,
    tiles,
    npcs: [
      { x: 6, y: 4, ch: 'K', name: 'Barkeeper', id: 'npc-barkeeper' },
      { x: 15, y: 6, ch: 'M', name: 'Merchant', id: 'npc-merchant' },
    ],
    items: [
      { x: 12, y: 9, ch: '!', name: 'Health Potion', id: 'item-potion' },
    ],
    exits: [
      { x: 29, y: 7, ch: '+', direction: 'east', target: 'unknown' },
    ],
    spawn: { x: 15, y: 12 },
  };
}

// --- Action handling ---
async function handleAction(action: string): Promise<void> {
  if (!action.trim()) return;
  narrative.addBlock(`> ${action}`, 'player-action');
  await sendAction(action);
}

// --- Death screen ---
function showDeathScreen(cause: string): void {
  const overlay = document.getElementById('death-overlay')!;
  const causeEl = document.getElementById('death-cause')!;
  const statsEl = document.getElementById('death-stats')!;

  causeEl.textContent = cause || 'The world continues without you.';
  statsEl.innerHTML = gameState ? `
    <div>Name: ${gameState.player.name}</div>
    <div>Level: ${gameState.player.level}</div>
    <div>Last Location: ${gameState.location.name}</div>
  ` : '';

  overlay.classList.remove('hidden');
}

// --- WebSocket message handling ---
function handleMessage(msg: any): void {
  switch (msg.type) {
    case 'narrative': {
      narrative.removeThinking();
      const segments = parseNarrative(msg.text || '');
      const html = renderSegments(segments);
      narrative.addHtml(html, 'narrative');

      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        const session = getSession();
        session.currentLocation = gameState.location.name;
        renderAllPanels();
      }

      if (msg.state_update?.status === 'dead' ||
          (msg.text && msg.text.toLowerCase().includes('you have died'))) {
        showDeathScreen(msg.state_update?.cause || '');
      }
      break;
    }
    case 'thinking':
      narrative.showThinking();
      break;
    default:
      console.log('Unknown message:', msg);
  }
}

// --- Character creation ---
async function enterWorld(playerName: string): Promise<void> {
  const overlay = document.getElementById('char-create-overlay')!;
  overlay.classList.add('hidden');

  const session = await initSession(playerName);
  gameState = createInitialState(playerName);
  gameState.location.name = session.currentLocation;

  if (!gameState.roomMap) {
    gameState.roomMap = getTestMap();
  }
  renderAllPanels();
  narrative.addBlock(`Welcome, ${playerName}. You find yourself at ${session.currentLocation}.`, 'system');

  if (session.openingNarrative) {
    const segments = parseNarrative(session.openingNarrative);
    narrative.addHtml(renderSegments(segments), 'narrative');
  }

  (document.getElementById('action-input') as HTMLInputElement).focus();
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  narrative = initNarrative(document.getElementById('narrative-pane')!);
  initMapPanel(document.getElementById('map-container')!, handleAction);

  const actionInput = document.getElementById('action-input') as HTMLInputElement;
  initInput(actionInput, handleAction);

  setMessageHandler(handleMessage);

  setConnectionHandler((connected) => {
    if (connected) {
      narrative.addBlock('Reconnected.', 'system');
    } else {
      narrative.addBlock('Connection lost. Reconnecting...', 'system');
    }
  });

  // Death screen — new character button
  document.getElementById('new-char-btn')!.addEventListener('click', () => {
    document.getElementById('death-overlay')!.classList.add('hidden');
    document.getElementById('char-create-overlay')!.classList.remove('hidden');
    document.getElementById('narrative-pane')!.innerHTML = '';
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });

  // Character creation
  const nameInput = document.getElementById('char-name-input') as HTMLInputElement;
  const enterBtn = document.getElementById('enter-world-btn')!;

  enterBtn.addEventListener('click', () => {
    const name = nameInput.value.trim() || 'Wanderer';
    enterWorld(name);
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      enterWorld(name);
    }
  });

  nameInput.focus();
});
