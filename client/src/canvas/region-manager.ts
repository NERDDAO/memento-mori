// src/canvas/region-manager.ts
import type { Region } from './types';

/**
 * Layout constants
 *
 * Outer frame:  col 0, col (totalCols-1), row 0, row (totalRows-1)  — double-line border
 * Inner area:   cols 1..(totalCols-2), rows 1..(totalRows-2)
 *
 * Row allocation (inside frame, top→bottom):
 *   row 1          : Header
 *   row 2          : hDiv0  (header/top-zone divider)
 *   rows 3..N      : Top zone  (2/3 of remaining content rows)
 *   row N+1        : hDiv1  (top/bottom zone divider)
 *   rows N+2..M    : Bottom zone  (1/3)
 *   row M+1        : hDiv2  (bottom zone/input divider)
 *   row M+2        : Input
 *   row M+3        : hDiv3  (input/status divider)
 *   row M+4        : Status
 *
 * Column allocation (inside frame):
 *   col 1..presentCols          : Present panel
 *   col presentCols+1           : vDiv0  (present/viewport)
 *   col presentCols+2..vDiv1-1  : Viewport panel
 *   col vDiv1                   : vDiv1  (viewport/sidebar)
 *   col vDiv1+1..totalCols-2    : Sidebar column
 *
 * Present width  : ~20 chars  (capped to available)
 * Sidebar width  : ~32 chars  (capped to available)
 *
 * Sidebar internal (top zone only):
 *   Top of sidebar → character panel (weight 2)
 *   sDiv0 row      : character/inventory divider
 *   inventory      : (weight 3)
 *   sDiv1 row      : inventory/quests divider
 *   quests         : (weight 2)
 */

const PRESENT_COLS  = 20;
const SIDEBAR_COLS  = 32;

