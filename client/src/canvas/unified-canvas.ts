// src/canvas/unified-canvas.ts
/**
 * UnifiedCanvas — owns the single <canvas> element, maintains the CharCell grid,
 * runs the paint loop, and handles mouse routing.
 */

import type { CharCell, CharSize } from '../renderer/canvas-text';
import { measureChar, fillCell, MONO_FONT } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';
import { computeRegions } from './region-manager';
import { drawBorders } from './border-renderer';
import { HitRegistry } from './hit-registry';
import { ModalManager } from './modal-manager';
import type { Region, PanelResult } from './types';

// ── Types ─────────────────────────────────────────────────────────

type ClickHandler  = (region: string, data: Record<string, unknown>) => void;
type WheelHandler  = (region: string, deltaY: number) => void;
type PixelRenderer = (ctx: CanvasRenderingContext2D, region: Region, charSize: CharSize) => void;

interface PixelRendererEntry {
  regionName: string;
  renderer: PixelRenderer;
}

interface OffscreenEntry {
  regionName: string;
  canvas: HTMLCanvasElement;
}

// ── UnifiedCanvas ─────────────────────────────────────────────────

export class UnifiedCanvas {
  readonly canvas: HTMLCanvasElement;
  regions: Map<string, Region>;
  readonly hitRegistry: HitRegistry;
  readonly modalManager: ModalManager;
  totalCols: number;
  totalRows: number;

  private readonly ctx: CanvasRenderingContext2D;
  private charSize: CharSize;
  private grid: CharCell[][];        // main content grid [row][col]
  private borderGrid: CharCell[][];  // border-only grid, rebuilt on resize

  private dirtySet = new Set<string>();  // region names needing repaint
  private allDirty = true;
  private renderScheduled = false;

  private clickHandlers:  ClickHandler[]  = [];
  private wheelHandlers:  WheelHandler[]  = [];
  private pixelRenderers: PixelRendererEntry[] = [];
  private offscreenSlots: OffscreenEntry[] = [];

  private observer: ResizeObserver;

  constructor(container: HTMLElement) {
    // Create canvas element
    this.canvas = document.createElement('canvas');
    this.canvas.style.display  = 'block';
    this.canvas.style.width    = '100%';
    this.canvas.style.height   = '100%';
    container.appendChild(this.canvas);

    const ctx = this.canvas.getContext('2d');
    if (!ctx) throw new Error('UnifiedCanvas: failed to get 2d context');
    this.ctx = ctx;

    // Measure char size (sets font on ctx as side effect)
    this.charSize = measureChar(this.ctx, MONO_FONT);

    // Initial dummy state before first resize
    this.totalCols  = 1;
    this.totalRows  = 1;
    this.grid       = [[{ char: ' ', fg: theme.colors.primary }]];
    this.borderGrid = [[{ char: ' ', fg: theme.colors.primary }]];
    this.regions      = new Map();
    this.hitRegistry  = new HitRegistry();
    this.modalManager = new ModalManager(this);

    // Bind mouse events
    this.canvas.addEventListener('click',      this._onClick.bind(this));
    this.canvas.addEventListener('mousemove',  this._onMouseMove.bind(this));
    this.canvas.addEventListener('mouseleave', this._onMouseLeave.bind(this));
    this.canvas.addEventListener('wheel',      this._onWheel.bind(this), { passive: false });

    // Watch for container size changes
    this.observer = new ResizeObserver(() => this._resize());
    this.observer.observe(container);

    // Initial layout
    this._resize();
  }

  // ── Resize ───────────────────────────────────────────────────────

  private _resize(): void {
    const rect = this.canvas.parentElement!.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    this.canvas.width  = Math.floor(rect.width  * dpr);
    this.canvas.height = Math.floor(rect.height * dpr);

    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Re-measure char size after transform change
    this.charSize  = measureChar(this.ctx, MONO_FONT);
    const { width: cw, height: ch } = this.charSize;

    this.totalCols = Math.max(Math.floor(rect.width  / cw), 10);
    this.totalRows = Math.max(Math.floor(rect.height / ch), 5);

    // Allocate fresh grids
    this.grid       = this._allocGrid(this.totalRows, this.totalCols);
    this.borderGrid = this._allocGrid(this.totalRows, this.totalCols);

    // Recompute regions and borders
    this.regions = computeRegions(this.totalCols, this.totalRows);
    drawBorders(this.borderGrid, this.regions, this.totalCols, this.totalRows);

    // Full repaint
    this.markAllDirty();
  }

