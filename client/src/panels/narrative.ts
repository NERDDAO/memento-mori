// src/panels/narrative.ts
/**
 * Canvas-rendered narrative panel with virtual scrolling.
 * Uses NarrativeStore for Pretext-measured block heights and
 * renders monospace text via canvas-text.ts utilities.
 */

import { parseNarrative, type StyledSegment } from '../renderer/text-renderer';
import { NarrativeStore } from '../renderer/line-cache';
import { onRoundStateChange, type RoundState } from '../state/round-state';
import { measureChar, fontForAttrs, MONO_FONT, ATTR_BOLD, ATTR_ITALIC, ATTR_UNDERLINE, type CharSize } from '../renderer/canvas-text';
import { theme } from '../renderer/theme';

// ── Types ────────────────────────────────────────────────────────

export interface NarrativeController {
  addBlock(text: string, type: string): void;
  addHtml(html: string, type: string): void;
  replaceBlock(id: string, text: string, type: string): void;
  removeBlockById(id: string): void;
  showThinking(): void;
  removeThinking(): void;
  scroll(deltaY: number): void;
  canvas: HTMLCanvasElement;
}

interface HitRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  entityId?: string;
  entityName?: string;
  npcName?: string;
}

/** A segment positioned for rendering on a specific line. */
interface PlacedSegment {
  text: string;
  col: number;
  row: number;      // row relative to block top
  fg: string;
  attrs?: number;
  entityId?: string;
  entityName?: string;
  npcName?: string;
}

// ── Color mappings ──────────────────────────────────────────────

const BLOCK_TYPE_COLORS: Record<string, string> = {
  'narrative':      theme.colors.primary,
  'player-action':  theme.colors.dim,
  'system':         theme.colors.system,
  'thinking':       theme.colors.system,
  'event':          theme.colors.dim,
  'event-combat':   theme.colors.damage,
  'event-xp':      theme.colors.heal,
  'event-death':    theme.colors.damage,
  'event-item':     theme.colors.npc,
  'ooc':            theme.colors.accent,
  'divider':        theme.colors.dim,
  'death-feed':     theme.colors.damage,
  'scene-art':      theme.colors.dim,
  'npc-name':       theme.colors.npc,
  'npc-dialogue':   theme.colors.npc,
  'npc-status':     theme.colors.system,
};

const ENTITY_TYPE_COLORS: Record<string, string> = {
  'npc':      theme.colors.npc,
  'item':     theme.colors.heal,
  'location': theme.colors.location,
  'exit':     theme.colors.location,
};

function segmentColor(seg: StyledSegment, blockColor: string): { fg: string; attrs?: number } {
  switch (seg.style) {
    case 'npc':      return { fg: theme.colors.npc };
    case 'damage':   return { fg: theme.colors.damage, attrs: ATTR_BOLD };
    case 'heal':     return { fg: theme.colors.heal, attrs: ATTR_BOLD };
    case 'system':   return { fg: theme.colors.system };
    case 'location': return { fg: theme.colors.location };
    case 'italic':   return { fg: blockColor, attrs: ATTR_ITALIC };
    case 'bold':     return { fg: blockColor, attrs: ATTR_BOLD };
    case 'entity':
      return {
        fg: ENTITY_TYPE_COLORS[seg.entityType || ''] || theme.colors.npc,
        attrs: ATTR_UNDERLINE,
      };
    case 'normal':
    default:
      return { fg: blockColor };
  }
}

// ── Exported init ───────────────────────────────────────────────

