// src/ui/terminal-panel.ts
/**
 * Canvas-backed terminal panel — renders a grid of CharCells with
 * diff-based repainting and clickable hit regions.
 */

import {
  CharCell,
  CharSize,
  measureChar,
  fillCell,
  MONO_FONT,
} from '../renderer/canvas-text';

// ── Types ────────────────────────────────────────────────────────

export interface HitRegion {
  col: number;
  row: number;
  width: number;
  height: number;
  data: { entityId?: string; entityType?: string; action?: string; [key: string]: any };
}

export interface TerminalPanelOptions {
  container: HTMLElement;
  font?: string;  // default: MONO_FONT
}

// ── Panel ────────────────────────────────────────────────────────

export class TerminalPanel {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  charSize: CharSize;
  cols: number = 0;
  rows: number = 0;

  private font: string;
  private prevCells: CharCell[][] = [];
  private lastCells: CharCell[][] = [];  // last painted content for resize repaint
  private hitRegions: HitRegion[] = [];
  private resizeObserver: ResizeObserver;
  private boundClick: (e: MouseEvent) => void;

  constructor(opts: TerminalPanelOptions) {
    this.font = opts.font ?? MONO_FONT;

    // Create canvas
    this.canvas = document.createElement('canvas');
    this.canvas.style.display = 'block';
    this.canvas.style.width = '100%';
    this.canvas.style.height = '100%';
    opts.container.appendChild(this.canvas);

    const ctx = this.canvas.getContext('2d');
    if (!ctx) throw new Error('TerminalPanel: failed to get 2d context');
    this.ctx = ctx;

    // Measure character cell size
    this.charSize = measureChar(this.ctx, this.font);

    // Initial sizing
    this.resize();

    // Resize observer
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(opts.container);

    // Click handler
    this.boundClick = (e: MouseEvent) => this.handleClick(e);
    this.canvas.addEventListener('click', this.boundClick);
  }

  /** Recalculate dimensions based on container size. */
  resize(): void {
    const rect = this.canvas.parentElement?.getBoundingClientRect();
    if (!rect) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = rect.width;
    const cssH = rect.height;

    // Set the canvas backing-store size (physical pixels)
    this.canvas.width  = Math.floor(cssW * dpr);
    this.canvas.height = Math.floor(cssH * dpr);

    // Scale the context so drawing operations use CSS-pixel coordinates
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Recalculate grid dimensions in CSS pixels
    this.cols = Math.floor(cssW / this.charSize.width);
    this.rows = Math.floor(cssH / this.charSize.height);

    // Force full repaint
    this.prevCells = [];
    if (this.lastCells.length > 0) {
      this.paint(this.lastCells);
    }
  }

  /**
   * Paint a 2D grid of CharCells, diffing against the previous frame
   * to only redraw changed cells.
   */
  paint(cells: CharCell[][]): void {
    const rows = Math.min(cells.length, this.rows);

    for (let r = 0; r < rows; r++) {
      const row = cells[r];
      const prevRow = this.prevCells[r];
      const cols = Math.min(row?.length ?? 0, this.cols);

      for (let c = 0; c < cols; c++) {
        const cell = row[c];
        const prev = prevRow?.[c];

        // Skip if unchanged
        if (
          prev &&
          prev.char === cell.char &&
          prev.fg === cell.fg &&
          prev.bg === cell.bg &&
          prev.attrs === cell.attrs
        ) {
          continue;
        }

        // Clear the cell area before drawing
        const px = c * this.charSize.width;
        const py = r * this.charSize.height;
        this.ctx.clearRect(px, py, this.charSize.width, this.charSize.height);

        fillCell(this.ctx, c, r, cell, this.charSize);
      }
    }

    // Deep-copy cells for next-frame diff and resize repaint
    this.prevCells = cells.map(row =>
      row.map(cell => ({ ...cell })),
    );
    this.lastCells = cells;
  }

  /** Register a clickable region (call after paint, before next paint). */
  registerHitRegion(region: HitRegion): void {
    this.hitRegions.push(region);
  }

  /** Clear all hit regions (call before each paint cycle). */
  clearHitRegions(): void {
    this.hitRegions = [];
  }

  /** Dispatch a custom event when a hit region is clicked. */
  private handleClick(e: MouseEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const col = Math.floor((e.clientX - rect.left) / this.charSize.width);
    const row = Math.floor((e.clientY - rect.top) / this.charSize.height);

    for (const region of this.hitRegions) {
      if (
        col >= region.col &&
        col < region.col + region.width &&
        row >= region.row &&
        row < region.row + region.height
      ) {
        this.canvas.dispatchEvent(
          new CustomEvent('panel-click', {
            detail: region.data,
            bubbles: true,
          }),
        );
        return;
      }
    }
  }

  /** Tear down observers and listeners. */
  destroy(): void {
    this.resizeObserver.disconnect();
    this.canvas.removeEventListener('click', this.boundClick);
  }
}