  private _allocGrid(rows: number, cols: number): CharCell[][] {
    const empty: CharCell = { char: ' ', fg: theme.colors.primary };
    return Array.from({ length: rows }, () =>
      Array.from({ length: cols }, () => ({ ...empty })),
    );
  }

  // ── Public content setters ───────────────────────────────────────

  /** Write a PanelResult's cells into the grid and register its hit regions. */
  setRegionContent(name: string, result: PanelResult): void {
    const region = this.regions.get(name);
    if (!region) return;

    const { cells, hitRegions } = result;

    // Write cells into the main grid at region offset
    for (let r = 0; r < cells.length && r < region.rows; r++) {
      const row = cells[r];
      for (let c = 0; c < row.length && c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr < this.totalRows && gc < this.totalCols) {
          this.grid[gr][gc] = row[c];
        }
      }
    }

    // Update hit regions — only clear this region's z=0 entries
    this.hitRegistry.clearRegion(name, 0);
    if (hitRegions && hitRegions.length > 0) {
      this.hitRegistry.registerPanel(name, region, hitRegions, 0);
    }

    this.markDirty(name);
  }

  /** Attach an offscreen HTMLCanvasElement to be blitted into a region. */
  setOffscreen(regionName: string, offscreenCanvas: HTMLCanvasElement): void {
    const existing = this.offscreenSlots.findIndex(s => s.regionName === regionName);
    if (existing >= 0) {
      this.offscreenSlots[existing] = { regionName, canvas: offscreenCanvas };
    } else {
      this.offscreenSlots.push({ regionName, canvas: offscreenCanvas });
    }
    this.markDirty(regionName);
  }

  /** Attach a pixel-level renderer callback for a region (e.g. narrative). */
  setPixelRenderer(
    regionName: string,
    renderer: (ctx: CanvasRenderingContext2D, region: Region, charSize: CharSize) => void,
  ): void {
    const existing = this.pixelRenderers.findIndex(p => p.regionName === regionName);
    if (existing >= 0) {
      this.pixelRenderers[existing] = { regionName, renderer };
    } else {
      this.pixelRenderers.push({ regionName, renderer });
    }
    this.markDirty(regionName);
  }

  // ── Event registration ───────────────────────────────────────────

  onClick(handler: ClickHandler): void {
    this.clickHandlers.push(handler);
  }

  onWheel(handler: WheelHandler): void {
    this.wheelHandlers.push(handler);
  }

  // ── Dirty tracking ───────────────────────────────────────────────

  markDirty(name: string): void {
    this.dirtySet.add(name);
    this._scheduleRender();
  }

  markAllDirty(): void {
    this.allDirty = true;
    this._scheduleRender();
  }

  private _scheduleRender(): void {
    if (this.renderScheduled) return;
    this.renderScheduled = true;
    requestAnimationFrame(() => {
      this.renderScheduled = false;
      this._paint();
    });
  }

  // ── Getters ──────────────────────────────────────────────────────

  getRegion(name: string): Region | undefined {
    return this.regions.get(name);
  }

  getCharSize(): CharSize {
    return this.charSize;
  }

  // ── Paint loop ───────────────────────────────────────────────────

  private _paint(): void {
    const ctx = this.ctx;
    const cs  = this.charSize;

    if (this.allDirty) {
      // Full repaint
      ctx.fillStyle = theme.colors.bg;
      ctx.fillRect(0, 0, this.totalCols * cs.width, this.totalRows * cs.height);

      // 1. Draw border chars
      for (let r = 0; r < this.totalRows; r++) {
        for (let c = 0; c < this.totalCols; c++) {
          const cell = this.borderGrid[r][c];
          if (cell.char !== ' ') fillCell(ctx, c, r, cell, cs);
        }
      }

      // 2. Paint all grid region cells
      for (const region of this.regions.values()) {
        if (region.name.startsWith('_') || region.type !== 'grid') continue;
        this._paintGridRegion(region);
      }

      // 3. Paint pixel renderers (clip + call)
      for (const entry of this.pixelRenderers) {
        const region = this.regions.get(entry.regionName);
        if (!region) continue;
        this._paintPixelRegion(region, entry.renderer);
      }

      // 4. Blit offscreen canvases
      for (const slot of this.offscreenSlots) {
        const region = this.regions.get(slot.regionName);
        if (!region) continue;
        this._blitOffscreen(region, slot.canvas);
      }

      // Paint modal overlays on top of everything
      if (this.modalManager.active) {
        this.modalManager.renderInto(this.grid, this.totalCols, this.totalRows);
        // Repaint: clear canvas, draw dimmed borders + grid, then pixel/offscreen regions
        ctx.fillStyle = theme.colors.bg;
        ctx.fillRect(0, 0, this.totalCols * cs.width, this.totalRows * cs.height);

        // Draw dimmed border chars
        for (let r = 0; r < this.totalRows; r++) {
          for (let c = 0; c < this.totalCols; c++) {
            const bc = this.borderGrid[r][c];
            if (bc.char !== ' ') {
              // Dim the border color to match backdrop
              fillCell(ctx, c, r, { ...bc, fg: theme.colors.dim }, cs);
            }
          }
        }

        // Draw grid cells (modal content + dimmed backdrop)
        for (let r = 0; r < this.totalRows; r++) {
          for (let c = 0; c < this.totalCols; c++) {
            const cell = this.grid[r][c];
            if (cell.char !== ' ' || cell.bg) {
              fillCell(ctx, c, r, cell, cs);
            }
          }
        }

        // Re-composite pixel renderers and offscreen slots,
        // but clip them so they don't overwrite the modal area
        const modalRegions = this.modalManager.getStack().map(m => m.region);
        for (const entry of this.pixelRenderers) {
          const region = this.regions.get(entry.regionName);
          if (region) {
            // Clip out modal areas from this region's paint
            ctx.save();
            ctx.beginPath();
            const rpx = region.col * cs.width;
            const rpy = region.row * cs.height;
            const rpw = region.cols * cs.width;
            const rph = region.rows * cs.height;
            ctx.rect(rpx, rpy, rpw, rph);
            for (const mr of modalRegions) {
              // Punch out modal rectangle (use evenodd to subtract)
              ctx.rect(mr.col * cs.width, mr.row * cs.height, mr.cols * cs.width, mr.rows * cs.height);
            }
            ctx.clip('evenodd');
            entry.renderer(ctx, region, cs);
            ctx.restore();
          }
        }
        for (const slot of this.offscreenSlots) {
          const region = this.regions.get(slot.regionName);
          if (region) {
            ctx.save();
            ctx.beginPath();
            const rpx = region.col * cs.width;
            const rpy = region.row * cs.height;
            const rpw = region.cols * cs.width;
            const rph = region.rows * cs.height;
            ctx.rect(rpx, rpy, rpw, rph);
            for (const mr of modalRegions) {
              ctx.rect(mr.col * cs.width, mr.row * cs.height, mr.cols * cs.width, mr.rows * cs.height);
            }
            ctx.clip('evenodd');
            this._blitOffscreen(region, slot.canvas);
            ctx.restore();
          }
        }
      }

      this.allDirty = false;
      this.dirtySet.clear();
    } else if (this.modalManager.active) {
      // When modals are active, force full repaint to handle overlay correctly
      this.allDirty = true;
      this.dirtySet.clear();
      this._paint();
      return;
    } else {
      // Partial repaint — only dirty regions
      for (const name of this.dirtySet) {
        const region = this.regions.get(name);
        if (!region || region.name.startsWith('_')) continue;

        // Clear the region's pixel bounds
        const px = region.col * cs.width;
        const py = region.row * cs.height;
        const pw = region.cols * cs.width;
        const ph = region.rows * cs.height;
        ctx.fillStyle = theme.colors.bg;
        ctx.fillRect(px, py, pw, ph);

        // Repaint border chars within this region's bounds (for border overlap)
        for (let r = region.row; r < region.row + region.rows && r < this.totalRows; r++) {
          for (let c = region.col; c < region.col + region.cols && c < this.totalCols; c++) {
            const cell = this.borderGrid[r][c];
            if (cell.char !== ' ') fillCell(ctx, c, r, cell, cs);
          }
        }

        if (region.type === 'grid') {
          this._paintGridRegion(region);
        }

        // Pixel renderer
        const pixEntry = this.pixelRenderers.find(p => p.regionName === name);
        if (pixEntry) this._paintPixelRegion(region, pixEntry.renderer);

        // Offscreen
        const offEntry = this.offscreenSlots.find(s => s.regionName === name);
        if (offEntry) this._blitOffscreen(region, offEntry.canvas);
      }

      this.dirtySet.clear();
    }
  }

  private _paintGridRegion(region: Region): void {
    const ctx = this.ctx;
    const cs  = this.charSize;
    for (let r = 0; r < region.rows; r++) {
      for (let c = 0; c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr >= this.totalRows || gc >= this.totalCols) continue;
        const cell = this.grid[gr][gc];
        if (cell.char !== ' ' || cell.bg) {
          fillCell(ctx, gc, gr, cell, cs);
        }
      }
    }
  }

  private _paintPixelRegion(region: Region, renderer: PixelRenderer): void {
    const ctx = this.ctx;
    const cs  = this.charSize;
    const px  = region.col  * cs.width;
    const py  = region.row  * cs.height;
    const pw  = region.cols * cs.width;
    const ph  = region.rows * cs.height;

    ctx.save();
    ctx.beginPath();
    ctx.rect(px, py, pw, ph);
    ctx.clip();
    renderer(ctx, region, cs);
    ctx.restore();
  }

  private _blitOffscreen(region: Region, offscreen: HTMLCanvasElement): void {
    const ctx = this.ctx;
    const cs  = this.charSize;
    const px  = region.col  * cs.width;
    const py  = region.row  * cs.height;
    const pw  = region.cols * cs.width;
    const ph  = region.rows * cs.height;
    ctx.drawImage(offscreen, px, py, pw, ph);
  }

  // ── Mouse helpers ─────────────────────────────────────────────────

  private _pixelToGrid(clientX: number, clientY: number): { col: number; row: number } {
    const rect = this.canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    return {
      col: Math.floor(x / this.charSize.width),
      row: Math.floor(y / this.charSize.height),
    };
  }

  private _pointToRegion(col: number, row: number): string | null {
    for (const region of this.regions.values()) {
      if (region.name.startsWith('_')) continue;
      if (
        col >= region.col && col < region.col + region.cols &&
        row >= region.row && row < region.row + region.rows
      ) {
        return region.name;
      }
    }
    return null;
  }

  // ── Mouse event handlers ──────────────────────────────────────────

  private _onClick(e: MouseEvent): void {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    if (hit) {
      for (const h of this.clickHandlers) h(hit.region, hit.data);
    }
  }

  private _onMouseMove(e: MouseEvent): void {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    this.canvas.style.cursor = hit ? 'pointer' : 'default';
  }

  private _onMouseLeave(_e: MouseEvent): void {
    this.canvas.style.cursor = 'default';
  }

  private _onWheel(e: WheelEvent): void {
    e.preventDefault();
    // If a modal is active, scroll it instead of the underlying region
    if (this.modalManager.active) {
      const delta = e.deltaY > 0 ? 3 : -3;
      this.modalManager.scroll(delta);
      return;
    }
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const regionName = this._pointToRegion(col, row);
    if (regionName) {
      for (const h of this.wheelHandlers) h(regionName, e.deltaY);
    }
  }
}
