// src/map/world-renderer.ts
/**
 * World map renderer — draws discovered locations as a node graph on canvas.
 * Locations are circles with names, connections are lines between them.
 * Current location is highlighted. Undiscovered neighbors shown as "?"
 */

import type { WorldMap, WorldMapNode } from './types';
import { ENTITY_COLORS } from './colors';

const NODE_RADIUS = 18;
const LABEL_FONT = '11px monospace';
const NODE_FONT = '13px monospace';
const PADDING = 40;

const COLORS = {
  bg: '#0a0a0f',
  nodeBg: '#16161f',
  nodeBorder: '#2a2a38',
  currentBg: '#1a1a35',
  currentBorder: '#8b5cf6',
  connection: '#2a2a38',
  connectionActive: '#3a3a50',
  text: '#c8c8d0',
  textDim: '#6a6a78',
  current: '#8b5cf6',
  discovered: '#50c878',
  undiscovered: '#3a3a48',
};

// Direction-based layout offsets
const DIR_OFFSETS: Record<string, { dx: number; dy: number }> = {
  north: { dx: 0, dy: -1 },
  south: { dx: 0, dy: 1 },
  east: { dx: 1, dy: 0 },
  west: { dx: -1, dy: 0 },
  northeast: { dx: 0.7, dy: -0.7 },
  northwest: { dx: -0.7, dy: -0.7 },
  southeast: { dx: 0.7, dy: 0.7 },
  southwest: { dx: -0.7, dy: 0.7 },
  up: { dx: 0.3, dy: -1 },
  down: { dx: -0.3, dy: 1 },
};

