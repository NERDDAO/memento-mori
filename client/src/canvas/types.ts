// src/canvas/types.ts
import type { CharCell } from '../renderer/canvas-text';

export interface Region {
  name: string;
  col: number;
  row: number;
  cols: number;
  rows: number;
  type: 'grid' | 'pixel';
  scrollOffset: number;
}

export interface PanelResult {
  cells: CharCell[][];
  hitRegions?: LocalHitRegion[];
}

export interface LocalHitRegion {
  col: number;
  row: number;
  width: number;
  height: number;
  data: Record<string, unknown>;
}

export interface OffscreenSlot {
  canvas: HTMLCanvasElement;
  regionName: string;
}
