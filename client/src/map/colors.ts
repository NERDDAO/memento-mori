// src/map/colors.ts

// [foreground, background] colors per tile character
const TILE_COLORS: Record<string, [string, string]> = {
  '#': ['#3a3a48', '#1a1a22'],   // wall
  '.': ['#2a2a35', '#0a0a0f'],   // floor
  '+': ['#50c8c8', '#0a0a0f'],   // door/exit
  'T': ['#8b6914', '#0a0a0f'],   // table
  'B': ['#8b6914', '#0a0a0f'],   // bar/counter
  '~': ['#3060c0', '#0a0a0f'],   // water
  ',': ['#2a5a2a', '#0a0a0f'],   // grass
  ':': ['#555550', '#0a0a0f'],   // gravel
  '=': ['#666660', '#0a0a0f'],   // road
  '^': ['#888880', '#0a0a0f'],   // stairs
  ' ': ['#0a0a0f', '#0a0a0f'],   // void
};

const DEFAULT_COLORS: [string, string] = ['#555555', '#0a0a0f'];

export function tileColors(ch: string): [string, string] {
  return TILE_COLORS[ch] || DEFAULT_COLORS;
}

export const ENTITY_COLORS = {
  player: '#ffd700',
  npc: '#d4a574',
  item: '#a335ee',
  exit: '#50c8c8',
} as const;