export function initNarrative(container: HTMLElement): NarrativeController {
  const store = new NarrativeStore(container.clientWidth);
  let userAtBottom = true;
  let renderScheduled = false;
  let thinkingBlockId: string | null = null;
  let scrollOffset = 0; // pixels from top
  let hitRegions: HitRegion[] = [];

  // Thinking animation state
  let thinkingDots = 0;
  let thinkingTimer: ReturnType<typeof setInterval> | null = null;

  // Create canvas
  container.innerHTML = '';
  const canvas = document.createElement('canvas');
  canvas.style.display = 'block';
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.cursor = 'default';
  container.appendChild(canvas);

  // Disable the scrollable overflow on the container since we handle scroll ourselves
  container.style.overflowY = 'hidden';

  const maybeCtx = canvas.getContext('2d');
  if (!maybeCtx) throw new Error('Narrative: failed to get 2d context');
  const ctx: CanvasRenderingContext2D = maybeCtx;

  const charSize = measureChar(ctx, MONO_FONT);

  // ── Caches ───────────────────────────────────────────────────
  // Maps block id -> parsed segments so we don't re-parse each frame
  const segmentCache = new Map<string, StyledSegment[]>();
  // Maps block id -> placed segments at current column width
  const layoutCache = new Map<string, { cols: number; placed: PlacedSegment[] }>();

  // ── Sizing ──────────────────────────────────────────────────

  let canvasW = 0;
  let canvasH = 0;
  let cols = 0;

  function resize(): void {
    const rect = container.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const dpr = window.devicePixelRatio || 1;
    canvasW = rect.width;
    canvasH = rect.height;

    canvas.width = Math.floor(canvasW * dpr);
    canvas.height = Math.floor(canvasH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    cols = Math.floor(canvasW / charSize.width);

    // Remeasure store and repaint
    store.remeasure(container.clientWidth);
    clampScroll();
    scheduleRender();
  }

  const resizeObserver = new ResizeObserver(() => resize());
  resizeObserver.observe(container);
  resize();

  // ── Scrolling ─────────────────────────────────────────────

  function clampScroll(): void {
    const maxScroll = Math.max(0, store.totalHeight - canvasH);
    scrollOffset = Math.max(0, Math.min(scrollOffset, maxScroll));
  }

  function scrollToBottom(): void {
    scrollOffset = Math.max(0, store.totalHeight - canvasH);
  }

  canvas.addEventListener('wheel', (e: WheelEvent) => {
    e.preventDefault();
    scrollOffset += e.deltaY;
    clampScroll();

    // Check if user is at bottom (within 30px tolerance)
    const maxScroll = Math.max(0, store.totalHeight - canvasH);
    userAtBottom = scrollOffset >= maxScroll - 30;

    scheduleRender();
  }, { passive: false });

  // ── Render loop ───────────────────────────────────────────

  function scheduleRender(): void {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      renderVisible();
    });
  }

  /**
   * Word-wrap and lay out styled segments into placed segments for a block.
   * Returns an array of PlacedSegments with col/row coordinates relative
   * to the block's top-left.
   */
  function layoutBlock(blockId: string, blockText: string, blockType: string): PlacedSegment[] {
    // Return cached layout if cols haven't changed (and not a thinking block)
    const cached = layoutCache.get(blockId);
    if (cached && cached.cols === cols && blockType !== 'thinking') {
      return cached.placed;
    }

    const blockColor = BLOCK_TYPE_COLORS[blockType] || theme.colors.primary;
    const padding = 2; // 2 chars of left padding
    const maxCol = Math.max(cols - padding * 2, 10);

    // Divider: draw a horizontal rule
    if (blockType === 'divider') {
      const rule = '\u2500'.repeat(Math.min(maxCol, cols - padding * 2));
      return [{ text: rule, col: padding, row: 0, fg: theme.colors.dim }];
    }

    // NPC name header: bold gold with diamond marker — clickable
    if (blockType === 'npc-name') {
      return [{ text: `\u25C6 ${blockText}`, col: padding, row: 0, fg: theme.colors.npc, attrs: ATTR_BOLD | ATTR_UNDERLINE, npcName: blockText }];
    }

    // NPC dialogue: indented, italic, with left bar
    if (blockType === 'npc-dialogue') {
      const dialogPadding = padding + 2;
      const dialogMaxCol = Math.max(cols - dialogPadding - padding, 10);
      const words = blockText.split(' ');
      const placed: PlacedSegment[] = [];
      let col = dialogPadding;
      let row = 0;
      // Draw left accent bar
      for (let r = 0; r < 20; r++) { // will be trimmed to actual rows
        placed.push({ text: '\u2502', col: padding, row: r, fg: theme.colors.npc });
      }
      for (const word of words) {
        if (col + word.length > dialogPadding + dialogMaxCol && col > dialogPadding) {
          row++;
          col = dialogPadding;
        }
        placed.push({ text: word + ' ', col, row, fg: theme.colors.npc, attrs: 2 }); // ATTR_ITALIC
        col += word.length + 1;
      }
      // Trim bar to actual row count
      const actualRows = row + 1;
      return placed.filter(p => !(p.text === '\u2502' && p.row >= actualRows));
    }

    // Get or compute segments
    let segments = segmentCache.get(blockId);
    if (!segments) {
      if (blockType === 'thinking') {
        const dots = '.'.repeat(thinkingDots % 4);
        segments = [{ text: `The world responds${dots}`, style: 'normal' as const }];
      } else if (blockType === 'player-action' || blockType === 'system') {
        segments = [{ text: blockText, style: 'normal' as const }];
      } else {
        segments = parseNarrative(blockText);
      }
      // Don't cache thinking blocks (they animate)
      if (blockType !== 'thinking') {
        segmentCache.set(blockId, segments);
      }
    }

    const placed: PlacedSegment[] = [];
    let col = padding;
    let row = 0;

    for (const seg of segments) {
      const { fg, attrs } = segmentColor(seg, blockColor);
      // Split segment text by newlines first
      const lines = seg.text.split('\n');

      for (let li = 0; li < lines.length; li++) {
        if (li > 0) {
          // Explicit newline: advance to next row
          col = padding;
          row++;
        }

        const words = lines[li].split(/( +)/); // preserve spaces as separate tokens
        for (const word of words) {
          if (!word) continue;

          // If this word would overflow, wrap
          if (col + word.length > padding + maxCol && col > padding) {
            col = padding;
            row++;
          }

          // If single word is longer than maxCol, break it
          if (word.length > maxCol) {
            let pos = 0;
            while (pos < word.length) {
              const chunk = word.slice(pos, pos + maxCol - (col - padding));
              placed.push({
                text: chunk,
                col,
                row,
                fg,
                attrs,
                entityId: seg.entityId,
                entityName: seg.style === 'entity' ? seg.text : undefined,
              });
              col += chunk.length;
              pos += chunk.length;
              if (pos < word.length) {
                col = padding;
                row++;
              }
            }
          } else {
            placed.push({
              text: word,
              col,
              row,
              fg,
              attrs,
              entityId: seg.entityId,
              entityName: seg.style === 'entity' ? seg.text : undefined,
            });
            col += word.length;
          }
        }
      }
    }

    // Cache the layout (skip thinking blocks since they animate)
    if (blockType !== 'thinking') {
      layoutCache.set(blockId, { cols, placed });
    }

    return placed;
  }

  function renderVisible(): void {
    // Clear canvas
    ctx.clearRect(0, 0, canvasW, canvasH);

    // Fill background
    ctx.fillStyle = theme.colors.bg;
    ctx.fillRect(0, 0, canvasW, canvasH);

    if (store.length === 0) return;

    const { start, end } = store.getVisibleRange(scrollOffset, canvasH);
    hitRegions = [];

    for (let i = start; i < end; i++) {
      const block = store.getBlock(i);
      if (!block) continue;

      // Block's Y position on screen (pixels)
      const blockScreenY = block.y - scrollOffset;

      // Skip if entirely off-screen (safety check)
      if (blockScreenY + block.height < 0 || blockScreenY > canvasH) continue;

      const placed = layoutBlock(block.id, block.text, block.type);

      for (const seg of placed) {
        // Convert segment row to pixel Y, then to canvas row
        const segPixelY = blockScreenY + seg.row * charSize.height;

        // Skip segments that are off-screen
        if (segPixelY + charSize.height < 0 || segPixelY > canvasH) continue;

        // Draw using pixel-based positioning (not grid rows) for sub-row precision
        drawTextAtPixel(ctx, seg.col, segPixelY, seg.text, seg.fg, charSize, seg.attrs);

        // Register hit region for entity segments
        if (seg.entityId) {
          hitRegions.push({
            x: seg.col * charSize.width,
            y: segPixelY,
            w: seg.text.length * charSize.width,
            h: charSize.height,
            entityId: seg.entityId,
            entityName: seg.entityName || seg.text,
          });
        }

        // Register hit region for clickable NPC name blocks
        if (seg.npcName) {
          hitRegions.push({
            x: seg.col * charSize.width,
            y: segPixelY,
            w: seg.text.length * charSize.width,
            h: charSize.height,
            npcName: seg.npcName,
          });
        }
      }
    }
  }

  /**
   * Draw text at a pixel Y position (not grid row).
   * Similar to drawText but takes pixelY directly for smooth sub-row scrolling.
   */
  function drawTextAtPixel(
    ctx: CanvasRenderingContext2D,
    col: number,
    pixelY: number,
    text: string,
    fg: string,
    cs: CharSize,
    attrs?: number,
  ): void {
    ctx.font = fontForAttrs(MONO_FONT, attrs);
    ctx.fillStyle = fg;
    ctx.textBaseline = 'top';
    ctx.textAlign = 'left';

    const yOffset = (cs.height - 13) * 0.35;

    for (let i = 0; i < text.length; i++) {
      const px = (col + i) * cs.width;
      ctx.fillText(text[i], px, pixelY + yOffset);
    }

    // Underline for entity links
    if (attrs && (attrs & ATTR_UNDERLINE)) {
      ctx.strokeStyle = fg;
      ctx.lineWidth = 1;
      const underY = pixelY + cs.height - 2;
      const startX = col * cs.width;
      ctx.beginPath();
      ctx.moveTo(startX, underY);
      ctx.lineTo(startX + text.length * cs.width, underY);
      ctx.stroke();
    }
  }

  // ── Click handling ────────────────────────────────────────

  canvas.addEventListener('click', (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const region of hitRegions) {
      if (mx >= region.x && mx < region.x + region.w &&
          my >= region.y && my < region.y + region.h) {
        if (region.npcName) {
          canvas.dispatchEvent(new CustomEvent('npc-name-click', {
            detail: { npcName: region.npcName },
            bubbles: true,
          }));
        } else {
          canvas.dispatchEvent(new CustomEvent('narrative-entity-click', {
            detail: { entityId: region.entityId, entityName: region.entityName },
            bubbles: true,
          }));
        }
        return;
      }
    }
  });

  // Cursor change on hover over entity regions
  canvas.addEventListener('mousemove', (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let overEntity = false;
    for (const region of hitRegions) {
      if (mx >= region.x && mx < region.x + region.w &&
          my >= region.y && my < region.y + region.h) {
        overEntity = true;
        break;
      }
    }
    canvas.style.cursor = overEntity ? 'pointer' : 'default';
  });

  // ── Block management ──────────────────────────────────────

  /** Track named blocks for replace/remove by custom ID */
  const namedBlockIds: Map<string, string> = new Map();

  function addBlockInternal(text: string, type: string, customId?: string): string {
    // Store still needs html field — pass empty string since we render via canvas
    const block = store.add(text, '', type);

    // Track custom ID mapping
    if (customId) {
      namedBlockIds.set(customId, block.id);
    }

    // Auto-scroll to bottom if user was at bottom
    if (userAtBottom) {
      requestAnimationFrame(() => {
        scrollToBottom();
        scheduleRender();
      });
    }

    scheduleRender();
    return block.id;
  }

  function removeNamedBlock(customId: string): void {
    const blockId = namedBlockIds.get(customId);
    if (blockId) {
      segmentCache.delete(blockId);
      layoutCache.delete(blockId);
      store.removeById(blockId);
      namedBlockIds.delete(customId);
    }
  }

  // ── Thinking animation ────────────────────────────────────

  function startThinkingAnimation(): void {
    if (thinkingTimer) return;
    thinkingDots = 0;
    thinkingTimer = setInterval(() => {
      thinkingDots = (thinkingDots + 1) % 4;
      // Invalidate the thinking segment cache to re-render with new dot count
      if (thinkingBlockId) segmentCache.delete(thinkingBlockId);
      scheduleRender();
    }, 500);
  }

  function stopThinkingAnimation(): void {
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
  }

  // ── Round phase dividers ──────────────────────────────────

  let lastPhase = '';
  onRoundStateChange((rs: RoundState) => {
    if (rs.phase === 'resolving' && lastPhase !== 'resolving') {
      addBlockInternal('', 'divider');
    }
    lastPhase = rs.phase;
  });

  // ── Public interface ──────────────────────────────────────

  return {
    addBlock(text: string, type: string) {
      addBlockInternal(text, type);
    },

    addHtml(html: string, type: string) {
      // Extract plain text from HTML for measurement and canvas rendering
      const temp = document.createElement('div');
      temp.innerHTML = html;
      const text = temp.textContent || temp.innerText || html;
      addBlockInternal(text, type);
    },

    replaceBlock(id: string, text: string, type: string) {
      removeNamedBlock(id);
      addBlockInternal(text, type, id);
    },

    removeBlockById(id: string) {
      removeNamedBlock(id);
      clampScroll();
      scheduleRender();
    },

    showThinking() {
      thinkingBlockId = addBlockInternal('The world responds', 'thinking');
      startThinkingAnimation();
    },

    removeThinking() {
      stopThinkingAnimation();
      if (thinkingBlockId) {
        segmentCache.delete(thinkingBlockId);
        layoutCache.delete(thinkingBlockId);
        store.removeById(thinkingBlockId);
        thinkingBlockId = null;
        clampScroll();
        scheduleRender();
      }
    },

    scroll(deltaY: number) {
      scrollOffset += deltaY;
      clampScroll();
      const maxScroll = Math.max(0, store.totalHeight - canvasH);
      userAtBottom = scrollOffset >= maxScroll - 30;
      scheduleRender();
    },

    canvas,
  };
}
