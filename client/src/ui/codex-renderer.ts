// src/ui/codex-renderer.ts
/**
 * CharCell-based codex modal renderer.
 * Replaces the DOM-based codex-modal.ts. Two-panel entity browser.
 */

import type { CharCell } from '../renderer/canvas-text';
import { ATTR_BOLD, ATTR_UNDERLINE } from '../renderer/canvas-text';
import type { PanelResult, LocalHitRegion } from '../canvas/types';
import type { ModalManager } from '../canvas/modal-manager';
import type { GameState } from '../state/game-state';
import { theme } from '../renderer/theme';
import { textRow, emptyRow, coloredRow } from '../panels/panel-utils';
import { GATEWAY_URL } from '../state/session';

const MODAL_NAME = 'codex';

// ── Types ───────────────────────────────────────────────────────

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
  type: string;
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
  attributes?: Record<string, unknown>;
}

interface CodexResponse {
  npcs: CodexEntity[];
  ground_items: CodexEntity[];
  inventory: CodexEntity[];
  locations: CodexEntity[];
  player: {
    id: string;
    name: string;
    level: number;
    health: number;
    archetype: string;
    chain: Record<string, unknown> | null;
  };
}

// ── Color helpers ───────────────────────────────────────────────

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
  if (entity.rarity && RARITY_COLORS[entity.rarity])
    return RARITY_COLORS[entity.rarity];
  return TYPE_COLORS.item;
}

function entityColor(entity: CodexEntity): string {
  if (entity.type === 'item') return itemColor(entity);
  return TYPE_COLORS[entity.type] || '#c8c8d0';
}

