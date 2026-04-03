// client/src/panels/exits.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

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

export function renderExitsPanel(
  panel: TerminalPanel, state: GameState, onAction: (action: string) => void,
): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  panel.clearHitRegions();

  if (state.location.exits.length === 0) {
    cells.push(textRow('None', theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }

  for (const e of state.location.exits) {
    const dir = typeof e === 'string' ? e : e.direction;
    const dest = typeof e === 'string' ? '' : e.name;
    const label = dir.charAt(0).toUpperCase() + dir.slice(1);

    const segments: Array<{ text: string; fg: string }> = [
      { text: '\u2192 ' + label, fg: theme.colors.location },
    ];
    if (dest) {
      segments.push({ text: '  ' + dest, fg: theme.colors.dim });
    }

    const rowIdx = cells.length;
    cells.push(coloredRow(segments, cols));

    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `go ${dir}` },
    });
  }

  panel.paint(cells);
}
