// src/panels/map.ts
import type { GameState } from '../state/game-state';
import type { RoomMap } from '../map/types';
import { MapRenderer } from '../map/renderer';
import { PlayerController, setupMapInput } from '../map/movement';
import { EntityCardManager } from '../map/entity-card';

let renderer: MapRenderer | null = null;
let controller: PlayerController | null = null;
let cardManager: EntityCardManager | null = null;
let cleanupInput: (() => void) | null = null;
const mapRef = { current: null as RoomMap | null };

export function initMapPanel(
  mapContainer: HTMLElement,
  _onAction: (action: string) => void,
): void {
  renderer = new MapRenderer(mapContainer);
  cardManager = new EntityCardManager(document.body);
}

export function updateMap(
  state: GameState,
  onAction: (action: string) => void,
): void {
  if (!state.roomMap || !renderer) return;

  const map = state.roomMap;
  mapRef.current = map;

  // Create or update controller
  if (!controller) {
    controller = new PlayerController(
      map,
      // onInteract — triggers crew call
      (type, entity) => {
        if (type === 'npc') onAction(`talk to ${entity.name}`);
        else if (type === 'item') onAction(`examine ${entity.name}`);
        else if (type === 'exit') onAction(`go ${entity.direction}`);
      },
      // onProximity — shows entity card (free KG lookup)
      (type, entity) => {
        if (!cardManager || !renderer) return;
        if (type && entity) {
          const screen = renderer.gridToScreen(entity.x, entity.y);
          cardManager.show(
            entity.id || entity.name,
            entity.name,
            type,
            screen.x,
            screen.y,
          );
        } else {
          cardManager.hide();
        }
      },
    );

    cleanupInput?.();
    cleanupInput = setupMapInput(controller, renderer, mapRef);
  } else {
    controller.loadMap(map);
  }

  renderer.render(map, controller.x, controller.y);
}

// Keep the existing text-based render for the side panel location info
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
