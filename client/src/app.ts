// src/app.ts
/**
 * Memento Mori — MUD Client
 * Thin orchestrator: wires session, panels, and message handling together.
 */

import { createInitialState, applyStateUpdate, type GameState } from './state/game-state';
import { getSession, sendAction, setMessageHandler, setConnectionHandler, GATEWAY_URL } from './state/session';
import { updateRoundState, type PhaseMessage } from './state/round-state';
import { setKnownEntities } from './renderer/text-renderer';
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
import { createInventoryModal } from './ui/inventory-modal';
import { createWikiPanel } from './ui/wiki';
import { createStatusBar } from './ui/status';
import { hasProvider, connectWallet, formatAddress, getAddress } from './chain/wallet';
import type { RoomMap } from './map/types';
import { createOverlayManager, type OverlayManager } from './ui/overlay';
import { startGame } from './flows/session-flow';
import { initInventoryApi } from './state/inventory-api';
import { setManageInventoryCallback } from './panels/inventory';

let gameState: GameState;
let narrative: NarrativeController;
let eventsFeed: NarrativeController;

let header: ReturnType<typeof createHeader>;
let npcDialog: ReturnType<typeof createDialog>;
let wiki: ReturnType<typeof createWikiPanel>;
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

// --- Panel rendering ---
function renderAllPanels(): void {
  if (!gameState) return;
  characterWin.setTitle(gameState.player.name || 'Character');
  renderCharacterPanel(characterWin.panel!, gameState);
  renderInventoryPanel(inventoryWin.panel!, gameState);
  exitsWin.setTitle(gameState.location.name || 'Exits');
  renderExitsPanel(exitsWin.panel!, gameState, handleAction);
  renderPresentPanel(presentWin.panel!, gameState, handleAction);
  renderQuestLogPanel(questWin.panel!, gameState.quests);
  renderFactionsPanel(factionWin.panel!, gameState.factions);
  updateMap(gameState, handleAction);

  // Show current location in wiki by default
  if (wiki && gameState.roomMap) {
    wiki.show(gameState.roomMap.id, gameState.roomMap.name);
  }
}