function formatAddr(addr: string): string {
  if (
    !addr ||
    addr.length < 10 ||
    addr === '0x0000000000000000000000000000000000000000'
  )
    return 'None';
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

/** Word-wrap text to fit cols. */
function wordWrap(text: string, cols: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split('\n')) {
    if (paragraph.length === 0) {
      lines.push('');
      continue;
    }
    const words = paragraph.split(/\s+/);
    let current = '';
    for (const word of words) {
      if (current.length === 0) {
        current = word;
      } else if (current.length + 1 + word.length <= cols) {
        current += ' ' + word;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current.length > 0) lines.push(current);
  }
  return lines;
}

// ── Render functions ────────────────────────────────────────────

function renderCodexContent(
  cols: number,
  _rows: number,
  codexData: CodexResponse | null,
  allEntities: CodexEntity[],
  selectedId: string | null,
): PanelResult {
  const cells: CharCell[][] = [];
  const hitRegions: LocalHitRegion[] = [];

  // Header
  cells.push(
    coloredRow(
      [
        { text: 'CODEX', fg: theme.colors.accent, attrs: ATTR_BOLD },
        { text: ' '.repeat(Math.max(0, cols - 8)), fg: theme.colors.dim },
        { text: '[\u00D7]', fg: theme.colors.damage },
      ],
      cols,
    ),
  );

  // Close button hit
  hitRegions.push({
    col: cols - 3,
    row: 0,
    width: 3,
    height: 1,
    data: { modalAction: 'close', modal: MODAL_NAME },
  });

  cells.push(
    coloredRow([{ text: '\u2500'.repeat(cols), fg: theme.colors.dim }], cols),
  );

  if (!codexData) {
    cells.push(
      coloredRow(
        [{ text: 'Loading...', fg: theme.colors.dim }],
        cols,
      ),
    );
    return { cells, hitRegions };
  }

  // Two-panel layout: sidebar (left) | detail (right)
  const sidebarCols = Math.min(24, Math.floor(cols * 0.3));
  const detailCols = cols - sidebarCols - 1; // 1 for divider

  const sidebarRows: CharCell[][] = [];
  const sidebarHits: LocalHitRegion[] = [];
  const detailRows: CharCell[][] = [];

  // ── Build sidebar ──
  const npcs = codexData.npcs || [];
  const groundItems = codexData.ground_items || [];
  const locations = codexData.locations || [];
  const currentLoc = locations.find(
    (l: CodexEntity) => l.current,
  );
  const exitLocs = locations.filter(
    (l: CodexEntity) => !l.current,
  );

  // Current location
  if (currentLoc) {
    const locText = truncate(`\u25C9 ${currentLoc.name}`, sidebarCols);
    const isSelected = currentLoc.id === selectedId;
    sidebarRows.push(
      coloredRow(
        [
          {
            text: locText,
            fg: TYPE_COLORS.location,
            attrs: isSelected ? ATTR_BOLD : undefined,
          },
        ],
        sidebarCols,
      ),
    );
    sidebarHits.push({
      col: 0,
      row: sidebarRows.length - 1,
      width: sidebarCols,
      height: 1,
      data: { codexSelect: currentLoc.id },
    });

    // NPCs
    for (const npc of npcs) {
      const npcText = truncate(`  ${npc.name}`, sidebarCols);
      const sel = npc.id === selectedId;
      sidebarRows.push(
        coloredRow(
          [
            {
              text: npcText,
              fg: TYPE_COLORS.npc,
              attrs: sel ? ATTR_BOLD : undefined,
            },
          ],
          sidebarCols,
        ),
      );
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: npc.id },
      });
    }

    // Ground items
    for (const gi of groundItems) {
      const giText = truncate(`  ${gi.name}`, sidebarCols);
      const sel = gi.id === selectedId;
      sidebarRows.push(
        coloredRow(
          [
            {
              text: giText,
              fg: itemColor(gi),
              attrs: sel ? ATTR_BOLD : undefined,
            },
          ],
          sidebarCols,
        ),
      );
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: gi.id },
      });
    }
  }

  // Exits
  if (exitLocs.length > 0) {
    sidebarRows.push(emptyRow(sidebarCols));
    sidebarRows.push(
      coloredRow([{ text: 'EXITS', fg: theme.colors.dim }], sidebarCols),
    );
    for (const loc of exitLocs) {
      const label = loc.direction
        ? truncate(`${loc.direction} \u2192 ${loc.name}`, sidebarCols)
        : truncate(loc.name, sidebarCols);
      const sel = loc.id === selectedId;
      sidebarRows.push(
        coloredRow(
          [
            {
              text: label,
              fg: TYPE_COLORS.location,
              attrs: sel ? ATTR_BOLD : undefined,
            },
          ],
          sidebarCols,
        ),
      );
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: loc.id },
      });
    }
  }

  // Player
  if (codexData.player) {
    sidebarRows.push(emptyRow(sidebarCols));
    const playerText = truncate(
      `\u2663 ${codexData.player.name}`,
      sidebarCols,
    );
    const sel = codexData.player.id === selectedId;
    sidebarRows.push(
      coloredRow(
        [
          {
            text: playerText,
            fg: TYPE_COLORS.player,
            attrs: sel ? ATTR_BOLD : undefined,
          },
        ],
        sidebarCols,
      ),
    );
    sidebarHits.push({
      col: 0,
      row: sidebarRows.length - 1,
      width: sidebarCols,
      height: 1,
      data: { codexSelect: codexData.player.id },
    });
  }

  // ── Build detail panel ──
  const selected = allEntities.find(e => e.id === selectedId);
  if (selected) {
    renderEntityDetail(detailRows, selected, detailCols, codexData, allEntities, sidebarCols);
  } else {
    detailRows.push(
      coloredRow(
        [{ text: 'No entities to display', fg: theme.colors.dim }],
        detailCols,
      ),
    );
  }

  // ── Merge sidebar + divider + detail ──
  const maxRows = Math.max(sidebarRows.length, detailRows.length);
  const dividerChar: CharCell = { char: '\u2502', fg: theme.colors.dim };

  for (let r = 0; r < maxRows; r++) {
    const left = sidebarRows[r] || emptyRow(sidebarCols);
    const right = detailRows[r] || emptyRow(detailCols);
    const combinedRow: CharCell[] = [
      ...left.slice(0, sidebarCols),
      dividerChar,
      ...right.slice(0, detailCols),
    ];
    while (combinedRow.length < cols) {
      combinedRow.push({ char: ' ', fg: theme.colors.primary });
    }
    cells.push(combinedRow);
  }

  // Offset hit regions for header rows
  const headerRowCount = 2;
  for (const h of sidebarHits) {
    h.row += headerRowCount;
  }
  hitRegions.push(...sidebarHits);

  return { cells, hitRegions };
}

