// src/canvas/border-renderer.ts
/**
 * Draws the complete BBS-style border layout into a CharCell[][] grid.
 *
 * Character sets used:
 *   Double-line outer frame  : ╔═╗║╚╝  junctions: ╠╣╦╩╬
 *   Single-line inner dividers: ─│  corners: ┌┐└┘  T-junctions: ├┤┬┴┼
 *   Mixed (single meets double border):
 *     single-H meets double-V left  : ╞  (U+255E)  right: ╡  (U+2561)
 *     double-V meets single-H top   : ╥  (U+2565)  bottom: ╨  (U+2568)
 *     single-V meets double-H top   : ╟  (U+255F)  bottom: ╚→╙ no — see below
 *     We use subset that's actually needed for this layout.
 */

import type { CharCell } from '../renderer/canvas-text';
import type { Region } from './types';
import { theme } from '../renderer/theme';

// ── Box-drawing codepoints ────────────────────────────────────────

// Double line
const D_TL  = '╔'; const D_TR  = '╗'; const D_BL  = '╚'; const D_BR  = '╝';
const D_H   = '═'; const D_V   = '║';
const D_ML  = '╠'; const D_MR  = '╣';   // double T-junctions (double crosses single-H)
const D_MT  = '╦'; const D_MB  = '╩';   // double top/bottom T-junctions
const D_CRS = '╬';                       // double cross

// Single line
const S_H   = '─'; const S_V   = '│';
const S_TL  = '┌'; const S_TR  = '┐'; const S_BL  = '└'; const S_BR  = '┘';
const S_ML  = '├'; const S_MR  = '┤';   // single left/right T-junctions
const S_MT  = '┬'; const S_MB  = '┴';   // single top/bottom T-junctions
const S_CRS = '┼';                       // single cross

// Mixed junctions (single line meets double-line frame)
// Single horizontal bar terminating at double-line vertical border
const M_SH_DV_L = '╞'; // single-H exits right from double-V (left frame edge)
const M_SH_DV_R = '╡'; // single-H exits left into double-V (right frame edge)
// Single vertical bar terminating at double-line horizontal border
const M_SV_DH_T = '╥'; // single-V hangs down from double-H (top frame edge)
const M_SV_DH_B = '╨'; // single-V rises up from double-H (bottom frame edge)

// ── Helper ────────────────────────────────────────────────────────

function setCell(grid: CharCell[][], row: number, col: number, char: string, fg: string): void {
  if (row < 0 || col < 0 || row >= grid.length || col >= (grid[0]?.length ?? 0)) return;
  grid[row][col] = { char, fg };
}

function hLine(grid: CharCell[][], row: number, colStart: number, colEnd: number, char: string, fg: string): void {
  for (let c = colStart; c <= colEnd; c++) setCell(grid, row, c, char, fg);
}

function vLine(grid: CharCell[][], col: number, rowStart: number, rowEnd: number, char: string, fg: string): void {
  for (let r = rowStart; r <= rowEnd; r++) setCell(grid, r, col, char, fg);
}

// ── Main export ───────────────────────────────────────────────────

