import { TerminalPanel } from './terminal-panel';

export interface WindowOptions {
  title: string;
  id?: string;
  className?: string;
  scrollable?: boolean;
  canvas?: boolean;
  /** Skip title bar for seamless unified layout */
  chromeless?: boolean;
}

export interface Window {
  el: HTMLElement;
  body: HTMLElement;
  panel?: TerminalPanel;
  setTitle(title: string): void;
  show(): void;
  hide(): void;
  toggle(): void;
  readonly visible: boolean;
}

export function createWindow(opts: WindowOptions): Window {
  const el = document.createElement('div');
  el.className = `win${opts.className ? ` ${opts.className}` : ''}`;
  if (opts.id) el.id = opts.id;

  let titleBar: HTMLElement | null = null;
  if (!opts.chromeless) {
    titleBar = document.createElement('div');
    titleBar.className = 'win-title';
    titleBar.textContent = `\u2500 ${opts.title} \u2500`;
    el.appendChild(titleBar);
  }

  const body = document.createElement('div');
  body.className = 'win-body';
  if (opts.scrollable) body.style.overflowY = 'auto';
  el.appendChild(body);

  // Create canvas-backed panel when requested
  let panel: TerminalPanel | undefined;
  if (opts.canvas) {
    panel = new TerminalPanel({ container: body });
  }

  return {
    el,
    body,
    panel,
    setTitle(title: string) {
      if (titleBar) titleBar.textContent = `\u2500 ${title} \u2500`;
    },
    show() { el.style.display = ''; },
    hide() { el.style.display = 'none'; },
    toggle() { el.style.display = el.style.display === 'none' ? '' : 'none'; },
    get visible() { return el.style.display !== 'none'; },
  };
}
