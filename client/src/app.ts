// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { type GameState } from './state/game-state';
import { getSession, sendAction, setMessageHandler, setConnectionHandler, GATEWAY_URL } from './state/session';
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
import { hasProvider, connectWallet, formatAddress, getAddress } from './chain/wallet';
import type { RoomMap } from './map/types';
import { type OverlayManager } from './ui/overlay';
import { startGame } from './flows/session-flow';
import { initInventoryApi } from './state/inventory-api';
import { initPanels } from './panel-setup';
import { initHotkeys } from './hotkeys';

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

// --- Archetype selection ---
let selectedArchetype = '';

async function loadArchetypes(): Promise<void> {
  const container = document.getElementById('archetype-cards');
  if (!container) return;
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/archetypes`);
    const archetypes = await resp.json();
    container.innerHTML = archetypes.map((a: { name: string; description: string; stats: { health?: number }; skills: Record<string, number>; starting_items: string[] }) => `
      <div class="archetype-card" data-archetype="${a.name}">
        <div class="archetype-name">${a.name}</div>
        <div class="archetype-desc">${a.description}</div>
        <div class="archetype-stats">HP: ${a.stats.health || 100} | Skills: ${Object.keys(a.skills).join(', ')}</div>
        <div class="archetype-items">${a.starting_items.join(', ')}</div>
      </div>
    `).join('');
    container.addEventListener('click', (e: MouseEvent) => {
      const card = (e.target as HTMLElement).closest('.archetype-card') as HTMLElement | null;
      if (!card) return;
      container.querySelectorAll('.archetype-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedArchetype = card.dataset.archetype || '';
    });
  } catch {
    // Fallback — no archetype selection available
    container.innerHTML = '<div style="color:var(--text-dim)">Archetypes unavailable</div>';
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

// --- Character picker (returning players) ---
interface CharacterSummary {
  player_id: string;
  player_name: string;
  archetype?: string;
  health?: number;
  is_dead?: boolean;
  death_cause?: string;
  death_location?: string;
}

function showCharacterPicker(characters: CharacterSummary[], walletAddress: string): void {
  const walletStepEl = document.getElementById('wallet-step')!;
  const pickerDiv = document.createElement('div');
  pickerDiv.id = 'char-picker';

  const alive = characters.filter((c: CharacterSummary) => !c.is_dead);
  const dead = characters.filter((c: CharacterSummary) => c.is_dead);

  let html = '<div class="picker-title">Your Characters</div>';

  // Living characters
  for (const c of alive) {
    html += `
      <div class="picker-card" data-player-id="${c.player_id}">
        <span class="picker-name">${c.player_name}</span>
        <span class="picker-info">${c.archetype || 'Unknown'} \u00B7 HP ${c.health}</span>
      </div>`;
  }

  // Memorial (dead) characters
  for (const c of dead) {
    html += `
      <div class="picker-card picker-memorial">
        <span class="picker-name">\u2620 ${c.player_name}</span>
        <span class="picker-info">${c.death_cause || 'Perished'} \u00B7 Fell at ${c.death_location || 'unknown'}</span>
      </div>`;
  }

  html += `
    <div class="picker-card picker-new">
      <span class="picker-name">+ New Character</span>
    </div>`;

  pickerDiv.innerHTML = html;
  walletStepEl.after(pickerDiv);

  pickerDiv.addEventListener('click', (e: MouseEvent) => {
    const card = (e.target as HTMLElement).closest('.picker-card') as HTMLElement | null;
    if (!card || card.classList.contains('picker-memorial')) return;
    if (card.classList.contains('picker-new')) {
      pickerDiv.remove();
      const archStep = document.getElementById('archetype-step');
      if (archStep) {
        archStep.classList.remove('hidden');
        loadArchetypes();
      } else {
        document.getElementById('name-step')!.classList.remove('hidden');
      }
    } else {
      const playerId = card.dataset.playerId!;
      const playerName = card.querySelector('.picker-name')!.textContent || 'Wanderer';
      pickerDiv.remove();
      overlays.dismiss('char-create');
      enterGame({ playerName, walletAddress, isReturning: true, playerId });
    }
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

  // Hotkeys: m (map), i (inventory), k (codex), narrative-entity-click
  initHotkeys({ mapWin, invModal, codex, narrative });

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

  // 10. Death screen — new character button
  document.getElementById('death-restart-btn')!.addEventListener('click', () => {
    overlays.dismiss('death');
    overlays.show('char-create');
    narrative = initNarrative(narrativeWin.body);
    initHotkeys({ mapWin, invModal, codex, narrative });
    (document.getElementById('char-name-input') as HTMLInputElement).focus();
  });

  // Character creation — two-step wallet gate
  const walletConnectBtn = document.getElementById('wallet-connect-btn')!;
  const walletStep = document.getElementById('wallet-step')!;
  const nameStep = document.getElementById('name-step')!;
  const walletPrompt = document.getElementById('wallet-prompt')!;
  const walletNoProvider = document.getElementById('wallet-no-provider')!;
  const walletAddressEl = document.getElementById('wallet-address')!;
  const nameInput = document.getElementById('char-name-input') as HTMLInputElement;
  const enterBtn = document.getElementById('char-create-btn')!;

  // Check for wallet provider on load
  if (!hasProvider()) {
    walletConnectBtn.classList.add('hidden');
    walletNoProvider.classList.remove('hidden');
  }

  const archetypeStep = document.getElementById('archetype-step');

  walletConnectBtn.addEventListener('click', async () => {
    try {
      walletPrompt.textContent = 'Connecting...';
      const addr = await connectWallet();
      walletStep.classList.add('hidden');
      walletAddressEl.textContent = `\u2713 ${formatAddress(addr)}`;

      // Check for existing characters
      try {
        const charResp = await fetch(`${GATEWAY_URL}/api/session/characters`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet_address: addr }),
        });
        const charData = await charResp.json();
        if (charData.characters && charData.characters.length > 0) {
          showCharacterPicker(charData.characters, addr);
          return;
        }
      } catch { /* no existing characters, proceed to creation */ }

      // No existing characters — proceed to archetype/name selection
      if (archetypeStep) {
        archetypeStep.classList.remove('hidden');
        loadArchetypes();
      } else {
        nameStep.classList.remove('hidden');
        nameInput.focus();
      }
    } catch {
      walletPrompt.textContent = 'Connection rejected. Try again.';
    }
  });

  // Archetype → Name step transition
  const archetypeNextBtn = document.getElementById('archetype-next-btn');
  if (archetypeNextBtn) {
    archetypeNextBtn.addEventListener('click', () => {
      if (archetypeStep) archetypeStep.classList.add('hidden');
      nameStep.classList.remove('hidden');
      nameInput.focus();
    });
  }

  enterBtn.addEventListener('click', () => {
    const name = nameInput.value.trim() || 'Wanderer';
    const wallet = getAddress();
    if (wallet) {
      overlays.dismiss('char-create');
      enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
    }
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      const wallet = getAddress();
      if (wallet) {
        overlays.dismiss('char-create');
        enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
      }
    }
  });
});
