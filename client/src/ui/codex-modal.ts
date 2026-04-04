// client/src/ui/codex-modal.ts
/**
 * Codex modal — two-panel entity browser.
 * Left sidebar lists NPCs, items, location; right panel shows detail + connections + onchain data.
 */

import type { GameState } from '../state/game-state';

export interface CodexModal {
  el: HTMLElement;
  open(entityId?: string): void;
  close(): void;
  readonly active: boolean;
}

// --- Types for codex API response ---

interface CodexRelationship {
  source: string;
  target: string;
  relationship: string;
  fact?: string;
}

interface CodexChainData {
  level?: number;
  alive?: boolean;
  wallet?: string;
  rarity?: string;
  ownerId?: string;
  locationId?: string;
  [key: string]: unknown;
}

interface CodexEntity {
  id: string;
  name: string;
  type: string;       // 'npc' | 'item' | 'location' | 'player'
  labels: string[];
  summary: string;
  relationships: CodexRelationship[];
  chain_data?: CodexChainData | null;
  rarity?: string;
}

interface CodexResponse {
  npcs: CodexEntity[];
  items: CodexEntity[];
  location: CodexEntity | null;
}

// --- Color map ---

const TYPE_COLORS: Record<string, string> = {
  npc: '#d4a574',
  item: '#808080',
  location: '#7aa2d4',
  player: '#8b5cf6',
};

const RARITY_COLORS: Record<string, string> = {
  common: '#808080',
  uncommon: '#1eff00',
  rare: '#0070dd',
  epic: '#a335ee',
  legendary: '#ff8000',
};

function itemColor(entity: CodexEntity): string {
  if (entity.rarity && RARITY_COLORS[entity.rarity]) return RARITY_COLORS[entity.rarity];
  return TYPE_COLORS.item;
}

