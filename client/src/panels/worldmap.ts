// client/src/panels/worldmap.ts
/**
 * Compass rose world map panel renderer.
 * Draws a N/S/E/W layout centered on the current room.
 *
 *        Dark Cave
 *            |
 *   ? --- [Threshold] --- Market
 *            |
 *        The Pit
 */

import type { GameState, WorldMapRoom } from '../state/game-state';
import type { CharCell } from '../renderer/canvas-text';
import type { PanelResult, LocalHitRegion } from '../canvas/types';
import { theme } from '../renderer/theme';
import { coloredRow, emptyRow, textRow } from './panel-utils';

const COLOR_CURRENT  = theme.colors.accent;    // #8b5cf6 — purple
const COLOR_VISITED  = theme.colors.location;  // #7aa2d4 — blue
const COLOR_UNVISITED = '#3a3a48';             // dim gray
const COLOR_LINE     = theme.colors.dim;        // connector lines
const COLOR_BRACKET  = theme.colors.primary;    // brackets around current room

// ── helpers ──────────────────────────────────────────────────────────────────

/** Center a string in a field of `width` chars, padding with spaces. */
function center(text: string, width: number): string {
  if (text.length >= width) return text.slice(0, width);
  const left = Math.floor((width - text.length) / 2);
  return ' '.repeat(left) + text + ' '.repeat(width - left - text.length);
}

/**
 * Build a CharCell[] row of exactly `cols` cells from colored segments.
 * The segments are laid out starting at `startCol`, rest is filled with spaces.
 */
function segmentRow(
  segments: Array<{ text: string; fg: string }>,
  cols: number,
  startCol: number = 0,
): CharCell[] {
  const row: CharCell[] = Array.from({ length: cols }, () => ({
    char: ' ',
    fg: theme.colors.primary,
  }));

  let col = startCol;
  for (const seg of segments) {
    for (const ch of seg.text) {
      if (col >= cols) break;
      row[col] = { char: ch, fg: seg.fg };
      col++;
    }
  }
  return row;
}

// ── main renderer ─────────────────────────────────────────────────────────────

export function renderWorldMapPanel(cols: number, _rows: number, state: GameState): PanelResult {
  const cells: CharCell[][] = [];
  const hitRegions: LocalHitRegion[] = [];

  const wm = state.worldMap;
  if (!wm) {
    cells.push(textRow('No map data', COLOR_UNVISITED, cols));
    return { cells };
  }

  // Find current room by UUID with name fallback.
  const currentId = wm.current_id || '';
  const currentRoom = currentId
    ? wm.rooms.find(r => r.id === currentId)
    : wm.rooms.find(r => r.name === wm.current);
  const currentName = currentRoom?.name || wm.current || state.location?.name || 'Unknown';

  // Index rooms by direction (neighbor rooms from the current room).
  const byDir: Record<string, WorldMapRoom> = {};
  for (const room of wm.rooms) {
    if (room === currentRoom) continue;
    if (room.direction) {
      byDir[room.direction.toLowerCase()] = room;
    }
  }

  // Build the bracketed label for the current room.
  const label = `[${currentName}]`;

  // ── Determine layout dimensions ───────────────────────────────────────────
  // We need to know how wide the West name is so we can position the center.
  const westRoom  = byDir['west'];
  const eastRoom  = byDir['east'];
  const northRoom = byDir['north'];
  const southRoom = byDir['south'];

  const westText  = westRoom  ? (westRoom.visited  ? westRoom.name  : '?') : null;
  const eastText  = eastRoom  ? (eastRoom.visited  ? eastRoom.name  : '?') : null;
  const northText = northRoom ? (northRoom.visited ? northRoom.name : '?') : null;
  const southText = southRoom ? (southRoom.visited ? southRoom.name : '?') : null;

  // Connector strings.
  const HORIZ = ' --- ';  // between west/east and center label

  // Compute the start column for the center label so everything is roughly
  // centered in the panel.
  const westPart  = westText  ? westText + HORIZ : '';
  const eastPart  = eastText  ? HORIZ + eastText : '';
  const mainLine  = westPart + label + eastPart;

  // Try to center the full main line, but clamp so it doesn't go negative.
  const mainStart = Math.max(0, Math.floor((cols - mainLine.length) / 2));

  // Column where the center of the current room label begins (for | connectors).
  const labelStartCol = mainStart + westPart.length;
  const labelMidCol   = labelStartCol + Math.floor(label.length / 2);

  // ── North row ─────────────────────────────────────────────────────────────
  if (northText !== null) {
    const fg = northRoom!.visited ? COLOR_VISITED : COLOR_UNVISITED;
    const nameStart = Math.max(0, labelMidCol - Math.floor(northText.length / 2));
    cells.push(segmentRow([{ text: northText, fg }], cols, nameStart));

    // Connector |
    cells.push(segmentRow([{ text: '|', fg: COLOR_LINE }], cols, labelMidCol));
  }

  // ── Main row: West --- [Current] --- East ────────────────────────────────
  {
    const segments: Array<{ text: string; fg: string }> = [];

    if (westText !== null) {
      const fg = westRoom!.visited ? COLOR_VISITED : COLOR_UNVISITED;
      segments.push({ text: westText, fg });
      segments.push({ text: HORIZ, fg: COLOR_LINE });
    }

    // Bracket + current room name + bracket
    segments.push({ text: '[', fg: COLOR_BRACKET });
    segments.push({ text: currentName, fg: COLOR_CURRENT });
    segments.push({ text: ']', fg: COLOR_BRACKET });

    if (eastText !== null) {
      const fg = eastRoom!.visited ? COLOR_VISITED : COLOR_UNVISITED;
      segments.push({ text: HORIZ, fg: COLOR_LINE });
      segments.push({ text: eastText, fg });
    }

    const mainRowIdx = cells.length;
    cells.push(segmentRow(segments, cols, mainStart));

    // Register hit regions on each direction segment within the main row.
    // West hit region: from mainStart to just before HORIZ
    if (westText !== null) {
      const westStart = mainStart;
      const westWidth = westText.length;
      hitRegions.push({
        col: westStart,
        row: mainRowIdx,
        width: westWidth,
        height: 1,
        data: { action: 'go west' },
      });
    }

    // East hit region: right after label+HORIZ
    if (eastText !== null) {
      const eastStart = mainStart + westPart.length + label.length + HORIZ.length;
      const eastWidth = eastText.length;
      hitRegions.push({
        col: eastStart,
        row: mainRowIdx,
        width: eastWidth,
        height: 1,
        data: { action: 'go east' },
      });
    }
  }

  // ── South row ─────────────────────────────────────────────────────────────
  if (southText !== null) {
    // Connector |
    cells.push(segmentRow([{ text: '|', fg: COLOR_LINE }], cols, labelMidCol));

    const fg = southRoom!.visited ? COLOR_VISITED : COLOR_UNVISITED;
    const nameStart = Math.max(0, labelMidCol - Math.floor(southText.length / 2));
    const southRowIdx = cells.length;
    cells.push(segmentRow([{ text: southText, fg }], cols, nameStart));

    hitRegions.push({
      col: nameStart,
      row: southRowIdx,
      width: southText.length,
      height: 1,
      data: { action: 'go south' },
    });
  }

  // Register North hit region (row 0 if northText exists).
  if (northText !== null) {
    const nameStart = Math.max(0, labelMidCol - Math.floor(northText.length / 2));
    hitRegions.push({
      col: nameStart,
      row: 0,
      width: northText.length,
      height: 1,
      data: { action: 'go north' },
    });
  }

  return { cells, hitRegions };
}
