// src/renderer/text-renderer.ts
/**
 * Pretext-powered text renderer for the narrative pane.
 * Uses Pretext for text measurement, renders to DOM with styled spans.
 */

// NOTE: Pretext integration is deferred — the library's API surface
// needs investigation for our use case (we need styled segments, not
// just measurement). For MVP, we use DOM-based rich text rendering.
// Pretext will be integrated when we need virtualized scrolling for
// very long sessions.

export interface StyledSegment {
  text: string;
  style: 'normal' | 'npc' | 'damage' | 'heal' | 'system' | 'location' | 'italic' | 'bold';
}

/**
 * Parse narrative text into styled segments.
 * Detects NPC names (quoted text), damage numbers, location names, etc.
 */
export function parseNarrative(text: string): StyledSegment[] {
  const segments: StyledSegment[] = [];
  // Simple regex-based parsing for MVP
  const pattern = /"([^"]+)"|(\d+ damage)|(\d+ health|\d+ HP)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    // Text before match
    if (match.index > lastIndex) {
      segments.push({ text: text.slice(lastIndex, match.index), style: 'normal' });
    }

    if (match[1]) {
      // Quoted text = NPC dialogue
      segments.push({ text: `"${match[1]}"`, style: 'npc' });
    } else if (match[2]) {
      // Damage number
      segments.push({ text: match[2], style: 'damage' });
    } else if (match[3]) {
      // Healing
      segments.push({ text: match[3], style: 'heal' });
    }

    lastIndex = match.index + match[0].length;
  }

  // Remaining text
  if (lastIndex < text.length) {
    segments.push({ text: text.slice(lastIndex), style: 'normal' });
  }

  return segments.length ? segments : [{ text, style: 'normal' }];
}

/**
 * Render styled segments to an HTML string.
 */
export function renderSegments(segments: StyledSegment[]): string {
  return segments.map(seg => {
    const cls = seg.style === 'normal' ? '' : seg.style;
    return cls ? `<span class="${cls}">${escapeHtml(seg.text)}</span>` : escapeHtml(seg.text);
  }).join('');
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
