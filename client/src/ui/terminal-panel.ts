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

// ── Helpers ─────────────────────────────────────────────────────

/** Brighten a hex color by ~30% for hover highlight. */
function brightenColor(hex: string): string {
  if (!hex || hex.length < 7) return '#ffffff';
  const r = Math.min(255, parseInt(hex.slice(1, 3), 16) + 60);
  const g = Math.min(255, parseInt(hex.slice(3, 5), 16) + 60);
  const b = Math.min(255, parseInt(hex.slice(5, 7), 16) + 60);
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

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
  private hoveredRegion: HitRegion | null = null;
  private resizeObserver: ResizeObserver;
  private boundClick: (e: MouseEvent) => void;
  private boundMouseMove: (e: MouseEvent) => void;
  private boundMouseLeave: () => void;

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

    // Hover handlers
    this.boundMouseMove = (e: MouseEvent) => this.handleMouseMove(e);
    this.boundMouseLeave = () => this.handleMouseLeave();
    this.canvas.addEventListener('mousemove', this.boundMouseMove);
    this.canvas.addEventListener('mouseleave', this.boundMouseLeave);
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

  /** Highlight hit region on hover — brighten fg and add underline. */
  private handleMouseMove(e: MouseEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const col = Math.floor((e.clientX - rect.left) / this.charSize.width);
    const row = Math.floor((e.clientY - rect.top) / this.charSize.height);

    let found: HitRegion | null = null;
    for (const region of this.hitRegions) {
      if (
        col >= region.col &&
        col < region.col + region.width &&
        row >= region.row &&
        row < region.row + region.height
      ) {
        found = region;
        break;
      }
    }

    if (found === this.hoveredRegion) return;

    // Restore previous hovered region
    if (this.hoveredRegion && this.lastCells.length > 0) {
      this.repaintRegion(this.hoveredRegion, false);
    }

    this.hoveredRegion = found;

    // Highlight new hovered region
    if (found && this.lastCells.length > 0) {
      this.repaintRegion(found, true);
      this.canvas.style.cursor = 'pointer';
    } else {
      this.canvas.style.cursor = '';
    }
  }

  private handleMouseLeave(): void {
    if (this.hoveredRegion && this.lastCells.length > 0) {
      this.repaintRegion(this.hoveredRegion, false);
    }
    this.hoveredRegion = null;
    this.canvas.style.cursor = '';
  }

  /** Repaint a hit region with hover highlight (brighten fg + underline) or restore original. */
  private repaintRegion(region: HitRegion, highlight: boolean): void {
    const rowEnd = Math.min(region.row + region.height, this.lastCells.length);
    for (let r = region.row; r < rowEnd; r++) {
      const rowCells = this.lastCells[r];
      if (!rowCells) continue;
      const colEnd = Math.min(region.col + region.width, rowCells.length);
      for (let c = region.col; c < colEnd; c++) {
        const cell = rowCells[c];
        if (!cell) continue;
        const px = c * this.charSize.width;
        const py = r * this.charSize.height;
        this.ctx.clearRect(px, py, this.charSize.width, this.charSize.height);
        if (highlight) {
          const brightened: CharCell = {
            char: cell.char,
            fg: brightenColor(cell.fg),
            bg: cell.bg,
            attrs: (cell.attrs ?? 0) | 4, // add underline
          };
          fillCell(this.ctx, c, r, brightened, this.charSize);
        } else {
          fillCell(this.ctx, c, r, cell, this.charSize);
          // Also update prevCells to match so diff paint works correctly
          if (this.prevCells[r]?.[c]) {
            this.prevCells[r][c] = { ...cell };
          }
        }
      }
    }
  }

  /** Tear down observers and listeners. */
  destroy(): void {
    this.resizeObserver.disconnect();
    this.canvas.removeEventListener('click', this.boundClick);
    this.canvas.removeEventListener('mousemove', this.boundMouseMove);
    this.canvas.removeEventListener('mouseleave', this.boundMouseLeave);
  }
}
