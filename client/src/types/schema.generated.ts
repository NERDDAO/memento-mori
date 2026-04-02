// AUTO-GENERATED — do not edit manually.
// Source: engine/src/memento/models/state_update.py
// Run: python scripts/gen-types.py

export interface ExitUpdate {
  direction?: string;
  name?: string;
}

export interface EntityRefUpdate {
  name?: string;
  id?: string;
  role?: string;
}

export interface InventoryItemUpdate {
  name?: string;
  rarity?: string;
  equipped?: boolean;
}

export interface WorldTimeDisplay {
  moon_phase?: string;
  moon_icon?: string;
  day_name?: string;
  day_number?: number;
  month?: string;
  season?: string;
  time_of_day?: string;
  tick?: number;
}

export interface RoomMapUpdate {
  id?: string;
  name?: string;
  width?: number;
  height?: number;
  tiles?: string[];
  npcs?: Record<string, any>[];
  items?: Record<string, any>[];
  exits?: Record<string, any>[];
  spawn?: Record<string, any>;
}

export interface CombatEvent {
  action_type?: string;
  target_name?: string;
  damage_dealt?: number | null;
  target_dead?: boolean;
  xp_gained?: number;
}

export interface InventoryEvent {
  event_type?: string;
  item_name?: string;
}

export interface EventSummary {
  categories?: string[];
  combat?: CombatEvent | null;
  inventory_changes?: InventoryEvent[];
  quest_update?: string;
  reputation_changes?: Record<string, any>;
}

export interface StateUpdate {
  schema_version?: number;
  location?: string | null;
  health?: number | null;
  max_health?: number | null;
  level?: number | null;
  xp?: number | null;
  exits?: ExitUpdate[] | null;
  npcs?: EntityRefUpdate[] | null;
  items?: EntityRefUpdate[] | null;
  inventory?: InventoryItemUpdate[] | null;
  room_map?: RoomMapUpdate | null;
  world_time?: WorldTimeDisplay | null;
  skills?: Record<string, any> | null;
  events?: EventSummary | null;
  active_quests?: QuestSummary[] | null;
  factions?: FactionStanding[] | null;
  status?: string | null;
  cause?: string | null;
  subsystem_warnings?: string[];
}

export const SCHEMA_VERSION = 1;
