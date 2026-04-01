// src/renderer/line-cache.ts
/**
 * Line cache for narrative text.
 * Stores rendered narrative blocks for efficient scrollback.
 * Pretext-based virtualized scrolling will be added when needed.
 */

export interface CachedBlock {
  id: string;
  html: string;
  type: 'narrative' | 'player-action' | 'system' | 'thinking';
  timestamp: number;
}

export class LineCache {
  private blocks: CachedBlock[] = [];
  private maxBlocks = 1000;

  add(html: string, type: CachedBlock['type']): CachedBlock {
    const block: CachedBlock = {
      id: `block-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      html,
      type,
      timestamp: Date.now(),
    };

    this.blocks.push(block);

    // Trim old blocks
    if (this.blocks.length > this.maxBlocks) {
      this.blocks = this.blocks.slice(-this.maxBlocks);
    }

    return block;
  }

  getAll(): CachedBlock[] {
    return this.blocks;
  }

  clear(): void {
    this.blocks = [];
  }

  get length(): number {
    return this.blocks.length;
  }
}
