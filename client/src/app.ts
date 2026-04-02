// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { createInitialState, applyStateUpdate, type GameState } from './state/game-state';
import { getSession, initSession, sendAction, setMessageHandler, setConnectionHandler } from './state/session';
import { parseNarrative, renderSegments, setKnownEntities } from './renderer/text-renderer';
import { initNarrative, type NarrativeController } from './panels/narrative';
import { initInput } from './panels/input';
import { initMapPanel, updateMap } from './panels/map';
import { WorldMapRenderer } from './map/world-renderer';
import type { WorldMap } from './map/types';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderExitsPanel } from './panels/exits';
import { renderPresentPanel } from './panels/present';
import { renderQuestLogPanel } from './panels/questlog';
import { renderFactionsPanel } from './panels/factions';
import { createWindow } from './ui/window';
import { createHeader, type WorldTime } from './ui/header';
import { createDialog } from './ui/dialog';
import { createWikiPanel } from './ui/wiki';
import { createStatusBar } from './ui/status';
import { hasProvider, connectWallet, formatAddress, getAddress } from './chain/wallet';
import type { RoomMap } from './map/types';

let gameState: GameState;
let narrative: NarrativeController;

let header: ReturnType<typeof createHeader>;
let npcDialog: ReturnType<typeof createDialog>;
let wiki: ReturnType<typeof createWikiPanel>;
let statusBar: ReturnType<typeof createStatusBar>;
let narrativeWin: ReturnType<typeof createWindow>;
let mapWin: ReturnType<typeof createWindow>;
let characterWin: ReturnType<typeof createWindow>;
let inventoryWin: ReturnType<typeof createWindow>;
let exitsWin: ReturnType<typeof createWindow>;
let presentWin: ReturnType<typeof createWindow>;
let questWin: ReturnType<typeof createWindow>;
let factionWin: ReturnType<typeof createWindow>;
let commandWin: ReturnType<typeof createWindow>;

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

