// src/panels/cards.ts
/**
 * Cards panel — renders NPC cards onto an offscreen canvas using Pretext
 * for text layout and BBS-style box-drawing borders.
 *
 * Uses title-inset borders: ╔═[ Name ]══════╗
 * Color-coded by role. Two cards per row.
 */

import { prepareWithSegments, walkLineRanges, type PreparedTextWithSegments } from '@chenglou/pretext';
import { theme } from '../renderer/theme';
import type { GameState, LocationEntity } from '../state/game-state';

// ── Fonts ────────────────────────────────────────────────────────
const NAME_FONT  = 'bold 13px monospace';
const LABEL_FONT = '11px monospace';
const HINT_FONT  = '10px monospace';

// ── Layout constants ─────────────────────────────────────────────
const CHAR_W     = 8;       // monospace char width at 13px (approximate)
const LINE_H     = 16;
const PAD_X      = 8;       // horizontal padding inside card
const PAD_Y      = 4;       // vertical padding
const CARD_GAP_X = 10;      // horizontal gap between 2-wide cards
const CARD_GAP_Y = 6;       // vertical gap between card rows

// ── Box-drawing ──────────────────────────────────────────────────
const BOX = {
  tl: '╔', tr: '╗', bl: '╚', br: '╝',
  h: '═', v: '║',
  ml: '╟', mr: '╢', mh: '─',  // single-line mid separator
};

// ── Role → color mapping ─────────────────────────────────────────
const ROLE_COLORS: Record<string, string> = {
  merchant:    '#d4a574',  // amber
  shopkeeper:  '#d4a574',
  quest:       '#8b5cf6',  // purple
  hostile:     '#e05050',  // red
  guard:       '#5a8fba',  // steel blue
  healer:      '#50c878',  // green
};

function roleColor(role: string): string {
  const key = role.toLowerCase();
  for (const [k, v] of Object.entries(ROLE_COLORS)) {
    if (key.includes(k)) return v;
  }
  return theme.colors.npc; // default amber
}

// ── Offscreen state ──────────────────────────────────────────────
let offscreen: HTMLCanvasElement | null = null;
let offscreenCtx: CanvasRenderingContext2D | null = null;

// ── Pretext measurement cache ────────────────────────────────────
const preparedCache = new Map<string, PreparedTextWithSegments>();

function getPrepared(text: string, font: string): PreparedTextWithSegments {
  const key = `${font}::${text}`;
  let p = preparedCache.get(key);
  if (!p) {
    p = prepareWithSegments(text, font);
    preparedCache.set(key, p);
  }
  return p;
}

function measureTextWidth(text: string, font: string): number {
  const p = getPrepared(text, font);
  let maxW = 0;
  walkLineRanges(p, 100_000, line => { if (line.width > maxW) maxW = line.width; });
  return maxW;
}

// ── Card drawing ─────────────────────────────────────────────────

interface CardMetrics {
  width: number;
  height: number;
}

function measureCard(npc: LocationEntity, cardW: number): CardMetrics {
  // Title row + label row + hint row = 3 content rows + borders
  const innerH = LINE_H * 3 + PAD_Y * 2;
  return { width: cardW, height: innerH + LINE_H * 2 }; // +2 for top/bottom borders
}

