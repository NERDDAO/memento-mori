// client/src/panels/panel-utils.ts
/**
 * Shared row-building helpers used across all panel files.
 */

import type { CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

/** Convert text to a full-width row of CharCells, padding to cols. */
export function textRow(text: string, fg: string, cols: number, attrs?: number): CharCell[] {
  const row: CharCell[] = [];
  for (let i = 0; i < cols; i++) {
    row.push({ char: i < text.length ? text[i] : ' ', fg, attrs });
  }
  return row;
}

/** Build a row from multiple colored segments, padding remainder to cols. */
export function coloredRow(
  segments: Array<{ text: string; fg: string; attrs?: number }>,
  cols: number,
): CharCell[] {
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

/** Return a blank row of cols cells (no shared-reference bug). */
export function emptyRow(cols: number): CharCell[] {
  return Array.from({ length: cols }, () => ({ char: ' ', fg: theme.colors.primary }));
}
