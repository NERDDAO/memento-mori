export interface WindowOptions {
  title: string;
  id?: string;
  className?: string;
  scrollable?: boolean;
}

export interface Window {
  el: HTMLElement;
  body: HTMLElement;
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

  const titleBar = document.createElement('div');
  titleBar.className = 'win-title';
  titleBar.textContent = `\u2500 ${opts.title} \u2500`;

  const body = document.createElement('div');
  body.className = 'win-body';
  if (opts.scrollable) body.style.overflowY = 'auto';

  el.appendChild(titleBar);
  el.appendChild(body);

  return {
    el,
    body,
    setTitle(title: string) {
      titleBar.textContent = `\u2500 ${title} \u2500`;
    },
    show() { el.style.display = ''; },
    hide() { el.style.display = 'none'; },
    toggle() { el.style.display = el.style.display === 'none' ? '' : 'none'; },
    get visible() { return el.style.display !== 'none'; },
  };
}