// --- Panel rendering ---
function renderAllPanels(): void {
  if (!gameState) return;
  characterWin.setTitle(gameState.player.name || 'Character');
  renderCharacterPanel(characterWin.body, gameState);
  renderInventoryPanel(inventoryWin.body, gameState);
  exitsWin.setTitle(gameState.location.name || 'Exits');
  renderExitsPanel(exitsWin.body, gameState, handleAction);
  renderPresentPanel(presentWin.body, gameState, handleAction);
  renderQuestLogPanel(questWin.body, gameState.quests);
  renderFactionsPanel(factionWin.body, gameState.factions);
  updateMap(gameState, handleAction);

  // Show current location in wiki by default
  if (wiki && gameState.roomMap) {
    wiki.show(gameState.roomMap.id, gameState.roomMap.name);
  }
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
  if (!action.trim() || action.length > 500) return;
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
      statusBar.setPhase('synced');
      const segments = parseNarrative(msg.text || '');
      const html = renderSegments(segments);
      narrative.addHtml(html, 'narrative');

      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        const session = getSession();
        session.currentLocation = gameState.location.name;
        if (gameState.roomMap) registerMapEntities(gameState.roomMap);

        if (msg.state_update.world_time) {
          header.updateTime(msg.state_update.world_time as WorldTime);
          statusBar.setTick(msg.state_update.world_time.tick || 0);
        }

        renderAllPanels();

        // Display event notifications
        if (msg.state_update.events) {
          const events = msg.state_update.events;
          if (events.combat) {
            const c = events.combat;
            if (c.damage_dealt != null) {
              narrative.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ''}`, 'event-combat');
            }
            if (c.xp_gained) {
              narrative.addBlock(`[+${c.xp_gained} XP]`, 'event-xp');
            }
            if (c.target_dead) {
              narrative.addBlock(`${c.target_name || 'Target'} has been slain.`, 'event-death');
            }
          }
          if (events.inventory_changes) {
            for (const inv of events.inventory_changes) {
              const prefix = inv.event_type === 'DROP' ? '-' : '+';
              narrative.addBlock(`[${prefix}${inv.item_name}]`, 'event-item');
            }
          }
        }
      }

      // Check for death via structured event or text fallback
      if (msg.state_update?.status === 'dead' ||
          msg.state_update?.events?.combat?.target_dead ||
          (msg.text && msg.text.toLowerCase().includes('you have died'))) {
        showDeathScreen(msg.state_update?.cause || '');
      }
      break;
    }
    case 'thinking':
      narrative.showThinking();
      statusBar.setPhase('thinking');
      break;
    case 'death_feed': {
      const skull = '\u2620';
      const deathMsg = `${skull} ${msg.player_name || 'Unknown'} (Level ${msg.level || '?'}) fell at ${msg.location || 'unknown'}. ${msg.cause || ''}`;
      narrative.addBlock(deathMsg, 'death-feed');
      break;
    }
    case 'status':
      if (msg.phase) statusBar.setPhase(msg.phase);
      if (msg.tick != null) statusBar.setTick(msg.tick);
      if (msg.chain != null) statusBar.setChain(msg.chain);
      break;
    default:
      console.log('Unknown message:', msg);
  }
}

// --- Archetype selection ---
let selectedArchetype = '';

async function loadArchetypes(): Promise<void> {
  const container = document.getElementById('archetype-cards');
  if (!container) return;
  try {
    const resp = await fetch('http://localhost:8080/api/archetypes');
    const archetypes = await resp.json();
    container.innerHTML = archetypes.map((a: any) => `
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

// --- Character creation ---
async function enterWorld(playerName: string, walletAddress: string): Promise<void> {
  const overlay = document.getElementById('char-create-overlay')!;
  overlay.classList.add('hidden');

  const session = await initSession(playerName, walletAddress, selectedArchetype);
  gameState = createInitialState(playerName);
  gameState.location.name = session.currentLocation;
  // Apply archetype data from session response
  if ((session as any).archetype) gameState.player.archetype = (session as any).archetype;
  if ((session as any).health) gameState.player.health = (session as any).health;
  if ((session as any).max_health) gameState.player.maxHealth = (session as any).max_health;
  if ((session as any).skills) gameState.player.skills = (session as any).skills;

  if (!gameState.roomMap) {
    applyStateUpdate(gameState, { room_map: getThresholdMap() });
  }
  registerMapEntities(gameState.roomMap);
  renderAllPanels();
  narrative.addBlock(`Welcome, ${playerName}. You find yourself at ${session.currentLocation}.`, 'system');

  if (session.openingNarrative) {
    const segments = parseNarrative(session.openingNarrative);
    narrative.addHtml(renderSegments(segments), 'narrative');
  }

  (document.getElementById('action-input') as HTMLInputElement).focus();
}

// --- Helper: replace a mount div with a component element ---
function mount(mountId: string, el: HTMLElement): void {
  const mountEl = document.getElementById(mountId);
  if (mountEl && mountEl.parentElement) {
    mountEl.parentElement.replaceChild(el, mountEl);
  }
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  // 1. Header
  header = createHeader();
  mount('tui-header', header.el);

  // 2. Create windows
  narrativeWin = createWindow({ title: 'Narrative', id: 'narrative-win', className: 'resizable', scrollable: true });
  mapWin = createWindow({ title: 'Map', id: 'map-win' });
  characterWin = createWindow({ title: 'Character', id: 'character-win', className: 'sidebar-win resizable' });
  inventoryWin = createWindow({ title: 'Inventory', id: 'inventory-win', className: 'sidebar-win resizable' });
  exitsWin = createWindow({ title: 'Exits', id: 'exits-win', className: 'sidebar-win resizable' });
  presentWin = createWindow({ title: 'Present', id: 'present-win', className: 'sidebar-win resizable' });
  questWin = createWindow({ title: 'Quests', id: 'quest-win', className: 'sidebar-win resizable' });
  factionWin = createWindow({ title: 'Factions', id: 'faction-win', className: 'sidebar-win resizable' });
  commandWin = createWindow({ title: 'Command', id: 'command-win' });

  // 3. Mount windows by replacing mount divs
  mount('narrative-mount', narrativeWin.el);
  mount('map-mount', mapWin.el);
  mount('character-mount', characterWin.el);
  mount('inventory-mount', inventoryWin.el);
  mount('exits-mount', exitsWin.el);
  mount('present-mount', presentWin.el);
  mount('quest-mount', questWin.el);
  mount('faction-mount', factionWin.el);
  mount('command-mount', commandWin.el);

  // Status bar
  statusBar = createStatusBar();
  mount('status-mount', statusBar.el);

  // 4. Map toggle with 'm' key (not when input focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'm' && document.activeElement?.tagName !== 'INPUT') {
      mapWin.toggle();
    }
  });

  // 5. Dialog
  npcDialog = createDialog();
  mount('dialog-mount', npcDialog.el);

  // 6. Narrative
  narrative = initNarrative(narrativeWin.body);

  // 6b. Entity link clicks (delegated — works with virtual scroll)
  narrativeWin.body.addEventListener('click', (e: MouseEvent) => {
    const link = (e.target as HTMLElement).closest('.entity-link') as HTMLElement | null;
    if (!link) return;
    const name = link.dataset.entityName;
    const id = link.dataset.entityId;
    if (name) {
      // Show in wiki panel
      if (id) {
        wiki.show(id, name);
      } else {
        wiki.showByName(name);
      }
    }
  });

  // 7. Command input
  commandWin.body.innerHTML = `
    <span class="prompt-char">&gt;</span>
    <input type="text" id="action-input" placeholder="What do you do?" autocomplete="off" spellcheck="false" />
  `;
  const actionInput = commandWin.body.querySelector('#action-input') as HTMLInputElement;
  initInput(actionInput, handleAction);

  // 8. Map + Wiki — split map window body into canvas wrap + world map + wiki panel
  const mapCanvasWrap = document.createElement('div');
  mapCanvasWrap.className = 'map-canvas-wrap';
  const worldMapWrap = document.createElement('div');
  worldMapWrap.className = 'map-canvas-wrap';
  worldMapWrap.style.display = 'none';
  wiki = createWikiPanel();
  mapWin.body.appendChild(mapCanvasWrap);
  mapWin.body.appendChild(worldMapWrap);
  mapWin.body.appendChild(wiki.el);
  initMapPanel(mapCanvasWrap, handleAction);

  // World map renderer
  const worldRenderer = new WorldMapRenderer(worldMapWrap);
  let worldMapData: WorldMap | null = null;
  let showingWorldMap = false;

  worldRenderer.setClickHandler((roomId) => {
    if (roomId && wiki) {
      const room = worldMapData?.rooms.find(r => r.id === roomId);
      if (room) wiki.show(roomId, room.name);
    }
  });

  async function fetchWorldMap(): Promise<void> {
    try {
      const resp = await fetch('http://localhost:8080/api/worldmap');
      const data = await resp.json();
      if (data.rooms && data.rooms.length > 0) {
        worldMapData = {
          rooms: data.rooms,
          connections: data.connections,
          currentRoom: gameState?.location?.name || '',
        };
      }
    } catch { /* world map unavailable */ }
  }

  function toggleWorldMap(): void {
    showingWorldMap = !showingWorldMap;
    mapCanvasWrap.style.display = showingWorldMap ? 'none' : '';
    worldMapWrap.style.display = showingWorldMap ? '' : 'none';
    mapWin.setTitle(showingWorldMap ? 'World Map' : 'Map');
    if (showingWorldMap && worldMapData) {
      worldMapData.currentRoom = gameState?.location?.name || '';
      worldRenderer.render(worldMapData);
    }
  }

  // 'w' key toggles world map (when input not focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'w' && document.activeElement?.tagName !== 'INPUT') {
      if (!worldMapData) fetchWorldMap().then(() => toggleWorldMap());
      else toggleWorldMap();
    }
  });

  // 9. Wire handlers
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
    document.getElementById('death-overlay')!.classList.add('hidden');
    document.getElementById('char-create-overlay')!.classList.remove('hidden');
    narrativeWin.body.innerHTML = '';
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
      // Show archetype selection (or skip to name if no archetype step)
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
    if (wallet) enterWorld(name, wallet);
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      const wallet = getAddress();
      if (wallet) enterWorld(name, wallet);
    }
  });
});
