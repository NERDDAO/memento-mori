// src/panels/viewer.ts
/**
 * ASCII art viewer panel — displays scene art or entity art in the
 * bottom-center region of the unified canvas.
 */

import type { PanelResult } from '../canvas/types';
import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';
import { ATTR_BOLD } from '../renderer/canvas-text';

let currentArt: string[] | null = null;
let currentLabel: string = '';

/** Set the art to display. Pass null to clear. */
export function setViewerArt(lines: string[] | null, label?: string): void {
  currentArt = lines;
  currentLabel = label || '';
}

/** Get current art (for external checks). */
export function getViewerArt(): string[] | null {
  return currentArt;
}

/** Render the viewer panel as CharCell[][]. */
export function renderViewer(cols: number, rows: number): PanelResult {
  const cells: CharCell[][] = [];
  const dim = theme.colors.dim;
  const primary = theme.colors.primary;

  if (!currentArt || currentArt.length === 0) {
    // Empty state — show dim placeholder
    for (let r = 0; r < rows; r++) {
      const row: CharCell[] = [];
      for (let c = 0; c < cols; c++) {
        row.push({ char: ' ', fg: dim });
      }
      cells.push(row);
    }
    // Center a dim label
    const label = '~ no scene ~';
    const startCol = Math.max(0, Math.floor((cols - label.length) / 2));
    const midRow = Math.floor(rows / 2);
    if (midRow < rows) {
      for (let i = 0; i < label.length && startCol + i < cols; i++) {
        cells[midRow][startCol + i] = { char: label[i], fg: dim };
      }
    }
    return { cells };
  }

  // Render art lines
  let artRow = 0;

  // Title row if label exists
  if (currentLabel) {
    const row: CharCell[] = [];
    const title = currentLabel.slice(0, cols);
    for (let c = 0; c < cols; c++) {
      if (c < title.length) {
        row.push({ char: title[c], fg: theme.colors.npc, attrs: ATTR_BOLD });
      } else {
        row.push({ char: ' ', fg: dim });
      }
    }
    cells.push(row);
    artRow++;
  }

  // Art lines
  for (const line of currentArt) {
    if (artRow >= rows) break;
    const row: CharCell[] = [];
    for (let c = 0; c < cols; c++) {
      if (c < line.length) {
        row.push({ char: line[c], fg: primary });
      } else {
        row.push({ char: ' ', fg: dim });
      }
    }
    cells.push(row);
    artRow++;
  }

  // Fill remaining rows
  while (cells.length < rows) {
    const row: CharCell[] = [];
    for (let c = 0; c < cols; c++) {
      row.push({ char: ' ', fg: dim });
    }
    cells.push(row);
  }

  return { cells };
}
