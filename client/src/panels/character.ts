// client/src/panels/character.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';
import { textRow, coloredRow, emptyRow } from './panel-utils';

function barRow(
  label: string,
  value: number,
  max: number,
  barLen: number,
  fullColor: string,
  emptyColor: string,
  cols: number,
): CharCell[] {
  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const filled = Math.round(pct * barLen);
  const empty = barLen - filled;
  const valText = ` ${value}/${max}`;

  const segments: Array<{ text: string; fg: string }> = [
    { text: label + ' ', fg: theme.colors.dim },
    { text: '\u2588'.repeat(filled), fg: fullColor },
    { text: '\u2591'.repeat(empty), fg: emptyColor },
    { text: valText, fg: theme.colors.primary },
  ];

  return coloredRow(segments, cols);
}

export function renderCharacterPanel(panel: TerminalPanel, state: GameState): void {
  const p = state.player;
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  // Archetype label
  if (p.archetype) {
    cells.push(textRow(p.archetype, theme.colors.accent, cols));
    cells.push(emptyRow(cols));
  }

  // HP bar
  const hpColor = p.health / p.maxHealth > 0.3 ? theme.colors.heal : theme.colors.damage;
  cells.push(barRow('HP', p.health, p.maxHealth, 10, hpColor, theme.colors.dim, cols));

  // XP bar
  cells.push(barRow('XP', p.xp, p.xpThreshold, 10, theme.colors.accent, theme.colors.dim, cols));

  // Level
  cells.push(coloredRow([
    { text: 'Lv ', fg: theme.colors.dim },
    { text: String(p.level), fg: theme.colors.primary },
  ], cols));

  // Skills
  const skillEntries = Object.entries(p.skills).filter(([, v]) => v > 0);
  if (skillEntries.length > 0) {
    cells.push(emptyRow(cols));
    for (const [name, level] of skillEntries) {
      const dots = '\u25CF'.repeat(level) + '\u25CB'.repeat(Math.max(0, 5 - level));
      cells.push(coloredRow([
        { text: name + ' ', fg: theme.colors.primary },
        { text: dots, fg: theme.colors.accent },
      ], cols));
    }
  }

  panel.paint(cells);
}