export function computeRegions(totalCols: number, totalRows: number): Map<string, Region> {
  const regions = new Map<string, Region>();

  // ── Column layout ────────────────────────────────────────────────
  // Inner width: col 1 to col (totalCols-2) inclusive
  const innerCols = totalCols - 2;  // available content columns

  // Clamp panel widths so they fit
  const presentCols  = Math.min(PRESENT_COLS, Math.floor(innerCols * 0.2));
  const sidebarCols  = Math.min(SIDEBAR_COLS, Math.floor(innerCols * 0.25));
  // +2 for the two vertical divider columns
  const viewportCols = innerCols - presentCols - sidebarCols - 2;

  // Absolute column positions (1-indexed inside frame)
  const colPresent  = 1;                                        // start of Present
  const colVDiv0    = colPresent + presentCols;                 // vDiv between Present and Viewport
  const colViewport = colVDiv0 + 1;                             // start of Viewport
  const colVDiv1    = colViewport + viewportCols;               // vDiv between Viewport and Sidebar
  const colSidebar  = colVDiv1 + 1;                             // start of Sidebar

  // ── Row layout ───────────────────────────────────────────────────
  // Fixed rows:
  //   row 0  : outer top border
  //   row 1  : Header
  //   row 2  : hDiv0 (header/top-zone)
  //   ...    : Top zone
  //   ...    : hDiv1 (top/bottom zone)
  //   ...    : Bottom zone
  //   ...    : hDiv2 (bottom zone/input)
  //   ...    : Input
  //   ...    : hDiv3 (input/status)
  //   ...    : Status
  //   last   : outer bottom border
  // Fixed: 2(frame) + 1(header) + 4(hDivs) + 1(input) + 1(status) = 9
  const contentZoneRows = Math.max(totalRows - 9, 2);

  // Split content zone: top 2/3, bottom 1/3 (minus 1 for hDiv1 between them)
  const topZoneRows    = Math.max(Math.floor(contentZoneRows * 2 / 3), 3);
  const bottomZoneRows = Math.max(contentZoneRows - topZoneRows, 1);

  // Absolute row positions
  const rowHeader   = 1;
  const rowHDiv0    = 2;
  const rowTopStart = 3;
  const rowHDiv1    = rowTopStart + topZoneRows;                  // divider between top/bottom
  const rowBotStart = rowHDiv1 + 1;
  const rowHDiv2    = rowBotStart + bottomZoneRows;               // divider before input
  const rowInput    = rowHDiv2 + 1;
  const rowHDiv3    = rowInput + 1;                               // divider before status
  const rowStatus   = rowHDiv3 + 1;

  // ── Sidebar internal row split ───────────────────────────────────
  // Sidebar panels only live in the top zone
  // Weights: character=2, inventory=3, quests=2  (total 7 units; 2 divider rows)
  const sidebarContentRows = topZoneRows - 2; // 2 internal hDiv rows
  const charRows      = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const questRows     = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const inventoryRows = Math.max(sidebarContentRows - charRows - questRows, 1);

  const rowSDiv0 = rowTopStart + charRows;         // character/inventory divider
  const rowSDiv1 = rowSDiv0 + 1 + inventoryRows;  // inventory/quests divider

  // ── Helper to register ───────────────────────────────────────────
  function add(r: Region): void {
    regions.set(r.name, r);
  }

  // ── Fixed panels ─────────────────────────────────────────────────
  add({
    name: 'header',
    col: colPresent,
    row: rowHeader,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: 'input',
    col: colPresent,
    row: rowInput,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: 'status',
    col: colPresent,
    row: rowStatus,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  // ── Top zone panels ──────────────────────────────────────────────
  add({
    name: 'present',
    col: colPresent,
    row: rowTopStart,
    cols: presentCols,
    rows: topZoneRows,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: 'viewport',
    col: colViewport,
    row: rowTopStart,
    cols: viewportCols,
    rows: topZoneRows,
    type: 'grid',
    scrollOffset: 0,
  });

  // Sidebar sub-panels
  add({
    name: 'character',
    col: colSidebar,
    row: rowTopStart,
    cols: sidebarCols,
    rows: charRows,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: 'inventory',
    col: colSidebar,
    row: rowSDiv0 + 1,
    cols: sidebarCols,
    rows: inventoryRows,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: 'quests',
    col: colSidebar,
    row: rowSDiv1 + 1,
    cols: sidebarCols,
    rows: questRows,
    type: 'grid',
    scrollOffset: 0,
  });

  // ── Bottom zone panels ───────────────────────────────────────────
  // Narrative spans present+viewport columns (separated by vDiv0, but narrative renders over it)
  const narrativeCols = presentCols + 1 + viewportCols; // +1 includes the vDiv0 column
  add({
    name: 'narrative',
    col: colPresent,
    row: rowBotStart,
    cols: narrativeCols,
    rows: bottomZoneRows,
    type: 'pixel',
    scrollOffset: 0,
  });

  add({
    name: 'events',
    col: colSidebar,
    row: rowBotStart,
    cols: sidebarCols,
    rows: bottomZoneRows,
    type: 'pixel',
    scrollOffset: 0,
  });

  // ── Divider metadata regions (useful for border renderer) ────────
  // These are stored so the border renderer can query their positions
  add({
    name: '_hDiv0',
    col: colPresent,
    row: rowHDiv0,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_hDiv1',
    col: colPresent,
    row: rowHDiv1,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_hDiv2',
    col: colPresent,
    row: rowHDiv2,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_hDiv3',
    col: colPresent,
    row: rowHDiv3,
    cols: innerCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_vDiv0',
    col: colVDiv0,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_vDiv1',
    col: colVDiv1,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows + 1 + bottomZoneRows, // extends into bottom zone
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_sDiv0',
    col: colSidebar,
    row: rowSDiv0,
    cols: sidebarCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  add({
    name: '_sDiv1',
    col: colSidebar,
    row: rowSDiv1,
    cols: sidebarCols,
    rows: 1,
    type: 'grid',
    scrollOffset: 0,
  });

  return regions;
}
