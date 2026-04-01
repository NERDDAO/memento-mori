// src/map/card-renderer.ts
/**
 * ASCII text card renderer — draws entity info cards using box-drawing
 * characters on a Canvas context. Integrates with the map canvas.
 */

import { prepare, layout } from '@chenglou/pretext';
import type { EntityCardData } from './entity-card';

const CARD_FONT = '13px monospace';
const CARD_BOLD_FONT = 'bold 14px monospace';
const CARD_DIM_FONT = '11px monospace';
const CHAR_W = 8.4;  // monospace char width at 13px
const LINE_H = 18;
const CARD_COLS = 28; // characters wide
const CARD_W = CARD_COLS * CHAR_W + 16; // with padding
const PAD = 8;

// Box-drawing chars
const BOX = {
  tl: '╔', tr: '╗', bl: '╚', br: '╝',
  h: '═', v: '║',
  ml: '╠', mr: '╣', mh: '═',
};

// Colors matching the theme
const COLORS = {
  border: '#2a2a38',
  bg: '#0e0e15',
  name: '#d4a574',
  label: '#5a5a70',
  text: '#c8c8d0',
  dim: '#4a4a58',
  hint: '#5a5a70',
  hpFull: '#50c878',
  hpLow: '#e05050',
  item: '#a335ee',
  exit: '#50c8c8',
};

export interface CardContent {
  type: 'entity' | 'player';
  name: string;
  labels: string[];
  summary: string;
  hint?: string;
  // Player-specific
  health?: number;
  maxHealth?: number;
  level?: number;
  xp?: number;
  xpThreshold?: number;
}

/**
 * Draw an ASCII-bordered card on a canvas context.
 * Returns the height consumed.
 */
export function drawCard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  content: CardContent,
): number {
  const maxTextW = (CARD_COLS - 2) * CHAR_W; // inner width minus borders
  let curY = y;

  // Measure summary text to determine card height
  let summaryLines: string[] = [];
  if (content.summary) {
    const prepared = prepare(content.summary, CARD_FONT);
    const result = layout(prepared, maxTextW, LINE_H);
    // Approximate line breaking — split by width
    summaryLines = wrapText(content.summary, CARD_COLS - 4);
  }

  const nameLines = wrapText(content.name, CARD_COLS - 4);
  const hasLabels = content.labels.length > 0;
  const hasHealth = content.health != null;
  const hasXp = content.xp != null;
  const hasHint = !!content.hint;

  // Calculate total lines
  let totalLines = nameLines.length;
  if (hasLabels) totalLines += 1;
  totalLines += 1; // separator
  if (summaryLines.length) totalLines += summaryLines.length + 1; // +1 for spacing
  if (hasHealth) totalLines += 1;
  if (hasXp) totalLines += 1;
  if (hasHint) totalLines += 2; // spacing + hint

  const cardH = (totalLines + 2) * LINE_H; // +2 for top/bottom borders

  // Background
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(x, curY, CARD_W, cardH);

  // Top border
  drawBoxLine(ctx, x, curY, BOX.tl, BOX.h, BOX.tr);
  curY += LINE_H;

  // Name
  ctx.fillStyle = COLORS.name;
  ctx.font = CARD_BOLD_FONT;
  for (const line of nameLines) {
    drawTextLine(ctx, x, curY, line, COLORS.name, CARD_BOLD_FONT);
    curY += LINE_H;
  }

  // Labels
  if (hasLabels) {
    const labelText = content.labels.join(' · ');
    drawTextLine(ctx, x, curY, labelText, COLORS.label, CARD_DIM_FONT);
    curY += LINE_H;
  }

  // Separator
  drawBoxLine(ctx, x, curY, BOX.ml, BOX.mh, BOX.mr);
  curY += LINE_H;

  // Summary
  if (summaryLines.length) {
    for (const line of summaryLines) {
      drawTextLine(ctx, x, curY, line, COLORS.text, CARD_FONT);
      curY += LINE_H;
    }
    curY += LINE_H * 0.5; // half-line spacing
  }

  // Health bar
  if (hasHealth && content.maxHealth) {
    const pct = content.health! / content.maxHealth;
    const barLen = CARD_COLS - 8;
    const filled = Math.round(pct * barLen);
    const bar = '█'.repeat(filled) + '░'.repeat(barLen - filled);
    const hpColor = pct > 0.3 ? COLORS.hpFull : COLORS.hpLow;
    drawTextLine(ctx, x, curY, `HP ${bar} ${content.health}`, hpColor, CARD_FONT);
    curY += LINE_H;
  }

  // XP bar
  if (hasXp && content.xpThreshold) {
    const pct = content.xp! / content.xpThreshold;
    const barLen = CARD_COLS - 8;
    const filled = Math.round(pct * barLen);
    const bar = '█'.repeat(filled) + '░'.repeat(barLen - filled);
    drawTextLine(ctx, x, curY, `XP ${bar} ${content.xp}`, COLORS.dim, CARD_FONT);
    curY += LINE_H;
  }

  // Hint
  if (hasHint) {
    curY += LINE_H * 0.5;
    drawTextLine(ctx, x, curY, content.hint!, COLORS.hint, CARD_DIM_FONT);
    curY += LINE_H;
  }

  // Bottom border
  drawBoxLine(ctx, x, curY, BOX.bl, BOX.h, BOX.br);
  curY += LINE_H;

  // Side borders
  ctx.fillStyle = COLORS.border;
  ctx.font = CARD_FONT;
  const rows = Math.floor((curY - y) / LINE_H);
  for (let i = 1; i < rows - 1; i++) {
    const rowY = y + i * LINE_H;
    ctx.fillText(BOX.v, x + PAD, rowY + LINE_H / 2);
    ctx.fillText(BOX.v, x + CARD_W - PAD, rowY + LINE_H / 2);
  }

  return curY - y;
}

function drawBoxLine(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  left: string, fill: string, right: string,
): void {
  ctx.font = CARD_FONT;
  ctx.fillStyle = COLORS.border;
  const line = left + fill.repeat(CARD_COLS - 2) + right;
  ctx.textAlign = 'left';
  ctx.fillText(line, x + PAD, y + LINE_H / 2);
  ctx.textAlign = 'center'; // reset
}

function drawTextLine(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  text: string, color: string, font: string,
): void {
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = 'left';
  ctx.fillText(text, x + PAD + CHAR_W * 2, y + LINE_H / 2);
  ctx.textAlign = 'center'; // reset
}

function wrapText(text: string, maxCols: number): string[] {
  const words = text.split(' ');
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    if (current.length + word.length + 1 > maxCols) {
      if (current) lines.push(current);
      current = word;
    } else {
      current = current ? current + ' ' + word : word;
    }
  }
  if (current) lines.push(current);
  return lines;
}

export { CARD_W };
