// src/layers/room-viewport.ts
//
// Adapts the opening arc's room data onto the EXISTING roguelike room system
// (src/map/renderer.ts MapRenderer + src/map/movement.ts PlayerController).
// It owns a detached MapRenderer canvas (blitted into a UnifiedCanvas region
// via uc.setOffscreen) and a stable PlayerController so setupMapInput can bind
// WASD once. Room data comes in via visitRoom/setContents; buildRoomMap turns
// it into the tile/entity RoomMap those systems already consume.

import type { RoomMap } from "../map/types";
import { MapRenderer } from "../map/renderer";
import { PlayerController, setupMapInput } from "../map/movement";
import { buildRoomMap } from "../state/room-map-builder";

export interface Thing {
  uuid: string;
  name: string;
}

/** Minimal surface the opening orchestrator drives — matched by MapLayer too. */
export interface RoomView {
  visitRoom(room: { uuid: string; name: string }, exits: { direction: string; target_id: string }[]): void;
  setContents(roomUuid: string, things: Thing[]): void;
  currentExits(): { direction: string; targetId: string }[];
  currentThings(): Thing[];
}

const ROOM_W = 28;
const ROOM_H = 16;

export class RoomViewportAdapter implements RoomView {
  private renderer: MapRenderer;
  private controller: PlayerController;
  private mapRef: { current: RoomMap | null };
  private room: { uuid: string; name: string } = { uuid: "", name: "" };
  private exits: { direction: string; target_id: string }[] = [];
  private things: Thing[] = [];
  private onChange: () => void;

  /** @param onChange called whenever the room canvas changes (re-blit the region). */
  constructor(onChange: () => void) {
    this.onChange = onChange;
    // Detached container — the canvas is used as a drawImage source, not in the DOM.
    const holder = document.createElement("div");
    this.renderer = new MapRenderer(holder);
    // Eager empty map + controller so setupMapInput binds a stable instance;
    // loadMap() mutates this same controller on every room change.
    const empty = buildRoomMap(this.room, [], [], ROOM_W, ROOM_H);
    this.mapRef = { current: empty };
    this.controller = new PlayerController(empty, () => {}, () => {});
  }

  /** The room canvas — pass to uc.setOffscreen(region, canvas). */
  get canvas(): HTMLCanvasElement {
    return this.renderer.element;
  }

  /** Wire WASD/hjkl/arrows onto the player; returns a teardown fn. */
  attachInput(): () => void {
    return setupMapInput(this.controller, this.renderer, this.mapRef, this.onChange);
  }

  visitRoom(room: { uuid: string; name: string }, exits: { direction: string; target_id: string }[]): void {
    this.room = room;
    this.exits = exits;
    this.things = [];
    this.rebuild();
  }

  setContents(roomUuid: string, things: Thing[]): void {
    if (roomUuid !== this.room.uuid) return;
    this.things = things;
    this.rebuild();
  }

  currentExits(): { direction: string; targetId: string }[] {
    return this.exits.map((e) => ({ direction: e.direction, targetId: e.target_id }));
  }

  currentThings(): Thing[] {
    return this.things;
  }

  private rebuild(): void {
    const map = buildRoomMap(this.room, this.exits, this.things, ROOM_W, ROOM_H);
    this.mapRef.current = map;
    this.controller.loadMap(map); // respawns at room centre
    this.render();
  }

  /** Re-draw the room canvas at the current player position and signal a re-blit. */
  render(): void {
    if (!this.mapRef.current) return;
    this.renderer.render(this.mapRef.current, this.controller.x, this.controller.y);
    this.onChange();
  }
}
