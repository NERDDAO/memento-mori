// src/panels/map.ts
import type { GameState } from '../state/game-state';
import type { RoomMap } from '../map/types';
import type { EntityCardData } from '../map/entity-card';
import type { CardContent } from '../map/card-renderer';
import { MapRenderer } from '../map/renderer';
import { PlayerController, setupMapInput } from '../map/movement';

let renderer: MapRenderer | null = null;
let controller: PlayerController | null = null;
let cleanupInput: (() => void) | null = null;
const mapRef = { current: null as RoomMap | null };

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
        if (type === 'npc') onAction(`talk to ${entity.name}`);
        else if (type === 'item') onAction(`examine ${entity.name}`);
        else if (type === 'exit') onAction(`go ${entity.direction}`);
      },
      // onProximity — show entity card on canvas
      (type, entity) => {
        if (!renderer) return;
        if (type && entity) {
          // Fetch from KG (async) then update card
          const entityId = entity.id || entity.name;
          fetchEntityData(entityId, entity.name).then(data => {
            const typeLabels: Record<string, string[]> = {
              npc: ['NPC'], item: ['Item'], exit: ['Exit'],
            };
            const hints: Record<string, string> = {
              npc: '[Enter] Talk', item: '[Enter] Examine', exit: '[Enter] Travel',
            };
            const card: CardContent = {
              type: 'entity',
              name: data.name || entity.name,
              labels: data.labels.length ? data.labels : (typeLabels[type!] || []),
              summary: data.summary || '',
              hint: hints[type!] || '[Enter] Interact',
            };
            renderer!.setCard(card);
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
}

// Keep the text-based location panel for the side (simplified)
export function renderLocationPanel(
  container: HTMLElement,
  state: GameState,
  onAction: (action: string) => void,
): void {
  let html = `<div style="color: var(--text-location); margin-bottom: 8px; font-size: 15px;">${state.location.name}</div>`;

  if (state.location.exits.length) {
    html += '<div style="margin-bottom: 8px;">';
    state.location.exits.forEach(exit => {
      html += `<button class="action-btn" data-action="go ${exit}">Go ${exit}</button>`;
    });
    html += '</div>';
  }

  if (state.location.npcs.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Present:</span></div>';
    state.location.npcs.forEach(npc => {
      html += `<div style="font-size: 13px; color: var(--text-npc); padding: 2px 0;">${npc}</div>`;
    });
  }

  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      if (action) onAction(action);
    });
  });
}
