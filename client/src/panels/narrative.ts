// src/panels/narrative.ts
import { parseNarrative, renderSegments } from '../renderer/text-renderer';
import { NarrativeStore } from '../renderer/line-cache';
import { onRoundStateChange, type RoundState } from '../state/round-state';

export interface NarrativeController {
  addBlock(text: string, type: string): void;
  addHtml(html: string, type: string): void;
  showThinking(): void;
  removeThinking(): void;
}

export function initNarrative(container: HTMLElement): NarrativeController {
  const store = new NarrativeStore(container.clientWidth);
  let userAtBottom = true;
  let renderScheduled = false;
  let thinkingBlockId: string | null = null;

  // Create the virtual scroll container.
  // The "spacer" div sets the total scrollable height.
  // Visible blocks are positioned absolutely within it.
  const spacer = document.createElement('div');
  spacer.style.position = 'relative';
  spacer.style.minHeight = '100%';

  // Clear the container's initial "Connecting..." message
  container.innerHTML = '';
  container.appendChild(spacer);

  // Track scroll position to know if user is at bottom
  container.addEventListener('scroll', () => {
    const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
    userAtBottom = atBottom;
    scheduleRender();
  });

  // Resize observer for remeasurement
  const resizeObserver = new ResizeObserver(() => {
    store.remeasure(container.clientWidth);
    spacer.style.height = `${store.totalHeight}px`;
    scheduleRender();
  });
  resizeObserver.observe(container);

  function scheduleRender(): void {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      renderVisible();
    });
  }

  function renderVisible(): void {
    const scrollTop = container.scrollTop;
    const viewportHeight = container.clientHeight;
    const { start, end } = store.getVisibleRange(scrollTop, viewportHeight);

    // Clear existing block elements (keep spacer itself)
    const existingBlocks = spacer.querySelectorAll('.narrative-block');
    existingBlocks.forEach(el => el.remove());

    // Render only visible blocks
    for (let i = start; i < end; i++) {
      const block = store.getBlock(i);
      if (!block) continue;

      const el = document.createElement('div');
      el.className = `narrative-block ${block.type}`;
      el.style.position = 'absolute';
      el.style.top = `${block.y}px`;
      el.style.left = '0';
      el.style.right = '0';
      el.innerHTML = block.html;
      spacer.appendChild(el);
    }
  }

  function addBlockInternal(text: string, html: string, type: string): string {
    const block = store.add(text, html, type);
    spacer.style.height = `${store.totalHeight}px`;

    // Auto-scroll to bottom if user was at bottom
    if (userAtBottom) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }

    scheduleRender();
    return block.id;
  }

  // Round phase dividers
  let lastPhase = '';
  onRoundStateChange((rs: RoundState) => {
    if (rs.phase === 'resolving' && lastPhase !== 'resolving') {
      addBlockInternal('', '<hr class="round-divider">', 'divider');
    }
    lastPhase = rs.phase;
  });

  return {
    addBlock(text: string, type: string) {
      let html: string;
      if (type === 'thinking') {
        html = 'The world responds';
      } else if (type === 'player-action' || type === 'system') {
        html = text.replace(/\n/g, '<br>')
          .replace(/"([^"]+)"/g, '<span class="npc-name">"$1"</span>');
      } else {
        const segments = parseNarrative(text);
        html = renderSegments(segments);
      }
      addBlockInternal(text, html, type);
    },

    addHtml(html: string, type: string) {
      // Extract plain text from HTML for Pretext measurement
      const temp = document.createElement('div');
      temp.innerHTML = html;
      const text = temp.textContent || temp.innerText || html;
      addBlockInternal(text, html, type);
    },

    showThinking() {
      thinkingBlockId = addBlockInternal('The world responds', 'The world responds', 'thinking');
    },

    removeThinking() {
      if (thinkingBlockId) {
        store.removeById(thinkingBlockId);
        thinkingBlockId = null;
        spacer.style.height = `${store.totalHeight}px`;
        scheduleRender();
      }
    },
  };
}
