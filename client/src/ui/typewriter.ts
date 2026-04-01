import { prepareWithSegments, layoutNextLine, type LayoutCursor } from '@chenglou/pretext';

export interface TypewriterController {
  start(): void;
  skip(): void;
  cancel(): void;
  onComplete(cb: () => void): void;
}

export interface TypewriterOptions {
  text: string;
  font: string;
  maxWidth: number;
  container: HTMLElement;
  charDelay?: number;       // ms per character, default 25
  lineClass?: string;       // CSS class for each line div
  cursorClass?: string;     // CSS class for the blinking cursor span
}

export function createTypewriter(opts: TypewriterOptions): TypewriterController {
  const {
    text,
    font,
    maxWidth,
    container,
    charDelay = 25,
    lineClass = 'tw-line',
    cursorClass = 'tw-cursor',
  } = opts;

  let completeCb: (() => void) | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;
  let started = false;

  // Pretext line-breaking
  const prepared = prepareWithSegments(text, font);
  const lines: string[] = [];
  let cursor: LayoutCursor = { segmentIndex: 0, graphemeIndex: 0 };
  while (true) {
    const line = layoutNextLine(prepared, cursor, maxWidth);
    if (!line) break;
    lines.push(line.text);
    cursor = line.end;
  }

  // State
  let lineIdx = 0;
  let charIdx = 0;
  let currentLineEl: HTMLElement | null = null;
  let cursorEl: HTMLElement | null = null;

  function ensureCursor() {
    if (!cursorEl) {
      cursorEl = document.createElement('span');
      cursorEl.className = cursorClass;
      cursorEl.textContent = '\u2588'; // full block cursor
    }
    return cursorEl;
  }

  function tick() {
    if (cancelled || lineIdx >= lines.length) {
      finish();
      return;
    }

    // Start a new line
    if (!currentLineEl) {
      currentLineEl = document.createElement('div');
      currentLineEl.className = lineClass;
      container.appendChild(currentLineEl);
    }

    // Reveal next character
    const line = lines[lineIdx];
    if (charIdx < line.length) {
      // Remove cursor, add char, re-add cursor
      ensureCursor().remove();
      currentLineEl.textContent = line.slice(0, charIdx + 1);
      currentLineEl.appendChild(ensureCursor());
      charIdx++;
      timer = setTimeout(tick, charDelay);
    } else {
      // Line complete — move to next
      ensureCursor().remove();
      lineIdx++;
      charIdx = 0;
      currentLineEl = null;
      timer = setTimeout(tick, charDelay);
    }
  }

  function finish() {
    if (cursorEl) cursorEl.remove();
    cursorEl = null;
    if (completeCb) completeCb();
  }

  function showAll() {
    if (timer) clearTimeout(timer);
    container.innerHTML = '';
    for (const line of lines) {
      const div = document.createElement('div');
      div.className = lineClass;
      div.textContent = line;
      container.appendChild(div);
    }
    finish();
  }

  return {
    start() {
      if (started) return;
      started = true;
      container.innerHTML = '';
      tick();
    },
    skip() {
      if (cancelled) return;
      showAll();
    },
    cancel() {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (cursorEl) cursorEl.remove();
    },
    onComplete(cb: () => void) {
      completeCb = cb;
    },
  };
}