export function drawBorders(
  grid: CharCell[][],
  regions: Map<string, Region>,
  totalCols: number,
  totalRows: number,
): void {
  const fg = theme.colors.dim;

  // Retrieve divider region positions from the metadata regions computed by region-manager
  const hDiv0 = regions.get('_hDiv0');
  const hDiv1 = regions.get('_hDiv1');
  const hDiv2 = regions.get('_hDiv2');
  const hDiv3 = regions.get('_hDiv3');
  const vDiv0 = regions.get('_vDiv0');
  const vDiv1 = regions.get('_vDiv1');
  const sDiv0 = regions.get('_sDiv0');
  const sDiv1 = regions.get('_sDiv1');

  const vDiv2 = regions.get('_vDiv2');
  const vDivMap = regions.get('_vDivMap');

  if (!hDiv0 || !hDiv1 || !hDiv2 || !hDiv3 || !vDiv0 || !vDiv1 || !sDiv0 || !sDiv1) {
    console.warn('[border-renderer] Missing divider metadata regions — skipping border draw');
    return;
  }

  // Narrow to non-optional for use in nested functions
  const vd0: Region = vDiv0;
  const vd1: Region = vDiv1;

  const lastCol = totalCols - 1;
  const lastRow = totalRows - 1;

  // Inner area column bounds
  const innerColStart = 1;
  const innerColEnd   = lastCol - 1;

  // ── 1. Outer double-line frame ────────────────────────────────────
  // Corners
  setCell(grid, 0,       0,       D_TL, fg);
  setCell(grid, 0,       lastCol, D_TR, fg);
  setCell(grid, lastRow, 0,       D_BL, fg);
  setCell(grid, lastRow, lastCol, D_BR, fg);
  // Top/bottom horizontal edges
  hLine(grid, 0,       1, lastCol - 1, D_H, fg);
  hLine(grid, lastRow, 1, lastCol - 1, D_H, fg);
  // Left/right vertical edges
  vLine(grid, 0,       1, lastRow - 1, D_V, fg);
  vLine(grid, lastCol, 1, lastRow - 1, D_V, fg);

  // ── 2. Horizontal dividers ────────────────────────────────────────
  // All horizontal dividers run the full inner width.
  // Where they meet the outer double-V frame they use ╠/╣.
  // Where they cross a single-V divider they use ┼ (or ┬/┴ at T-ends).

  function drawHDiv(row: number): void {
    // Left junction with double-V frame
    setCell(grid, row, 0, D_ML, fg);
    // Right junction with double-V frame
    setCell(grid, row, lastCol, D_MR, fg);
    // Fill inner with double-H
    hLine(grid, row, innerColStart, innerColEnd, D_H, fg);
    // Fix intersections with any vertical dividers that cross or touch this row
    if (row >= vd0.row && row < vd0.row + vd0.rows) {
      setCell(grid, row, vd0.col, '\u256A', fg); // ╪ double-H × single-V (crossing)
    }
    if (row >= vd1.row && row < vd1.row + vd1.rows) {
      setCell(grid, row, vd1.col, '\u256A', fg); // ╪ double-H × single-V (crossing)
    }
    if (vDiv2 && row >= vDiv2.row && row < vDiv2.row + vDiv2.rows) {
      setCell(grid, row, vDiv2.col, '\u256A', fg); // ╪ double-H × single-V (crossing)
    }
    if (vDivMap && row >= vDivMap.row && row < vDivMap.row + vDivMap.rows) {
      setCell(grid, row, vDivMap.col, '\u256A', fg); // ╪ double-H × single-V (crossing)
    }
  }

  // hDiv0 after header — double-H (header is fixed row, treated as major divider)
  drawHDiv(hDiv0.row);
  // hDiv1 after status
  drawHDiv(hDiv1.row);
  // hDiv2 between top and bottom zone
  drawHDiv(hDiv2.row);
  // hDiv3 between bottom zone and input
  drawHDiv(hDiv3.row);

  // For hDiv2 (top/bottom zone boundary): vDiv0 does NOT extend into bottom zone,
  // but vDiv1 DOES. Correct the vDiv0 junction on hDiv2 row — it should be ╦
  // (top T of single-V into double-H, from above only — vDiv0 ends here).
  // vDiv0 ends at row (hDiv2.row - 1), so at hDiv2.row we place a bottom-T for single-V.
  // Actually since vDiv0 stops at top zone end, the character at (hDiv2.row, vDiv0.col)
  // should be ╦ if vDiv0 is ABOVE this divider (i.e. the single-V comes from above only).
  // Use ╦ = double-H with single-V going UP only — but standard box drawing doesn't have that.
  // Closest: ╤ (double-H with single-V bottom) or ╧ (double-H with single-V top).
  // vDiv0 is ABOVE hDiv2 → use ╧ (double-H, single-V exits upward = bottom junction from above)
  setCell(grid, hDiv2.row, vDiv0.col, '╧', fg);
  // vDiv1 crosses hDiv2 (extends into bottom zone) → use ╪ (double-H crossed by single-V)
  // ╪ = U+256A — but this might not be in all fonts. Use ╫ (double-V crossed by single-H)
  // Actually we want double-H (row direction) crossed by single-V (col direction): ╪ U+256A
  setCell(grid, hDiv2.row, vDiv1.col, '\u256A', fg); // ╪

  // ── 3. Vertical dividers in top zone ─────────────────────────────
  // vDiv0: Present | Viewport  (top zone only)
  vLine(grid, vDiv0.col, vDiv0.row, vDiv0.row + vDiv0.rows - 1, S_V, fg);
  // vDiv1: Viewport | Sidebar  (top zone + bottom zone, i.e. vDiv1.rows)
  vLine(grid, vDiv1.col, vDiv1.row, vDiv1.row + vDiv1.rows - 1, S_V, fg);

  // Junction at hDiv2 row for vDiv0 was set above.
  // Junction at hDiv2 row for vDiv1 was set above.

  // Where vDiv0/vDiv1 meet hDiv0, hDiv1, hDiv3 (which are double-H lines):
  // Single-V meets double-H → use ╫ (U+256B) = double-V × single-H, not what we need.
  // We need: single-V continued, double-H continued → ╪ (U+256A).
  // But simpler: for top-of-vDiv (meeting top frame), use M_SV_DH_T = ╥.
  // For intersections with hDivs within the vDiv range:
  const vDivCols = [vDiv0.col, vDiv1.col];
  const hDivRows = [hDiv0.row, hDiv1.row, hDiv3.row];

  for (const vc of vDivCols) {
    // Top of vDiv meets outer double-H frame (row 0) — but vDivs start at row 5+ inside frame
    // Top of vDiv meets hDiv1 (which is directly above top zone start) → M_SV_DH_B junction
    // The junction char at a double-H row crossed by a continuing single-V is ╪ (U+256A)
    for (const hr of hDivRows) {
      // Check if this vDiv column crosses this hDiv row
      const vr = vc === vDiv0.col ? vDiv0 : vDiv1;
      if (hr >= vr.row && hr < vr.row + vr.rows) {
        setCell(grid, hr, vc, '\u256A', fg); // ╪ double-H × single-V
      }
    }

    // Top frame: vDiv starts at rowTopStart (row 5), which is 1 row below hDiv1 (row 4).
    // No junction needed with outer top frame (row 0).

    // At hDiv1 bottom edge (row 4), the vDiv hasn't started yet — no junction.
    // However the vDivs START at rowTopStart. The hDiv1 is at rowTopStart-1.
    // So at hDiv1 row, the single-V does NOT cross. Correct — ╪ only placed if within range.
  }

  // Junction where vDiv meets outer top frame: vDivs start inside, so only junction with
  // hDiv1 if it falls within range (it doesn't — hDiv1 is row 4, vDivs start at row 5).
  // However we DO need a junction at row 0 (outer frame) only if vDiv starts at row 1 (it doesn't).
  // The outer frame top row junction for a single-V entering from below: ╥
  // This only applies if vDivs ran all the way to row 0, which they don't.

  // ── 4. Sidebar internal horizontal dividers (single-line) ─────────
  // These run from colSidebar to colSidebar+sidebarCols-1
  const sCol = sDiv0.col;
  const sEnd = sDiv0.col + sDiv0.cols - 1;

  // sDiv0: character | inventory
  setCell(grid, sDiv0.row, vDiv1.col, S_ML, fg); // left junction touches vDiv1
  hLine(grid, sDiv0.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv0.row, lastCol, M_SH_DV_R, fg); // right junction at double-V frame

  // sDiv1: inventory | quests
  setCell(grid, sDiv1.row, vDiv1.col, S_ML, fg);
  hLine(grid, sDiv1.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv1.row, lastCol, M_SH_DV_R, fg);

  // ── 5. Junctions: top/bottom of vDivs at hDivs ───────────────────
  // vDiv0 starts at rowTopStart (row after hDiv1).
  // At its top (hDiv1 row) the double-H continues — no junction needed (vDiv hasn't started).
  // At its bottom (row hDiv2) — already handled above as ╧.

  // vDiv1 top is same as vDiv0 top (rowTopStart). Same logic.
  // vDiv1 passes through hDiv2 → already handled as ╪.
  // vDiv1 bottom is at rowHDiv3 - 1. At hDiv3 row, vDiv1 ends just above it.
  // Actually vDiv1.rows = topZoneRows + 1 + bottomZoneRows
  // so vDiv1 ends at row = vDiv1.row + vDiv1.rows - 1 = rowBotStart + bottomZoneRows - 1 = rowHDiv3 - 1
  // So at hDiv3 row, vDiv1 does NOT continue below → use ╧ again (single-V from above only)
  setCell(grid, hDiv3.row, vDiv1.col, '╧', fg);

  // vDiv0 does not reach hDiv3 at all (ends at hDiv2).

  // ── 6. Where vDivs meet outer top/bottom double-H frame ──────────
  // vDiv0 and vDiv1 do NOT touch the outer frame rows (row 0 / lastRow).
  // They start at rowTopStart (row 5) and end above hDiv3, never reaching row 0 or lastRow.
  // No mixed junctions needed with outer frame for vertical dividers.

  // However, hDivs DO span the full inner width and cross double-V columns at col 0/lastCol
  // — already handled by D_ML/D_MR in drawHDiv().

  // ── 7. vDivMap: map | cards divider in top zone ───────────────────
  if (vDivMap) {
    vLine(grid, vDivMap.col, vDivMap.row, vDivMap.row + vDivMap.rows - 1, S_V, fg);
    // Junction at hDiv0 (above top zone): single-V goes down from double-H
    setCell(grid, hDiv0.row, vDivMap.col, M_SV_DH_T, fg); // ╥
    // Junction at hDiv1 (below top zone): single-V comes from above
    setCell(grid, hDiv1.row, vDivMap.col, '╧', fg); // ╧
  }

  // ── 8. vDiv2: narrative | viewer divider in bottom zone ──────────
  if (vDiv2) {
    vLine(grid, vDiv2.col, vDiv2.row, vDiv2.row + vDiv2.rows - 1, S_V, fg);
    // Junction at hDiv1 (top of bottom zone): vDiv2 starts below → ╤ (single-V goes down from double-H)
    setCell(grid, hDiv1.row, vDiv2.col, M_SV_DH_T, fg); // ╥
    // Junction at hDiv2 (bottom of bottom zone): vDiv2 ends above → ╧ (single-V comes from above into double-H)
    setCell(grid, hDiv2.row, vDiv2.col, M_SV_DH_B, fg); // ╨
  }
}
