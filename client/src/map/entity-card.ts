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

  async show(entityId: string, entityName: string, screenX: number, screenY: number): Promise<void> {
    if (this.currentId === entityId && this.cardEl.style.display !== 'none') return;
    this.currentId = entityId;

    let card = this.cache.get(entityId);
    if (!card) {
      // Fetch from KG via REST (no LLM)
      try {
        const endpoint = entityId.includes('-')
          ? `/api/entity/${entityId}`
          : `/api/entity/search/${encodeURIComponent(entityName)}`;
        const resp = await fetch(endpoint);
        card = await resp.json();
        if (card && card.name) {
          this.cache.set(entityId, card);
        }
      } catch {
        card = { id: entityId, name: entityName, labels: [], summary: 'Unknown entity.' };
      }
    }

    if (!card) return;

    // Measure with Pretext
    const namePrepared = prepare(card.name, CARD_NAME_FONT);
    const nameResult = layout(namePrepared, CARD_MAX_WIDTH, CARD_NAME_LINE_HEIGHT);

    let descHeight = 0;
    if (card.summary) {
      const descPrepared = prepare(card.summary, CARD_FONT);
      const descResult = layout(descPrepared, CARD_MAX_WIDTH, CARD_LINE_HEIGHT);
      descHeight = descResult.height;
    }

    const totalHeight = 12 + nameResult.height + (card.labels.length ? 20 : 0) + (descHeight ? descHeight + 8 : 0) + 24 + 12;

    // Position card above the entity
    this.cardEl.style.left = `${screenX - 130}px`;
    this.cardEl.style.top = `${screenY - totalHeight - 8}px`;
    this.cardEl.style.width = `${CARD_MAX_WIDTH + 24}px`;

    const labelsHtml = card.labels.length
      ? `<div class="card-labels">${card.labels.join(' · ')}</div>`
      : '';
    const descHtml = card.summary
      ? `<div class="card-desc">${card.summary}</div>`
      : '';

    this.cardEl.innerHTML = `
      <div class="card-name">${card.name}</div>
      ${labelsHtml}
      ${descHtml}
      <div class="card-hint">Enter to interact</div>
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
