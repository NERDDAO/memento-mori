// client/src/panels/factions.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

function dispositionColor(disposition: string): string {
  switch (disposition) {
    case 'hostile':    return theme.colors.damage;
    case 'unfriendly': return theme.colors.damage;
    case 'friendly':   return theme.colors.heal;
    case 'allied':     return theme.colors.heal;
    default:           return theme.colors.primary;
  }
}

function coloredRow(segments: Array<{ text: string; fg: string; attrs?: number }>, cols: number): CharCell[] {
  const row: CharCell[] = [];
  for (const seg of segments) {
    for (const ch of seg.text) {
      row.push({ char: ch, fg: seg.fg, attrs: seg.attrs });
    }
  }
  while (row.length < cols) {
    row.push({ char: ' ', fg: theme.colors.primary });
  }
  return row;
}

function textRow(text: string, fg: string, cols: number): CharCell[] {
  const row: CharCell[] = [];
  for (let i = 0; i < cols; i++) {
    row.push({ char: i < text.length ? text[i] : ' ', fg });
  }
  return row;
}

function emptyRow(cols: number): CharCell[] {
  return Array(cols).fill({ char: ' ', fg: theme.colors.primary });
}

export function renderFactionsPanel(panel: TerminalPanel, factions: GameState['factions']): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  if (!factions || factions.length === 0) {
    cells.push(textRow('No known factions', theme.colors.dim, cols));
    panel.paint(cells);
    return;
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

  panel.paint(cells);
}
