// client/src/panels/inventory.ts
import type { GameState } from '../state/game-state';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};

export function renderInventoryPanel(body: HTMLElement, state: GameState): void {
  if (state.inventory.length === 0) {
    body.innerHTML = '<div class="empty-msg">Empty</div>';
    return;
  }
  body.innerHTML = state.inventory
    .map((item) => {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      const equip = item.equipped ? '<span class="item-equip">E</span>' : '';
      return `<div class="item-row"><span class="item-bullet">\u00B7</span> <span style="color:${color}">${item.name}</span>${equip}</div>`;
    })
    .join('');
}
