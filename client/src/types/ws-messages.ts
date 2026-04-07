// src/types/ws-messages.ts
/** Discriminated union of all WebSocket message types from the server. */

import type { StateUpdate } from './schema.generated';

export interface NarrativeMessage {
  type: 'narrative';
  text?: string;
  npc?: string;
  npc_username?: string;
  channel?: string;
  state_update?: StateUpdate;
}

export interface DeathFeedMessage {
  type: 'death_feed';
  player_name?: string;
  level?: number;
  location?: string;
  cause?: string;
}

export interface SceneArtMessage {
  type: 'scene_art';
  lines?: string[];
}

export interface EntityArtMessage {
  type: 'entity_art';
  entity_id?: string;
  lines?: string[];
}

export interface NpcStatusMessage {
  type: 'npc_status';
  npc?: string;
  npc_username?: string;
  text?: string;
}

export interface PhaseMessage {
  type: 'phase';
  phase: string;
  crew?: string;
  location?: string;
  action_count?: number;
  deadline?: number;
}

export interface StatusMessage {
  type: 'status';
  tick?: number;
  chain?: boolean;
  activity?: string;
}

export interface PlayerJoinedMessage {
  type: 'player_joined';
  player_id: string;
  player_name: string;
}

export interface PlayerLeftMessage {
  type: 'player_left';
  player_id: string;
  player_name: string;
}

export interface PresencePlayer {
  player_id: string;
  player_name: string;
}

export interface PresenceMessage {
  type: 'presence';
  players?: PresencePlayer[];
}

export interface StateUpdateMessage {
  type: 'state_update';
  state_update?: StateUpdate;
}

export interface RoomItemsChangedMessage {
  type: 'room_items_changed';
}

export interface CodexRefreshMessage {
  type: 'codex_refresh';
  entity_id?: string;
}

export interface NpcLeftMessage {
  type: 'npc_left';
  npc_name: string;
}

export interface NpcJoinedMessage {
  type: 'npc_joined';
  npc_name: string;
  npc_id?: string;
}

export interface PositionUpdateMessage {
  type: 'position_update';
  entity_id: string;
  x: number;
  y: number;
}

export interface EpisodeFeedMessage {
  type: 'episode_feed';
  episode_uuid: string;
  agent_id: string;
  name: string;
  summary: string;
  location: string;
  timestamp: string;
}

export interface ToolEventMessage {
  type: 'tool_event';
  tool: string;
  npc?: string;
  summary: string;
  data?: Record<string, unknown>;
  location: string;
}

export type WsMessage =
  | NarrativeMessage
  | DeathFeedMessage
  | SceneArtMessage
  | EntityArtMessage
  | NpcStatusMessage
  | PhaseMessage
  | StatusMessage
  | PlayerJoinedMessage
  | PlayerLeftMessage
  | PresenceMessage
  | StateUpdateMessage
  | RoomItemsChangedMessage
  | CodexRefreshMessage
  | NpcLeftMessage
  | NpcJoinedMessage
  | PositionUpdateMessage
  | EpisodeFeedMessage
  | ToolEventMessage;
