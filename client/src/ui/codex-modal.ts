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
  relationships?: CodexRelationship[];
  chain_data?: CodexChainData | null;
  rarity?: string;
  equipped?: boolean;
  slot_type?: string;
  effects?: string[];
  exits?: Array<{ direction: string; target: string }>;
  current?: boolean;
  direction?: string;
  attributes?: Record<string, any>;
}

interface CodexResponse {
  npcs: CodexEntity[];
  ground_items: CodexEntity[];
  inventory: CodexEntity[];
  locations: CodexEntity[];
  player: { id: string; name: string; level: number; health: number; archetype: string; chain: Record<string, unknown> | null };
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
  let _detailPage = 0;

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

    // Build flat entity list — room entities only (no player inventory)
    _allEntities = [];
    const seen = new Set<string>();
    if (_codexData) {
      for (const npc of (_codexData.npcs || [])) {
        if (!seen.has(npc.id)) { seen.add(npc.id); _allEntities.push({ ...npc, type: 'npc' }); }
      }
      for (const gi of (_codexData.ground_items || [])) {
        if (!seen.has(gi.id)) { seen.add(gi.id); _allEntities.push({ ...gi, type: 'item' }); }
      }
      for (const loc of (_codexData.locations || [])) {
        if (!seen.has(loc.id)) { seen.add(loc.id); _allEntities.push({ ...loc, type: 'location', labels: loc.labels || ['Location'] }); }
      }
      // Player entity (without inventory items)
      if (_codexData.player) {
        const p = _codexData.player;
        if (!seen.has(p.id)) {
          seen.add(p.id);
          _allEntities.push({ id: p.id, name: p.name, type: 'player', labels: [p.archetype || 'Player'], summary: '' });
        }
      }
    }

