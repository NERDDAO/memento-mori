// src/map/movement.ts
import type { RoomMap } from './types';

export type RoomNpc = RoomMap['npcs'][number];
export type RoomItem = RoomMap['items'][number];
export type RoomExit = RoomMap['exits'][number];

/** Union of all placeable entities on the room map. */
export type MapEntity = RoomNpc | RoomItem | RoomExit;

/**
 * Interaction/proximity callbacks receive a correlated (type, entity) pair.
 * TypeScript cannot express the correlation between the two parameters in a
 * single callback signature, so `entity` is typed as the full union and
 * callers narrow with `type` guards + type assertions.
 */
export type InteractionCallback = (type: 'npc' | 'item' | 'exit', entity: MapEntity) => void;
export type ProximityCallback = (type: 'npc' | 'item' | 'exit' | null, entity: MapEntity | null) => void;

export class PlayerController {
  x: number;
  y: number;
  private map: RoomMap;
  private onInteract: InteractionCallback;
  private onProximity: ProximityCallback;
  private lastProximity: string = '';

  constructor(map: RoomMap, onInteract: InteractionCallback, onProximity: ProximityCallback) {
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.map = map;
    this.onInteract = onInteract;
    this.onProximity = onProximity;
  }

  move(dx: number, dy: number): boolean {
    const nx = this.x + dx;
    const ny = this.y + dy;
    if (!this.isWalkable(nx, ny)) return false;

    this.x = nx;
    this.y = ny;
    this.checkProximity();
    return true;
  }

  interact(): void {
    // Check adjacent + current tile for entities
    const dirs = [[0,0],[0,-1],[0,1],[-1,0],[1,0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;

      const exit = this.map.exits.find(e => e.x === tx && e.y === ty);
      if (exit) { this.onInteract('exit', exit); this.syncPosition(); return; }

      const npc = this.map.npcs.find(n => n.x === tx && n.y === ty);
      if (npc) { this.onInteract('npc', npc); this.syncPosition(); return; }

      const item = this.map.items.find(i => i.x === tx && i.y === ty);
      if (item) { this.onInteract('item', item); this.syncPosition(); return; }
    }
  }

  private checkProximity(): void {
    const dirs = [[0,-1],[0,1],[-1,0],[1,0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;

      const npc = this.map.npcs.find(n => n.x === tx && n.y === ty);
      if (npc && this.lastProximity !== npc.id) {
        this.lastProximity = npc.id;
        this.onProximity('npc', npc);
        return;
      }

      const item = this.map.items.find(i => i.x === tx && i.y === ty);
      if (item && this.lastProximity !== item.id) {
        this.lastProximity = item.id;
        this.onProximity('item', item);
        return;
      }

      const exit = this.map.exits.find(e => e.x === tx && e.y === ty);
      if (exit) {
        const exitId = `exit-${exit.direction}`;
        if (this.lastProximity !== exitId) {
          this.lastProximity = exitId;
          this.onProximity('exit', exit);
          return;
        }
      }
    }

    // Nothing nearby
    if (this.lastProximity !== '') {
      this.lastProximity = '';
      this.onProximity(null, null);
    }
  }

  private isWalkable(x: number, y: number): boolean {
    if (x < 0 || x >= this.map.width || y < 0 || y >= this.map.height) return false;
    const ch = this.map.tiles[y * this.map.width + x];
    return ch !== '#' && ch !== undefined && ch !== ' ';
  }

  /** Send current position to server for chain sync. Fire-and-forget. */
  syncPosition(): void {
    const pid = (window as any).__mmPlayerId;
    if (!pid) return;

    // Fire-and-forget — don't block interaction
    fetch('/api/position/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: pid, x: this.x, y: this.y }),
    }).catch(() => {});  // Best effort
  }

  loadMap(map: RoomMap): void {
    this.map = map;
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.lastProximity = '';
  }
}

// Key bindings
const MOVE_KEYS: Record<string, [number, number]> = {
  ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
  w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0],
  k: [0, -1], j: [0, 1], h: [-1, 0], l: [1, 0],
};

export function setupMapInput(
  controller: PlayerController,
  renderer: { render: (map: RoomMap, x: number, y: number) => void },
  map: { current: RoomMap | null },
): () => void {
  const handler = (e: KeyboardEvent) => {
    // Don't capture if typing in the action input
    if ((e.target as HTMLElement)?.tagName === 'INPUT') return;

    const delta = MOVE_KEYS[e.key];
    if (delta) {
      e.preventDefault();
      if (controller.move(delta[0], delta[1]) && map.current) {
        renderer.render(map.current, controller.x, controller.y);
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      // Don't capture Enter in input
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      e.preventDefault();
      controller.interact();
    }
  };

  document.addEventListener('keydown', handler);
  return () => document.removeEventListener('keydown', handler);
}
