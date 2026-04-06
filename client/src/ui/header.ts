// client/src/ui/header.ts
import type { PanelResult } from '../canvas/types';
import { coloredRow } from '../panels/panel-utils';
import { theme } from '../renderer/theme';

export interface WorldTime {
  moon_phase: string;
  moon_icon: string;
  day_name: string;
  day_number: number;
  month: string;
  season: string;
  time_of_day: string;
}

export interface Header {
  el: HTMLElement;
  updateTime(time: WorldTime): void;
}

export function createHeader(): Header {
  const el = document.createElement('div');
  el.className = 'tui-header';
  el.innerHTML = `
    <span class="header-time">
      <span class="header-moon">\u263D</span>
      <span class="header-date">\u2014</span>
    </span>
    <span class="header-title">MEMENTO MORI</span>
  `;

  const moonEl = el.querySelector('.header-moon') as HTMLElement;
  const dateEl = el.querySelector('.header-date') as HTMLElement;

  return {
    el,
    updateTime(time: WorldTime) {
      moonEl.textContent = time.moon_icon;
      dateEl.textContent = `${time.moon_phase}  \u00B7  ${ordinal(time.day_number)} of ${time.month}  \u00B7  ${time.time_of_day}`;
    },
  };
}

export function renderHeader(cols: number, state: { title: string; worldTime?: WorldTime }): PanelResult {
  const titleText = state.title;
  let timeText = '';
  if (state.worldTime) {
    const wt = state.worldTime;
    timeText = `${wt.moon_icon} ${wt.moon_phase}  ·  ${ordinal(wt.day_number)} of ${wt.month}  ·  ${wt.time_of_day}`;
  }

  // Build: [title left] [spaces] [time right]
  const spacerLen = Math.max(1, cols - titleText.length - timeText.length);
  const spacer = ' '.repeat(spacerLen);

  const segments: Array<{ text: string; fg: string }> = [
    { text: titleText, fg: theme.colors.npc },
    { text: spacer, fg: theme.colors.primary },
  ];
  if (timeText) {
    segments.push({ text: timeText, fg: theme.colors.dim });
  }

  return { cells: [coloredRow(segments, cols)] };
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}
