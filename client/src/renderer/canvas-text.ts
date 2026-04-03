// src/renderer/canvas-text.ts
/**
 * Shared canvas text-rendering utilities for monospace terminal panels.
 * Generalised from card-renderer.ts patterns.
 */

import { theme } from './theme';

// ── Types ────────────────────────────────────────────────────────

export interface CharCell {
  char: string;    // single character
  fg: string;      // foreground color
  bg?: string;     // optional background color
  attrs?: number;  // bitmask: 1=bold, 2=italic, 4=underline
}

export interface CharSize {
  width: number;
  height: number;
}

// ── Attr bitmask constants ───────────────────────────────────────

export const ATTR_BOLD      = 1;
export const ATTR_ITALIC    = 2;
export const ATTR_UNDERLINE = 4;

// ── Box-drawing characters ───────────────────────────────────────

export const BOX = {
  tl: '\u2554', tr: '\u2557', bl: '\u255A', br: '\u255D',
  h: '\u2550', v: '\u2551',
  ml: '\u2560', mr: '\u2563',
  lt: '\u255F', rt: '\u2562', lh: '\u2500',  // light horizontal for subtitles
} as const;

// ── Font constants ───────────────────────────────────────────────

export const MONO_FONT = '13px monospace';
export const BOLD_FONT = 'bold 13px monospace';
export const DIM_FONT  = '11px monospace';

// ── Helpers ──────────────────────────────────────────────────────

/** Build a CSS font string from the base font and an attrs bitmask. */
function fontForAttrs(baseFont: string, attrs?: number): string {
  if (!attrs) return baseFont;
  // Extract size+family from baseFont (e.g. "13px monospace")
  const sizeMatch = baseFont.match(/(\d+px\s+.+)$/);
  const sizeAndFamily = sizeMatch ? sizeMatch[1] : baseFont;
  const parts: string[] = [];
  if (attrs & ATTR_ITALIC) parts.push('italic');
  if (attrs & ATTR_BOLD)   parts.push('bold');
  parts.push(sizeAndFamily);
  return parts.join(' ');
}

// ── Core functions ───────────────────────────────────────────────

/**
 * Measure a reference character to determine monospace cell dimensions.
 * Sets the font on ctx as a side-effect.
 */
export function measureChar(ctx: CanvasRenderingContext2D, font: string): CharSize {
  ctx.font = font;
  const metrics = ctx.measureText('M');
  const width = metrics.width;
  // Line height: use font-metrics ascent+descent if available, else approximate
  const ascent  = metrics.actualBoundingBoxAscent  ?? 0;
  const descent = metrics.actualBoundingBoxDescent ?? 0;
  const measured = ascent + descent;
  // Pad line height to ~1.38x the measured glyph height (matches the 13px -> 18px ratio)
  const height = measured > 0 ? Math.ceil(measured * 1.38) : 18;
  return { width, height };
}

/**
 * Draw a single CharCell at character-grid coordinates.
 */
export function fillCell(
  ctx: CanvasRenderingContext2D,
  col: number,
  row: number,
  cell: CharCell,
  charSize: CharSize,
): void {
  const px = col * charSize.width;
  const py = row * charSize.height;

  // Background fill
  if (cell.bg) {
    ctx.fillStyle = cell.bg;
    ctx.fillRect(px, py, charSize.width, charSize.height);
  }

  // Character
  if (cell.char && cell.char !== ' ') {
    ctx.font = fontForAttrs(MONO_FONT, cell.attrs);
    ctx.fillStyle = cell.fg;
    ctx.textBaseline = 'top';
    ctx.textAlign = 'left';
    // Vertically center the glyph within the cell
    const fontSize = parseInt(ctx.font.replace(/^[^\d]*/, '')) || 13;
    const yOffset = (charSize.height - fontSize) * 0.35;
    ctx.fillText(cell.char, px, py + yOffset);
  }

  // Underline
  if (cell.attrs && (cell.attrs & ATTR_UNDERLINE)) {
    ctx.strokeStyle = cell.fg;
    ctx.lineWidth = 1;
    const underY = py + charSize.height - 2;
    ctx.beginPath();
    ctx.moveTo(px, underY);
    ctx.lineTo(px + charSize.width, underY);
    ctx.stroke();
  }
}

/**
 * Draw a string starting at (col, row) using a single foreground color.
 */
export function drawText(
  ctx: CanvasRenderingContext2D,
  col: number,
  row: number,
  text: string,
  fg: string,
  charSize: CharSize,
  attrs?: number,
): void {
  ctx.font = fontForAttrs(MONO_FONT, attrs);
  ctx.fillStyle = fg;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  const py = row * charSize.height;
  const yOffset = (charSize.height - 13) * 0.35;  // 13 = base font size
  for (let i = 0; i < text.length; i++) {
    const px = (col + i) * charSize.width;
    ctx.fillText(text[i], px, py + yOffset);
  }
}

/**
 * Draw a box-drawing frame using double-line characters.
 */
export function drawBox(
  ctx: CanvasRenderingContext2D,
  col: number,
  row: number,
  w: number,
  h: number,
  charSize: CharSize,
  borderColor?: string,
): void {
  const color = borderColor ?? theme.colors.dim;

  // Top border:  ╔══════╗
  const topLine = BOX.tl + BOX.h.repeat(w - 2) + BOX.tr;
  drawText(ctx, col, row, topLine, color, charSize);

  // Side borders: ║      ║
  for (let r = 1; r < h - 1; r++) {
    drawText(ctx, col, row + r, BOX.v, color, charSize);
    drawText(ctx, col + w - 1, row + r, BOX.v, color, charSize);
  }

  // Bottom border: ╚══════╝
  const botLine = BOX.bl + BOX.h.repeat(w - 2) + BOX.br;
  drawText(ctx, col, row + h - 1, botLine, color, charSize);
}

/**
 * Draw a label + progress bar, e.g. `HP ████░░ 42/50`
 */
export function drawBar(
  ctx: CanvasRenderingContext2D,
  col: number,
  row: number,
  label: string,
  value: number,
  max: number,
  barLen: number,
  fullColor: string,
  emptyColor: string,
  charSize: CharSize,
): void {
  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const filled = Math.round(pct * barLen);
  const empty  = barLen - filled;

  // Label
  drawText(ctx, col, row, label + ' ', theme.colors.dim, charSize);

  const barStart = col + label.length + 1;

  // Filled portion
  if (filled > 0) {
    drawText(ctx, barStart, row, '\u2588'.repeat(filled), fullColor, charSize);
  }

  // Empty portion
  if (empty > 0) {
    drawText(ctx, barStart + filled, row, '\u2591'.repeat(empty), emptyColor, charSize);
  }

  // Value text
  const valText = ` ${value}/${max}`;
  drawText(ctx, barStart + barLen, row, valText, theme.colors.primary, charSize);
}
