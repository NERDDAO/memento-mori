// client/src/panels/factions.ts
import type { GameState } from '../state/game-state';
import type { CharCell } from '../renderer/canvas-text';
import type { PanelResult } from '../canvas/types';
import { theme } from '../renderer/theme';
import { textRow, coloredRow, emptyRow } from './panel-utils';

function dispositionColor(disposition: string): string {
  switch (disposition) {
    case 'hostile':    return theme.colors.damage;
    case 'unfriendly': return theme.colors.damage;
    case 'friendly':   return theme.colors.heal;
    case 'allied':     return theme.colors.heal;
    default:           return theme.colors.primary;
  }
}


export function renderFactionsPanel(cols: number, _rows: number, factions: GameState['factions']): PanelResult {
  const cells: CharCell[][] = [];

  if (!factions || factions.length === 0) {
    cells.push(textRow('No known factions', theme.colors.dim, cols));
    return { cells };
  }

  for (let i = 0; i < factions.length; i++) {
    const f = factions[i];
    if (i > 0) cells.push(emptyRow(cols));

    // Faction name
    cells.push(textRow(f.name, theme.colors.primary, cols));

    // Reputation bar + disposition
    const normalized = Math.round((f.reputation + 1) * 5);
    const clamped = Math.max(0, Math.min(10, normalized));
    const barColor = dispositionColor(f.disposition);

    cells.push(coloredRow([
      { text: '\u2588'.repeat(clamped), fg: barColor },
      { text: '\u2591'.repeat(10 - clamped), fg: theme.colors.dim },
      { text: ' ' + f.disposition, fg: barColor },
    ], cols));
  }

  return { cells };
}
