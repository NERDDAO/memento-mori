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
function getThresholdMap(): RoomMap {
  // The Threshold — seeded room with real KG entity UUIDs
  const w = 35, h = 18;
  const tiles: string[] = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (y === 0 || y === h - 1 || x === 0 || x === w - 1) tiles.push('#');
      else if (x >= 5 && x <= 7 && y >= 3 && y <= 7) tiles.push('B');
      else if ((x === 12 && (y === 4 || y === 5)) || (x === 20 && (y === 4 || y === 5))) tiles.push('T');
      else if ((x === 12 && (y === 9 || y === 10)) || (x === 20 && (y === 9 || y === 10))) tiles.push('T');
      else if (y === 14 && x >= 14 && x <= 20) tiles.push(':');
      else tiles.push('.');
    }
  }
  tiles[9 * w + (w - 1)] = '+';   // east exit
  tiles[0 * w + 17] = '+';         // north exit
  tiles[(h - 1) * w + 17] = '+';   // south entrance

  return {
    id: 'c800dabf-b1ef-4033-a594-b1d7f80ee316',
    name: 'The Threshold',
    width: w,
    height: h,
    tiles,
    npcs: [
      { x: 6, y: 5, ch: 'G', name: 'Grumlock Stonebrow', id: '7c167ff0-d4c1-479f-b61d-22f108213575' },
      { x: 22, y: 6, ch: 'R', name: 'Roric the Sly', id: 'd4566673-e13a-4adc-9e35-2f6e45750664' },
      { x: 15, y: 10, ch: 'E', name: 'Elara Brightwood', id: '0b3dc518-1420-4741-8fb6-72e7e75ca370' },
    ],
    items: [
      { x: 13, y: 9, ch: '?', name: 'Tattered Journal', id: '8fe4b8d7-f31e-4cf5-ae64-e74c566e8c4a' },
      { x: 28, y: 3, ch: '!', name: 'Dull Iron Dagger', id: '306b569d-c2d6-4c02-8ad5-e881969827b4' },
    ],
    exits: [
      { x: 34, y: 9, ch: '+', direction: 'east', target: 'The Fog Road' },
      { x: 17, y: 0, ch: '+', direction: 'north', target: 'The Skeletal Woods' },
      { x: 17, y: 17, ch: '+', direction: 'south', target: 'The Wastes' },
    ],
    spawn: { x: 17, y: 15 },
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
    gameState.roomMap = getThresholdMap();
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
