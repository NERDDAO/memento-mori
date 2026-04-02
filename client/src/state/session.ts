// src/state/session.ts
/** Session management — auth, WebSocket connection, x402 payment, player identity. */

import { sendPayment, waitForTransaction, signMessage } from '../chain/wallet';

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
  token: string;
}

const session: Session = {
  playerId: '',
  sessionId: '',
  playerName: '',
  walletAddress: '',
  currentLocation: '',
  connected: false,
  openingNarrative: '',
  token: '',
};

let ws: WebSocket | null = null;
let onMessage: ((msg: any) => void) | null = null;
let onConnectionChange: ((connected: boolean) => void) | null = null;
let onPaymentRequired: ((payment: any) => void) | null = null;

export function setConnectionHandler(handler: (connected: boolean) => void): void {
  onConnectionChange = handler;
}

export function setPaymentHandler(handler: (payment: any) => void): void {
  onPaymentRequired = handler;
}

export function getSession(): Session {
  return session;
}

export function setMessageHandler(handler: (msg: any) => void): void {
  onMessage = handler;
}

/** Build headers with session token if available. */
function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (session.token) h['Authorization'] = `Bearer ${session.token}`;
  return h;
}

/**
 * Handle a 402 Payment Required response.
 * Prompts wallet to send USDC, waits for confirmation, retries with receipt.
 */
async function handlePaymentRequired(
  resp: Response,
  retryFn: (receiptHeader: string) => Promise<Response>,
): Promise<Response> {
  const data = await resp.json();
  const payment = data.payment;
  if (!payment) throw new Error('Invalid 402 response — no payment instructions');

  // Notify UI about payment
  if (onPaymentRequired) onPaymentRequired(payment);

  // Send payment via wallet
  const txHash = await sendPayment(payment.recipient, payment.amount, payment.asset);
  await waitForTransaction(txHash);

  // Retry with receipt
  return retryFn(txHash);
}

export async function initSession(playerName: string, walletAddress: string, archetype: string = ''): Promise<Session> {
  const body = JSON.stringify({ player_name: playerName, wallet_address: walletAddress, archetype });

  const makeRequest = (receiptHeader?: string) => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (receiptHeader) headers['X-Payment-Receipt'] = receiptHeader;
    return fetch(`${GATEWAY_URL}/api/session/create`, { method: 'POST', headers, body });
  };

  let resp = await makeRequest();

  if (resp.status === 402) {
    resp = await handlePaymentRequired(resp, (receipt) => makeRequest(receipt));
  }

  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || '';
  session.token = data.session_token || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', playerName);
  localStorage.setItem('mm_wallet', walletAddress);
  localStorage.setItem('mm_token', session.token);

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
  // Resume uses wallet signature (not payment) to prove ownership
  const signMsg = `Memento Mori: resume ${playerId} at ${Date.now()}`;
  let sig = '';
  try {
    sig = await signMessage(signMsg);
  } catch {
    // Signature declined — can't resume
    throw new Error('Wallet signature required to resume');
  }

  const resp = await fetch(`${GATEWAY_URL}/api/session/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_id: playerId,
      wallet_address: walletAddress,
      signature: sig,
      sign_message: signMsg,
    }),
  });

  if (resp.status === 401) {
    const err = await resp.json();
    throw new Error(err.message || 'Authentication failed');
  }

  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = data.player_name;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = '';
  session.token = data.session_token || '';

  localStorage.setItem('mm_player_id', session.playerId);
  localStorage.setItem('mm_player_name', session.playerName);
  localStorage.setItem('mm_wallet', walletAddress);
  localStorage.setItem('mm_token', session.token);

  connectWebSocket();
  return session;
}

export async function sendAction(action: string): Promise<void> {
  await fetch(`${GATEWAY_URL}/api/action`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      player_id: session.playerId,
      action: action,
      location: session.currentLocation,
    }),
  });
}
