// src/message-handler.ts
/**
 * WebSocket message handler — extracted from app.ts.
 * Pure switch-dispatch over WsMessage, delegates side-effects via AppRefs.
 */

import { applyStateUpdate, syncEntityField, type GameState } from './state/game-state';
import { getSession } from './state/session';
import { updateRoundState, type PhaseMessage as RoundPhaseMessage } from './state/round-state';
import type { WsMessage } from './types/ws-messages';
import type { NarrativeController } from './panels/narrative';
import { renderCharacterPanel } from './panels/character';
import { renderInventoryPanel } from './panels/inventory';
import { renderWorldMapPanel } from './panels/worldmap';
import { renderPresentPanel } from './panels/present';
import { renderQuestLogPanel } from './panels/questlog';
import { renderFactionsPanel } from './panels/factions';
import { updateMap } from './panels/map';
import type { WorldTime } from './ui/header';
import type { TerminalPanel } from './ui/terminal-panel';

/** Minimal panel-bearing window interface — avoids importing full Window type. */
interface PanelWindow {
  panel?: TerminalPanel;
  setTitle(title: string): void;
}

/** All shared state the message handler needs from app.ts. */
export interface AppRefs {
  getGameState(): GameState | undefined;
  narrative: NarrativeController;
  eventsFeed: NarrativeController;
  header: { updateTime(t: WorldTime): void };
  statusBar: { setTick(t: number): void; setChain(c: boolean): void; setActivity(a: string): void };
  codex: { active: boolean; refreshEntityArt(entityId: string, lines: string[]): void };
  invModal: { active: boolean; refresh(): void };
  characterWin: PanelWindow;
  inventoryWin: PanelWindow;
  exitsWin: PanelWindow;
  presentWin: PanelWindow;
  questWin: PanelWindow;
  factionWin: PanelWindow;
  handleAction: (action: string) => Promise<void>;
  registerMapEntities: (map: import('./map/types').RoomMap | null) => void;
  fetchPlayerWorldMap: () => Promise<void>;
  showDeathScreen: (cause: string) => void;
}

/** Tracks the last dialogue message from each NPC (keyed by display name). */
const lastNpcMessages = new Map<string, string>();

/** Retrieve the last stored NPC dialogue line for a given NPC name. */
export function getLastNpcMessage(npcName: string): string {
  return lastNpcMessages.get(npcName) || '';
}

