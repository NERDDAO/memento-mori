// client/src/panels/present.ts
import type { GameState } from '../state/game-state';

export function renderPresentPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  if (npcs.length === 0 && items.length === 0) {
    body.innerHTML = '<div class="empty-msg">Nothing here</div>';
    return;
  }
  let html = '';
  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : (npc as any).name;
    const role = typeof npc === 'string' ? '' : ((npc as any).role || '');
    html += `<div class="npc-row" data-action="talk to ${name}" style="cursor:pointer"><span class="npc-diamond">\u25C6</span><span class="npc">${name}</span>${role ? `<span class="npc-role">\u2014 ${role}</span>` : ''}</div>`;
  }
  for (const item of items) {
    const name = typeof item === 'string' ? item : (item as any).name;
    html += `<div class="item-row" data-action="examine ${name}" style="cursor:pointer"><span class="item-bullet">\u00B7</span> ${name}</div>`;
  }
  body.innerHTML = html;
  body.querySelectorAll('[data-action]').forEach((el) => {
    el.addEventListener('click', () => onAction((el as HTMLElement).dataset.action!));
  });
}
