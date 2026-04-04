// src/map/entity-card.ts

import { prepare, layout } from '@chenglou/pretext';

export interface EntityCardData {
  id: string;
  name: string;
  labels: string[];
  summary: string;
}

const CARD_MAX_WIDTH = 260;
const CARD_FONT = '13px system-ui, sans-serif';
const CARD_NAME_FONT = "15px Georgia, 'Times New Roman', serif";
const CARD_LINE_HEIGHT = 18;
const CARD_NAME_LINE_HEIGHT = 22;

// UUID pattern — real KG entities have UUIDs, test entities have prefixed IDs
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export class EntityCardManager {
  private container: HTMLElement;
  private cardEl: HTMLDivElement;
  private cache: Map<string, EntityCardData> = new Map();
  private currentId: string = '';

  constructor(container: HTMLElement) {
    this.container = container;
    this.cardEl = document.createElement('div');
    this.cardEl.className = 'entity-card';
    this.cardEl.style.display = 'none';
    this.container.appendChild(this.cardEl);
  }

  async show(
    entityId: string,
    entityName: string,
    entityType: 'npc' | 'item' | 'exit',
    screenX: number,
    screenY: number,
  ): Promise<void> {
    if (this.currentId === entityId && this.cardEl.style.display !== 'none') return;
    this.currentId = entityId;

    let card = this.cache.get(entityId);
    if (!card) {
      // Only fetch from KG if it's a real UUID (not a test/placeholder ID)
      if (UUID_RE.test(entityId)) {
        try {
          const resp = await fetch(`/api/entity/${entityId}`);
          const data = await resp.json();
          if (data && data.name && !data.error) {
            card = data as EntityCardData;
            this.cache.set(entityId, card);
          }
        } catch {
          // KG unavailable — fall through to local
        }
      }

      // If KG fetch didn't work or ID isn't a UUID, try search by name
      if (!card && entityName) {
        try {
          const resp = await fetch(`/api/entity/search/${encodeURIComponent(entityName)}`);
          const data = await resp.json();
          if (data && data.name && !data.error) {
            card = data as EntityCardData;
            this.cache.set(entityId, card);
          }
        } catch {
          // Search failed — fall through to local
        }
      }

      // Fallback: build card from local RoomMap data
      if (!card) {
        const typeLabels: Record<string, string[]> = {
          npc: ['NPC'],
          item: ['Item'],
          exit: ['Exit'],
        };
        card = {
          id: entityId,
          name: entityName,
          labels: typeLabels[entityType] || [],
          summary: '',
        };
        this.cache.set(entityId, card);
      }
    }

    // Measure with Pretext
    const namePrepared = prepare(card.name, CARD_NAME_FONT);
    const nameResult = layout(namePrepared, CARD_MAX_WIDTH, CARD_NAME_LINE_HEIGHT);

    let descHeight = 0;
    if (card.summary) {
      const descPrepared = prepare(card.summary, CARD_FONT);
      const descResult = layout(descPrepared, CARD_MAX_WIDTH, CARD_LINE_HEIGHT);
      descHeight = descResult.height;
    }

    const totalHeight = 12 + nameResult.height + 20 + (descHeight ? descHeight + 8 : 0) + 24 + 12;

    // Position card above the entity
    this.cardEl.style.left = `${screenX - 130}px`;
    this.cardEl.style.top = `${screenY - totalHeight - 8}px`;
    this.cardEl.style.width = `${CARD_MAX_WIDTH + 24}px`;

    const labelsHtml = `<div class="card-labels">${card.labels.join(' · ')}</div>`;
    const descHtml = card.summary
      ? `<div class="card-desc">${card.summary}</div>`
      : '';

    const hintText = entityType === 'exit'
      ? 'Enter to travel'
      : entityType === 'npc'
        ? 'Enter to talk'
        : 'Enter to examine';

    this.cardEl.innerHTML = `
      <div class="card-name">${card.name}</div>
      ${labelsHtml}
      ${descHtml}
      <div class="card-hint">${hintText}</div>
    `;
    this.cardEl.style.display = 'block';
  }

  hide(): void {
    this.cardEl.style.display = 'none';
    this.currentId = '';
  }

  clearCache(): void {
    this.cache.clear();
  }
}
