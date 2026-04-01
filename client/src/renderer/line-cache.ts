// src/renderer/line-cache.ts
/**
 * NarrativeStore — Pretext-measured block storage for virtualized scrolling.
 * Each block's height is computed via Pretext prepare() + layout(), no DOM needed.
 */

import { prepare, layout } from '@chenglou/pretext';
import { narrativeFont } from './theme';

export interface NarrativeBlock {
  id: string;
  text: string;      // raw text (for Pretext measurement)
  html: string;       // rendered HTML (for DOM insertion)
  type: string;       // 'narrative' | 'player-action' | 'system' | 'thinking'
  height: number;     // measured height in px (from Pretext)
  y: number;          // cumulative Y offset
  timestamp: number;
}

export class NarrativeStore {
  private blocks: NarrativeBlock[] = [];
  private _totalHeight = 0;
  private paneWidth: number;
  private font: string;
  private lineHeight: number;
  private blockMargin = 20; // matches CSS .narrative-block margin-bottom

  constructor(paneWidth: number) {
    this.paneWidth = Math.max(paneWidth - 64, 200); // subtract padding (32px each side)
    this.font = narrativeFont();
    this.lineHeight = 16 * 1.7; // fontSize * CSS line-height
  }

  add(text: string, html: string, type: string): NarrativeBlock {
    let height: number;
    try {
      const prepared = prepare(text, this.font);
      const result = layout(prepared, this.paneWidth, this.lineHeight);
      height = result.height + this.blockMargin;
    } catch {
      // Fallback: estimate ~27px per line, ~80 chars per line
      const lines = Math.max(1, Math.ceil(text.length / 80));
      height = lines * this.lineHeight + this.blockMargin;
    }

    const block: NarrativeBlock = {
      id: `b-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      text,
      html,
      type,
      height,
      y: this._totalHeight,
      timestamp: Date.now(),
    };

    this.blocks.push(block);
    this._totalHeight += height;
    return block;
  }

  get totalHeight(): number {
    return this._totalHeight;
  }

  get length(): number {
    return this.blocks.length;
  }

  /**
   * Get the range of block indices visible in the viewport.
   * Uses binary search on cumulative Y offsets.
   */
  getVisibleRange(scrollTop: number, viewportHeight: number): { start: number; end: number } {
    if (this.blocks.length === 0) return { start: 0, end: 0 };

    // Binary search for first visible block
    let lo = 0;
    let hi = this.blocks.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.blocks[mid].y + this.blocks[mid].height <= scrollTop) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    const start = lo;

    // Linear scan for last visible block (viewport is usually small)
    const bottom = scrollTop + viewportHeight;
    let end = start;
    while (end < this.blocks.length && this.blocks[end].y < bottom) {
      end++;
    }

    // Add buffer of 3 blocks above and below for smooth scrolling
    return {
      start: Math.max(0, start - 3),
      end: Math.min(this.blocks.length, end + 3),
    };
  }

  getBlock(index: number): NarrativeBlock | undefined {
    return this.blocks[index];
  }

  getAll(): NarrativeBlock[] {
    return this.blocks;
  }

  /** Remove a block by ID and recompute Y offsets. */
  removeById(id: string): boolean {
    const idx = this.blocks.findIndex(b => b.id === id);
    if (idx === -1) return false;
    this.blocks.splice(idx, 1);
    // Recompute Y offsets from the removed index onward
    this._totalHeight = idx > 0 ? this.blocks[idx - 1].y + this.blocks[idx - 1].height : 0;
    for (let i = idx; i < this.blocks.length; i++) {
      this.blocks[i].y = this._totalHeight;
      this._totalHeight += this.blocks[i].height;
    }
    return true;
  }

  /**
   * Remeasure all blocks at a new width (called on window resize).
   * Pretext's layout() is ~0.09ms/500 texts, so this is cheap.
   */
  remeasure(newWidth: number): void {
    this.paneWidth = Math.max(newWidth - 64, 200);
    this._totalHeight = 0;
    for (const block of this.blocks) {
      try {
        const prepared = prepare(block.text, this.font);
        const result = layout(prepared, this.paneWidth, this.lineHeight);
        block.height = result.height + this.blockMargin;
      } catch {
        const lines = Math.max(1, Math.ceil(block.text.length / 80));
        block.height = lines * this.lineHeight + this.blockMargin;
      }
      block.y = this._totalHeight;
      this._totalHeight += block.height;
    }
  }
}
