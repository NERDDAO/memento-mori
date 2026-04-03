// client/src/panels/present.ts
import type { GameState } from '../state/game-state';
import { onRoundStateChange, getRoundState, type RoundState } from '../state/round-state';

let currentBody: HTMLElement | null = null;

// Pulse NPC rows during npc_response phase
onRoundStateChange((rs: RoundState) => {
  if (!currentBody) return;
  const rows = currentBody.querySelectorAll('.npc-row');
  rows.forEach((row) => {
    (row as HTMLElement).classList.toggle('npc-thinking', rs.phase === 'npc_response');
  });
});

export function renderPresentPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  currentBody = body;
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  if (npcs.length === 0 && items.length === 0) {
    body.innerHTML = '<div class="empty-msg">Nothing here</div>';
    return;
  }
  const rs = getRoundState();
  const thinkingClass = rs.phase === 'npc_response' ? ' npc-thinking' : '';
  let html = '';
  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : (npc as any).name;
    const role = typeof npc === 'string' ? '' : ((npc as any).role || '');
    html += `<div class="npc-row${thinkingClass}" data-action="talk to ${name}" style="cursor:pointer"><span class="npc-diamond">\u25C6</span><span class="npc">${name}</span>${role ? `<span class="npc-role">\u2014 ${role}</span>` : ''}</div>`;
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
