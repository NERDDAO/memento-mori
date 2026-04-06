// src/ui/status.ts
/**
 * Status bar — round phase indicator (left), chain status (center), tick (right).
 */

import { onRoundStateChange, type RoundState } from '../state/round-state';
import type { PanelResult } from '../canvas/types';
import { coloredRow } from '../panels/panel-utils';
import { theme } from '../renderer/theme';

export interface StatusState {
  phase: string;
  tick: number;
  chain: boolean;
  activity: string;
  location: string;
}

export function renderStatusBar(cols: number, state: StatusState): PanelResult {
  // Left: phase + optional activity
  let phaseText: string;
  switch (state.phase) {
    case 'ready':
      phaseText = state.location ? `✓ Ready · ${state.location}` : '✓ Ready';
      break;
    case 'collecting':
      phaseText = `⟳ Collecting · ${state.tick}s`;
      break;
    case 'resolving':
      phaseText = '⟳ Resolving';
      break;
    case 'npc_response':
      phaseText = '⟳ NPCs Responding';
      break;
    default:
      phaseText = state.phase;
  }
  if (state.activity) {
    phaseText += `  ✨ ${state.activity}`;
  }

  // Center: chain status
  const chainText = state.chain ? '◆ Redstone: synced' : '◇ Redstone: offline';
  const chainColor = state.chain ? theme.colors.heal : theme.colors.dim;

  // Right: tick counter
  const tickText = `☽ Tick ${state.tick}`;

  // Layout: left | center padded | right
  const innerSpace = cols - phaseText.length - chainText.length - tickText.length;
  const leftPad = Math.max(1, Math.floor(innerSpace / 2));
  const rightPad = Math.max(1, innerSpace - leftPad);

  const segments: Array<{ text: string; fg: string }> = [
    { text: phaseText, fg: theme.colors.system },
    { text: ' '.repeat(leftPad), fg: theme.colors.primary },
    { text: chainText, fg: chainColor },
    { text: ' '.repeat(rightPad), fg: theme.colors.primary },
    { text: tickText, fg: theme.colors.dim },
  ];

  return { cells: [coloredRow(segments, cols)] };
}

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
