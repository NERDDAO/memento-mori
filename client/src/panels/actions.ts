// src/panels/actions.ts
/** Actions panel — context-sensitive action buttons based on current state. */

import type { GameState } from '../state/game-state';

export function renderActionsPanel(
  container: HTMLElement,
  state: GameState,
  onAction: (action: string) => void,
): void {
  const actions: Array<{ label: string; action: string }> = [
    { label: 'Look around', action: 'look around' },
  ];

  state.location.npcs.forEach(npc => {
    actions.push({ label: `Talk to ${npc}`, action: `talk to ${npc}` });
  });

  state.location.items.forEach(item => {
    actions.push({ label: `Examine ${item}`, action: `examine ${item}` });
    actions.push({ label: `Pick up ${item}`, action: `pick up ${item}` });
  });

  container.innerHTML = actions
    .map(a => `<button class="action-btn" data-action="${a.action}">${a.label}</button>`)
    .join('');

  container.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      if (action) onAction(action);
    });
  });
}