export class WorldMapRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private dpr: number;
  private onClick: ((roomId: string) => void) | null = null;
  private lastMap: WorldMap | null = null;
  private nodePositions: Map<string, { x: number; y: number }> = new Map();

  constructor(container: HTMLElement) {
    this.dpr = Math.min(devicePixelRatio, 2);
    this.canvas = document.createElement('canvas');
    this.canvas.style.display = 'block';
    this.canvas.style.background = COLORS.bg;
    this.canvas.style.cursor = 'pointer';
    this.ctx = this.canvas.getContext('2d')!;
    container.appendChild(this.canvas);

    this.canvas.addEventListener('click', (e) => this.handleClick(e));
  }

  setClickHandler(handler: (roomId: string) => void): void {
    this.onClick = handler;
  }

  render(map: WorldMap): void {
    this.lastMap = map;
    this.layoutNodes(map);

    const { width, height } = this.computeBounds();
    this.canvas.width = width * this.dpr;
    this.canvas.height = height * this.dpr;
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;

    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

    // Clear
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, width, height);

    // Draw connections
    for (const conn of map.connections) {
      const from = this.nodePositions.get(conn.from);
      const to = this.nodePositions.get(conn.to);
      if (!from || !to) continue;

      const isActive = conn.from === map.currentRoom || conn.to === map.currentRoom;
      ctx.strokeStyle = isActive ? COLORS.connectionActive : COLORS.connection;
      ctx.lineWidth = isActive ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();

      // Direction label at midpoint
      if (conn.direction) {
        const mx = (from.x + to.x) / 2;
        const my = (from.y + to.y) / 2;
        ctx.font = '9px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = COLORS.textDim;
        ctx.fillText(conn.direction[0].toUpperCase(), mx, my);
      }
    }

    // Draw nodes
    for (const room of map.rooms) {
      const pos = this.nodePositions.get(room.id);
      if (!pos) continue;

      const isCurrent = room.id === map.currentRoom;

      // Node circle
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, NODE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = isCurrent ? COLORS.currentBg : COLORS.nodeBg;
      ctx.fill();
      ctx.strokeStyle = isCurrent ? COLORS.currentBorder : COLORS.nodeBorder;
      ctx.lineWidth = isCurrent ? 2.5 : 1;
      ctx.stroke();

      // Node icon
      ctx.font = NODE_FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = isCurrent ? COLORS.current : COLORS.discovered;
      ctx.fillText(isCurrent ? '@' : '\u25CF', pos.x, pos.y);

      // Name label below
      ctx.font = LABEL_FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = isCurrent ? COLORS.text : COLORS.textDim;
      const label = room.name.length > 16 ? room.name.slice(0, 14) + '..' : room.name;
      ctx.fillText(label, pos.x, pos.y + NODE_RADIUS + 4);
    }
  }

  private layoutNodes(map: WorldMap): void {
    this.nodePositions.clear();

    if (map.rooms.length === 0) return;

    // Use provided x,y if available, otherwise auto-layout from connections
    const hasCoords = map.rooms.some(r => r.x !== 0 || r.y !== 0);

    if (hasCoords) {
      // Use provided coordinates, just scale to fit
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const r of map.rooms) {
        minX = Math.min(minX, r.x); minY = Math.min(minY, r.y);
        maxX = Math.max(maxX, r.x); maxY = Math.max(maxY, r.y);
      }
      const rangeX = maxX - minX || 1;
      const rangeY = maxY - minY || 1;
      const areaW = 400;
      const areaH = 300;
      for (const r of map.rooms) {
        this.nodePositions.set(r.id, {
          x: PADDING + ((r.x - minX) / rangeX) * areaW,
          y: PADDING + ((r.y - minY) / rangeY) * areaH,
        });
      }
    } else {
      // Auto-layout: place current room at center, use connections + directions
      this.autoLayout(map);
    }
  }

  private autoLayout(map: WorldMap): void {
    const spacing = 100;
    const placed = new Set<string>();

    // Find current room or first room
    const startId = map.currentRoom || map.rooms[0]?.id;
    if (!startId) return;

    const centerX = 220;
    const centerY = 180;

    this.nodePositions.set(startId, { x: centerX, y: centerY });
    placed.add(startId);

    // BFS from current room using connections
    const queue = [startId];
    while (queue.length > 0) {
      const nodeId = queue.shift()!;
      const nodePos = this.nodePositions.get(nodeId)!;

      for (const conn of map.connections) {
        let neighborId = '';
        let direction = conn.direction;
        if (conn.from === nodeId && !placed.has(conn.to)) {
          neighborId = conn.to;
        } else if (conn.to === nodeId && !placed.has(conn.from)) {
          neighborId = conn.from;
          // Reverse direction
          const reverseDir: Record<string, string> = {
            north: 'south', south: 'north', east: 'west', west: 'east',
            northeast: 'southwest', northwest: 'southeast',
            southeast: 'northwest', southwest: 'northeast',
          };
          direction = reverseDir[direction] || direction;
        }

        if (!neighborId) continue;

        const offset = DIR_OFFSETS[direction] || { dx: 0, dy: -1 };
        const nx = nodePos.x + offset.dx * spacing;
        const ny = nodePos.y + offset.dy * spacing;

        // Avoid overlap: nudge if too close to existing nodes
        let finalX = nx, finalY = ny;
        for (const pos of this.nodePositions.values()) {
          const dist = Math.hypot(finalX - pos.x, finalY - pos.y);
          if (dist < NODE_RADIUS * 3) {
            finalX += (Math.random() - 0.5) * 40;
            finalY += (Math.random() - 0.5) * 40;
          }
        }

        this.nodePositions.set(neighborId, { x: finalX, y: finalY });
        placed.add(neighborId);
        queue.push(neighborId);
      }
    }

    // Place any orphaned nodes
    let orphanX = PADDING;
    for (const room of map.rooms) {
      if (!placed.has(room.id)) {
        this.nodePositions.set(room.id, { x: orphanX, y: centerY + spacing });
        orphanX += spacing;
        placed.add(room.id);
      }
    }
  }

  private computeBounds(): { width: number; height: number } {
    let maxX = 200, maxY = 200;
    for (const pos of this.nodePositions.values()) {
      maxX = Math.max(maxX, pos.x + PADDING + NODE_RADIUS);
      maxY = Math.max(maxY, pos.y + PADDING + NODE_RADIUS + 20);
    }
    return { width: Math.ceil(maxX), height: Math.ceil(maxY) };
  }

  private handleClick(e: MouseEvent): void {
    if (!this.lastMap || !this.onClick) return;
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const room of this.lastMap.rooms) {
      const pos = this.nodePositions.get(room.id);
      if (!pos) continue;
      const dist = Math.hypot(mx - pos.x, my - pos.y);
      if (dist <= NODE_RADIUS + 4) {
        this.onClick(room.id);
        return;
      }
    }
  }
}
