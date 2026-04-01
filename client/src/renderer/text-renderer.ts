// src/renderer/text-renderer.ts
/**
 * Text renderer for the narrative pane.
 * Parses narrative into styled segments with entity highlighting.
 */

export interface StyledSegment {
  text: string;
  style: 'normal' | 'npc' | 'damage' | 'heal' | 'system' | 'location' | 'italic' | 'bold' | 'entity';
  entityId?: string;
  entityType?: string; // npc, item, exit, location
}

// Known entity names — populated from RoomMap data
// Maps name -> { id, type } for highlighting and coloring by type
let knownEntities: Map<string, { id: string; type: string }> = new Map();

/**
 * Register entity names for highlighting in narrative text.
 * Call this when a room map is loaded.
 */
export function setKnownEntities(entities: Array<{ name: string; id: string; type: string }>): void {
  knownEntities = new Map();
  for (const e of entities) {
    knownEntities.set(e.name, { id: e.id, type: e.type });
  }
}

/**
 * Parse narrative text into styled segments.
 * Detects: quoted dialogue, damage/heal numbers, and known entity names.
 */
export function parseNarrative(text: string): StyledSegment[] {
  const segments: StyledSegment[] = [];

  // First pass: split by quoted dialogue and damage/heal patterns
  const pattern = /"([^"]+)"|(\d+ damage)|(\d+ health|\d+ HP)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const rawSegments: StyledSegment[] = [];

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      rawSegments.push({ text: text.slice(lastIndex, match.index), style: 'normal' });
    }
    if (match[1]) {
      rawSegments.push({ text: `"${match[1]}"`, style: 'npc' });
    } else if (match[2]) {
      rawSegments.push({ text: match[2], style: 'damage' });
    } else if (match[3]) {
      rawSegments.push({ text: match[3], style: 'heal' });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    rawSegments.push({ text: text.slice(lastIndex), style: 'normal' });
  }
  if (rawSegments.length === 0) {
    rawSegments.push({ text, style: 'normal' });
  }

  // Second pass: highlight known entity names within 'normal' segments
  if (knownEntities.size === 0) return rawSegments;

  for (const seg of rawSegments) {
    if (seg.style !== 'normal') {
      segments.push(seg);
      continue;
    }
    // Search for entity names in the text
    const highlighted = highlightEntities(seg.text);
    segments.push(...highlighted);
  }

  return segments;
}

/**
 * Find and highlight known entity names within a text string.
 */
function highlightEntities(text: string): StyledSegment[] {
  if (knownEntities.size === 0) return [{ text, style: 'normal' }];

  // Build regex from entity names (longest first to avoid partial matches)
  const names = Array.from(knownEntities.keys()).sort((a, b) => b.length - a.length);
  const escaped = names.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const entityPattern = new RegExp(`(${escaped.join('|')})`, 'gi');

  const segments: StyledSegment[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;

  while ((m = entityPattern.exec(text)) !== null) {
    if (m.index > lastIdx) {
      segments.push({ text: text.slice(lastIdx, m.index), style: 'normal' });
    }
    const matchedName = m[1];
    // Find the canonical name (case-insensitive lookup)
    let entityId = '';
    let entityType = '';
    for (const [name, info] of knownEntities.entries()) {
      if (name.toLowerCase() === matchedName.toLowerCase()) {
        entityId = info.id;
        entityType = info.type;
        break;
      }
    }
    segments.push({
      text: matchedName,
      style: 'entity',
      entityId,
      entityType,
    });
    lastIdx = m.index + matchedName.length;
  }

  if (lastIdx < text.length) {
    segments.push({ text: text.slice(lastIdx), style: 'normal' });
  }

  return segments.length ? segments : [{ text, style: 'normal' }];
}

/**
 * Render styled segments to an HTML string.
 * Entity segments get a clickable class with data-entity-id.
 */
export function renderSegments(segments: StyledSegment[]): string {
  return segments.map(seg => {
    if (seg.style === 'entity' && seg.entityId) {
      const typeClass = seg.entityType ? `entity-${seg.entityType}` : '';
      return `<span class="entity-link ${typeClass}" data-entity-id="${escapeHtml(seg.entityId)}" data-entity-name="${escapeHtml(seg.text)}">${escapeHtml(seg.text)}</span>`;
    }
    const cls = seg.style === 'normal' ? '' : seg.style;
    return cls ? `<span class="${cls}">${escapeHtml(seg.text)}</span>` : escapeHtml(seg.text);
  }).join('');
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
