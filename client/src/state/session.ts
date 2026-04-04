// src/state/session.ts
/** Session management — auth, WebSocket connection, player identity. */

const GATEWAY_PORT = window.location.port || '8081';
export const GATEWAY_URL = `${window.location.protocol}//${window.location.hostname}:${GATEWAY_PORT}`;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:${GATEWAY_PORT}/ws`;

export interface Session {
  playerId: string;
  sessionId: string;
  playerName: string;
  walletAddress: string;
  currentLocation: string;
  connected: boolean;
  openingNarrative: string;
}

const session: Session = {
  playerId: '',
  sessionId: '',
  playerName: '',
  walletAddress: '',
  currentLocation: '',
  connected: false,
  openingNarrative: '',
};

let ws: WebSocket | null = null;
let onMessage: ((msg: any) => void) | null = null;
let onConnectionChange: ((connected: boolean) => void) | null = null;

export function setConnectionHandler(handler: (connected: boolean) => void): void {
  onConnectionChange = handler;
}

export function getSession(): Session {
  return session;
}

export function setMessageHandler(handler: (msg: any) => void): void {
  onMessage = handler;
}

export interface SessionCreateResponse {
  player_id: string;
  session_id: string;
  location: string;
  opening_narrative?: string;
  archetype?: string;
  health?: number;
  max_health?: number;
  skills?: Record<string, number>;
  inventory?: string[];
  room_map?: any;
}

export async function initSession(playerName: string, walletAddress: string, archetype: string = ''): Promise<SessionCreateResponse> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName, wallet_address: walletAddress, archetype }),
  });
  const data: SessionCreateResponse = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', playerName);
  localStorage.setItem('mm_wallet', walletAddress);

  connectWebSocket();
  return data;
}

export async function joinSession(playerId: string): Promise<SessionCreateResponse> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId }),
  });
  const data: SessionCreateResponse = await resp.json();

  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.currentLocation = data.location;

  localStorage.setItem('mm_player_id', session.playerId);

  connectWebSocket();
  return data;
}

function connectWebSocket(): void {
  ws = new WebSocket(`${WS_URL}/${session.playerId}`);
  ws.onopen = () => {
    session.connected = true;
    onConnectionChange?.(true);
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (onMessage) onMessage(msg);
  };
  ws.onclose = () => {
    session.connected = false;
    onConnectionChange?.(false);
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