function entityColor(entity: CodexEntity): string {
  if (entity.type === 'item') return itemColor(entity);
  return TYPE_COLORS[entity.type] || '#c8c8d0';
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatAddr(addr: string): string {
  if (!addr || addr.length < 10 || addr === '0x0000000000000000000000000000000000000000') return 'None';
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

// --- Factory ---

export function createCodexModal(getState: () => GameState, playerId: () => string): CodexModal {
  const backdrop = document.createElement('div');
  backdrop.className = 'dialog-backdrop';
  backdrop.style.display = 'none';

  const win = document.createElement('div');
  win.className = 'dialog-win';
  win.style.maxWidth = '700px';
  win.style.width = '90vw';

  backdrop.appendChild(win);

  // Close on backdrop click
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && backdrop.style.display !== 'none') close();
  });

  let _codexData: CodexResponse | null = null;
  let _selectedId: string | null = null;
  let _allEntities: CodexEntity[] = [];

  function close() {
    backdrop.style.display = 'none';
  }

  async function open(entityId?: string) {
    backdrop.style.display = '';
    win.innerHTML = '';

    // Show loading state
    const loading = document.createElement('div');
    loading.style.color = '#6a6a78';
    loading.style.fontStyle = 'italic';
    loading.style.padding = '16px';
    loading.textContent = 'Loading...';
    win.appendChild(loading);

    // Fetch codex data
    try {
      const pid = playerId();
      const state = getState();
      const locId = state?.roomMap?.id || '';
      const url = locId ? `/api/codex/${pid}?location_uuid=${locId}` : `/api/codex/${pid}`;
      const resp = await fetch(url);
      _codexData = await resp.json();
    } catch {
      _codexData = null;
    }

    // Build flat entity list
    _allEntities = [];
    if (_codexData) {
      _allEntities.push(...(_codexData.npcs || []));
      _allEntities.push(...(_codexData.ground_items || []));
      _allEntities.push(...(_codexData.inventory || []));
      _allEntities.push(...(_codexData.locations || []));
    }

    // Also include inventory + ground items from game state as fallback entities
    const state = getState();
    if (state) {
      for (const inv of state.inventory) {
        if (!_allEntities.find(e => e.id === inv.id)) {
          _allEntities.push({
            id: inv.id,
            name: inv.name,
            type: 'item',
            labels: [inv.rarity, inv.slot_type].filter(Boolean),
            summary: inv.effects.join(', ') || '',
            relationships: [],
            rarity: inv.rarity,
          });
        }
      }
      for (const gi of state.location.items) {
        if (!_allEntities.find(e => e.id === gi.id)) {
          _allEntities.push({
            id: gi.id,
            name: gi.name,
            type: 'item',
            labels: [],
            summary: '',
            relationships: [],
          });
        }
      }
    }

    // Select entity
    if (entityId) {
      _selectedId = entityId;
    } else if (_codexData?.npcs?.length) {
      _selectedId = _codexData.npcs[0].id;
    } else if (_allEntities.length) {
      _selectedId = _allEntities[0].id;
    } else {
      _selectedId = null;
    }

    render();
  }

  function render() {
    win.innerHTML = '';

    // -- Header --
    const header = document.createElement('div');
    header.className = 'win-title dialog-title';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';

    const title = document.createElement('span');
    title.style.color = '#8b5cf6';
    title.textContent = 'CODEX';

    const closeBtn = document.createElement('span');
    closeBtn.textContent = '[\u00D7]';
    closeBtn.style.color = '#e05050';
    closeBtn.style.cursor = 'pointer';
    closeBtn.onclick = close;

    header.appendChild(title);
    header.appendChild(closeBtn);
    win.appendChild(header);

    // -- Two-panel body --
    const body = document.createElement('div');
    body.style.display = 'flex';
    body.style.gap = '0';
    body.style.fontFamily = "'Fira Code', monospace";
    body.style.fontSize = '12px';
    body.style.lineHeight = '1.6';
    body.style.minHeight = '300px';
    body.style.maxHeight = '60vh';

    // Left sidebar
    const sidebar = document.createElement('div');
    sidebar.style.width = '140px';
    sidebar.style.flexShrink = '0';
    sidebar.style.borderRight = '1px solid #1a1a24';
    sidebar.style.overflowY = 'auto';
    sidebar.style.padding = '8px 0';

    const state = getState();
    const npcs = _codexData?.npcs || [];
    const items = _allEntities.filter(e => e.type === 'item');
    const locations = _codexData?.locations || [];

    // NPCs section
    if (npcs.length) {
      const npcHeader = document.createElement('div');
      npcHeader.style.color = '#6a6a78';
      npcHeader.style.fontSize = '10px';
      npcHeader.style.letterSpacing = '1px';
      npcHeader.style.padding = '2px 8px';
      npcHeader.textContent = `NPCs (${npcs.length})`;
      sidebar.appendChild(npcHeader);

      for (const npc of npcs) {
        sidebar.appendChild(createSidebarItem(npc, TYPE_COLORS.npc));
      }
    }

    // Items section
    if (items.length) {
      const itemHeader = document.createElement('div');
      itemHeader.style.color = '#6a6a78';
      itemHeader.style.fontSize = '10px';
      itemHeader.style.letterSpacing = '1px';
      itemHeader.style.padding = '6px 8px 2px';
      itemHeader.textContent = `ITEMS (${items.length})`;
      sidebar.appendChild(itemHeader);

      for (const item of items) {
        sidebar.appendChild(createSidebarItem(item, itemColor(item)));
      }
    }

    // Locations section
    if (locations.length) {
      const locHeader = document.createElement('div');
      locHeader.style.color = '#6a6a78';
      locHeader.style.fontSize = '10px';
      locHeader.style.letterSpacing = '1px';
      locHeader.style.padding = '6px 8px 2px';
      locHeader.textContent = `LOCATIONS (${locations.length})`;
      sidebar.appendChild(locHeader);

      for (const loc of locations) {
        const label = loc.current ? `${loc.name} \u25C9` : loc.direction ? `${loc.direction} \u2192 ${loc.name}` : loc.name;
        const el = createSidebarItem({ ...loc, name: label }, TYPE_COLORS.location);
        sidebar.appendChild(el);
      }
    }

    // Right detail panel
    const detail = document.createElement('div');
    detail.style.flex = '1';
    detail.style.minWidth = '0';
    detail.style.overflowY = 'auto';
    detail.style.padding = '8px 12px';

    const selected = _allEntities.find(e => e.id === _selectedId);
    if (selected) {
      renderDetail(detail, selected);
    } else {
      detail.style.color = '#6a6a78';
      detail.style.fontStyle = 'italic';
      detail.style.paddingTop = '16px';
      detail.textContent = 'No entities to display';
    }

    body.appendChild(sidebar);
    body.appendChild(detail);
    win.appendChild(body);
  }

  function createSidebarItem(entity: CodexEntity, color: string): HTMLElement {
    const item = document.createElement('div');
    item.style.padding = '2px 8px';
    item.style.cursor = 'pointer';
    item.style.color = color;
    item.style.fontSize = '11px';
    item.style.whiteSpace = 'nowrap';
    item.style.overflow = 'hidden';
    item.style.textOverflow = 'ellipsis';

    if (entity.id === _selectedId) {
      item.style.background = '#1a1a24';
    }

    item.textContent = entity.name;

    item.addEventListener('click', () => {
      _selectedId = entity.id;
      render();
    });

    return item;
  }

  function renderDetail(container: HTMLElement, entity: CodexEntity) {
    // Entity name
    const name = document.createElement('div');
    name.style.color = entityColor(entity);
    name.style.fontWeight = 'bold';
    name.style.fontSize = '15px';
    name.style.marginBottom = '4px';
    name.textContent = entity.name;
    container.appendChild(name);

    // Labels
    if (entity.labels.length) {
      const labels = document.createElement('div');
      labels.style.color = '#6a6a78';
      labels.style.fontSize = '10px';
      labels.style.marginBottom = '8px';
      labels.textContent = entity.labels.join(' \u00B7 ');
      container.appendChild(labels);
    }

    // Summary
    if (entity.summary) {
      const summary = document.createElement('div');
      summary.style.color = '#c8c8d0';
      summary.style.lineHeight = '1.5';
      summary.style.marginBottom = '12px';
      summary.textContent = entity.summary;
      container.appendChild(summary);
    }

    // Connections
    if (entity.relationships && entity.relationships.length > 0) {
      const connHeader = document.createElement('div');
      connHeader.style.color = '#6a6a78';
      connHeader.style.fontSize = '10px';
      connHeader.style.letterSpacing = '1px';
      connHeader.style.marginBottom = '4px';
      connHeader.textContent = 'CONNECTIONS';
      container.appendChild(connHeader);

      for (const rel of entity.relationships) {
        const row = document.createElement('div');
        row.style.marginBottom = '4px';

        const relType = document.createElement('span');
        relType.style.color = '#6a6a78';
        relType.style.fontSize = '10px';
        relType.textContent = rel.relationship.replace(/_/g, ' ') + ' ';

        const target = document.createElement('span');
        const other = rel.source === entity.name ? rel.target : rel.source;
        target.style.color = '#7aa2d4';
        target.style.cursor = 'pointer';
        target.style.textDecoration = 'underline dotted';
        target.textContent = other;

        // Click to navigate to connected entity
        target.addEventListener('click', () => {
          const linked = _allEntities.find(e => e.name === other);
          if (linked) {
            _selectedId = linked.id;
            render();
          }
        });

        row.appendChild(relType);
        row.appendChild(target);

        if (rel.fact) {
          const fact = document.createElement('div');
          fact.style.color = '#6a6a78';
          fact.style.fontSize = '11px';
          fact.style.fontStyle = 'italic';
          fact.style.marginLeft = '8px';
          fact.textContent = rel.fact.length > 100 ? rel.fact.slice(0, 100) + '\u2026' : rel.fact;
          row.appendChild(fact);
        }

        container.appendChild(row);
      }

      // Spacer before onchain
      const spacer = document.createElement('div');
      spacer.style.marginTop = '12px';
      container.appendChild(spacer);
    }

    // Onchain section
    if (entity.chain_data) {
      renderChainSection(container, entity);
    }
  }

  function renderChainSection(container: HTMLElement, entity: CodexEntity) {
    const chain = entity.chain_data!;

    const card = document.createElement('div');
    card.style.border = '1px solid #1a3a1a';
    card.style.borderRadius = '3px';
    card.style.padding = '8px';
    card.style.marginTop = '4px';

    const cardHeader = document.createElement('div');
    cardHeader.style.color = '#50c878';
    cardHeader.style.fontSize = '10px';
    cardHeader.style.letterSpacing = '1px';
    cardHeader.style.marginBottom = '4px';
    cardHeader.textContent = 'ONCHAIN';
    card.appendChild(cardHeader);

    if (entity.type === 'npc' || entity.type === 'player') {
      // Character chain data
      if (chain.level != null) addChainRow(card, 'Level', String(chain.level));
      if (chain.alive != null) addChainRow(card, 'Status', chain.alive ? 'Alive' : 'Dead');
      if (chain.wallet) addChainRow(card, 'Wallet', formatAddr(chain.wallet));
    } else if (entity.type === 'item') {
      // Item chain data
      if (chain.rarity) addChainRow(card, 'Rarity', String(chain.rarity));
      if (chain.ownerId) addChainRow(card, 'Owner', formatAddr(chain.ownerId));
      if (chain.locationId) addChainRow(card, 'Location', formatAddr(chain.locationId));
    }

    container.appendChild(card);
  }

  function addChainRow(container: HTMLElement, label: string, value: string) {
    const row = document.createElement('div');
    row.style.padding = '1px 0';
    row.style.fontSize = '12px';

    const lbl = document.createElement('span');
    lbl.style.color = '#6a6a78';
    lbl.style.display = 'inline-block';
    lbl.style.width = '70px';
    lbl.style.fontSize = '10px';
    lbl.style.letterSpacing = '0.5px';
    lbl.style.textTransform = 'uppercase';
    lbl.textContent = label;

    const val = document.createElement('span');
    val.style.color = '#c8c8d0';
    val.textContent = value;

    row.appendChild(lbl);
    row.appendChild(val);
    container.appendChild(row);
  }

  return {
    el: backdrop,
    open,
    close,
    get active() {
      return backdrop.style.display !== 'none';
    },
  };
}
