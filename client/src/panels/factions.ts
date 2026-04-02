// client/src/panels/factions.ts
import type { GameState } from '../state/game-state';

function dispositionColor(disposition: string): string {
  switch (disposition) {
    case 'hostile': return 'faction-hostile';
    case 'unfriendly': return 'faction-hostile';
    case 'friendly': return 'faction-friendly';
    case 'allied': return 'faction-friendly';
    default: return 'faction-neutral';
  }
}

export function renderFactionsPanel(body: HTMLElement, factions: GameState['factions']): void {
  if (!factions || factions.length === 0) {
    body.innerHTML = '<div class="empty-msg">No known factions</div>';
    return;
  }

  const html = factions.map(f => {
    // Map -1..1 reputation to a 0..10 bar
    const normalized = Math.round((f.reputation + 1) * 5);
    const clamped = Math.max(0, Math.min(10, normalized));
    const colorClass = dispositionColor(f.disposition);
    const bar = '\u2588'.repeat(clamped) + '\u2591'.repeat(10 - clamped);

    return `
      <div class="faction-entry">
        <div class="faction-name">${f.name}</div>
        <div class="faction-bar">
          <span class="${colorClass}">${bar}</span>
          <span class="faction-disposition">${f.disposition}</span>
        </div>
      </div>
    `;
  }).join('');

  body.innerHTML = html;
}
