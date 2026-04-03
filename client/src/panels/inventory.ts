// client/src/panels/inventory.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};

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
