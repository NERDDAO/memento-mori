// client/src/panels/inventory.ts
/**
 * Inventory sidebar panel — equipped slot glyphs + backpack list.
 * "manage inventory" button opens the full modal.
 */
import type { GameState } from '../state/game-state';
import type { TerminalPanel } from '../ui/terminal-panel';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';
import { textRow, coloredRow, emptyRow } from './panel-utils';

const RARITY_COLORS: Record<string, string> = {
  common: '#808080', uncommon: '#1eff00', rare: '#0070dd', epic: '#a335ee', legendary: '#ff8000',
};

const SLOT_GLYPHS: Record<string, string> = {
  weapon: '\u2694',
  armor: '\u{1F6E1}',
  accessory: '\u25C7',
  ring: '\u25CB',
};

const SLOT_ORDER = ['weapon', 'armor', 'accessory', 'ring'] as const;

/** Callback to open inventory modal — set by app.ts */
export let onManageInventory: (() => void) | null = null;
export function setManageInventoryCallback(fn: () => void): void {
  onManageInventory = fn;
}


export function renderInventoryPanel(panel: TerminalPanel, state: GameState): void {
  const cols = panel.cols;
  const cells: CharCell[][] = [];

  // ── EQUIPPED ──
  cells.push(coloredRow([{ text: 'EQUIPPED', fg: theme.colors.dim }], cols));

  for (const slot of SLOT_ORDER) {
    const glyph = SLOT_GLYPHS[slot] || '?';
    const item = state.inventory.find(i => i.equipped && i.slot_type === slot);

    if (item) {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      cells.push(coloredRow([
        { text: `${glyph} `, fg: theme.colors.dim },
        { text: item.name, fg: color },
      ], cols));
    } else {
      cells.push(coloredRow([
        { text: `${glyph} `, fg: theme.colors.dim },
        { text: '- empty -', fg: '#3a3a48' },
      ], cols));
    }
  }

  // ── Separator ──
  cells.push(emptyRow(cols));

  // ── PACK ──
  const backpack = state.inventory.filter(i => !i.equipped);
  const count = backpack.length;
  cells.push(coloredRow([
    { text: 'PACK', fg: theme.colors.dim },
    { text: ` ${count}/10`, fg: theme.colors.primary },
  ], cols));

  if (count === 0) {
    cells.push(textRow('  Empty', theme.colors.dim, cols));
  } else {
    for (const item of backpack) {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      const segments: Array<{ text: string; fg: string }> = [
        { text: '\u00B7 ', fg: theme.colors.dim },
        { text: item.name, fg: color },
      ];
      if (item.quantity > 1) {
        segments.push({ text: ` \u00D7${item.quantity}`, fg: theme.colors.heal });
      }
      cells.push(coloredRow(segments, cols));
    }
  }

  // ── Manage button ──
  cells.push(emptyRow(cols));
  cells.push(coloredRow([
    { text: '  [manage inventory]', fg: theme.colors.accent },
  ], cols));

  panel.paint(cells);
}
