// client/src/ui/header.ts
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

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}
