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

/**
 * Sign a message with the connected wallet (for session verification).
 * Returns the signature hex string.
 */
export async function signMessage(message: string): Promise<string> {
  if (!window.ethereum) throw new Error('No wallet provider');
  const from = getAddress();
  if (!from) throw new Error('Wallet not connected');

  const signature = await window.ethereum.request({
    method: 'personal_sign',
    params: [message, from],
  }) as string;

  return signature;
}

/**
 * Send an ERC-20 transfer (for x402 payment).
 * Returns the transaction hash.
 */
export async function sendPayment(
  recipient: string,
  amount: string,
  assetContract: string,
): Promise<string> {
  if (!window.ethereum) throw new Error('No wallet provider');
  const from = getAddress();
  if (!from) throw new Error('Wallet not connected');

  // ERC-20 transfer(address,uint256) function selector
  const transferSelector = '0xa9059cbb';
  // Encode recipient (pad to 32 bytes)
  const encodedRecipient = recipient.toLowerCase().replace('0x', '').padStart(64, '0');
  // Encode amount (hex, pad to 32 bytes)
  const amountHex = BigInt(amount).toString(16).padStart(64, '0');
  const data = transferSelector + encodedRecipient + amountHex;

  const txHash = await window.ethereum.request({
    method: 'eth_sendTransaction',
    params: [{
      from,
      to: assetContract,
      data,
    }],
  }) as string;

  return txHash;
}

/**
 * Wait for a transaction to be confirmed.
 */
export async function waitForTransaction(txHash: string): Promise<void> {
  if (!window.ethereum) return;
  for (let i = 0; i < 30; i++) {
    const receipt = await window.ethereum.request({
      method: 'eth_getTransactionReceipt',
      params: [txHash],
    });
    if (receipt) return;
    await new Promise(r => setTimeout(r, 2000));
  }
  throw new Error('Transaction not confirmed after 60s');
}