function drawCard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  npc: LocationEntity,
  cardW: number,
): number {
  const role = npc.role || 'NPC';
  const borderColor = roleColor(role);
  const borderDim = borderColor + '88'; // semi-transparent for box lines
  const nameColor = borderColor;
  const innerW = cardW - PAD_X * 2;

  let curY = y;

  // ── Background ──────────────────────────────────────────────
  const metrics = measureCard(npc, cardW);
  ctx.fillStyle = theme.colors.bg;
  ctx.fillRect(x, curY, cardW, metrics.height);

  // ── Top border with title inset ─────────────────────────────
  // ╔═[ Name ]══════════════╗
  const borderCharW = CHAR_W;
  // Max name width: cardW minus border chrome (╔═[  ]══╗ = ~7 chars)
  const maxNamePx = cardW - borderCharW * 8;
  let displayName = npc.name;
  let nameW = measureTextWidth(` ${displayName} `, NAME_FONT);
  // Truncate with ellipsis if too wide
  while (nameW > maxNamePx && displayName.length > 3) {
    displayName = displayName.slice(0, -2) + '…';
    nameW = measureTextWidth(` ${displayName} `, NAME_FONT);
  }
  const nameText = ` ${displayName} `;

  // Left portion: ╔═[
  const leftPrefix = BOX.tl + BOX.h + '[';
  // Right portion: ]═...═╗
  const rightSuffix = ']';

  ctx.font = '13px monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const rowMid = curY + LINE_H / 2;

  // Draw left prefix
  ctx.fillStyle = borderDim;
  ctx.fillText(leftPrefix, x + 1, rowMid);
  const prefixW = leftPrefix.length * borderCharW;

  // Draw name in title
  ctx.font = NAME_FONT;
  ctx.fillStyle = nameColor;
  ctx.fillText(nameText, x + 1 + prefixW, rowMid);

  // Draw right suffix + fill
  ctx.font = '13px monospace';
  ctx.fillStyle = borderDim;
  const afterName = x + 1 + prefixW + nameW;
  ctx.fillText(rightSuffix, afterName, rowMid);
  const suffixEndX = afterName + borderCharW;

  // Fill remaining top border with ═
  const fillChars = Math.max(0, Math.floor((x + cardW - borderCharW - suffixEndX) / borderCharW));
  if (fillChars > 0) {
    ctx.fillText(BOX.h.repeat(fillChars), suffixEndX, rowMid);
  }
  // Top-right corner
  ctx.fillText(BOX.tr, x + cardW - borderCharW - 1, rowMid);

  curY += LINE_H;

  // ── Role label ──────────────────────────────────────────────
  // ║  role_label                          ║
  ctx.fillStyle = borderDim;
  ctx.font = '13px monospace';
  ctx.fillText(BOX.v, x + 1, curY + LINE_H / 2);
  ctx.fillText(BOX.v, x + cardW - borderCharW - 1, curY + LINE_H / 2);

  ctx.font = LABEL_FONT;
  ctx.fillStyle = theme.colors.dim;
  ctx.fillText(role, x + PAD_X + borderCharW, curY + LINE_H / 2);
  curY += LINE_H;

  // ── Separator ───────────────────────────────────────────────
  // ╟──────────────────────────╢
  ctx.font = '13px monospace';
  ctx.fillStyle = borderDim;
  ctx.fillText(BOX.ml, x + 1, curY + LINE_H / 2);
  const sepChars = Math.max(0, Math.floor((cardW - borderCharW * 2 - 2) / borderCharW));
  ctx.fillText(BOX.mh.repeat(sepChars), x + 1 + borderCharW, curY + LINE_H / 2);
  ctx.fillText(BOX.mr, x + cardW - borderCharW - 1, curY + LINE_H / 2);
  curY += LINE_H;

  // ── Hint row ────────────────────────────────────────────────
  // ║  [Enter] Talk                        ║
  ctx.fillStyle = borderDim;
  ctx.font = '13px monospace';
  ctx.fillText(BOX.v, x + 1, curY + LINE_H / 2);
  ctx.fillText(BOX.v, x + cardW - borderCharW - 1, curY + LINE_H / 2);

  ctx.font = HINT_FONT;
  ctx.fillStyle = theme.colors.dim + 'aa';
  ctx.fillText('[Enter] Talk', x + PAD_X + borderCharW, curY + LINE_H / 2);
  curY += LINE_H;

  // ── Bottom border ───────────────────────────────────────────
  // ╚══════════════════════════╝
  ctx.font = '13px monospace';
  ctx.fillStyle = borderDim;
  ctx.fillText(BOX.bl, x + 1, curY + LINE_H / 2);
  const botChars = Math.max(0, Math.floor((cardW - borderCharW * 2 - 2) / borderCharW));
  ctx.fillText(BOX.h.repeat(botChars), x + 1 + borderCharW, curY + LINE_H / 2);
  ctx.fillText(BOX.br, x + cardW - borderCharW - 1, curY + LINE_H / 2);
  curY += LINE_H;

  // ── Side border fills (vertical lines for content rows) ─────
  // Already drawn inline above

  return curY - y;
}

// ── Public API ───────────────────────────────────────────────────

/** Render NPC cards onto an offscreen canvas. Returns null if no NPCs. */
export function renderCardsCanvas(state: GameState, regionW: number, regionH: number): HTMLCanvasElement | null {
  const npcs = state.location.npcs;

  if (!offscreen) {
    offscreen = document.createElement('canvas');
    offscreenCtx = offscreen.getContext('2d')!;
  }

  if (npcs.length === 0) {
    // Draw empty state
    offscreen.width = Math.max(regionW, 100);
    offscreen.height = Math.max(regionH, 40);
    const ctx = offscreenCtx!;
    ctx.fillStyle = theme.colors.bg;
    ctx.fillRect(0, 0, offscreen.width, offscreen.height);
    ctx.font = '13px monospace';
    ctx.fillStyle = theme.colors.dim;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('~ no one here ~', offscreen.width / 2, offscreen.height / 2);
    ctx.textAlign = 'left';
    return offscreen;
  }

  // 2-wide layout
  const cardW = Math.floor((regionW - CARD_GAP_X) / 2);

  // Measure total height
  let totalH = PAD_Y;
  for (let i = 0; i < npcs.length; i += 2) {
    const leftM = measureCard(npcs[i], cardW);
    const rightM = i + 1 < npcs.length ? measureCard(npcs[i + 1], cardW) : { height: 0 };
    totalH += Math.max(leftM.height, rightM.height) + CARD_GAP_Y;
  }

  offscreen.width = Math.max(regionW, 100);
  offscreen.height = Math.max(totalH, regionH);

  const ctx = offscreenCtx!;
  ctx.fillStyle = theme.colors.bg;
  ctx.fillRect(0, 0, offscreen.width, offscreen.height);

  // Draw cards in pairs
  let curY = PAD_Y;
  for (let i = 0; i < npcs.length; i += 2) {
    const leftH = drawCard(ctx, 0, curY, npcs[i], cardW);
    let rightH = 0;
    if (i + 1 < npcs.length) {
      rightH = drawCard(ctx, cardW + CARD_GAP_X, curY, npcs[i + 1], cardW);
    }
    curY += Math.max(leftH, rightH) + CARD_GAP_Y;
  }

  return offscreen;
}
