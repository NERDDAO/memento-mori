// src/state/game-state.ts
/** Client-side game state — mirrors a subset of the KG. */

import type { RoomMap } from '../map/types';
import type { StateUpdate } from '../types/schema.generated';
import { SCHEMA_VERSION } from '../types/schema.generated';

export interface LocationExit {
  direction: string;
  name: string;
}

export interface LocationEntity {
  name: string;
  id: string;
  role?: string;
}

export interface GameState {
  player: {
    name: string;
    archetype: string;
    level: number;
    health: number;
    maxHealth: number;
    xp: number;
    xpThreshold: number;
    skills: Record<string, number>;
  };
  location: {
    name: string;
    description: string;
    exits: LocationExit[];
    npcs: LocationEntity[];
    items: LocationEntity[];
  };
  inventory: Array<{
    name: string;
    rarity: string;
    equipped: boolean;
  }>;
  quests: Array<{
    name: string;
    description: string;
    currentStage: number;
    totalStages: number;
    giver: string;
    completed: boolean;
  }>;
  factions: Array<{
    name: string;
    reputation: number;
    disposition: string;
  }>;
  roomMap: RoomMap | null;
}

export function createInitialState(playerName: string): GameState {
  return {
    player: {
      name: playerName,
      archetype: '',
      level: 1,
      health: 100,
      maxHealth: 100,
      xp: 0,
      xpThreshold: 100,
      skills: {},
    },
    location: {
      name: 'Unknown',
      description: '',
      exits: [],
      npcs: [],
      items: [],
    },
    inventory: [],
    quests: [],
    factions: [],
    roomMap: null,
  };
}

export function applyStateUpdate(state: GameState, update: StateUpdate): void {
  // Schema version check — warn if server sends a newer schema
  if (update.schema_version && update.schema_version > SCHEMA_VERSION) {
    console.warn(`Server schema version ${update.schema_version} > client ${SCHEMA_VERSION}. Please refresh.`);
  }
  if (update.location) state.location.name = update.location;
  if (update.health != null) state.player.health = update.health;
  if (update.max_health != null) state.player.maxHealth = update.max_health;
  if (update.level != null) state.player.level = update.level;
  if (update.xp != null) state.player.xp = update.xp;
  if (update.exits) state.location.exits = update.exits;
  if (update.npcs) state.location.npcs = update.npcs;
  if (update.items) state.location.items = update.items;
  if (update.inventory) {
    state.inventory = update.inventory.map((i: any) => ({
      name: i.name || '?',
      rarity: i.rarity || 'common',
      equipped: i.equipped || false,
    }));
  }
  if (update.skills) state.player.skills = update.skills as Record<string, number>;
  if (update.room_map) {
    state.roomMap = update.room_map;
    // Sync roomMap entities into location for sidebar panels
    const rm = update.room_map;
    if (rm.name) state.location.name = rm.name;
    if (rm.exits) {
      state.location.exits = rm.exits.map((e: any) => ({
        direction: e.direction || '',
        name: e.target || e.name || '',
      }));
    }
    if (rm.npcs) {
      state.location.npcs = rm.npcs.map((n: any) => ({
        name: n.name || '',
        id: n.id || '',
        role: n.role || '',
      }));
    }
    if (rm.items) {
      state.location.items = rm.items.map((i: any) => ({
        name: i.name || '',
        id: i.id || '',
      }));
    }
  }
  if (update.active_quests) {
    state.quests = (update.active_quests as any[]).map((q: any) => ({
      name: q.name || '',
      description: q.description || '',
      currentStage: q.current_stage || 0,
      totalStages: q.total_stages || 0,
      giver: q.giver || '',
      completed: q.completed || false,
    }));
  }
  if (update.factions) {
    state.factions = (update.factions as any[]).map((f: any) => ({
      name: f.name || '',
      reputation: f.reputation || 0,
      disposition: f.disposition || 'neutral',
    }));
  }
}

/** Update DOM elements to reflect current state. */
export function renderState(state: GameState): void {
  const set = (id: string, text: string) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  set('char-name', state.player.name);
  set('char-level', String(state.player.level));
  set('char-health', `${state.player.health}/${state.player.maxHealth}`);
  set('char-xp', `${state.player.xp}/${state.player.xpThreshold}`);
  set('location-name', state.location.name);

  // Health bar
  const fill = document.getElementById('health-fill');
  if (fill) {
    const pct = Math.max(0, Math.min(100, (state.player.health / state.player.maxHealth) * 100));
    fill.style.width = `${pct}%`;
  }

  // Exits
  const exitsEl = document.getElementById('location-exits');
  if (exitsEl) {
    exitsEl.textContent = state.location.exits.length
      ? `Exits: ${state.location.exits.join(', ')}`
      : '';
  }

  // Inventory
  const invEl = document.getElementById('inventory-list');
  if (invEl) {
    if (state.inventory.length === 0) {
      invEl.innerHTML = '<div class="inventory-item" style="color: var(--text-dim);">Empty</div>';
    } else {
      invEl.innerHTML = state.inventory
        .map(item => `<div class="inventory-item">${item.name} <span style="color: var(--text-dim);">[${item.rarity}]</span></div>`)
        .join('');
    }
  }
}
