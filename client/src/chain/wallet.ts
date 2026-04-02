// client/src/chain/wallet.ts
/**
 * Wallet connection via EIP-1193 (window.ethereum).
 * No library dependencies — raw provider API.
 */

declare global {
  interface Window {
    ethereum?: {
      request(args: { method: string; params?: unknown[] }): Promise<unknown>;
      on(event: string, handler: (...args: unknown[]) => void): void;
      removeListener(event: string, handler: (...args: unknown[]) => void): void;
    };
  }
}

let connectedAddress: string | null = null;

export function hasProvider(): boolean {
  return typeof window.ethereum !== 'undefined';
}

export async function connectWallet(): Promise<string> {
  if (!window.ethereum) {
    throw new Error('No wallet provider found');
  }
  const accounts = (await window.ethereum.request({
    method: 'eth_requestAccounts',
  })) as string[];
  if (!accounts.length) {
    throw new Error('No accounts returned');
  }
  connectedAddress = accounts[0];
  localStorage.setItem('mm_wallet', connectedAddress);
  return connectedAddress;
}

export function getAddress(): string | null {
  if (connectedAddress) return connectedAddress;
  return localStorage.getItem('mm_wallet');
}

export function formatAddress(addr: string): string {
  if (addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
