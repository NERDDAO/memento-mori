// src/char-creation.ts
/**
 * Character creation flow: wallet connect, archetype selection, name input.
 * Extracted from app.ts — pure UI wiring, no game state mutation.
 */

import { GATEWAY_URL } from './state/session';
import { hasProvider, connectWallet, formatAddress, getAddress } from './chain/wallet';
import { type OverlayManager } from './ui/overlay';

// --- Archetype selection ---
let selectedArchetype = '';

async function loadArchetypes(): Promise<void> {
  const container = document.getElementById('archetype-cards');
  if (!container) return;
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/archetypes`);
    const archetypes = await resp.json();
    container.innerHTML = archetypes.map((a: { name: string; description: string; stats: { health?: number }; skills: Record<string, number>; starting_items: string[] }) => `
      <div class="archetype-card" data-archetype="${a.name}">
        <div class="archetype-name">${a.name}</div>
        <div class="archetype-desc">${a.description}</div>
        <div class="archetype-stats">HP: ${a.stats.health || 100} | Skills: ${Object.keys(a.skills).join(', ')}</div>
        <div class="archetype-items">${a.starting_items.join(', ')}</div>
      </div>
    `).join('');
    container.addEventListener('click', (e: MouseEvent) => {
      const card = (e.target as HTMLElement).closest('.archetype-card') as HTMLElement | null;
      if (!card) return;
      container.querySelectorAll('.archetype-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedArchetype = card.dataset.archetype || '';
    });
  } catch {
    // Fallback — no archetype selection available
    container.innerHTML = '<div style="color:var(--text-dim)">Archetypes unavailable</div>';
  }
}

// --- Character picker (returning players) ---
interface CharacterSummary {
  player_id: string;
  player_name: string;
  archetype?: string;
  health?: number;
  is_dead?: boolean;
  death_cause?: string;
  death_location?: string;
}

function showCharacterPicker(
  characters: CharacterSummary[],
  walletAddress: string,
  overlays: OverlayManager,
  enterGame: (config: { playerName: string; walletAddress: string; isReturning: boolean; playerId?: string; archetype?: string }) => void,
): void {
  const walletStepEl = document.getElementById('wallet-step')!;
  const pickerDiv = document.createElement('div');
  pickerDiv.id = 'char-picker';

  const alive = characters.filter((c: CharacterSummary) => !c.is_dead);
  const dead = characters.filter((c: CharacterSummary) => c.is_dead);

  let html = '<div class="picker-title">Your Characters</div>';

  // Living characters
  for (const c of alive) {
    html += `
      <div class="picker-card" data-player-id="${c.player_id}">
        <span class="picker-name">${c.player_name}</span>
        <span class="picker-info">${c.archetype || 'Unknown'} \u00B7 HP ${c.health}</span>
      </div>`;
  }

  // Memorial (dead) characters
  for (const c of dead) {
    html += `
      <div class="picker-card picker-memorial">
        <span class="picker-name">\u2620 ${c.player_name}</span>
        <span class="picker-info">${c.death_cause || 'Perished'} \u00B7 Fell at ${c.death_location || 'unknown'}</span>
      </div>`;
  }

  html += `
    <div class="picker-card picker-new">
      <span class="picker-name">+ New Character</span>
    </div>`;

  pickerDiv.innerHTML = html;
  walletStepEl.after(pickerDiv);

  pickerDiv.addEventListener('click', (e: MouseEvent) => {
    const card = (e.target as HTMLElement).closest('.picker-card') as HTMLElement | null;
    if (!card || card.classList.contains('picker-memorial')) return;
    if (card.classList.contains('picker-new')) {
      pickerDiv.remove();
      const archStep = document.getElementById('archetype-step');
      if (archStep) {
        archStep.classList.remove('hidden');
        loadArchetypes();
      } else {
        document.getElementById('name-step')!.classList.remove('hidden');
      }
    } else {
      const playerId = card.dataset.playerId!;
      const playerName = card.querySelector('.picker-name')!.textContent || 'Wanderer';
      pickerDiv.remove();
      overlays.dismiss('char-create');
      enterGame({ playerName, walletAddress, isReturning: true, playerId });
    }
  });
}

// --- Public entry point ---
export function initCharCreation(
  enterGame: (config: { playerName: string; walletAddress: string; isReturning: boolean; playerId?: string; archetype?: string }) => void,
  overlays: OverlayManager,
): void {
  const walletConnectBtn = document.getElementById('wallet-connect-btn')!;
  const walletStep = document.getElementById('wallet-step')!;
  const nameStep = document.getElementById('name-step')!;
  const walletPrompt = document.getElementById('wallet-prompt')!;
  const walletNoProvider = document.getElementById('wallet-no-provider')!;
  const walletAddressEl = document.getElementById('wallet-address')!;
  const nameInput = document.getElementById('char-name-input') as HTMLInputElement;
  const enterBtn = document.getElementById('char-create-btn')!;

  // Check for wallet provider on load
  if (!hasProvider()) {
    walletConnectBtn.classList.add('hidden');
    walletNoProvider.classList.remove('hidden');
  }

  const archetypeStep = document.getElementById('archetype-step');

  walletConnectBtn.addEventListener('click', async () => {
    try {
      walletPrompt.textContent = 'Connecting...';
      const addr = await connectWallet();
      walletStep.classList.add('hidden');
      walletAddressEl.textContent = `\u2713 ${formatAddress(addr)}`;

      // Check for existing characters
      try {
        const charResp = await fetch(`${GATEWAY_URL}/api/session/characters`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet_address: addr }),
        });
        const charData = await charResp.json();
        if (charData.characters && charData.characters.length > 0) {
          showCharacterPicker(charData.characters, addr, overlays, enterGame);
          return;
        }
      } catch { /* no existing characters, proceed to creation */ }

      // No existing characters — proceed to archetype/name selection
      if (archetypeStep) {
        archetypeStep.classList.remove('hidden');
        loadArchetypes();
      } else {
        nameStep.classList.remove('hidden');
        nameInput.focus();
      }
    } catch {
      walletPrompt.textContent = 'Connection rejected. Try again.';
    }
  });

  // Archetype -> Name step transition
  const archetypeNextBtn = document.getElementById('archetype-next-btn');
  if (archetypeNextBtn) {
    archetypeNextBtn.addEventListener('click', () => {
      if (archetypeStep) archetypeStep.classList.add('hidden');
      nameStep.classList.remove('hidden');
      nameInput.focus();
    });
  }

  enterBtn.addEventListener('click', () => {
    const name = nameInput.value.trim() || 'Wanderer';
    const wallet = getAddress();
    if (wallet) {
      overlays.dismiss('char-create');
      enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
    }
  });

  nameInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = nameInput.value.trim() || 'Wanderer';
      const wallet = getAddress();
      if (wallet) {
        overlays.dismiss('char-create');
        enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
      }
    }
  });
}
