// src/panels/viewport.ts
/**
 * ASCII viewport panel — dedicated area below the map for entity cards
 * and scene art. Renders CardContent as a canvas CharCell grid.
 */

import type { TerminalPanel } from '../ui/terminal-panel';
import type { CardContent } from '../map/card-renderer';
import { type CharCell, ATTR_BOLD } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

// Bar characters
const BAR_FULL = '█';
const BAR_EMPTY = '░';
const BAR_WIDTH = 12;

/** Render entity/player card content into the viewport TerminalPanel. */
export function renderViewport(
  panel: TerminalPanel,
  card: CardContent | null,
  sceneArt: string[] | null,
): void {
  const cells: CharCell[][] = [];
  const cols = panel.cols;
  if (cols < 10) return;

  panel.clearHitRegions();

  if (sceneArt && sceneArt.length > 0) {
    // Scene art mode — render ASCII art centered
    const artColor = theme.colors.dim;
    for (const line of sceneArt) {
      const row: CharCell[] = [];
      for (let c = 0; c < cols; c++) {
        row.push({ char: line[c] || ' ', fg: artColor });
      }
      cells.push(row);
    }
  } else if (card) {
    // Entity card mode — render card info
    renderCard(cells, cols, card);
  } else {
    // Empty — show placeholder
    const msg = '~ nothing in focus ~';
    const row: CharCell[] = [];
    const pad = Math.max(0, Math.floor((cols - msg.length) / 2));
    for (let c = 0; c < cols; c++) {
      const ch = c >= pad && c < pad + msg.length ? msg[c - pad] : ' ';
      row.push({ char: ch, fg: theme.colors.dim });
    }
    cells.push(row);
  }

  panel.paint(cells);
}

function renderCard(cells: CharCell[][], cols: number, card: CardContent): void {
  const { colors } = theme;

  // Row 1: Name
  const nameRow: CharCell[] = [];
  const nameColor = card.type === 'player' ? colors.accent : colors.npc;
  writeText(nameRow, cols, `◆ ${card.name}`, nameColor, ATTR_BOLD);
  cells.push(nameRow);

  // Row 2: Labels
  if (card.labels.length > 0) {
    const labelRow: CharCell[] = [];
    const labelText = card.labels.map(l => `[${l}]`).join(' ');
    writeText(labelRow, cols, `  ${labelText}`, colors.dim);
    cells.push(labelRow);
  }

  // Row 3: Summary (truncated to fit)
  if (card.summary) {
    const maxLen = cols - 2;
    const summary = card.summary.length > maxLen
      ? card.summary.slice(0, maxLen - 3) + '...'
      : card.summary;
    const summaryRow: CharCell[] = [];
    writeText(summaryRow, cols, `  ${summary}`, colors.primary);
    cells.push(summaryRow);
  }

  // Health bar
  if (card.health !== undefined && card.maxHealth !== undefined) {
    const hpRow: CharCell[] = [];
    const hpPct = Math.max(0, Math.min(1, card.health / card.maxHealth));
    const hpColor = hpPct > 0.3 ? colors.heal : colors.damage;
    const filled = Math.round(hpPct * BAR_WIDTH);
    const barStr = BAR_FULL.repeat(filled) + BAR_EMPTY.repeat(BAR_WIDTH - filled);
    writeText(hpRow, cols, `  HP `, colors.dim);
    appendText(hpRow, barStr, hpColor);
    appendText(hpRow, ` ${card.health}/${card.maxHealth}`, colors.primary);
    padRow(hpRow, cols);
    cells.push(hpRow);
  }

  // XP bar
  if (card.xp !== undefined && card.xpThreshold !== undefined) {
    const xpRow: CharCell[] = [];
    const xpPct = Math.max(0, Math.min(1, card.xp / card.xpThreshold));
    const filled = Math.round(xpPct * BAR_WIDTH);
    const barStr = BAR_FULL.repeat(filled) + BAR_EMPTY.repeat(BAR_WIDTH - filled);
    writeText(xpRow, cols, `  XP `, colors.dim);
    appendText(xpRow, barStr, colors.accent);
    appendText(xpRow, ` ${card.xp}/${card.xpThreshold}`, colors.primary);
    padRow(xpRow, cols);
    cells.push(xpRow);
  }

  // Level
  if (card.level !== undefined) {
    const lvRow: CharCell[] = [];
    writeText(lvRow, cols, `  Lv ${card.level}`, colors.dim);
    cells.push(lvRow);
  }

  // Hint
  if (card.hint) {
    const hintRow: CharCell[] = [];
    writeText(hintRow, cols, `  ${card.hint}`, colors.dim);
    cells.push(hintRow);
  }
}

// Helpers

function writeText(row: CharCell[], cols: number, text: string, fg: string, attrs?: number): void {
  for (let i = 0; i < cols; i++) {
    row.push({ char: text[i] || ' ', fg, attrs });
  }
}

function appendText(row: CharCell[], text: string, fg: string, attrs?: number): void {
  for (const ch of text) {
    row.push({ char: ch, fg, attrs });
  }
}

function padRow(row: CharCell[], cols: number): void {
  while (row.length < cols) {
    row.push({ char: ' ', fg: '#0a0a0f' });
  }
}
