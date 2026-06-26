import { test, expect } from "bun:test";
import { buildRoomMap } from "./room-map-builder";

const room = { uuid: "r1", name: "the deep roads" };

test("builds an enclosed room: # walls border, . floor interior", () => {
  const m = buildRoomMap(room, [], [], 20, 12);
  expect(m.width).toBe(20);
  expect(m.height).toBe(12);
  // every border cell is a wall
  for (let x = 0; x < m.width; x++) {
    expect(m.tiles[x]).toBe("#"); // top row
    expect(m.tiles[(m.height - 1) * m.width + x]).toBe("#"); // bottom row
  }
  // centre is floor + spawn
  expect(m.tiles[m.spawn.y * m.width + m.spawn.x]).toBe(".");
  expect(m.spawn.x).toBeGreaterThan(0);
  expect(m.spawn.x).toBeLessThan(m.width - 1);
});

test("each exit becomes a walkable + door on a wall edge", () => {
  const m = buildRoomMap(room, [{ direction: "on", target_id: "r2" }], [], 20, 12);
  expect(m.exits.length).toBe(1);
  const e = m.exits[0];
  expect(e.ch).toBe("+");
  expect(e.direction).toBe("on");
  expect(e.target).toBe("r2");
  // door sits on an edge…
  const onEdge = e.x === 0 || e.y === 0 || e.x === m.width - 1 || e.y === m.height - 1;
  expect(onEdge).toBe(true);
  // …and the tile under it is floor (walkable), not wall
  expect(m.tiles[e.y * m.width + e.x]).toBe(".");
});

test("entities are placed at distinct interior floor cells with a glyph", () => {
  const things = [
    { uuid: "e1", name: "a dying adventurer" },
    { uuid: "e2", name: "an iron blade" },
  ];
  const m = buildRoomMap(room, [{ direction: "on", target_id: "r2" }], things, 24, 14);
  expect(m.npcs.length).toBe(2);
  const seen = new Set<string>();
  for (const n of m.npcs) {
    // interior, not on a wall
    expect(n.x).toBeGreaterThan(0);
    expect(n.y).toBeGreaterThan(0);
    expect(n.x).toBeLessThan(m.width - 1);
    expect(n.y).toBeLessThan(m.height - 1);
    expect(m.tiles[n.y * m.width + n.x]).toBe(".");
    expect(n.ch.length).toBe(1);
    seen.add(`${n.x},${n.y}`);
  }
  expect(seen.size).toBe(2); // no overlap
  // first glyph derives from the name
  expect(m.npcs.find((n) => n.id === "e1")!.ch).toBe("A");
});

test("placement is deterministic for the same uuid", () => {
  const things = [{ uuid: "e1", name: "a dying adventurer" }];
  const a = buildRoomMap(room, [], things, 24, 14).npcs[0];
  const b = buildRoomMap(room, [], things, 24, 14).npcs[0];
  expect({ x: a.x, y: a.y }).toEqual({ x: b.x, y: b.y });
});
