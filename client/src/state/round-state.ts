/** Shared round state — components subscribe to phase changes. */

export type Phase = "ready" | "collecting" | "resolving" | "npc_response";

export interface RoundState {
  phase: Phase;
  crew?: string;
  location?: string;
  actionCount?: number;
  deadline?: number;       // unix ms
  secondsLeft?: number;    // computed locally
}

export interface PhaseMessage {
  type: "phase";
  phase: Phase;
  crew?: string;
  location?: string;
  action_count?: number;
  deadline?: number;
}

type RoundListener = (state: RoundState) => void;

const listeners: RoundListener[] = [];
let countdownTimer: ReturnType<typeof setInterval> | null = null;
let safetyTimer: ReturnType<typeof setTimeout> | null = null;

// Safety timeout — force ready if stuck in resolving/npc_response for too long.
const SAFETY_TIMEOUT_MS = 120_000; // 2 minutes

const state: RoundState = {
  phase: "ready",
};

export function getRoundState(): RoundState {
  return state;
}

export function onRoundStateChange(listener: RoundListener): () => void {
  listeners.push(listener);
  return () => {
    const idx = listeners.indexOf(listener);
    if (idx >= 0) listeners.splice(idx, 1);
  };
}

function notify(): void {
  for (const fn of listeners) fn(state);
}

function stopCountdown(): void {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
  state.secondsLeft = undefined;
  state.deadline = undefined;
}

function startCountdown(deadline: number): void {
  stopCountdown();
  state.deadline = deadline;
  state.secondsLeft = Math.ceil((deadline - Date.now()) / 1000);

  countdownTimer = setInterval(() => {
    if (!state.deadline) { stopCountdown(); return; }
    const left = Math.ceil((state.deadline - Date.now()) / 1000);
    state.secondsLeft = Math.max(0, left);
    notify();
  }, 1000);
}

function clearSafetyTimer(): void {
  if (safetyTimer) {
    clearTimeout(safetyTimer);
    safetyTimer = null;
  }
}

function startSafetyTimer(): void {
  clearSafetyTimer();
  safetyTimer = setTimeout(() => {
    safetyTimer = null;
    if (state.phase === "resolving" || state.phase === "npc_response") {
      console.warn(`[round-state] safety timeout — forcing ready (was ${state.phase})`);
      state.phase = "ready";
      state.crew = undefined;
      stopCountdown();
      notify();
    }
  }, SAFETY_TIMEOUT_MS);
}

export function updateRoundState(msg: PhaseMessage): void {
  state.phase = msg.phase;
  state.crew = msg.crew;

  if (msg.location) state.location = msg.location;
  if (msg.action_count != null) state.actionCount = msg.action_count;

  if (msg.phase === "collecting" && msg.deadline) {
    startCountdown(msg.deadline);
  } else if (msg.phase !== "collecting") {
    stopCountdown();
    state.actionCount = undefined;
  }

  // Safety timeout: if we enter a locked phase, start a timer to force ready
  if (msg.phase === "resolving" || msg.phase === "npc_response") {
    startSafetyTimer();
  } else {
    clearSafetyTimer();
  }

  notify();
}
