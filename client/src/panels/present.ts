// client/src/panels/present.ts
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { getRoundState } from '../state/round-state';
import { theme } from '../renderer/theme';
import { textRow, coloredRow } from './panel-utils';


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
  // During npc_response phase, use a dimmer/pulsing color for NPCs
  const npcColor = isThinking ? theme.colors.system : theme.colors.npc;

  for (const npc of npcs) {
    const name = typeof npc === 'string' ? npc : npc.name;
    const role = typeof npc === 'string' ? '' : (npc.role || '');

    const segments: Array<{ text: string; fg: string }> = [
      { text: '\u25C6 ', fg: npcColor },
      { text: name, fg: npcColor },
    ];
    if (role) {
      segments.push({ text: ' \u2014 ' + role, fg: theme.colors.dim });
    }

    const rowIdx = cells.length;
    cells.push(coloredRow(segments, cols));

    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `talk to ${name}` },
    });
  }

  for (const p of players) {
    const name = typeof p === 'string' ? p : p.name;
    cells.push(coloredRow([
      { text: '@ ', fg: theme.colors.heal },
      { text: name, fg: theme.colors.primary },
    ], cols));
  }

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