function renderEntityDetail(
  rows: CharCell[][],
  entity: CodexEntity,
  cols: number,
  codexData: CodexResponse,
  allEntities: CodexEntity[],
  _sidebarCols: number,
): void {
  const attrs = (entity.attributes || {}) as Record<string, unknown>;

  // Name
  rows.push(
    coloredRow(
      [{ text: entity.name, fg: entityColor(entity), attrs: ATTR_BOLD }],
      cols,
    ),
  );

  // Labels
  if (entity.labels.length) {
    rows.push(
      coloredRow(
        [{ text: entity.labels.join(' \u00B7 '), fg: theme.colors.dim }],
        cols,
      ),
    );
  }
  rows.push(emptyRow(cols));

  // Summary
  let summaryText = entity.summary || '';
  if (summaryText.startsWith('{')) {
    summaryText = (attrs.description as string) || (attrs.personality as string) || '';
  }
  if (!summaryText && attrs.description) {
    summaryText = attrs.description as string;
  }
  if (summaryText) {
    const wrapped = wordWrap(summaryText, cols);
    for (const line of wrapped) {
      rows.push(textRow(line, theme.colors.primary, cols));
    }
    rows.push(emptyRow(cols));
  }

  // ASCII art (just show a placeholder or first few lines)
  const asciiArt = attrs.ascii_art as string | undefined;
  if (asciiArt) {
    const artLines = asciiArt.split('\n').slice(0, 8);
    for (const line of artLines) {
      rows.push(
        coloredRow(
          [{ text: truncate(line, cols), fg: entityColor(entity) }],
          cols,
        ),
      );
    }
    if (asciiArt.split('\n').length > 8) {
      rows.push(
        coloredRow(
          [{ text: '  ... (truncated)', fg: theme.colors.dim }],
          cols,
        ),
      );
    }
    rows.push(emptyRow(cols));
  } else if (entity.type !== 'player') {
    rows.push(
      coloredRow(
        [{ text: '[ art pending ]', fg: '#3a3a48' }],
        cols,
      ),
    );
    rows.push(emptyRow(cols));
  }

  // NPC attributes
  if (entity.type === 'npc') {
    if (attrs.personality) addSection(rows, cols, 'PERSONALITY', attrs.personality as string);
    if (attrs.backstory) addSection(rows, cols, 'BACKSTORY', attrs.backstory as string);
    if (attrs.stats && typeof attrs.stats === 'object') {
      const statsText = Object.entries(attrs.stats as Record<string, unknown>)
        .map(([k, v]) => `${k} ${v}`)
        .join(' \u00B7 ');
      addSection(rows, cols, 'STATS', statsText);
    }
    if (attrs.skills && typeof attrs.skills === 'object') {
      const skillsText = Object.entries(attrs.skills as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ');
      addSection(rows, cols, 'SKILLS', skillsText);
    }
    if (Array.isArray(attrs.abilities) && attrs.abilities.length) {
      rows.push(
        coloredRow([{ text: 'ABILITIES', fg: theme.colors.dim }], cols),
      );
      for (const ab of attrs.abilities as Array<{ name: string; description: string }>) {
        rows.push(
          coloredRow(
            [
              { text: ab.name, fg: theme.colors.accent },
              { text: ` \u2014 ${ab.description}`, fg: theme.colors.dim },
            ],
            cols,
          ),
        );
      }
      rows.push(emptyRow(cols));
    }
    if (Array.isArray(attrs.traits) && attrs.traits.length) {
      addSection(rows, cols, 'TRAITS', (attrs.traits as string[]).join(', '));
    }
    if (attrs.disposition) addSection(rows, cols, 'DISPOSITION', attrs.disposition as string);
    if (attrs.motivation) addSection(rows, cols, 'MOTIVATION', attrs.motivation as string);
  }

  // Item attributes
  if (entity.type === 'item') {
    const parts: string[] = [];
    if (attrs.damage) parts.push(`Damage: ${attrs.damage}`);
    if (attrs.defense) parts.push(`Defense: ${attrs.defense}`);
    if (attrs.weight) parts.push(`Weight: ${attrs.weight}`);
    if (parts.length) addSection(rows, cols, 'MECHANICS', parts.join(' \u00B7 '));
    if (attrs.lore) addSection(rows, cols, 'LORE', attrs.lore as string);
    if (Array.isArray(attrs.effects) && attrs.effects.length) {
      addSection(rows, cols, 'EFFECTS', (attrs.effects as string[]).join(', '));
    }
  }

  // Location attributes
  if (entity.type === 'location') {
    if (attrs.biome) addSection(rows, cols, 'BIOME', attrs.biome as string);
    if (attrs.atmosphere) addSection(rows, cols, 'ATMOSPHERE', attrs.atmosphere as string);
    if (attrs.culture) addSection(rows, cols, 'CULTURE', attrs.culture as string);
    if (Array.isArray(attrs.threats) && attrs.threats.length) {
      addSection(rows, cols, 'THREATS', (attrs.threats as string[]).join(', '));
    }
    if (attrs.danger_level) {
      const dl = attrs.danger_level as number;
      const skulls = '\u2620'.repeat(Math.min(dl, 5));
      addSection(rows, cols, 'DANGER', `${skulls} (${dl}/10)`);
    }
    if (attrs.lore) addSection(rows, cols, 'LORE', attrs.lore as string);
  }

  // Player stats
  if (entity.type === 'player' && codexData.player) {
    const p = codexData.player;
    rows.push(
      coloredRow([{ text: 'STATS', fg: theme.colors.dim }], cols),
    );
    rows.push(
      coloredRow(
        [
          { text: 'Level: ', fg: theme.colors.dim },
          { text: String(p.level || 1), fg: theme.colors.primary },
        ],
        cols,
      ),
    );
    rows.push(
      coloredRow(
        [
          { text: 'Health: ', fg: theme.colors.dim },
          { text: String(p.health || 100), fg: theme.colors.heal },
        ],
        cols,
      ),
    );
    rows.push(
      coloredRow(
        [
          { text: 'Archetype: ', fg: theme.colors.dim },
          { text: p.archetype || 'Unknown', fg: theme.colors.accent },
        ],
        cols,
      ),
    );
    rows.push(emptyRow(cols));
  }

  // Location exits
  if (entity.type === 'location' && entity.exits) {
    rows.push(
      coloredRow([{ text: 'EXITS', fg: theme.colors.dim }], cols),
    );
    for (const ex of entity.exits) {
      rows.push(
        coloredRow(
          [
            { text: ex.direction || '?', fg: theme.colors.accent },
            { text: ' \u2192 ', fg: theme.colors.dim },
            { text: ex.target || '?', fg: TYPE_COLORS.location },
          ],
          cols,
        ),
      );
    }
    rows.push(emptyRow(cols));

    // Present entities
    if (entity.current) {
      rows.push(
        coloredRow([{ text: 'PRESENT', fg: theme.colors.dim }], cols),
      );
      if (codexData.player) {
        rows.push(
          coloredRow(
            [{ text: `\u2663 ${codexData.player.name} (you)`, fg: TYPE_COLORS.player }],
            cols,
          ),
        );
      }
      for (const npc of codexData.npcs || []) {
        rows.push(
          coloredRow(
            [{ text: `\u25CF ${npc.name}`, fg: TYPE_COLORS.npc }],
            cols,
          ),
        );
      }
      for (const item of codexData.ground_items || []) {
        rows.push(
          coloredRow(
            [{ text: `\u2022 ${item.name}`, fg: itemColor(item) }],
            cols,
          ),
        );
      }
      rows.push(emptyRow(cols));
    }
  }

  // Connections
  if (entity.relationships?.length) {
    rows.push(
      coloredRow([{ text: 'CONNECTIONS', fg: theme.colors.dim }], cols),
    );
    for (const rel of entity.relationships) {
      const relType = rel.relationship.replace(/_/g, ' ');
      const other = rel.source === entity.name ? rel.target : rel.source;
      rows.push(
        coloredRow(
          [
            { text: relType + ' ', fg: theme.colors.dim },
            { text: other, fg: TYPE_COLORS.location, attrs: ATTR_UNDERLINE },
          ],
          cols,
        ),
      );
      if (rel.fact) {
        const factText =
          rel.fact.length > 80 ? rel.fact.slice(0, 80) + '\u2026' : rel.fact;
        const wrapped = wordWrap(`  ${factText}`, cols);
        for (const line of wrapped) {
          rows.push(textRow(line, theme.colors.dim, cols));
        }
      }
    }
    rows.push(emptyRow(cols));
  }

  // Onchain
  if (entity.chain_data) {
    const chain = entity.chain_data;
    rows.push(
      coloredRow([{ text: 'ONCHAIN', fg: theme.colors.heal }], cols),
    );

    if (entity.type === 'npc' || entity.type === 'player') {
      if (chain.level != null) addChainRow(rows, cols, 'Level', String(chain.level));
      if (chain.alive != null) addChainRow(rows, cols, 'Status', chain.alive ? 'Alive' : 'Dead');
      if (chain.wallet) addChainRow(rows, cols, 'Wallet', formatAddr(chain.wallet));
    } else if (entity.type === 'item') {
      if (chain.rarity) addChainRow(rows, cols, 'Rarity', String(chain.rarity));
      if (chain.ownerId) addChainRow(rows, cols, 'Owner', formatAddr(chain.ownerId));
      if (chain.locationId) addChainRow(rows, cols, 'Location', formatAddr(chain.locationId));
    }
    rows.push(emptyRow(cols));
  }
}

function addSection(
  rows: CharCell[][],
  cols: number,
  label: string,
  text: string,
): void {
  rows.push(coloredRow([{ text: label, fg: theme.colors.dim }], cols));
  const wrapped = wordWrap(text, cols);
  for (const line of wrapped) {
    rows.push(textRow(line, theme.colors.primary, cols));
  }
  rows.push(emptyRow(cols));
}

function addChainRow(
  rows: CharCell[][],
  cols: number,
  label: string,
  value: string,
): void {
  rows.push(
    coloredRow(
      [
        { text: `${label.padEnd(10)}`, fg: theme.colors.dim },
        { text: value, fg: theme.colors.primary },
      ],
      cols,
    ),
  );
}

function truncate(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 1) + '\u2026';
}

