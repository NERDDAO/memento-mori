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
    .map((dir) =>
      `<div class="exit-row" data-dir="${dir}"><span class="exit-dir">\u2192 ${dir.charAt(0).toUpperCase() + dir.slice(1)}</span></div>`,
    )
    .join('');
  body.querySelectorAll('.exit-row').forEach((row) => {
    row.addEventListener('click', () => onAction(`go ${(row as HTMLElement).dataset.dir}`));
  });
}
