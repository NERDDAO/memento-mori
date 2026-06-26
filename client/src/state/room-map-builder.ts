// src/state/room-map-builder.ts
//
// Builds a RoomMap (the existing roguelike room-interior model from
// src/map/types.ts) for the opening arc, which only knows a room
// `{uuid, name}`, its exits `{direction, target_id}`, and the entities in it
// `{uuid, name}` — with NO tile grid or coordinates. This is the "look creates
// a room boundary and places entities" step: draw an enclosed room (# walls,
// . floor), cut each exit as a + door into the matching wall side, and place
// each entity at a deterministic interior cell so the existing MapRenderer +
// PlayerController (src/map/) can render and walk it unchanged.

import type { RoomMap } from "../map/types";

type Side = "top" | "bottom" | "left" | "right";

/** Narrative exit directions → which wall the door sits in. */
const SIDE_BY_DIR: Record<string, Side> = {
  north: "top", up: "top", n: "top", u: "top",
  south: "bottom", down: "bottom", s: "bottom", d: "bottom",
  east: "right", e: "right",
  west: "left", w: "left",
};

/** Stable 32-bit FNV-1a hash — deterministic entity placement (same uuid → same cell). */
function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export interface OpeningRoom {
  uuid: string;
  name: string;
}
export interface OpeningExit {
  direction: string;
  target_id: string;
}
export interface OpeningThing {
  uuid: string;
  name: string;
}

/**
 * Build a RoomMap for the current opening room.
 *
 * @param width  desired interior width in tiles  (clamped to [12, 48])
 * @param height desired interior height in tiles (clamped to [8, 24])
 */
export function buildRoomMap(
  room: OpeningRoom,
  exits: OpeningExit[],
  things: OpeningThing[],
  width = 28,
  height = 16,
): RoomMap {
  const W = Math.max(12, Math.min(Math.round(width), 48));
  const H = Math.max(8, Math.min(Math.round(height), 24));
  const idx = (x: number, y: number): number => y * W + x;

  // 1. Boundary: # walls around a . floor.
  const tiles: string[] = new Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const edge = x === 0 || y === 0 || x === W - 1 || y === H - 1;
      tiles[idx(x, y)] = edge ? "#" : ".";
    }
  }

  // 2. Exits: a + door cut into the matching wall (walkable floor under it).
  //    Directions without a compass mapping ("on") fall back to free sides.
  const FALLBACK: Side[] = ["bottom", "top", "right", "left"];
  const usedSides = new Set<Side>();
  const exitCells: RoomMap["exits"] = [];
  for (const ex of exits) {
    let side: Side | undefined = SIDE_BY_DIR[(ex.direction || "").toLowerCase()];
    if (side === undefined || usedSides.has(side)) {
      side = FALLBACK.find((s) => !usedSides.has(s)) ?? "bottom";
    }
    usedSides.add(side);
    let ex_x: number;
    let ex_y: number;
    if (side === "top") { ex_x = (W / 2) | 0; ex_y = 0; }
    else if (side === "bottom") { ex_x = (W / 2) | 0; ex_y = H - 1; }
    else if (side === "left") { ex_x = 0; ex_y = (H / 2) | 0; }
    else { ex_x = W - 1; ex_y = (H / 2) | 0; }
    tiles[idx(ex_x, ex_y)] = "."; // door is walkable so the player can step onto it
    exitCells.push({ x: ex_x, y: ex_y, ch: "+", direction: ex.direction, target: ex.target_id });
  }

  // 3. Spawn: room centre (always floor).
  const spawn = { x: (W / 2) | 0, y: (H / 2) | 0 };
  tiles[idx(spawn.x, spawn.y)] = ".";

  // 4. Entities: deterministic interior placement, no overlaps.
  const occupied = new Set<number>([idx(spawn.x, spawn.y), ...exitCells.map((e) => idx(e.x, e.y))]);
  const npcs: RoomMap["npcs"] = [];
  const iw = W - 2;
  const ih = H - 2;
  for (const t of things) {
    const base = hashStr(t.uuid);
    for (let attempt = 0; attempt < iw * ih; attempt++) {
      const k = (base + attempt * 2654435761) >>> 0;
      const x = 1 + (k % iw);
      const y = 1 + (Math.floor(k / iw) % ih);
      const cell = idx(x, y);
      if (!occupied.has(cell) && tiles[cell] === ".") {
        occupied.add(cell);
        const glyph = (t.name.trim()[0] || "?").toUpperCase();
        npcs.push({ x, y, ch: glyph, name: t.name, id: t.uuid });
        break;
      }
    }
  }

  return { id: room.uuid, name: room.name, width: W, height: H, tiles, npcs, items: [], exits: exitCells, spawn };
}
