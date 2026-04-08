// src/panels/viewer.ts
/**
 * ASCII art viewer panel — renders scene/entity art onto an offscreen canvas
 * that scales to fit the region, avoiding cropping.
 */

import { theme } from '../renderer/theme';

const ART_FONT = '13px monospace';
const ART_LINE_HEIGHT = 16;
const ART_CHAR_WIDTH = 8; // approximate monospace char width at 13px

let currentArt: string[] | null = null;
let currentLabel: string = '';
let offscreen: HTMLCanvasElement | null = null;
let offscreenCtx: CanvasRenderingContext2D | null = null;

/** Set the art to display. Pass null to clear. */
export function setViewerArt(lines: string[] | null, label?: string): void {
  currentArt = lines;
  currentLabel = label || '';
}

/** Get current art (for external checks). */
export function getViewerArt(): string[] | null {
  return currentArt;
}

/** Render the viewer art onto an offscreen canvas. Returns null if no art. */
export function renderViewerCanvas(): HTMLCanvasElement | null {
  if (!currentArt || currentArt.length === 0) return null;

  if (!offscreen) {
    offscreen = document.createElement('canvas');
    offscreenCtx = offscreen.getContext('2d')!;
  }

  const ctx = offscreenCtx!;
  const lines = currentArt;

  // Measure content size
  const maxLineLen = Math.max(...lines.map(l => l.length));
  const labelHeight = currentLabel ? ART_LINE_HEIGHT + 4 : 0;
  const artW = maxLineLen * ART_CHAR_WIDTH + 16; // padding
  const artH = lines.length * ART_LINE_HEIGHT + labelHeight + 8; // padding

  offscreen.width = artW;
  offscreen.height = artH;

  // Clear
  ctx.fillStyle = theme.colors.bg;
  ctx.fillRect(0, 0, artW, artH);

  let curY = 4;

  // Label
  if (currentLabel) {
    ctx.font = 'bold 14px monospace';
    ctx.fillStyle = theme.colors.npc;
    ctx.textAlign = 'left';
    ctx.fillText(currentLabel, 8, curY + ART_LINE_HEIGHT * 0.8);
    curY += ART_LINE_HEIGHT + 4;
  }

  // Art lines
  ctx.font = ART_FONT;
  ctx.fillStyle = theme.colors.primary;
  ctx.textAlign = 'left';

  for (const line of lines) {
    curY += ART_LINE_HEIGHT;
    ctx.fillText(line, 8, curY - 2);
  }

  return offscreen;
}
