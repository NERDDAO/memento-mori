// src/canvas/hit-registry.ts
import type { LocalHitRegion, Region } from './types';

export interface GlobalHitEntry {
  region: string;
  col: number;
  row: number;
  width: number;
  height: number;
  z: number;
  data: Record<string, unknown>;
}

export class HitRegistry {
  private entries: GlobalHitEntry[] = [];

  /** Clear all hit entries, or only those at a specific z-layer. */
  clear(z?: number): void {
    if (z === undefined) {
      this.entries = [];
    } else {
      this.entries = this.entries.filter(e => e.z !== z);
    }
  }

  /** Clear all hit entries for a specific region at a specific z-layer. */
  clearRegion(regionName: string, z: number): void {
    this.entries = this.entries.filter(e => !(e.region === regionName && e.z === z));
  }

  /**
   * Register all local hit regions for a panel, translating their coordinates
   * from panel-local space to global grid space.
   */
  registerPanel(
    regionName: string,
    region: Region,
    localRegions: LocalHitRegion[],
    z = 0,
  ): void {
    for (const local of localRegions) {
      this.entries.push({
        region: regionName,
        col: region.col + local.col,
        row: region.row + local.row,
        width: local.width,
        height: local.height,
        z,
        data: local.data,
      });
    }
  }

  /** Register a single pre-translated global hit entry. */
  register(entry: GlobalHitEntry): void {
    this.entries.push(entry);
  }

  /**
   * Test a grid position against all registered entries.
   * Returns the hit with the highest z-layer, or null if none.
   */
  hitTest(col: number, row: number): { region: string; data: Record<string, unknown> } | null {
    let best: GlobalHitEntry | null = null;

    for (const e of this.entries) {
      if (
        col >= e.col &&
        col < e.col + e.width &&
        row >= e.row &&
        row < e.row + e.height
      ) {
        if (best === null || e.z > best.z) {
          best = e;
        }
      }
    }

    if (best === null) return null;
    return { region: best.region, data: best.data };
  }

  /** Returns true if any entries exist at z > 0 (i.e. a modal/overlay layer is active). */
  hasModalLayer(): boolean {
    return this.entries.some(e => e.z > 0);
  }
}
