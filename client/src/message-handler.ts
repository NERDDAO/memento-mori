// src/message-handler.ts
/**
 * WebSocket message handler — extracted from app.ts.
 * Pure switch-dispatch over WsMessage, delegates side-effects via AppRefs.
 */

import { applyStateUpdate, syncEntityField, type GameState } from './state/game-state';
import { getSession } from './state/session';
import { updateRoundState, type PhaseMessage as RoundPhaseMessage } from './state/round-state';
import type { WsMessage, ToolEventMessage } from './types/ws-messages';
import type { NarrativeController } from './panels/narrative';
import type { WorldTime } from './ui/header';

/** All shared state the message handler needs from app.ts. */
export interface AppRefs {
  getGameState(): GameState | undefined;
  narrative: NarrativeController;
  eventsFeed: NarrativeController;
  renderAllPanels(): void;
  header: { updateTime(t: WorldTime): void };
  statusBar: { setTick(t: number): void; setChain(c: boolean): void; setActivity(a: string): void };
  codex: { active: boolean; refreshEntityArt(entityId: string, lines: string[]): void };
  invModal: { active: boolean; refresh(): void };
  handleAction: (action: string) => Promise<void>;
  registerMapEntities: (map: import('./map/types').RoomMap | null) => void;
  fetchPlayerWorldMap: () => Promise<void>;
  showDeathScreen: (cause: string) => void;
  setViewportScene?: (lines: string[]) => void;
}

/** Format a tool event into a compact badge string. */
function formatToolBadge(msg: ToolEventMessage): string {
  const s = msg.summary || '';
  switch (msg.tool) {
    case 'mm_resolve_combat': return `\u2694\uFE0F ${s}`;
    case 'mm_give_item':      return `\uD83C\uDF81 ${s}`;
    case 'mm_skill_check':    return `\uD83C\uDFB2 ${s}`;
    case 'mm_give_quest':     return `\uD83D\uDCDC ${s}`;
    case 'mm_move_to':        return `\uD83D\uDEB6 ${s}`;
    case 'mm_create_npc':     return `\u2728 ${s}`;
    case 'mm_create_item':    return `\u2728 ${s}`;
    default:                  return s;
  }
}

/** Tracks the last dialogue message from each NPC (keyed by display name). */
const lastNpcMessages = new Map<string, string>();

/** Retrieve the last stored NPC dialogue line for a given NPC name. */
export function getLastNpcMessage(npcName: string): string {
  return lastNpcMessages.get(npcName) || '';
}

export function createMessageHandler(refs: AppRefs): (msg: WsMessage) => void {

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
          // NPC final message (narrated log) — route to events feed, not main narrative.
          // Real dialogue comes through tool_event (mm_npc_response).
          const npcKey = msg.npc_username || msg.npc.toLowerCase().replace(/\s+/g, '-');
          refs.narrative.removeBlockById(`npc-status-${npcKey}`);
          refs.eventsFeed.addBlock(`[${msg.npc}] ${msg.text || ''}`, 'npc-log');
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

          refs.renderAllPanels();
          refs.fetchPlayerWorldMap();

          // Display event notifications in the main narrative feed (alongside tool badges)
          if (msg.state_update.events) {
            const events = msg.state_update.events;
            if (events.combat) {
              const c = events.combat;
              if (c.damage_dealt != null) {
                refs.narrative.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ''}`, 'event-combat');
              }
              if (c.xp_gained) {
                refs.narrative.addBlock(`[+${c.xp_gained} XP]`, 'event-xp');
              }
              if (c.target_dead) {
                refs.narrative.addBlock(`${c.target_name || 'Target'} has been slain.`, 'event-death');
              }
            }
            if (events.inventory_changes) {
              for (const inv of events.inventory_changes) {
                const prefix = inv.event_type === 'DROP' ? '-' : '+';
                refs.narrative.addBlock(`[${prefix}${inv.item_name}]`, 'event-item');
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
        const artLines = msg.lines || [];
        // Send to viewport panel
        if (artLines.length > 0) {
          refs.setViewportScene?.(artLines);
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
            refs.renderAllPanels();
            refs.narrative.addBlock(`${msg.player_name} arrived.`, 'system');
          }
        }
        break;
      }
      case 'player_left': {
        if (gameState) {
          gameState.location.players = gameState.location.players.filter(p => p.id !== msg.player_id);
          refs.renderAllPanels();
          refs.narrative.addBlock(`${msg.player_name} departed.`, 'system');
        }
        break;
      }
      case 'position_update': {
        if (gameState && msg.entity_id) {
          syncEntityField(gameState, msg.entity_id, { x: msg.x, y: msg.y });
          refs.renderAllPanels();
        }
        break;
      }
      case 'npc_left': {
        if (gameState) {
          const leftName = (msg.npc_name as string).toLowerCase();
          gameState.location.npcs = gameState.location.npcs.filter(n =>
            n.name.toLowerCase() !== leftName && !n.name.toLowerCase().startsWith(leftName)
          );
          refs.renderAllPanels();
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
            refs.renderAllPanels();
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
          refs.renderAllPanels();
        }
        break;
      }
      case 'state_update': {
        // Standalone state_update (from inventory actions, not embedded in narrative)
        if (msg.state_update && gameState) {
          applyStateUpdate(gameState, msg.state_update);
          refs.renderAllPanels();
          refs.fetchPlayerWorldMap();
          if (refs.invModal.active) refs.invModal.refresh();
        }
        break;
      }
      case 'room_items_changed': {
        if (refs.invModal.active) refs.invModal.refresh();
        break;
      }
      case 'tool_event': {
        if (msg.tool === 'mm_npc_response') {
          // NPC dialogue via tool — render as name + dialogue
          if (msg.npc) {
            lastNpcMessages.set(msg.npc, msg.summary || '');
            const npcKey = msg.npc.toLowerCase().replace(/\s+/g, '-');
            refs.narrative.removeBlockById(`npc-status-${npcKey}`);
            refs.narrative.addBlock(msg.npc, 'npc-name');
            refs.narrative.addBlock(msg.summary || '', 'npc-dialogue');
          }
        } else {
          // Mechanical tool event — show as inline badge
          refs.narrative.addBlock(`[${formatToolBadge(msg)}]`, 'tool-badge');
        }
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