// --- Action handling ---
async function handleAction(action: string): Promise<void> {
  if (!action.trim() || action.length > 500) return;
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

// --- WebSocket message handling ---
function handleMessage(msg: any): void {
  switch (msg.type) {
    case 'narrative': {
      narrative.removeThinking();
      const channel = msg.channel || 'narrative';

      // Route by channel: narrative prose stays in narrative, events go to events feed
      if (channel === 'events') {
        eventsFeed.addBlock(msg.text || '', 'event');
      } else if (channel === 'ooc') {
        eventsFeed.addBlock(msg.text || '', 'ooc');
      } else if (msg.npc) {
        // NPC dialogue — remove thinking indicator and show with name header
        const npcKey = msg.npc_username || msg.npc.toLowerCase().replace(/\s+/g, '-');
        narrative.removeBlockById(`npc-status-${npcKey}`);
        narrative.addBlock(`${msg.npc}`, 'npc-name');
        narrative.addBlock(msg.text || '', 'npc-dialogue');
      } else {
        narrative.addBlock(msg.text || '', 'narrative');
      }

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

        // Display event notifications in the events feed
        if (msg.state_update.events) {
          const events = msg.state_update.events;
          if (events.combat) {
            const c = events.combat;
            if (c.damage_dealt != null) {
              eventsFeed.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ''}`, 'event-combat');
            }
            if (c.xp_gained) {
              eventsFeed.addBlock(`[+${c.xp_gained} XP]`, 'event-xp');
            }
            if (c.target_dead) {
              eventsFeed.addBlock(`${c.target_name || 'Target'} has been slain.`, 'event-death');
            }
          }
          if (events.inventory_changes) {
            for (const inv of events.inventory_changes) {
              const prefix = inv.event_type === 'DROP' ? '-' : '+';
              eventsFeed.addBlock(`[${prefix}${inv.item_name}]`, 'event-item');
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
    case 'death_feed': {
      const skull = '\u2620';
      const deathMsg = `${skull} ${msg.player_name || 'Unknown'} (Level ${msg.level || '?'}) fell at ${msg.location || 'unknown'}. ${msg.cause || ''}`;
      narrative.addBlock(deathMsg, 'death-feed');
      break;
    }
    case 'scene_art': {
      // Render scene art as a narrative block
      const artText = (msg.lines || []).join('\n');
      if (artText) {
        narrative.addBlock(artText, 'scene-art');
      }
      break;
    }
    case 'entity_art': {
      // Cache on the entity in game state
      if (msg.entity_id && gameState) {
        const npc = gameState.location.npcs.find(n => n.id === msg.entity_id);
        const item = gameState.location.items.find(i => i.id === msg.entity_id);
        const entity = npc || item;
        if (entity) {
          entity.ascii_art = (msg.lines || []).join('\n');
        }
      }
      break;
    }
    case 'npc_status': {
      // NPC thinking/status — replace previous status for this NPC
      const npcKey = msg.npc_username || msg.npc || 'unknown';
      narrative.replaceBlock(`npc-status-${npcKey}`, `${msg.npc}: ${msg.text}`, 'npc-status');
      break;
    }
    case 'phase': {
      updateRoundState(msg as PhaseMessage);
      // Show phase progress in events feed
      const phase = msg.phase || '';
      const crew = msg.crew || '';
      if (phase === 'resolving' && crew) {
        eventsFeed.replaceBlock('phase-progress', `[${crew}]`, 'event');
      } else if (phase === 'npc_response') {
        eventsFeed.replaceBlock('phase-progress', '[waiting for NPCs]', 'event');
      } else if (phase === 'ready') {
        eventsFeed.removeBlockById('phase-progress');
      }
      break;
    }
    case 'status':
      if (msg.tick != null) statusBar.setTick(msg.tick);
      if (msg.chain != null) statusBar.setChain(msg.chain);
      break;
    case 'player_joined': {
      if (gameState) {
        const exists = gameState.location.players.some(p => p.id === msg.player_id);
        if (!exists) {
          gameState.location.players.push({ name: msg.player_name, id: msg.player_id });
          renderPresentPanel(presentWin.panel!, gameState, handleAction);
          narrative.addBlock(`${msg.player_name} arrived.`, 'system');
        }
      }
      break;
    }
    case 'player_left': {
      if (gameState) {
        gameState.location.players = gameState.location.players.filter(p => p.id !== msg.player_id);
        renderPresentPanel(presentWin.panel!, gameState, handleAction);
        narrative.addBlock(`${msg.player_name} departed.`, 'system');
      }
      break;
    }
    case 'presence': {
      if (gameState) {
        gameState.location.players = (msg.players || []).map((p: { player_name: string; player_id: string }) => ({
          name: p.player_name,
          id: p.player_id,
        }));
        renderPresentPanel(presentWin.panel!, gameState, handleAction);
      }
      break;
    }
    case 'state_update': {
      // Standalone state_update (from inventory actions, not embedded in narrative)
      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        renderAllPanels();
        if (invModal.active) invModal.refresh();
      }
      break;
    }
    case 'room_items_changed': {
      // Ground items changed — refresh room manifest
      // The next state_update will have the updated room_map
      if (invModal.active) invModal.refresh();
      break;
    }
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
        initInventoryApi(gameState, session.playerId, renderAllPanels);
        if (gameState.roomMap) registerMapEntities(gameState.roomMap);
        renderAllPanels();
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
  narrativeWin = createWindow({ title: 'Narrative', id: 'narrative-win', className: 'resizable' });
  eventsWin = createWindow({ title: 'Events', id: 'events-win' });
  mapWin = createWindow({ title: 'Map', id: 'map-win' });
  characterWin = createWindow({ title: 'Character', id: 'character-win', className: 'sidebar-win resizable', canvas: true });
  inventoryWin = createWindow({ title: 'Inventory', id: 'inventory-win', className: 'sidebar-win resizable', canvas: true });
  exitsWin = createWindow({ title: 'Exits', id: 'exits-win', className: 'sidebar-win resizable', canvas: true });
  presentWin = createWindow({ title: 'Present', id: 'present-win', className: 'sidebar-win resizable', canvas: true });
  questWin = createWindow({ title: 'Quests', id: 'quest-win', className: 'sidebar-win resizable', canvas: true });
  factionWin = createWindow({ title: 'Factions', id: 'faction-win', className: 'sidebar-win resizable', canvas: true });
  commandWin = createWindow({ title: 'Command', id: 'command-win' });

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
  statusBar = createStatusBar();
  mount('status-mount', statusBar.el);

  // Overlay manager
  overlays = createOverlayManager(['char-create', 'death', 'loading', 'intro']);

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
    if (detail.questName && gameState) {
      const quest = gameState.quests.find(q => q.name === detail.questName);
      if (quest) npcDialog.showQuest(quest);
    }
  });

  // 4. Map toggle with 'm' key (not when input focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'm' && document.activeElement?.tagName !== 'INPUT') {
      mapWin.toggle();
    }
  });

  // 5. Dialog
  npcDialog = createDialog();
  mount('dialog-mount', npcDialog.el);

  // 5b. Inventory modal
  invModal = createInventoryModal(() => gameState);
  document.body.appendChild(invModal.el);
  setManageInventoryCallback(() => invModal.open());

  // 'i' key toggles inventory modal (when input not focused)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'i' && document.activeElement?.tagName !== 'INPUT') {
      if (invModal.active) invModal.close();
      else invModal.open();
    }
  });

  // 6. Narrative + Events feed
  narrative = initNarrative(narrativeWin.body);
  eventsFeed = initNarrative(eventsWin.body);

  // 6b. Entity clicks from canvas narrative panel
  narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
    const { entityId, entityName } = (e as CustomEvent).detail;
    if (entityName) {
      if (entityId) {
        wiki.show(entityId, entityName);
      } else {
        wiki.showByName(entityName);
      }
    }
  });

  // 7. Command input
  commandWin.body.innerHTML = `
    <span class="prompt-char">&gt;</span>
    <input type="text" id="action-input" placeholder="What do you do?" autocomplete="off" spellcheck="false" />
  `;
  const actionInput = commandWin.body.querySelector('#action-input') as HTMLInputElement;
  initInput(actionInput, handleAction, () => ({
    npcs: gameState?.location?.npcs || [],
    players: gameState?.location?.players || [],
  }));

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
      const resp = await fetch(`${GATEWAY_URL}/api/worldmap`);
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
    overlays.dismiss('death');
    overlays.show('char-create');
    narrative = initNarrative(narrativeWin.body);
    narrative.canvas.addEventListener('narrative-entity-click', (e: Event) => {
      const { entityId, entityName } = (e as CustomEvent).detail;
      if (entityName) {
        if (entityId) wiki.show(entityId, entityName);
        else wiki.showByName(entityName);
      }
    });
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
