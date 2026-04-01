// src/app.ts
/**
 * Memento Mori — MUD Client
 * Entry point: manages WebSocket connection, input handling, and narrative display.
 */

import { createInitialState, renderState, type GameState } from './state/game-state';
import { parseNarrative, renderSegments } from './renderer/text-renderer';

const GATEWAY_URL = 'http://localhost:8080';
const WS_URL = 'ws://localhost:8080/ws';

// --- State ---
let playerId = '';
let sessionId = '';
let currentLocation = '';
let ws: WebSocket | null = null;
let gameState: GameState;
const commandHistory: string[] = [];
let historyIndex = -1;

// --- DOM ---
const narrativePane = document.getElementById('narrative-pane')!;
const actionInput = document.getElementById('action-input') as HTMLInputElement;

// --- Session ---
async function createSession(playerName: string): Promise<void> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName }),
  });
  const data = await resp.json();
  playerId = data.player_id;
  sessionId = data.session_id;
  currentLocation = data.location;

  document.getElementById('char-name')!.textContent = playerName;
  document.getElementById('location-name')!.textContent = currentLocation;

  gameState = createInitialState(playerName);
  gameState.location.name = currentLocation;
  renderState(gameState);

  connectWebSocket();
  addNarrative(`Welcome, ${playerName}. You find yourself at ${currentLocation}.`, 'system');

  if (data.opening_narrative) {
    addNarrative(data.opening_narrative, 'narrative');
  }
}

// --- WebSocket ---
function connectWebSocket(): void {
  ws = new WebSocket(`${WS_URL}/${playerId}`);

  ws.onopen = () => {
    addNarrative('Connected.', 'system');
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };

  ws.onclose = () => {
    addNarrative('Connection lost. Refresh to reconnect.', 'system');
  };
}

function handleMessage(msg: { type: string; text?: string; location?: string }): void {
  switch (msg.type) {
    case 'narrative': {
      // Remove thinking indicator
      const thinking = narrativePane.querySelector('.thinking');
      if (thinking) thinking.remove();

      // Use text-renderer module
      const segments = parseNarrative(msg.text || '');
      const html = renderSegments(segments);
      addNarrativeHtml(html, 'narrative');

      // Apply state update if present
      const stateUpdate = (msg as any).state_update;
      if (stateUpdate && gameState) {
        if (stateUpdate.location) {
          gameState.location.name = stateUpdate.location;
          currentLocation = stateUpdate.location;
        }
        renderState(gameState);
      }
      break;
    }
    case 'thinking':
      addNarrative('The world responds', 'thinking');
      break;
    default:
      console.log('Unknown message:', msg);
  }
}

// --- Narrative Display ---
function addNarrativeHtml(html: string, type: string): void {
  const block = document.createElement('div');
  block.className = `narrative-block ${type}`;
  block.innerHTML = html;
  narrativePane.appendChild(block);
  narrativePane.scrollTop = narrativePane.scrollHeight;
}

function addNarrative(text: string, type: string): void {
  const block = document.createElement('div');
  block.className = `narrative-block ${type}`;

  if (type === 'thinking') {
    block.className = 'narrative-block thinking';
  }

  // Simple rich text: bold NPC names in quotes
  const html = text
    .replace(/\n/g, '<br>')
    .replace(/"([^"]+)"/g, '<span class="npc-name">"$1"</span>');

  block.innerHTML = html;
  narrativePane.appendChild(block);

  // Auto-scroll to bottom
  narrativePane.scrollTop = narrativePane.scrollHeight;
}

// --- Input ---
async function submitAction(action: string): Promise<void> {
  if (!action.trim()) return;

  // Show player action in narrative
  addNarrative(`> ${action}`, 'player-action');

  // Add to history
  commandHistory.unshift(action);
  historyIndex = -1;

  // Send to gateway
  await fetch(`${GATEWAY_URL}/api/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_id: playerId,
      action: action,
      location: currentLocation,
    }),
  });
}

// Make submitAction available globally for action buttons
(window as unknown as Record<string, unknown>).submitAction = submitAction;

// Input handling
actionInput.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    const action = actionInput.value.trim();
    if (action) {
      submitAction(action);
      actionInput.value = '';
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (historyIndex < commandHistory.length - 1) {
      historyIndex++;
      actionInput.value = commandHistory[historyIndex];
    }
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (historyIndex > 0) {
      historyIndex--;
      actionInput.value = commandHistory[historyIndex];
    } else {
      historyIndex = -1;
      actionInput.value = '';
    }
  }
});

// --- Init ---
// Auto-create session on load (prompt for name later)
const urlParams = new URLSearchParams(window.location.search);
const playerName = urlParams.get('name') || 'Wanderer';
createSession(playerName);
