// src/canvas/modal-manager.ts
/**
 * ModalManager — manages a stack of CharCell[][] overlay modals
 * rendered on top of the UnifiedCanvas grid at z-layer 1+.
 */

import type { CharCell } from '../renderer/canvas-text';
import type { Region, PanelResult, LocalHitRegion } from './types';
import type { UnifiedCanvas } from './unified-canvas';
import { theme } from '../renderer/theme';

export interface ModalState {
  name: string;
  region: Region;
  z: number;
  cells: CharCell[][];
  hitRegions: LocalHitRegion[];
  scrollOffset: number;
  totalContentRows: number;
  renderFn?: () => PanelResult;
}

export class ModalManager {
  private stack: ModalState[] = [];
  private uc: UnifiedCanvas;

  constructor(uc: UnifiedCanvas) {
    this.uc = uc;
  }

  /** Open a modal centered on screen at given % of grid. Returns the state for content updates. */
  open(name: string, widthPct: number, heightPct: number): ModalState {
    // Close existing modal with same name
    this.close(name);

    const totalCols = this.uc.totalCols;
    const totalRows = this.uc.totalRows;
    // Account for double-line border around modal (2 cols, 2 rows)
    const innerCols = Math.floor((totalCols - 2) * widthPct);
    const innerRows = Math.floor((totalRows - 2) * heightPct);
    const cols = innerCols + 2; // +2 for modal border
    const rows = innerRows + 2;
    const col = Math.floor((totalCols - cols) / 2);
    const row = Math.floor((totalRows - rows) / 2);

    const z = this.stack.length + 1;
    const state: ModalState = {
      name,
      region: { name: `modal_${name}`, col, row, cols, rows, type: 'grid', scrollOffset: 0 },
      z,
      cells: [],
      hitRegions: [],
      scrollOffset: 0,
      totalContentRows: 0,
    };

    this.stack.push(state);
    this.uc.markAllDirty();
    return state;
  }

  /** Update modal content. */
  setContent(name: string, result: PanelResult): void {
    const modal = this.stack.find(m => m.name === name);
    if (!modal) return;
    modal.cells = result.cells;
    modal.hitRegions = result.hitRegions || [];
    modal.totalContentRows = result.cells.length;

    // Register hit regions at modal z-layer
    this.uc.hitRegistry.clear(modal.z);
    if (modal.hitRegions.length > 0) {
      // Offset by modal content area (inside border)
      const contentRegion: Region = {
        ...modal.region,
        name: `modal_${name}_content`,
        col: modal.region.col + 1,
        row: modal.region.row + 1,
        cols: modal.region.cols - 2,
        rows: modal.region.rows - 2,
      };
      this.uc.hitRegistry.registerPanel(`modal_${name}`, contentRegion, modal.hitRegions, modal.z);
    }

    this.uc.markAllDirty();
  }

  close(name: string): void {
    const idx = this.stack.findIndex(m => m.name === name);
    if (idx === -1) return;
    const modal = this.stack[idx];
    this.uc.hitRegistry.clear(modal.z);
    this.stack.splice(idx, 1);
    this.uc.markAllDirty();
  }

  closeTopmost(): string | null {
    if (this.stack.length === 0) return null;
    const top = this.stack.pop()!;
    this.uc.hitRegistry.clear(top.z);
    this.uc.markAllDirty();
    return top.name;
  }

  get active(): boolean {
    return this.stack.length > 0;
  }

  get topmost(): ModalState | null {
    return this.stack[this.stack.length - 1] || null;
  }

  getStack(): ModalState[] {
    return this.stack;
  }

  isOpen(name: string): boolean {
    return this.stack.some(m => m.name === name);
  }

  /** Render all modals into the unified canvas grid. Called during paint. */
  renderInto(grid: CharCell[][], totalCols: number, totalRows: number): void {
    for (const modal of this.stack) {
      const { region, cells, scrollOffset } = modal;

      // 1. Dim backdrop -- darken all cells outside the modal
      for (let r = 0; r < totalRows; r++) {
        for (let c = 0; c < totalCols; c++) {
          if (
            r >= region.row &&
            r < region.row + region.rows &&
            c >= region.col &&
            c < region.col + region.cols
          )
            continue;
          if (grid[r] && grid[r][c]) {
            grid[r][c] = { ...grid[r][c], fg: theme.colors.dim, bg: undefined };
          }
        }
      }

      // 2. Draw double-line border around modal
      const D = {
        H: '\u2550',
        V: '\u2551',
        TL: '\u2554',
        TR: '\u2557',
        BL: '\u255A',
        BR: '\u255D',
      };
      const borderFg = theme.colors.accent;
      const bg = theme.colors.bg;

      // Top border
      if (region.row < totalRows && region.col + region.cols <= totalCols) {
        grid[region.row][region.col] = { char: D.TL, fg: borderFg, bg };
        for (let c = 1; c < region.cols - 1; c++) {
          grid[region.row][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[region.row][region.col + region.cols - 1] = { char: D.TR, fg: borderFg, bg };
      }
      // Bottom border
      const botRow = region.row + region.rows - 1;
      if (botRow < totalRows && region.col + region.cols <= totalCols) {
        grid[botRow][region.col] = { char: D.BL, fg: borderFg, bg };
        for (let c = 1; c < region.cols - 1; c++) {
          grid[botRow][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[botRow][region.col + region.cols - 1] = { char: D.BR, fg: borderFg, bg };
      }
      // Side borders + clear interior
      for (let r = 1; r < region.rows - 1; r++) {
        const gr = region.row + r;
        if (gr >= totalRows) break;
        grid[gr][region.col] = { char: D.V, fg: borderFg, bg };
        grid[gr][region.col + region.cols - 1] = { char: D.V, fg: borderFg, bg };
        // Clear interior
        for (let c = 1; c < region.cols - 1; c++) {
          grid[gr][region.col + c] = { char: ' ', fg: theme.colors.primary, bg };
        }
      }

      // 3. Write modal content (with scroll offset)
      const contentCol = region.col + 1;
      const contentRow = region.row + 1;
      const contentCols = region.cols - 2;
      const contentRows = region.rows - 2;

      for (let r = 0; r < contentRows; r++) {
        const srcRow = r + scrollOffset;
        if (srcRow >= cells.length) break;
        const srcRowCells = cells[srcRow];
        if (!srcRowCells) continue;
        for (let c = 0; c < Math.min(srcRowCells.length, contentCols); c++) {
          const gr = contentRow + r;
          const gc = contentCol + c;
          if (gr < totalRows && gc < totalCols) {
            grid[gr][gc] = { ...srcRowCells[c], bg };
          }
        }
      }
    }
  }

  /** Scroll the topmost modal. */
  scroll(deltaRows: number): void {
    const modal = this.topmost;
    if (!modal) return;
    const maxScroll = Math.max(0, modal.totalContentRows - (modal.region.rows - 2));
    modal.scrollOffset = Math.max(0, Math.min(modal.scrollOffset + deltaRows, maxScroll));
    this.uc.markAllDirty();
  }
}
