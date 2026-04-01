// src/panels/narrative.ts
/** Narrative panel — scrolling story text with rich segment rendering. */

import { parseNarrative, renderSegments } from '../renderer/text-renderer';

export interface NarrativeController {
  addBlock(text: string, type: string): void;
  addHtml(html: string, type: string): void;
  showThinking(): void;
  removeThinking(): void;
}

export function initNarrative(container: HTMLElement): NarrativeController {
  return {
    addBlock(text: string, type: string) {
      const block = document.createElement('div');
      block.className = `narrative-block ${type}`;
      if (type === 'thinking') {
        block.textContent = 'The world responds';
      } else if (type === 'player-action') {
        block.innerHTML = text.replace(/\n/g, '<br>');
      } else {
        const segments = parseNarrative(text);
        block.innerHTML = renderSegments(segments);
      }
      container.appendChild(block);
      container.scrollTop = container.scrollHeight;
    },
    addHtml(html: string, type: string) {
      const block = document.createElement('div');
      block.className = `narrative-block ${type}`;
      block.innerHTML = html;
      container.appendChild(block);
      container.scrollTop = container.scrollHeight;
    },
    showThinking() {
      this.addBlock('The world responds', 'thinking');
    },
    removeThinking() {
      const el = container.querySelector('.thinking');
      if (el) el.remove();
    },
  };
}