export function createMessageHandler(refs: AppRefs): (msg: WsMessage) => void {

  /** Re-render every side panel from current game state. */
  function renderAllPanels(): void {
    const gameState = refs.getGameState();
    if (!gameState) return;
    refs.characterWin.setTitle(gameState.player.name || 'Character');
    renderCharacterPanel(refs.characterWin.panel!, gameState);
    renderInventoryPanel(refs.inventoryWin.panel!, gameState);
    renderWorldMapPanel(refs.exitsWin.panel!, gameState, refs.handleAction);
    renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
    renderQuestLogPanel(refs.questWin.panel!, gameState.quests);
    renderFactionsPanel(refs.factionWin.panel!, gameState.factions);
    updateMap(gameState, refs.handleAction);
  }

  return function handleMessage(msg: WsMessage): void {
    const gameState = refs.getGameState();

    switch (msg.type) {
      case 'narrative': {
        refs.narrative.removeThinking();
        const channel = msg.channel || 'narrative';

        // Route by channel: narrative prose stays in narrative, events go to events feed
        if (channel === 'events') {
          refs.eventsFeed.addBlock(msg.text || '', 'event');
        } else if (channel === 'ooc') {
          refs.eventsFeed.addBlock(msg.text || '', 'ooc');
        } else if (msg.npc) {
          // NPC dialogue — remove thinking indicator and show with name header
          lastNpcMessages.set(msg.npc, msg.text || '');
          const npcKey = msg.npc_username || msg.npc.toLowerCase().replace(/\s+/g, '-');
          refs.narrative.removeBlockById(`npc-status-${npcKey}`);
          refs.narrative.addBlock(`${msg.npc}`, 'npc-name');
          refs.narrative.addBlock(msg.text || '', 'npc-dialogue');
        } else {
          refs.narrative.addBlock(msg.text || '', 'narrative');
        }

        if (msg.state_update && gameState) {
          applyStateUpdate(gameState, msg.state_update);
          const session = getSession();
          session.currentLocation = gameState.location.name;
          if (gameState.roomMap) refs.registerMapEntities(gameState.roomMap);

          if (msg.state_update.world_time) {
            refs.header.updateTime(msg.state_update.world_time as WorldTime);
            refs.statusBar.setTick(msg.state_update.world_time.tick || 0);
          }

          renderAllPanels();
          refs.fetchPlayerWorldMap();

          // Display event notifications in the events feed
          if (msg.state_update.events) {
            const events = msg.state_update.events;
            if (events.combat) {
              const c = events.combat;
              if (c.damage_dealt != null) {
                refs.eventsFeed.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ''}`, 'event-combat');
              }
              if (c.xp_gained) {
                refs.eventsFeed.addBlock(`[+${c.xp_gained} XP]`, 'event-xp');
              }
              if (c.target_dead) {
                refs.eventsFeed.addBlock(`${c.target_name || 'Target'} has been slain.`, 'event-death');
              }
            }
            if (events.inventory_changes) {
              for (const inv of events.inventory_changes) {
                const prefix = inv.event_type === 'DROP' ? '-' : '+';
                refs.eventsFeed.addBlock(`[${prefix}${inv.item_name}]`, 'event-item');
              }
            }
          }
        }

        // Check for death via structured event or text fallback
        if (msg.state_update?.status === 'dead' ||
            msg.state_update?.events?.combat?.target_dead ||
            (msg.text && msg.text.toLowerCase().includes('you have died'))) {
          refs.showDeathScreen(msg.state_update?.cause || '');
        }
        break;
      }
      case 'death_feed': {
        const skull = '\u2620';
        const deathMsg = `${skull} ${msg.player_name || 'Unknown'} (Level ${msg.level || '?'}) fell at ${msg.location || 'unknown'}. ${msg.cause || ''}`;
        refs.narrative.addBlock(deathMsg, 'death-feed');
        break;
      }
      case 'scene_art': {
        // Render scene art as a narrative block
        const artText = (msg.lines || []).join('\n');
        if (artText) {
          refs.narrative.addBlock(artText, 'scene-art');
        }
        break;
      }
      case 'entity_art': {
        // Cache on the entity in game state
        const artLines = msg.lines || [];
        if (msg.entity_id && gameState) {
          syncEntityField(gameState, msg.entity_id, { ascii_art: artLines.join('\n') });
        }
        // Update codex modal if it's open
        if (msg.entity_id && refs.codex?.active) {
          refs.codex.refreshEntityArt(msg.entity_id, artLines);
        }
        break;
      }
      case 'codex_refresh': {
        // Enrichment finished — no-op while codex is open (art updates come via entity_art).
        // Data will be fresh next time codex is opened.
        break;
      }
      case 'npc_status': {
        // NPC thinking/status — replace previous status for this NPC
        const npcKey = msg.npc_username || msg.npc || 'unknown';
        refs.narrative.replaceBlock(`npc-status-${npcKey}`, `${msg.npc}: ${msg.text}`, 'npc-status');
        break;
      }
      case 'phase': {
        updateRoundState(msg as RoundPhaseMessage);
        // Show phase progress in events feed
        const phase = msg.phase || '';
        const crew = msg.crew || '';
        if (phase === 'resolving' && crew) {
          refs.eventsFeed.replaceBlock('phase-progress', `[${crew}]`, 'event');
        } else if (phase === 'npc_response') {
          refs.eventsFeed.replaceBlock('phase-progress', '[waiting for NPCs]', 'event');
        } else if (phase === 'ready') {
          refs.eventsFeed.removeBlockById('phase-progress');
        }
        break;
      }
      case 'status':
        if (msg.tick != null) refs.statusBar.setTick(msg.tick);
        if (msg.chain != null) refs.statusBar.setChain(msg.chain);
        if (msg.activity) refs.statusBar.setActivity(msg.activity);
        break;
      case 'player_joined': {
        if (gameState) {
          const exists = gameState.location.players.some(p => p.id === msg.player_id);
          if (!exists) {
            gameState.location.players.push({ name: msg.player_name, id: msg.player_id });
            renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
            refs.narrative.addBlock(`${msg.player_name} arrived.`, 'system');
          }
        }
        break;
      }
      case 'player_left': {
        if (gameState) {
          gameState.location.players = gameState.location.players.filter(p => p.id !== msg.player_id);
          renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
          refs.narrative.addBlock(`${msg.player_name} departed.`, 'system');
        }
        break;
      }
      case 'position_update': {
        if (gameState && msg.entity_id) {
          syncEntityField(gameState, msg.entity_id, { x: msg.x, y: msg.y });
          updateMap(gameState, refs.handleAction);
        }
        break;
      }
      case 'npc_left': {
        if (gameState) {
          const leftName = (msg.npc_name as string).toLowerCase();
          gameState.location.npcs = gameState.location.npcs.filter(n =>
            n.name.toLowerCase() !== leftName && !n.name.toLowerCase().startsWith(leftName)
          );
          renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
        }
        break;
      }
      case 'npc_joined': {
        if (gameState && msg.npc_name) {
          const joinName = (msg.npc_name as string).toLowerCase();
          const exists = gameState.location.npcs.some(n =>
            n.name.toLowerCase() === joinName || n.name.toLowerCase().startsWith(joinName)
          );
          if (!exists) {
            gameState.location.npcs.push({ name: msg.npc_name, id: msg.npc_id || '', role: '' });
            renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
          }
        }
        break;
      }
      case 'presence': {
        if (gameState) {
          gameState.location.players = (msg.players || []).map((p: { player_name: string; player_id: string }) => ({
            name: p.player_name,
            id: p.player_id,
          }));
          renderPresentPanel(refs.presentWin.panel!, gameState, refs.handleAction);
        }
        break;
      }
      case 'state_update': {
        // Standalone state_update (from inventory actions, not embedded in narrative)
        if (msg.state_update && gameState) {
          applyStateUpdate(gameState, msg.state_update);
          renderAllPanels();
          refs.fetchPlayerWorldMap();
          if (refs.invModal.active) refs.invModal.refresh();
        }
        break;
      }
      case 'room_items_changed': {
        // Ground items changed — refresh room manifest
        // The next state_update will have the updated room_map
        if (refs.invModal.active) refs.invModal.refresh();
        break;
      }
      case 'episode_feed': {
        const label = msg.location ? `[Chronicle \u00B7 ${msg.location}]` : '[Chronicle]';
        refs.eventsFeed.addBlock(`${label} ${msg.name}: ${msg.summary}`, 'event');
        break;
      }
      default:
        console.log('Unknown message:', msg);
    }
  };
}
