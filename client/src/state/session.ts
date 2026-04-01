// src/state/session.ts
/** Session management — auth, WebSocket connection, player identity. */

export interface Session {
  playerId: string;
  sessionId: string;
  playerName: string;
  connected: boolean;
}

export function createSession(): Session {
  return {
    playerId: '',
    sessionId: '',
    playerName: '',
    connected: false,
  };
}
