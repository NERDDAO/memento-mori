// src/ui/wiki.ts
/**
 * Wiki panel — KG entity browser with clickable edge navigation.
 * Paginated: shows one "page" at a time within a fixed-height panel.
 * Page 1 = entity info, Page 2+ = edge groups.
 */

const GATEWAY = '';
const SUMMARY_MAX = 150;
const ITEMS_PER_PAGE = 8;

interface WikiEntity {
  id: string;
  name: string;
  labels: string[];
  summary: string;
}

interface WikiEdge {
  source: string;
  target: string;
  relationship: string;
  fact: string;
}

interface NeighborResponse {
  entity: WikiEntity;
  neighbors: WikiEntity[];
  edges: WikiEdge[];
}

// A "page" is a discrete chunk of content
interface WikiPage {
  title: string;       // shown in page header
  html: string;        // content
  links: Array<{ name: string; id?: string }>; // clickable entities on this page
}

export interface WikiPanel {
  el: HTMLElement;
  show(entityId: string, entityName: string): Promise<void>;
  showByName(name: string): Promise<void>;
  clear(): void;
}

export function createWikiPanel(): WikiPanel {
  const el = document.createElement('div');
  el.className = 'wiki-panel';
  el.innerHTML = '<div class="wiki-empty">Click an entity to browse</div>';

  const cache = new Map<string, NeighborResponse>();
  const navStack: Array<{ id: string; name: string }> = [];
  let currentId = '';
  let pages: WikiPage[] = [];
  let pageIdx = 0;

  async function fetchEntity(id: string): Promise<NeighborResponse | null> {
    if (cache.has(id)) return cache.get(id)!;
    try {
      const resp = await fetch(`${GATEWAY}/api/entity/${id}/neighbors`);
      const data: NeighborResponse = await resp.json();
      if (data.entity.name !== 'Unknown') {
        cache.set(id, data);
        return data;
      }
    } catch { /* KG unavailable */ }
    return null;
  }

  async function fetchByName(name: string): Promise<NeighborResponse | null> {
    try {
      const resp = await fetch(`${GATEWAY}/api/entity/search/${encodeURIComponent(name)}`);
      const data = await resp.json();
      if (data && data.id && !data.error) {
        return fetchEntity(data.id);
      }
    } catch { /* search failed */ }
    return null;
  }

  function cleanSummary(raw: string): string {
    if (raw.startsWith('{') || raw.startsWith('[') || raw.startsWith('"')) return '';
    if (raw.length > SUMMARY_MAX) return raw.slice(0, SUMMARY_MAX) + '\u2026';
    return raw;
  }

  function buildPages(data: NeighborResponse): WikiPage[] {
    const { entity, neighbors, edges } = data;
    const result: WikiPage[] = [];

    // Page 1: Entity overview
    let overviewHtml = '';
    overviewHtml += `<div class="wiki-name">${esc(entity.name)}</div>`;
    if (entity.labels.length) {
      overviewHtml += `<div class="wiki-labels">${entity.labels.map(l => esc(l)).join(' \u00B7 ')}</div>`;
    }
    const summary = cleanSummary(entity.summary);
    if (summary) {
      overviewHtml += `<div class="wiki-summary">${esc(summary)}</div>`;
    }

    // Show edge group names as a table of contents
    const grouped = new Map<string, WikiEdge[]>();
    for (const edge of edges) {
      const key = edge.relationship || 'connected';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(edge);
    }

    const edgeNames = new Set(edges.flatMap(e => [e.source, e.target]));
    const extraNeighbors = neighbors.filter(n => !edgeNames.has(n.name) && n.id !== entity.id);

    if (grouped.size > 0 || extraNeighbors.length > 0) {
      overviewHtml += '<div class="wiki-toc-label">Connections:</div>';
      let tocIdx = 2; // page numbers start at 1 for overview
      for (const [rel, group] of grouped) {
        overviewHtml += `<div class="wiki-toc-item" data-page="${tocIdx}">${formatRel(rel)} (${group.length})</div>`;
        tocIdx += Math.ceil(group.length / ITEMS_PER_PAGE);
      }
      if (extraNeighbors.length) {
        overviewHtml += `<div class="wiki-toc-item" data-page="${tocIdx}">Nearby (${extraNeighbors.length})</div>`;
      }
    }

    result.push({ title: entity.name, html: overviewHtml, links: [] });

    // One page per edge group (chunked if > ITEMS_PER_PAGE)
    for (const [rel, group] of grouped) {
      const chunks = chunk(group, ITEMS_PER_PAGE);
      for (let ci = 0; ci < chunks.length; ci++) {
        const label = formatRel(rel);
        const suffix = chunks.length > 1 ? ` ${ci + 1}/${chunks.length}` : '';
        let html = `<div class="wiki-page-heading">${esc(label)}${suffix}</div>`;
        const links: WikiPage['links'] = [];
        for (const edge of chunks[ci]) {
          const other = edge.source === entity.name ? edge.target : edge.source;
          html += `<div class="wiki-link" data-name="${esc(other)}">\u00B7 ${esc(other)}</div>`;
          if (edge.fact) {
            const cleanFact = edge.fact.length > 80 ? edge.fact.slice(0, 80) + '\u2026' : edge.fact;
            html += `<div class="wiki-fact">${esc(cleanFact)}</div>`;
          }
          links.push({ name: other });
        }
        result.push({ title: label, html, links });
      }
    }

    // Neighbors pages (chunked)
    if (extraNeighbors.length) {
      const chunks = chunk(extraNeighbors, ITEMS_PER_PAGE);
      for (let ci = 0; ci < chunks.length; ci++) {
        const suffix = chunks.length > 1 ? ` ${ci + 1}/${chunks.length}` : '';
        let html = `<div class="wiki-page-heading">Nearby${suffix}</div>`;
        const links: WikiPage['links'] = [];
        for (const n of chunks[ci]) {
          html += `<div class="wiki-link" data-name="${esc(n.name)}" data-id="${esc(n.id)}">\u00B7 ${esc(n.name)}</div>`;
          links.push({ name: n.name, id: n.id });
        }
        result.push({ title: 'Nearby', html, links });
      }
    }

    return result;
  }

  function renderPage() {
    if (!pages.length) return;
    const page = pages[pageIdx];
    const total = pages.length;

    let html = '';

    // Back button
    if (navStack.length > 1) {
      const prev = navStack[navStack.length - 2];
      html += `<div class="wiki-back" data-id="${esc(prev.id)}" data-name="${esc(prev.name)}">\u2190 ${esc(prev.name)}</div>`;
    }

    // Page content
    html += page.html;

    // Pagination controls
    if (total > 1) {
      html += '<div class="wiki-pagination">';
      html += `<span class="wiki-page-btn wiki-prev ${pageIdx === 0 ? 'disabled' : ''}">\u25C0</span>`;
      html += `<span class="wiki-page-num">${pageIdx + 1}/${total}</span>`;
      html += `<span class="wiki-page-btn wiki-next ${pageIdx >= total - 1 ? 'disabled' : ''}">\u25B6</span>`;
      html += '</div>';
    }

    el.innerHTML = html;

    // Wire pagination
    const prevBtn = el.querySelector('.wiki-prev');
    const nextBtn = el.querySelector('.wiki-next');
    if (prevBtn && pageIdx > 0) {
      prevBtn.addEventListener('click', () => { pageIdx--; renderPage(); });
    }
    if (nextBtn && pageIdx < total - 1) {
      nextBtn.addEventListener('click', () => { pageIdx++; renderPage(); });
    }

    // Wire TOC clicks (jump to page)
    el.querySelectorAll('.wiki-toc-item').forEach((item) => {
      item.addEventListener('click', () => {
        const target = parseInt((item as HTMLElement).dataset.page || '1', 10) - 1;
        if (target >= 0 && target < total) {
          pageIdx = target;
          renderPage();
        }
      });
    });

    // Wire entity link clicks
    el.querySelectorAll('.wiki-link').forEach((link) => {
      link.addEventListener('click', () => {
        const id = (link as HTMLElement).dataset.id;
        const name = (link as HTMLElement).dataset.name!;
        if (id) show(id, name);
        else showByName(name);
      });
    });

    // Wire back button
    el.querySelectorAll('.wiki-back').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = (btn as HTMLElement).dataset.id!;
        const name = (btn as HTMLElement).dataset.name!;
        navStack.pop();
        show(id, name);
      });
    });

    el.scrollTop = 0;
  }

  function renderFallback(name: string) {
    el.innerHTML = `
      <div class="wiki-name">${esc(name)}</div>
      <div class="wiki-summary wiki-empty">No knowledge graph data available</div>
    `;
  }

  async function show(entityId: string, entityName: string) {
    if (entityId === currentId) return;
    currentId = entityId;
    navStack.push({ id: entityId, name: entityName });
    el.innerHTML = '<div class="wiki-loading">Loading\u2026</div>';
    const data = await fetchEntity(entityId);
    if (data) {
      pages = buildPages(data);
      pageIdx = 0;
      renderPage();
    } else {
      renderFallback(entityName);
    }
  }

  async function showByName(name: string) {
    el.innerHTML = '<div class="wiki-loading">Loading\u2026</div>';
    const data = await fetchByName(name);
    if (data) {
      currentId = data.entity.id;
      navStack.push({ id: data.entity.id, name: data.entity.name });
      pages = buildPages(data);
      pageIdx = 0;
      renderPage();
    } else {
      renderFallback(name);
    }
  }

  return {
    el,
    show,
    showByName,
    clear() {
      currentId = '';
      navStack.length = 0;
      pages = [];
      pageIdx = 0;
      el.innerHTML = '<div class="wiki-empty">Click an entity to browse</div>';
    },
  };
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatRel(rel: string): string {
  return rel.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function chunk<T>(arr: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    result.push(arr.slice(i, i + size));
  }
  return result;
}
