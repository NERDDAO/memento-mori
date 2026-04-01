// src/state/session.ts
/** Session management — auth, WebSocket connection, player identity. */

const GATEWAY_URL = 'http://localhost:8080';
const WS_URL = 'ws://localhost:8080/ws';

export interface Session {
  playerId: string;
  sessionId: string;
  playerName: string;
  currentLocation: string;
  connected: boolean;
  openingNarrative: string;
}

const session: Session = {
  playerId: '',
  sessionId: '',
  playerName: '',
  currentLocation: '',
  connected: false,
  openingNarrative: '',
};

let ws: WebSocket | null = null;
let onMessage: ((msg: any) => void) | null = null;

export function getSession(): Session {
  return session;
}

export function setMessageHandler(handler: (msg: any) => void): void {
  onMessage = handler;
}

export async function initSession(playerName: string): Promise<Session> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName }),
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', playerName);

  connectWebSocket();
  return session;
}

function connectWebSocket(): void {
  ws = new WebSocket(`${WS_URL}/${session.playerId}`);
  ws.onopen = () => {
    session.connected = true;
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (onMessage) onMessage(msg);
  };
  ws.onclose = () => {
    session.connected = false;
    setTimeout(() => {
      if (!session.connected) connectWebSocket();
    }, 3000);
  };
}

export async function sendAction(action: string): Promise<void> {
  await fetch(`${GATEWAY_URL}/api/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_id: session.playerId,
      action: action,
      location: session.currentLocation,
    }),
  });
}