// ── Codex Controller ────────────────────────────────────────────

export interface CodexModalController {
  open(entityId?: string): void;
  close(): void;
  refreshEntityArt(entityId: string, lines: string[]): void;
  selectEntity(entityId: string): void;
  readonly active: boolean;
}

export function createCodexController(
  mm: ModalManager,
  getState: () => GameState,
  playerId: () => string,
): CodexModalController {
  let _codexData: CodexResponse | null = null;
  let _selectedId: string | null = null;
  let _allEntities: CodexEntity[] = [];

  function render(): void {
    if (!mm.isOpen(MODAL_NAME)) return;
    const modal = mm.getStack().find(m => m.name === MODAL_NAME);
    if (!modal) return;
    const contentCols = modal.region.cols - 2;
    const contentRows = modal.region.rows - 2;
    mm.setContent(
      MODAL_NAME,
      renderCodexContent(contentCols, contentRows, _codexData, _allEntities, _selectedId),
    );
  }

  async function open(entityId?: string): Promise<void> {
    mm.open(MODAL_NAME, 0.7, 0.7);

    // Show loading state
    const modal = mm.getStack().find(m => m.name === MODAL_NAME);
    if (modal) {
      const contentCols = modal.region.cols - 2;
      mm.setContent(MODAL_NAME, {
        cells: [
          coloredRow(
            [{ text: 'Loading...', fg: theme.colors.dim }],
            contentCols,
          ),
        ],
      });
    }

    // Fetch codex data
    try {
      const pid = playerId();
      const state = getState();
      const locId = state?.roomMap?.id || '';
      const url = locId
        ? `${GATEWAY_URL}/api/codex/${pid}?location_uuid=${locId}`
        : `${GATEWAY_URL}/api/codex/${pid}`;
      const resp = await fetch(url);
      _codexData = await resp.json();
    } catch {
      _codexData = null;
    }

    // Build flat entity list
    _allEntities = [];
    const seen = new Set<string>();
    if (_codexData) {
      for (const npc of _codexData.npcs || []) {
        if (!seen.has(npc.id)) {
          seen.add(npc.id);
          _allEntities.push({ ...npc, type: 'npc' });
        }
      }
      for (const gi of _codexData.ground_items || []) {
        if (!seen.has(gi.id)) {
          seen.add(gi.id);
          _allEntities.push({ ...gi, type: 'item' });
        }
      }
      for (const loc of _codexData.locations || []) {
        if (!seen.has(loc.id)) {
          seen.add(loc.id);
          _allEntities.push({
            ...loc,
            type: 'location',
            labels: loc.labels || ['Location'],
          });
        }
      }
      if (_codexData.player && !seen.has(_codexData.player.id)) {
        seen.add(_codexData.player.id);
        _allEntities.push({
          id: _codexData.player.id,
          name: _codexData.player.name,
          type: 'player',
          labels: [_codexData.player.archetype || 'Player'],
          summary: '',
        });
      }
    }

    // Select entity
    if (entityId) {
      _selectedId = entityId;
    } else {
      const currentLoc = (_codexData?.locations || []).find(
        (l: CodexEntity) => l.current,
      );
      _selectedId =
        currentLoc?.id || (_allEntities.length ? _allEntities[0].id : null);
    }
    if (
      _selectedId &&
      !_allEntities.find(e => e.id === _selectedId)
    ) {
      _selectedId = _allEntities.length ? _allEntities[0].id : null;
    }

    render();
  }

  function close(): void {
    mm.close(MODAL_NAME);
  }

  function refreshEntityArt(entityId: string, lines: string[]): void {
    const artText = lines.join('\n');
    const entity = _allEntities.find(e => e.id === entityId);
    if (entity) {
      if (!entity.attributes) entity.attributes = {};
      (entity.attributes as Record<string, unknown>).ascii_art = artText;
      if (_selectedId === entityId && mm.isOpen(MODAL_NAME)) {
        render();
      }
    }
  }

  /** Handle codexSelect click — select an entity in the sidebar. */
  function handleSelect(entityId: string): void {
    _selectedId = entityId;
    // Reset scroll
    const modal = mm.getStack().find(m => m.name === MODAL_NAME);
    if (modal) modal.scrollOffset = 0;
    render();
  }

  return {
    open,
    close,
    refreshEntityArt,
    selectEntity: handleSelect,
    get active() {
      return mm.isOpen(MODAL_NAME);
    },
  };
}
