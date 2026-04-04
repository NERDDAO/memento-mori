// src/ui/status.ts
/**
 * Status bar — round phase indicator (left), chain status (center), tick (right).
 */

import { onRoundStateChange, type RoundState } from '../state/round-state';

export interface StatusBar {
  el: HTMLElement;
  setChain(connected: boolean): void;
  setTick(tick: number): void;
  setActivity(text: string): void;
}

export function createStatusBar(): StatusBar {
  const el = document.createElement('div');
  el.className = 'status-bar';
  el.innerHTML = `
    <span class="status-phase">\u2713 Ready</span>
    <span class="status-activity"></span>
    <span class="status-chain">\u25C7 Redstone: offline</span>
    <span class="status-tick">\u263D Tick 0</span>
  `;

  const phaseEl = el.querySelector('.status-phase') as HTMLElement;
  const activityEl = el.querySelector('.status-activity') as HTMLElement;
  const chainEl = el.querySelector('.status-chain') as HTMLElement;
  const tickEl = el.querySelector('.status-tick') as HTMLElement;
  let activityTimer: ReturnType<typeof setTimeout> | null = null;

  function renderPhase(rs: RoundState): void {
    switch (rs.phase) {
      case 'ready':
        phaseEl.textContent = rs.location
          ? `\u2713 Ready \u00B7 ${rs.location}`
          : '\u2713 Ready';
        phaseEl.className = 'status-phase ready';
        break;
      case 'collecting': {
        const count = rs.actionCount ?? 0;
        const timer = rs.secondsLeft != null ? ` (${rs.secondsLeft}s)` : '';
        phaseEl.textContent = `\u27F3 Collecting \u00B7 ${count} action${count !== 1 ? 's' : ''}${timer}`;
        phaseEl.className = 'status-phase collecting';
        break;
      }
      case 'resolving': {
        const crewLabel = rs.crew
          ? rs.crew.charAt(0).toUpperCase() + rs.crew.slice(1).replace('_', '-')
          : '';
        phaseEl.textContent = crewLabel
          ? `\u27F3 Resolving \u00B7 ${crewLabel}`
          : '\u27F3 Resolving';
        phaseEl.className = 'status-phase resolving';
        break;
      }
      case 'npc_response':
        phaseEl.textContent = '\u27F3 NPCs Responding';
        phaseEl.className = 'status-phase npc-response';
        break;
    }
  }

  onRoundStateChange(renderPhase);

  return {
    el,
    setChain(connected: boolean) {
      chainEl.textContent = connected
        ? '\u25C6 Redstone: synced'
        : '\u25C7 Redstone: offline';
      chainEl.className = `status-chain ${connected ? 'connected' : ''}`;
    },
    setTick(tick: number) {
      tickEl.textContent = `\u263D Tick ${tick}`;
    },
    setActivity(text: string) {
      if (activityTimer) clearTimeout(activityTimer);
      if (text) {
        activityEl.textContent = `\u2728 ${text}`;
        activityEl.style.color = '#8b5cf6';
        // Auto-clear after 5 seconds
        activityTimer = setTimeout(() => {
          activityEl.textContent = '';
          activityTimer = null;
        }, 5000);
      } else {
        activityEl.textContent = '';
      }
    },
  };
}
