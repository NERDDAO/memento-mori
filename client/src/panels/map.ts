// src/panels/map.ts
/** Location/map panel — renders current location with exits, NPCs, and items. */

import type { GameState } from '../state/game-state';

export function renderLocationPanel(
  container: HTMLElement,
  state: GameState,
  onAction: (action: string) => void,
): void {
  let html = `<div id="location-name" style="color: var(--text-location); margin-bottom: 8px; font-size: 15px;">${state.location.name}</div>`;

  if (state.location.exits.length) {
    html += '<div id="location-exits" style="margin-bottom: 8px;">';
    state.location.exits.forEach(exit => {
      html += `<button class="action-btn" data-action="go ${exit}">Go ${exit}</button>`;
    });
    html += '</div>';
  } else {
    html += '<div id="location-exits" style="font-size: 13px; color: var(--text-dim); font-family: system-ui, sans-serif;"></div>';
  }

  if (state.location.npcs.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Present:</span></div>';
    state.location.npcs.forEach(npc => {
      html += `<div style="font-size: 13px; color: var(--text-npc); padding: 2px 0;">${npc}</div>`;
    });
  }

  if (state.location.items.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Visible:</span></div>';
    state.location.items.forEach(item => {
      html += `<div style="font-size: 13px; color: var(--text-primary); padding: 2px 0;">${item}</div>`;
    });
  }

  container.innerHTML = html;

  container.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      if (action) onAction(action);
    });
  });
}
