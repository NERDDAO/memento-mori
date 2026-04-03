// client/src/panels/inventory.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';
import { textRow, coloredRow } from './panel-utils';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};


export function renderInventoryPanel(panel: TerminalPanel, state: GameState): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  if (state.inventory.length === 0) {
    cells.push(textRow('Empty', theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }

  for (const item of state.inventory) {
    const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
    const segments: Array<{ text: string; fg: string }> = [
      { text: '\u00B7 ', fg: theme.colors.dim },
      { text: item.name, fg: color },
    ];
    if (item.equipped) {
      segments.push({ text: ' [E]', fg: theme.colors.heal });
    }
    cells.push(coloredRow(segments, cols));
  }

  panel.paint(cells);
}
