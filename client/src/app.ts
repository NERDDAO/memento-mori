// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { createInitialState, type GameState } from './state/game-state';
import { getSession, initSession, sendAction, setMessageHandler } from './state/session';
import { parseNarrative, renderSegments } from './renderer/text-renderer';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { initInput } from './panels/input';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderLocationPanel } from './panels/map';
import { renderActionsPanel } from './panels/actions';

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
}

// --- Action handling ---
async function handleAction(action: string): Promise<void> {
  if (!action.trim()) return;
  narrative.addBlock(`> ${action}`, 'player-action');
  await sendAction(action);
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
        const u = msg.state_update;
        if (u.location) {
          gameState.location.name = u.location;
          const session = getSession();
          session.currentLocation = u.location;
        }
        renderAllPanels();
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

  const actionInput = document.getElementById('action-input') as HTMLInputElement;
  initInput(actionInput, handleAction);

  setMessageHandler(handleMessage);

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
