// src/map/types.ts

export interface RoomMap {
  id: string;
  name: string;
  width: number;
  height: number;
  tiles: string[];  // flat array, row-major: tiles[y * width + x]
  npcs: Array<{ x: number; y: number; ch: string; name: string; id: string }>;
  items: Array<{ x: number; y: number; ch: string; name: string; id: string }>;
  exits: Array<{ x: number; y: number; ch: string; direction: string; target: string }>;
  spawn: { x: number; y: number };
}

export interface EntityCard {
  id: string;
  name: string;
  labels: string[];
  summary: string;
}

export interface WorldMapNode {
  id: string;
  name: string;
  x: number;
  y: number;
}

export interface WorldMap {
  rooms: WorldMapNode[];
  connections: Array<{ from: string; to: string; direction: string }>;
  currentRoom: string;
}
