// src/panels/inventory.ts
/** Inventory panel — renders item list with rarity colors. */

import type { GameState } from '../state/game-state';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080',
  uncommon: '#1eff00',
  rare: '#0070dd',
  epic: '#a335ee',
  legendary: '#ff8000',
};

export function renderInventoryPanel(container: HTMLElement, state: GameState): void {
  if (state.inventory.length === 0) {
    container.innerHTML = '<div class="inventory-item" style="color: var(--text-dim);">Empty</div>';
    return;
  }
  container.innerHTML = state.inventory
    .map(item => {
      const color = RARITY_COLORS[item.rarity] || 'var(--text-dim)';
      return `<div class="inventory-item">
      ${item.name} <span style="color: ${color};">[${item.rarity}]</span>
      ${item.equipped ? ' <span style="color: var(--accent);">equipped</span>' : ''}
    </div>`;
    })
    .join('');
}
