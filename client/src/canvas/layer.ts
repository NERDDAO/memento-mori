import type { PanelResult } from "./types";

export interface Layer {
  readonly id: string;
  readonly regionName: string;
  render(cols: number, rows: number): PanelResult;
  onKey?(key: string): void;
}
