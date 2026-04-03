// src/ui/ascii-art-viewer.ts
/**
 * Reusable ASCII art renderer for canvas contexts and terminal panels.
 */

import { drawText, type CharSize, type CharCell } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

export interface AsciiArtOptions {
  lines: string[];
  width: number;
  height: number;
  fg?: string;          // default: theme.colors.primary
  borderColor?: string;  // optional border
  title?: string;        // optional title above art
}

/**
 * Draw ASCII art onto a canvas context at a given pixel position.
 * Returns the total height consumed in pixels.
 */
export function drawAsciiArt(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  opts: AsciiArtOptions,
  charSize: CharSize,
): number {
  const fg = opts.fg ?? theme.colors.primary;
  let curY = y;

  // Optional title
  if (opts.title) {
    const col = Math.floor(x / charSize.width);
    const row = Math.floor(curY / charSize.height);
    drawText(ctx, col, row, opts.title, theme.colors.npc, charSize, 1); // bold
    curY += charSize.height;
  }

  // Draw each line
  for (const line of opts.lines) {
    const col = Math.floor(x / charSize.width);
    const row = Math.floor(curY / charSize.height);
    drawText(ctx, col, row, line, fg, charSize);
    curY += charSize.height;
  }

  return curY - y;
}

/**
 * Render ASCII art into a CharCell[][] grid that can be painted by a TerminalPanel.
 * Useful for embedding art in panel content.
 */
export function artToCells(
  lines: string[],
  fg?: string,
): CharCell[][] {
  const color = fg ?? theme.colors.primary;
  return lines.map(line =>
    Array.from(line).map(char => ({ char, fg: color }))
  );
}
