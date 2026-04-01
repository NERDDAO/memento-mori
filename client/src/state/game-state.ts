// src/state/game-state.ts
/** Client-side game state — mirrors a subset of the KG. */

export interface GameState {
  player: {
    name: string;
    level: number;
    health: number;
    maxHealth: number;
    xp: number;
    xpThreshold: number;
  };
  location: {
    name: string;
    description: string;
    exits: string[];
    npcs: string[];
    items: string[];
  };
  inventory: Array<{
    name: string;
    rarity: string;
    equipped: boolean;
  }>;
}

export function createInitialState(playerName: string): GameState {
  return {
    player: {
      name: playerName,
      level: 1,
      health: 100,
      maxHealth: 100,
      xp: 0,
      xpThreshold: 100,
    },
    location: {
      name: 'Unknown',
      description: '',
      exits: [],
      npcs: [],
      items: [],
    },
    inventory: [],
  };
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
