// client/src/panels/exits.ts
import type { GameState } from '../state/game-state';

export function renderExitsPanel(
  body: HTMLElement, state: GameState, onAction: (action: string) => void,
): void {
  if (state.location.exits.length === 0) {
    body.innerHTML = '<div class="empty-msg">None</div>';
    return;
  }
  body.innerHTML = state.location.exits
    .map((e) => {
      const dir = typeof e === 'string' ? e : e.direction;
      const dest = typeof e === 'string' ? '' : e.name;
      const label = dir.charAt(0).toUpperCase() + dir.slice(1);
      return `<div class="exit-row" data-dir="${dir}"><span class="exit-dir">\u2192 ${label}</span>${dest ? `<span class="exit-dest">${dest}</span>` : ''}</div>`;
    })
    .join('');
  body.querySelectorAll('.exit-row').forEach((row) => {
    row.addEventListener('click', () => onAction(`go ${(row as HTMLElement).dataset.dir}`));
  });
}
