// src/panels/map.ts
import type { GameState } from '../state/game-state';
import type { RoomMap } from '../map/types';
import type { EntityCardData } from '../map/entity-card';
import type { CardContent } from '../map/card-renderer';
import { MapRenderer } from '../map/renderer';
import { PlayerController, setupMapInput, type RoomNpc, type RoomItem, type RoomExit } from '../map/movement';

let renderer: MapRenderer | null = null;
let controller: PlayerController | null = null;
let cleanupInput: (() => void) | null = null;
const mapRef = { current: null as RoomMap | null };

// Viewport callback — receives card content for the ASCII viewport panel
let viewportCallback: ((card: CardContent | null) => void) | null = null;

/** Set the callback that receives card content for the viewport panel. */
export function setViewportCallback(cb: (card: CardContent | null) => void): void {
  viewportCallback = cb;
}

// Entity data cache (fetched from KG)
const entityCache: Map<string, EntityCardData> = new Map();
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function fetchEntityData(id: string, name: string): Promise<EntityCardData> {
  const cached = entityCache.get(id);
  if (cached) return cached;

  // Try KG fetch for real UUIDs
  if (UUID_RE.test(id)) {
    try {
      const resp = await fetch(`/api/entity/${id}`);
      const data = await resp.json();
      if (data && data.name && !data.error) {
        entityCache.set(id, data);
        return data;
      }
    } catch { /* fall through */ }
  }

  // Try search by name
  try {
    const resp = await fetch(`/api/entity/search/${encodeURIComponent(name)}`);
    const data = await resp.json();
    if (data && data.name && !data.error) {
      entityCache.set(id, data);
      return data;
    }
  } catch { /* fall through */ }

  // Local fallback
  const fallback: EntityCardData = { id, name, labels: [], summary: '' };
  entityCache.set(id, fallback);
  return fallback;
}

/** Get the map renderer's canvas element for compositing. */
export function getMapCanvas(): HTMLCanvasElement | null {
  return renderer?.element ?? null;
}

export function initMapPanel(
  mapContainer: HTMLElement,
  _onAction: (action: string) => void,
): void {
  renderer = new MapRenderer(mapContainer);
}

export function updateMap(
  state: GameState,
  onAction: (action: string) => void,
): void {
  if (!state.roomMap || !renderer) return;

  const map = state.roomMap;
  mapRef.current = map;

  if (!controller) {
    controller = new PlayerController(
      map,
      // onInteract — triggers crew call
      (type, entity) => {
        if (type === 'npc') {
          const npc = entity as RoomNpc;
          document.dispatchEvent(new CustomEvent('narrative-entity-click', {
            detail: { entityId: npc.id, entityName: npc.name },
            bubbles: true,
          }));
        } else if (type === 'item') {
          const item = entity as RoomItem;
          document.dispatchEvent(new CustomEvent('narrative-entity-click', {
            detail: { entityId: item.id, entityName: item.name },
            bubbles: true,
          }));
        } else if (type === 'exit') {
          onAction(`go ${(entity as RoomExit).direction}`);
        }
      },
      // onProximity — show entity card on canvas
      (type, entity) => {
        if (!renderer) return;
        if (type && entity) {
          // Derive display name/id — exits lack .id/.name, using direction/target instead
          const entityId = 'id' in entity ? entity.id : ('target' in entity ? entity.target : '');
          const entityName = 'name' in entity ? entity.name : ('target' in entity ? entity.target : '');
          fetchEntityData(entityId || entityName, entityName).then(data => {
            const typeLabels: Record<string, string[]> = {
              npc: ['NPC'], item: ['Item'], exit: ['Exit'],
            };
            const hints: Record<string, string> = {
              npc: '[Enter] Talk', item: '[Enter] Examine', exit: '[Enter] Travel',
            };
            const card: CardContent = {
              type: 'entity',
              name: data.name || entityName,
              labels: data.labels.length ? data.labels : (typeLabels[type!] || []),
              summary: data.summary || '',
              hint: hints[type!] || '[Enter] Interact',
            };
            renderer!.setCard(card);
            viewportCallback?.(card);
            if (mapRef.current && controller) {
              renderer!.render(mapRef.current, controller.x, controller.y);
            }
          });
        } else {
          // Nothing nearby — show player card
          showPlayerCard(state);
        }
      },
    );

    cleanupInput?.();
    cleanupInput = setupMapInput(controller, renderer, mapRef);
  } else {
    controller.loadMap(map);
  }

  // Default: show player card
  showPlayerCard(state);
  renderer.render(map, controller.x, controller.y);
}

function showPlayerCard(state: GameState): void {
  if (!renderer) return;
  const card: CardContent = {
    type: 'player',
    name: state.player.name,
    labels: ['Player'],
    summary: state.location.name,
    health: state.player.health,
    maxHealth: state.player.maxHealth,
    level: state.player.level,
    xp: state.player.xp,
    xpThreshold: state.player.xpThreshold,
  };
  renderer.setCard(card);
  viewportCallback?.(card);
}
