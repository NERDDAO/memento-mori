// src/state/session.ts
/** Session management — auth, WebSocket connection, player identity. */

// Use relative URLs so the client works behind any reverse proxy (Caddy, nginx)
const GATEWAY_URL = '';
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;

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

export async function initSession(playerName: string, walletAddress: string, archetype: string = ''): Promise<Session> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName, wallet_address: walletAddress, archetype }),
  });
  const data = await resp.json();
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
  return session;
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

export async function fetchExistingPlayers(walletAddress: string): Promise<any[]> {
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/players?wallet=${walletAddress}`);
    return await resp.json();
  } catch {
    return [];
  }
}

export async function resumeSession(playerId: string, walletAddress: string): Promise<Session> {
  const resp = await fetch(`${GATEWAY_URL}/api/session/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId, wallet_address: walletAddress }),
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = data.player_name;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', session.playerName);
  localStorage.setItem('mm_wallet', walletAddress);

  connectWebSocket();
  return session;
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
