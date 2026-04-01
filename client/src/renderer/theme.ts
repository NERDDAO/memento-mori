// src/renderer/theme.ts
/** Color tokens and font configuration for the MUD renderer. */

export const theme = {
  colors: {
    primary: '#c8c8d0',
    dim: '#6a6a78',
    npc: '#d4a574',
    damage: '#e05050',
    heal: '#50c878',
    system: '#5a5a70',
    location: '#7aa2d4',
    accent: '#8b5cf6',
    bg: '#0a0a0f',
  },
  fonts: {
    narrative: "'Georgia', 'Times New Roman', serif",
    ui: "system-ui, -apple-system, sans-serif",
    mono: "'Fira Code', 'Cascadia Code', monospace",
  },
  sizes: {
    narrativeText: 16,
    uiText: 13,
    lineHeight: 1.7,
  },
} as const;

export type Theme = typeof theme;
