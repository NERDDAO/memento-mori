// client/src/panels/present.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { ATTR_BOLD } from '../renderer/canvas-text';
import { getRoundState } from '../state/round-state';
import { theme } from '../renderer/theme';
import { textRow, coloredRow, emptyRow } from './panel-utils';


export function renderPresentPanel(
  panel: TerminalPanel, state: GameState, onAction: (action: string) => void,
): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  const players = state.location.players || [];

  panel.clearHitRegions();

  if (npcs.length === 0 && items.length === 0 && players.length === 0) {
    cells.push(textRow('Nothing here', theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }

  const rs = getRoundState();
  const isThinking = rs.phase === 'npc_response';
  const npcColor = isThinking ? theme.colors.system : theme.colors.npc;

  // NPCs — card-style with role
  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : npc.name;
    const role = typeof npc === 'string' ? '' : (npc.role || '');

    const startRow = cells.length;

    // Name line with diamond
    cells.push(coloredRow([
      { text: '\u25C6 ', fg: npcColor },
      { text: name, fg: npcColor, attrs: ATTR_BOLD },
    ], cols));

    // Role line (indented)
    if (role) {
      cells.push(coloredRow([
        { text: '  ', fg: theme.colors.dim },
        { text: role, fg: theme.colors.dim },
      ], cols));
    }

    // Separator
    const sep: CharCell[] = [];
    for (let i = 0; i < cols; i++) {
      sep.push({ char: i < cols - 1 ? '\u2500' : ' ', fg: '#1a1a25' });
    }
    cells.push(sep);

    // Hit region spans all rows for this NPC
    panel.registerHitRegion({
      col: 0,
      row: startRow,
      width: cols,
      height: cells.length - startRow,
      data: { action: `talk to ${name}` },
    });
  }

  // Players
  if (players.length > 0) {
    for (const p of players) {
      const name = typeof p === 'string' ? p : p.name;
      cells.push(coloredRow([
        { text: '@ ', fg: theme.colors.heal },
        { text: name, fg: theme.colors.primary },
      ], cols));
    }
    cells.push(emptyRow(cols));
  }

  // Items
  for (const item of items) {
    const name = typeof item === 'string' ? item : item.name;

    const rowIdx = cells.length;
    cells.push(coloredRow([
      { text: '\u00B7 ', fg: theme.colors.dim },
      { text: name, fg: theme.colors.primary },
    ], cols));

    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `examine ${name}` },
    });
  }

  panel.paint(cells);
}