    // Select entity — default to current location
    if (entityId) {
      _selectedId = entityId;
    } else {
      const currentLoc = (_codexData?.locations || []).find((l: any) => l.current);
      _selectedId = currentLoc?.id || (_allEntities.length ? _allEntities[0].id : null);
    }
    if (_selectedId && !_allEntities.find(e => e.id === _selectedId)) {
      _selectedId = _allEntities.length ? _allEntities[0].id : null;
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

    const npcs = _codexData?.npcs || [];
    const groundItems = _codexData?.ground_items || [];
    const invItems = _codexData?.inventory || [];
    const locations = _codexData?.locations || [];
    const currentLoc = locations.find((l: any) => l.current);
    const exitLocs = locations.filter((l: any) => !l.current);

    // Current location section (expanded — shows its NPCs + ground items)
    if (currentLoc) {
      const locHeader = createSectionHeader(`\u25C9 ${currentLoc.name}`, TYPE_COLORS.location, true);
      locHeader.addEventListener('click', () => { _selectedId = currentLoc.id; render(); });
      sidebar.appendChild(locHeader);

      // NPCs in this room
      for (const npc of npcs) {
        sidebar.appendChild(createSidebarItem(npc, TYPE_COLORS.npc, '  '));
      }
      // Ground items in this room
      for (const gi of groundItems) {
        sidebar.appendChild(createSidebarItem(gi, itemColor(gi), '  '));
      }
    }

    // Exit locations (collapsed — just names)
    if (exitLocs.length) {
      const exitHeader = createSectionHeader('EXITS', '#6a6a78');
      sidebar.appendChild(exitHeader);
      for (const loc of exitLocs) {
        const label = loc.direction ? `${loc.direction} \u2192 ${loc.name}` : loc.name;
        sidebar.appendChild(createSidebarItem({ ...loc, name: label }, TYPE_COLORS.location));
      }
    }

    // Player section — player name with inventory nested under it
    const playerData = _codexData?.player;
    if (playerData) {
      // Add player entity to _allEntities if not there
      if (!_allEntities.find(e => e.id === playerData.id)) {
        _allEntities.push({
          id: playerData.id,
          name: playerData.name,
          type: 'player',
          labels: [playerData.archetype || 'Player'],
          summary: '',
        });
      }
      const playerHeader = createSectionHeader(`\u2663 ${playerData.name}`, TYPE_COLORS.player, true);
      playerHeader.addEventListener('click', () => { _selectedId = playerData.id; render(); });
      sidebar.appendChild(playerHeader);
    }

    // Right detail panel
    const detail = document.createElement('div');
    detail.style.flex = '1';
    detail.style.minWidth = '0';
    detail.style.display = 'flex';
    detail.style.flexDirection = 'column';
    detail.style.padding = '8px 12px';

    const selected = _allEntities.find(e => e.id === _selectedId);
    if (selected) {
      // Collect sections into pages
      const sections: HTMLElement[] = [];
      renderDetailSections(sections, selected);

      const SECTIONS_PER_PAGE = 4;
      const totalPages = Math.max(1, Math.ceil(sections.length / SECTIONS_PER_PAGE));
      _detailPage = Math.min(_detailPage, totalPages - 1);

      const contentArea = document.createElement('div');
      contentArea.style.flex = '1';
      contentArea.style.overflowY = 'hidden';

      const start = _detailPage * SECTIONS_PER_PAGE;
      const pageSections = sections.slice(start, start + SECTIONS_PER_PAGE);
      for (const sec of pageSections) {
        contentArea.appendChild(sec);
      }
      detail.appendChild(contentArea);

      // Pagination controls
      if (totalPages > 1) {
        const pager = document.createElement('div');
        pager.style.display = 'flex';
        pager.style.justifyContent = 'center';
        pager.style.alignItems = 'center';
        pager.style.gap = '12px';
        pager.style.padding = '6px 0 2px';
        pager.style.borderTop = '1px solid #1a1a24';
        pager.style.color = '#6a6a78';
        pager.style.fontSize = '11px';

        const prev = document.createElement('span');
        prev.textContent = '\u25C0';
        prev.style.cursor = _detailPage > 0 ? 'pointer' : 'default';
        prev.style.color = _detailPage > 0 ? '#8b5cf6' : '#3a3a48';
        if (_detailPage > 0) {
          prev.addEventListener('click', () => { _detailPage--; render(); });
        }

        const info = document.createElement('span');
        info.textContent = `${_detailPage + 1}/${totalPages}`;

        const next = document.createElement('span');
        next.textContent = '\u25B6';
        next.style.cursor = _detailPage < totalPages - 1 ? 'pointer' : 'default';
        next.style.color = _detailPage < totalPages - 1 ? '#8b5cf6' : '#3a3a48';
        if (_detailPage < totalPages - 1) {
          next.addEventListener('click', () => { _detailPage++; render(); });
        }

        pager.appendChild(prev);
        pager.appendChild(info);
        pager.appendChild(next);
        detail.appendChild(pager);
      }
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

  function createSectionHeader(text: string, color: string, bold: boolean = false): HTMLElement {
    const el = document.createElement('div');
    el.style.color = color;
    el.style.fontSize = '10px';
    el.style.letterSpacing = '1px';
    el.style.padding = '6px 8px 2px';
    el.style.cursor = 'pointer';
    if (bold) {
      el.style.fontWeight = 'bold';
      el.style.fontSize = '11px';
    }
    el.textContent = text;
    return el;
  }

  function createSidebarItem(entity: CodexEntity, color: string, prefix: string = ''): HTMLElement {
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

    item.textContent = prefix + entity.name;

    item.addEventListener('click', () => {
      _selectedId = entity.id;
      _detailPage = 0;
      render();
    });

    return item;
  }

  function renderDetailSections(sections: HTMLElement[], entity: CodexEntity) {
    // Wrapper that creates a section div and pushes it
    const container = { appendChild(el: HTMLElement) { sections.push(el); } } as HTMLElement;
    renderDetailInto(container, entity);
  }

  function renderDetailInto(container: HTMLElement, entity: CodexEntity) {
    const attrs = entity.attributes || {};

    // Header section: name + labels + summary
    const headerSection = document.createElement('div');
    headerSection.style.marginBottom = '8px';

    const name = document.createElement('div');
    name.style.color = entityColor(entity);
    name.style.fontWeight = 'bold';
    name.style.fontSize = '15px';
    name.style.marginBottom = '4px';
    name.textContent = entity.name;
    headerSection.appendChild(name);

    if (entity.labels.length) {
      const labels = document.createElement('div');
      labels.style.color = '#6a6a78';
      labels.style.fontSize = '10px';
      labels.style.marginBottom = '8px';
      labels.textContent = entity.labels.join(' \u00B7 ');
      headerSection.appendChild(labels);
    }

    let summaryText = entity.summary || '';
    if (summaryText.startsWith('{')) {
      summaryText = attrs.description || attrs.personality || '';
    }
    if (!summaryText && attrs.description) {
      summaryText = attrs.description;
    }
    if (summaryText) {
      const summary = document.createElement('div');
      summary.style.color = '#c8c8d0';
      summary.style.lineHeight = '1.5';
      summary.textContent = summaryText;
      headerSection.appendChild(summary);
    }
    container.appendChild(headerSection);

    // Attributes section
    if (Object.keys(attrs).length > 0) {
      // NPC attributes
      if (entity.type === 'npc') {
        if (attrs.personality) addSection(container, 'PERSONALITY', attrs.personality);
        if (attrs.backstory) addSection(container, 'BACKSTORY', attrs.backstory);
        if (attrs.stats && Object.keys(attrs.stats).length) {
          const statsText = Object.entries(attrs.stats).map(([k, v]) => `${k} ${v}`).join(' \u00B7 ');
          addSection(container, 'STATS', statsText);
        }
        if (attrs.skills && Object.keys(attrs.skills).length) {
          const skillsText = Object.entries(attrs.skills).map(([k, v]) => `${k}: ${v}`).join(', ');
          addSection(container, 'SKILLS', skillsText);
        }
        if (attrs.abilities?.length) {
          const abDiv = document.createElement('div');
          abDiv.style.marginBottom = '8px';
          const abHeader = document.createElement('div');
          abHeader.style.color = '#6a6a78';
          abHeader.style.fontSize = '10px';
          abHeader.style.letterSpacing = '1px';
          abHeader.style.marginBottom = '4px';
          abHeader.textContent = 'ABILITIES';
          abDiv.appendChild(abHeader);
          for (const ab of attrs.abilities) {
            const row = document.createElement('div');
            row.style.marginBottom = '4px';
            row.innerHTML = `<span style="color:#8b5cf6">${esc(ab.name)}</span> <span style="color:#6a6a78">\u2014 ${esc(ab.description)}</span>`;
            abDiv.appendChild(row);
          }
          container.appendChild(abDiv);
        }
        if (attrs.traits?.length) addSection(container, 'TRAITS', attrs.traits.join(', '));
        if (attrs.disposition) addSection(container, 'DISPOSITION', attrs.disposition);
        if (attrs.motivation) addSection(container, 'MOTIVATION', attrs.motivation);
      }

      // Item attributes
      if (entity.type === 'item') {
        const parts: string[] = [];
        if (attrs.damage) parts.push(`Damage: ${attrs.damage}`);
        if (attrs.defense) parts.push(`Defense: ${attrs.defense}`);
        if (attrs.weight) parts.push(`Weight: ${attrs.weight}`);
        if (parts.length) addSection(container, 'MECHANICS', parts.join(' \u00B7 '));
        if (attrs.lore) addSection(container, 'LORE', attrs.lore);
        if (attrs.effects?.length) addSection(container, 'EFFECTS', attrs.effects.join(', '));
      }

      // Location attributes — grouped into one section
      if (entity.type === 'location') {
        const locAttrs = document.createElement('div');
        locAttrs.style.marginBottom = '8px';
        let hasLocAttrs = false;
        if (attrs.biome) { addSectionTo(locAttrs, 'BIOME', attrs.biome); hasLocAttrs = true; }
        if (attrs.atmosphere) { addSectionTo(locAttrs, 'ATMOSPHERE', attrs.atmosphere); hasLocAttrs = true; }
        if (attrs.culture) { addSectionTo(locAttrs, 'CULTURE', attrs.culture); hasLocAttrs = true; }
        if (attrs.threats?.length) { addSectionTo(locAttrs, 'THREATS', attrs.threats.join(', ')); hasLocAttrs = true; }
        if (attrs.danger_level) {
          const skulls = '\u2620'.repeat(Math.min(attrs.danger_level, 5));
          addSectionTo(locAttrs, 'DANGER', `${skulls} (${attrs.danger_level}/10)`);
          hasLocAttrs = true;
        }
        if (attrs.lore) { addSectionTo(locAttrs, 'LORE', attrs.lore); hasLocAttrs = true; }
        if (hasLocAttrs) container.appendChild(locAttrs);
      }
    }

    // Player-specific: show stats + inventory
    if (entity.type === 'player') {
      const playerData = _codexData?.player;
      if (playerData) {
        const statsDiv = document.createElement('div');
        statsDiv.style.marginBottom = '12px';
        statsDiv.innerHTML = `
          <div style="color:#6a6a78;font-size:10px;letter-spacing:1px;margin-bottom:4px">STATS</div>
          <div>Level: <span style="color:#c8c8d0">${playerData.level || 1}</span></div>
          <div>Health: <span style="color:#50c878">${playerData.health || 100}</span></div>
          <div>Archetype: <span style="color:#8b5cf6">${esc(playerData.archetype || 'Unknown')}</span></div>
        `;
        container.appendChild(statsDiv);
      }

      const spacer = document.createElement('div');
      spacer.style.marginTop = '12px';
      container.appendChild(spacer);
    }

    // Location-specific: exits + present grouped into one section
    if (entity.type === 'location' && entity.exits) {
      const locSection = document.createElement('div');
      locSection.style.marginBottom = '8px';

      addSectionTo(locSection, 'EXITS', '');
      // Replace the empty body with clickable exits
      const exitsBody = locSection.lastElementChild?.querySelector('div:last-child');
      if (exitsBody) exitsBody.remove();
      for (const ex of entity.exits) {
        const row = document.createElement('div');
        row.style.marginBottom = '2px';
        row.innerHTML = `<span style="color:#8b5cf6">${esc(ex.direction || '?')}</span> <span style="color:#6a6a78">\u2192</span> <span style="color:#7aa2d4;cursor:pointer">${esc(ex.target || '?')}</span>`;
        const targetSpan = row.querySelector('span:last-child');
        if (targetSpan) {
          targetSpan.addEventListener('click', () => {
            const linked = _allEntities.find(e => e.name === ex.target);
            if (linked) { _selectedId = linked.id; _detailPage = 0; render(); }
          });
        }
        locSection.appendChild(row);
      }

      // Present — player, NPCs, ground items
      if (entity.current) {
        const npcsHere = _codexData?.npcs || [];
        const itemsHere = _codexData?.ground_items || [];
        const playerHere = _codexData?.player;

        const presHeader = document.createElement('div');
        presHeader.style.color = '#6a6a78';
        presHeader.style.fontSize = '10px';
        presHeader.style.letterSpacing = '1px';
        presHeader.style.margin = '8px 0 4px';
        presHeader.textContent = 'PRESENT';
        locSection.appendChild(presHeader);

        if (playerHere) {
          const row = document.createElement('div');
          row.style.color = TYPE_COLORS.player;
          row.style.cursor = 'pointer';
          row.textContent = `\u2663 ${playerHere.name} (you)`;
          row.addEventListener('click', () => { _selectedId = playerHere.id; _detailPage = 0; render(); });
          locSection.appendChild(row);
        }
        for (const npc of npcsHere) {
          const row = document.createElement('div');
          row.style.color = TYPE_COLORS.npc;
          row.style.cursor = 'pointer';
          row.textContent = `\u25CF ${npc.name}`;
          row.addEventListener('click', () => { _selectedId = npc.id; _detailPage = 0; render(); });
          locSection.appendChild(row);
        }
        for (const item of itemsHere) {
          const row = document.createElement('div');
          row.style.color = itemColor(item);
          row.style.cursor = 'pointer';
          row.textContent = `\u2022 ${item.name}`;
          row.addEventListener('click', () => { _selectedId = item.id; _detailPage = 0; render(); });
          locSection.appendChild(row);
        }
      }

      container.appendChild(locSection);
    }

    // Connections
    if (entity.relationships?.length) {
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

  function addSectionTo(parent: HTMLElement, label: string, text: string) {
    const section = document.createElement('div');
    section.style.marginBottom = '6px';
    const header = document.createElement('div');
    header.style.color = '#6a6a78';
    header.style.fontSize = '10px';
    header.style.letterSpacing = '1px';
    header.style.marginBottom = '2px';
    header.textContent = label;
    section.appendChild(header);
    if (text) {
      const body = document.createElement('div');
      body.style.color = '#c8c8d0';
      body.style.fontSize = '12px';
      body.textContent = text;
      section.appendChild(body);
    }
    parent.appendChild(section);
  }

  function addSection(container: HTMLElement, label: string, text: string) {
    addSectionTo(container, label, text);
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
