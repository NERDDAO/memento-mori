// src/types/schema.generated.ts
var SCHEMA_VERSION = 1;

// src/state/game-state.ts
function createInitialState(playerName) {
  return {
    player: {
      name: playerName,
      archetype: "",
      level: 1,
      health: 100,
      maxHealth: 100,
      xp: 0,
      xpThreshold: 100,
      skills: {}
    },
    location: {
      name: "Unknown",
      description: "",
      exits: [],
      npcs: [],
      items: []
    },
    inventory: [],
    quests: [],
    factions: [],
    roomMap: null
  };
}
function applyStateUpdate(state, update) {
  if (update.schema_version && update.schema_version > SCHEMA_VERSION) {
    console.warn(`Server schema version ${update.schema_version} > client ${SCHEMA_VERSION}. Please refresh.`);
  }
  if (update.location)
    state.location.name = update.location;
  if (update.health != null)
    state.player.health = update.health;
  if (update.max_health != null)
    state.player.maxHealth = update.max_health;
  if (update.level != null)
    state.player.level = update.level;
  if (update.xp != null)
    state.player.xp = update.xp;
  if (update.exits)
    state.location.exits = update.exits;
  if (update.npcs)
    state.location.npcs = update.npcs;
  if (update.items)
    state.location.items = update.items;
  if (update.inventory) {
    state.inventory = update.inventory.map((i) => ({
      name: i.name || "?",
      rarity: i.rarity || "common",
      equipped: i.equipped || false
    }));
  }
  if (update.skills)
    state.player.skills = update.skills;
  if (update.room_map) {
    state.roomMap = update.room_map;
    const rm = update.room_map;
    if (rm.name)
      state.location.name = rm.name;
    if (rm.exits) {
      state.location.exits = rm.exits.map((e) => ({
        direction: e.direction || "",
        name: e.target || e.name || ""
      }));
    }
    if (rm.npcs) {
      state.location.npcs = rm.npcs.map((n) => ({
        name: n.name || "",
        id: n.id || "",
        role: n.role || ""
      }));
    }
    if (rm.items) {
      state.location.items = rm.items.map((i) => ({
        name: i.name || "",
        id: i.id || ""
      }));
    }
  }
  if (update.active_quests) {
    state.quests = update.active_quests.map((q) => ({
      name: q.name || "",
      description: q.description || "",
      currentStage: q.current_stage || 0,
      totalStages: q.total_stages || 0,
      giver: q.giver || "",
      completed: q.completed || false
    }));
  }
  if (update.factions) {
    state.factions = update.factions.map((f) => ({
      name: f.name || "",
      reputation: f.reputation || 0,
      disposition: f.disposition || "neutral"
    }));
  }
}

// src/state/session.ts
var GATEWAY_PORT = window.location.port || "8081";
var GATEWAY_URL = `${window.location.protocol}//${window.location.hostname}:${GATEWAY_PORT}`;
var WS_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:${GATEWAY_PORT}/ws`;
var session = {
  playerId: "",
  sessionId: "",
  playerName: "",
  walletAddress: "",
  currentLocation: "",
  connected: false,
  openingNarrative: ""
};
var ws = null;
var onMessage = null;
var onConnectionChange = null;
function setConnectionHandler(handler) {
  onConnectionChange = handler;
}
function getSession() {
  return session;
}
function setMessageHandler(handler) {
  onMessage = handler;
}
async function initSession(playerName, walletAddress, archetype = "") {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName, wallet_address: walletAddress, archetype })
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.walletAddress = walletAddress;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || "";
  localStorage.setItem("mm_player_id", session.playerId);
  localStorage.setItem("mm_player_name", playerName);
  localStorage.setItem("mm_wallet", walletAddress);
  connectWebSocket();
  return session;
}
function connectWebSocket() {
  ws = new WebSocket(`${WS_URL}/${session.playerId}`);
  ws.onopen = () => {
    session.connected = true;
    onConnectionChange?.(true);
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (onMessage)
      onMessage(msg);
  };
  ws.onclose = () => {
    session.connected = false;
    onConnectionChange?.(false);
    setTimeout(() => {
      if (!session.connected)
        connectWebSocket();
    }, 3000);
  };
}
async function sendAction(action) {
  await fetch(`${GATEWAY_URL}/api/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      player_id: session.playerId,
      action,
      location: session.currentLocation
    })
  });
}

// src/renderer/text-renderer.ts
var knownEntities = new Map;
function setKnownEntities(entities) {
  knownEntities = new Map;
  for (const e of entities) {
    knownEntities.set(e.name, { id: e.id, type: e.type });
  }
}
function parseNarrative(text) {
  const segments = [];
  const pattern = /"([^"]+)"|(\d+ damage)|(\d+ health|\d+ HP)/g;
  let lastIndex = 0;
  let match;
  const rawSegments = [];
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      rawSegments.push({ text: text.slice(lastIndex, match.index), style: "normal" });
    }
    if (match[1]) {
      rawSegments.push({ text: `"${match[1]}"`, style: "npc" });
    } else if (match[2]) {
      rawSegments.push({ text: match[2], style: "damage" });
    } else if (match[3]) {
      rawSegments.push({ text: match[3], style: "heal" });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    rawSegments.push({ text: text.slice(lastIndex), style: "normal" });
  }
  if (rawSegments.length === 0) {
    rawSegments.push({ text, style: "normal" });
  }
  if (knownEntities.size === 0)
    return rawSegments;
  for (const seg of rawSegments) {
    if (seg.style !== "normal") {
      segments.push(seg);
      continue;
    }
    const highlighted = highlightEntities(seg.text);
    segments.push(...highlighted);
  }
  return segments;
}
function highlightEntities(text) {
  if (knownEntities.size === 0)
    return [{ text, style: "normal" }];
  const names = Array.from(knownEntities.keys()).sort((a, b) => b.length - a.length);
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const entityPattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const segments = [];
  let lastIdx = 0;
  let m;
  while ((m = entityPattern.exec(text)) !== null) {
    if (m.index > lastIdx) {
      segments.push({ text: text.slice(lastIdx, m.index), style: "normal" });
    }
    const matchedName = m[1];
    let entityId = "";
    let entityType = "";
    for (const [name, info] of knownEntities.entries()) {
      if (name.toLowerCase() === matchedName.toLowerCase()) {
        entityId = info.id;
        entityType = info.type;
        break;
      }
    }
    segments.push({
      text: matchedName,
      style: "entity",
      entityId,
      entityType
    });
    lastIdx = m.index + matchedName.length;
  }
  if (lastIdx < text.length) {
    segments.push({ text: text.slice(lastIdx), style: "normal" });
  }
  return segments.length ? segments : [{ text, style: "normal" }];
}
function renderSegments(segments) {
  return segments.map((seg) => {
    if (seg.style === "entity" && seg.entityId) {
      const typeClass = seg.entityType ? `entity-${seg.entityType}` : "";
      return `<span class="entity-link ${typeClass}" data-entity-id="${escapeHtml(seg.entityId)}" data-entity-name="${escapeHtml(seg.text)}">${escapeHtml(seg.text)}</span>`;
    }
    const cls = seg.style === "normal" ? "" : seg.style;
    return cls ? `<span class="${cls}">${escapeHtml(seg.text)}</span>` : escapeHtml(seg.text);
  }).join("");
}
function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// node_modules/@chenglou/pretext/dist/bidi.js
var baseTypes = [
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "S",
  "B",
  "S",
  "WS",
  "B",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "B",
  "B",
  "B",
  "S",
  "WS",
  "ON",
  "ON",
  "ET",
  "ET",
  "ET",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "CS",
  "ON",
  "CS",
  "ON",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "EN",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "ON",
  "ON",
  "ON",
  "ON",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "B",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "BN",
  "CS",
  "ON",
  "ET",
  "ET",
  "ET",
  "ET",
  "ON",
  "ON",
  "ON",
  "ON",
  "L",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "ET",
  "ET",
  "EN",
  "EN",
  "ON",
  "L",
  "ON",
  "ON",
  "ON",
  "EN",
  "L",
  "ON",
  "ON",
  "ON",
  "ON",
  "ON",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "ON",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "ON",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L",
  "L"
];
var arabicTypes = [
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "CS",
  "AL",
  "ON",
  "ON",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "AN",
  "ET",
  "AN",
  "AN",
  "AL",
  "AL",
  "AL",
  "NSM",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "ON",
  "NSM",
  "NSM",
  "NSM",
  "NSM",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL",
  "AL"
];
function classifyChar(charCode) {
  if (charCode <= 255)
    return baseTypes[charCode];
  if (1424 <= charCode && charCode <= 1524)
    return "R";
  if (1536 <= charCode && charCode <= 1791)
    return arabicTypes[charCode & 255];
  if (1792 <= charCode && charCode <= 2220)
    return "AL";
  return "L";
}
function computeBidiLevels(str) {
  const len = str.length;
  if (len === 0)
    return null;
  const types = new Array(len);
  let numBidi = 0;
  for (let i = 0;i < len; i++) {
    const t = classifyChar(str.charCodeAt(i));
    if (t === "R" || t === "AL" || t === "AN")
      numBidi++;
    types[i] = t;
  }
  if (numBidi === 0)
    return null;
  const startLevel = len / numBidi < 0.3 ? 0 : 1;
  const levels = new Int8Array(len);
  for (let i = 0;i < len; i++)
    levels[i] = startLevel;
  const e = startLevel & 1 ? "R" : "L";
  const sor = e;
  let lastType = sor;
  for (let i = 0;i < len; i++) {
    if (types[i] === "NSM")
      types[i] = lastType;
    else
      lastType = types[i];
  }
  lastType = sor;
  for (let i = 0;i < len; i++) {
    const t = types[i];
    if (t === "EN")
      types[i] = lastType === "AL" ? "AN" : "EN";
    else if (t === "R" || t === "L" || t === "AL")
      lastType = t;
  }
  for (let i = 0;i < len; i++) {
    if (types[i] === "AL")
      types[i] = "R";
  }
  for (let i = 1;i < len - 1; i++) {
    if (types[i] === "ES" && types[i - 1] === "EN" && types[i + 1] === "EN") {
      types[i] = "EN";
    }
    if (types[i] === "CS" && (types[i - 1] === "EN" || types[i - 1] === "AN") && types[i + 1] === types[i - 1]) {
      types[i] = types[i - 1];
    }
  }
  for (let i = 0;i < len; i++) {
    if (types[i] !== "EN")
      continue;
    let j;
    for (j = i - 1;j >= 0 && types[j] === "ET"; j--)
      types[j] = "EN";
    for (j = i + 1;j < len && types[j] === "ET"; j++)
      types[j] = "EN";
  }
  for (let i = 0;i < len; i++) {
    const t = types[i];
    if (t === "WS" || t === "ES" || t === "ET" || t === "CS")
      types[i] = "ON";
  }
  lastType = sor;
  for (let i = 0;i < len; i++) {
    const t = types[i];
    if (t === "EN")
      types[i] = lastType === "L" ? "L" : "EN";
    else if (t === "R" || t === "L")
      lastType = t;
  }
  for (let i = 0;i < len; i++) {
    if (types[i] !== "ON")
      continue;
    let end = i + 1;
    while (end < len && types[end] === "ON")
      end++;
    const before = i > 0 ? types[i - 1] : sor;
    const after = end < len ? types[end] : sor;
    const bDir = before !== "L" ? "R" : "L";
    const aDir = after !== "L" ? "R" : "L";
    if (bDir === aDir) {
      for (let j = i;j < end; j++)
        types[j] = bDir;
    }
    i = end - 1;
  }
  for (let i = 0;i < len; i++) {
    if (types[i] === "ON")
      types[i] = e;
  }
  for (let i = 0;i < len; i++) {
    const t = types[i];
    if ((levels[i] & 1) === 0) {
      if (t === "R")
        levels[i]++;
      else if (t === "AN" || t === "EN")
        levels[i] += 2;
    } else if (t === "L" || t === "AN" || t === "EN") {
      levels[i]++;
    }
  }
  return levels;
}
function computeSegmentLevels(normalized, segStarts) {
  const bidiLevels = computeBidiLevels(normalized);
  if (bidiLevels === null)
    return null;
  const segLevels = new Int8Array(segStarts.length);
  for (let i = 0;i < segStarts.length; i++) {
    segLevels[i] = bidiLevels[segStarts[i]];
  }
  return segLevels;
}

// node_modules/@chenglou/pretext/dist/analysis.js
var collapsibleWhitespaceRunRe = /[ \t\n\r\f]+/g;
var needsWhitespaceNormalizationRe = /[\t\n\r\f]| {2,}|^ | $/;
function getWhiteSpaceProfile(whiteSpace) {
  const mode = whiteSpace ?? "normal";
  return mode === "pre-wrap" ? { mode, preserveOrdinarySpaces: true, preserveHardBreaks: true } : { mode, preserveOrdinarySpaces: false, preserveHardBreaks: false };
}
function normalizeWhitespaceNormal(text) {
  if (!needsWhitespaceNormalizationRe.test(text))
    return text;
  let normalized = text.replace(collapsibleWhitespaceRunRe, " ");
  if (normalized.charCodeAt(0) === 32) {
    normalized = normalized.slice(1);
  }
  if (normalized.length > 0 && normalized.charCodeAt(normalized.length - 1) === 32) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
}
function normalizeWhitespacePreWrap(text) {
  if (!/[\r\f]/.test(text))
    return text.replace(/\r\n/g, `
`);
  return text.replace(/\r\n/g, `
`).replace(/[\r\f]/g, `
`);
}
var sharedWordSegmenter = null;
var segmenterLocale;
function getSharedWordSegmenter() {
  if (sharedWordSegmenter === null) {
    sharedWordSegmenter = new Intl.Segmenter(segmenterLocale, { granularity: "word" });
  }
  return sharedWordSegmenter;
}
var arabicScriptRe = /\p{Script=Arabic}/u;
var combiningMarkRe = /\p{M}/u;
var decimalDigitRe = /\p{Nd}/u;
function containsArabicScript(text) {
  return arabicScriptRe.test(text);
}
function isCJK(s) {
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (c >= 19968 && c <= 40959 || c >= 13312 && c <= 19903 || c >= 131072 && c <= 173791 || c >= 173824 && c <= 177983 || c >= 177984 && c <= 178207 || c >= 178208 && c <= 183983 || c >= 183984 && c <= 191471 || c >= 196608 && c <= 201551 || c >= 63744 && c <= 64255 || c >= 194560 && c <= 195103 || c >= 12288 && c <= 12351 || c >= 12352 && c <= 12447 || c >= 12448 && c <= 12543 || c >= 44032 && c <= 55215 || c >= 65280 && c <= 65519) {
      return true;
    }
  }
  return false;
}
var kinsokuStart = new Set([
  "，",
  "．",
  "！",
  "：",
  "；",
  "？",
  "、",
  "。",
  "・",
  "）",
  "〕",
  "〉",
  "》",
  "」",
  "』",
  "】",
  "〗",
  "〙",
  "〛",
  "ー",
  "々",
  "〻",
  "ゝ",
  "ゞ",
  "ヽ",
  "ヾ"
]);
var kinsokuEnd = new Set([
  '"',
  "(",
  "[",
  "{",
  "“",
  "‘",
  "«",
  "‹",
  "（",
  "〔",
  "〈",
  "《",
  "「",
  "『",
  "【",
  "〖",
  "〘",
  "〚"
]);
var forwardStickyGlue = new Set([
  "'",
  "’"
]);
var leftStickyPunctuation = new Set([
  ".",
  ",",
  "!",
  "?",
  ":",
  ";",
  "،",
  "؛",
  "؟",
  "।",
  "॥",
  "၊",
  "။",
  "၌",
  "၍",
  "၏",
  ")",
  "]",
  "}",
  "%",
  '"',
  "”",
  "’",
  "»",
  "›",
  "…"
]);
var arabicNoSpaceTrailingPunctuation = new Set([
  ":",
  ".",
  "،",
  "؛"
]);
var myanmarMedialGlue = new Set([
  "၏"
]);
var closingQuoteChars = new Set([
  "”",
  "’",
  "»",
  "›",
  "」",
  "』",
  "】",
  "》",
  "〉",
  "〕",
  "）"
]);
function isLeftStickyPunctuationSegment(segment) {
  if (isEscapedQuoteClusterSegment(segment))
    return true;
  let sawPunctuation = false;
  for (const ch of segment) {
    if (leftStickyPunctuation.has(ch)) {
      sawPunctuation = true;
      continue;
    }
    if (sawPunctuation && combiningMarkRe.test(ch))
      continue;
    return false;
  }
  return sawPunctuation;
}
function isCJKLineStartProhibitedSegment(segment) {
  for (const ch of segment) {
    if (!kinsokuStart.has(ch) && !leftStickyPunctuation.has(ch))
      return false;
  }
  return segment.length > 0;
}
function isForwardStickyClusterSegment(segment) {
  if (isEscapedQuoteClusterSegment(segment))
    return true;
  for (const ch of segment) {
    if (!kinsokuEnd.has(ch) && !forwardStickyGlue.has(ch) && !combiningMarkRe.test(ch))
      return false;
  }
  return segment.length > 0;
}
function isEscapedQuoteClusterSegment(segment) {
  let sawQuote = false;
  for (const ch of segment) {
    if (ch === "\\" || combiningMarkRe.test(ch))
      continue;
    if (kinsokuEnd.has(ch) || leftStickyPunctuation.has(ch) || forwardStickyGlue.has(ch)) {
      sawQuote = true;
      continue;
    }
    return false;
  }
  return sawQuote;
}
function splitTrailingForwardStickyCluster(text) {
  const chars = Array.from(text);
  let splitIndex = chars.length;
  while (splitIndex > 0) {
    const ch = chars[splitIndex - 1];
    if (combiningMarkRe.test(ch)) {
      splitIndex--;
      continue;
    }
    if (kinsokuEnd.has(ch) || forwardStickyGlue.has(ch)) {
      splitIndex--;
      continue;
    }
    break;
  }
  if (splitIndex <= 0 || splitIndex === chars.length)
    return null;
  return {
    head: chars.slice(0, splitIndex).join(""),
    tail: chars.slice(splitIndex).join("")
  };
}
function isRepeatedSingleCharRun(segment, ch) {
  if (segment.length === 0)
    return false;
  for (const part of segment) {
    if (part !== ch)
      return false;
  }
  return true;
}
function endsWithArabicNoSpacePunctuation(segment) {
  if (!containsArabicScript(segment) || segment.length === 0)
    return false;
  return arabicNoSpaceTrailingPunctuation.has(segment[segment.length - 1]);
}
function endsWithMyanmarMedialGlue(segment) {
  if (segment.length === 0)
    return false;
  return myanmarMedialGlue.has(segment[segment.length - 1]);
}
function splitLeadingSpaceAndMarks(segment) {
  if (segment.length < 2 || segment[0] !== " ")
    return null;
  const marks = segment.slice(1);
  if (/^\p{M}+$/u.test(marks)) {
    return { space: " ", marks };
  }
  return null;
}
function endsWithClosingQuote(text) {
  for (let i = text.length - 1;i >= 0; i--) {
    const ch = text[i];
    if (closingQuoteChars.has(ch))
      return true;
    if (!leftStickyPunctuation.has(ch))
      return false;
  }
  return false;
}
function classifySegmentBreakChar(ch, whiteSpaceProfile) {
  if (whiteSpaceProfile.preserveOrdinarySpaces || whiteSpaceProfile.preserveHardBreaks) {
    if (ch === " ")
      return "preserved-space";
    if (ch === "\t")
      return "tab";
    if (whiteSpaceProfile.preserveHardBreaks && ch === `
`)
      return "hard-break";
  }
  if (ch === " ")
    return "space";
  if (ch === " " || ch === " " || ch === "⁠" || ch === "\uFEFF") {
    return "glue";
  }
  if (ch === "​")
    return "zero-width-break";
  if (ch === "­")
    return "soft-hyphen";
  return "text";
}
function splitSegmentByBreakKind(segment, isWordLike, start, whiteSpaceProfile) {
  const pieces = [];
  let currentKind = null;
  let currentText = "";
  let currentStart = start;
  let currentWordLike = false;
  let offset = 0;
  for (const ch of segment) {
    const kind = classifySegmentBreakChar(ch, whiteSpaceProfile);
    const wordLike = kind === "text" && isWordLike;
    if (currentKind !== null && kind === currentKind && wordLike === currentWordLike) {
      currentText += ch;
      offset += ch.length;
      continue;
    }
    if (currentKind !== null) {
      pieces.push({
        text: currentText,
        isWordLike: currentWordLike,
        kind: currentKind,
        start: currentStart
      });
    }
    currentKind = kind;
    currentText = ch;
    currentStart = start + offset;
    currentWordLike = wordLike;
    offset += ch.length;
  }
  if (currentKind !== null) {
    pieces.push({
      text: currentText,
      isWordLike: currentWordLike,
      kind: currentKind,
      start: currentStart
    });
  }
  return pieces;
}
function isTextRunBoundary(kind) {
  return kind === "space" || kind === "preserved-space" || kind === "zero-width-break" || kind === "hard-break";
}
var urlSchemeSegmentRe = /^[A-Za-z][A-Za-z0-9+.-]*:$/;
function isUrlLikeRunStart(segmentation, index) {
  const text = segmentation.texts[index];
  if (text.startsWith("www."))
    return true;
  return urlSchemeSegmentRe.test(text) && index + 1 < segmentation.len && segmentation.kinds[index + 1] === "text" && segmentation.texts[index + 1] === "//";
}
function isUrlQueryBoundarySegment(text) {
  return text.includes("?") && (text.includes("://") || text.startsWith("www."));
}
function mergeUrlLikeRuns(segmentation) {
  const texts = segmentation.texts.slice();
  const isWordLike = segmentation.isWordLike.slice();
  const kinds = segmentation.kinds.slice();
  const starts = segmentation.starts.slice();
  for (let i = 0;i < segmentation.len; i++) {
    if (kinds[i] !== "text" || !isUrlLikeRunStart(segmentation, i))
      continue;
    let j = i + 1;
    while (j < segmentation.len && !isTextRunBoundary(kinds[j])) {
      texts[i] += texts[j];
      isWordLike[i] = true;
      const endsQueryPrefix = texts[j].includes("?");
      kinds[j] = "text";
      texts[j] = "";
      j++;
      if (endsQueryPrefix)
        break;
    }
  }
  let compactLen = 0;
  for (let read = 0;read < texts.length; read++) {
    const text = texts[read];
    if (text.length === 0)
      continue;
    if (compactLen !== read) {
      texts[compactLen] = text;
      isWordLike[compactLen] = isWordLike[read];
      kinds[compactLen] = kinds[read];
      starts[compactLen] = starts[read];
    }
    compactLen++;
  }
  texts.length = compactLen;
  isWordLike.length = compactLen;
  kinds.length = compactLen;
  starts.length = compactLen;
  return {
    len: compactLen,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function mergeUrlQueryRuns(segmentation) {
  const texts = [];
  const isWordLike = [];
  const kinds = [];
  const starts = [];
  for (let i = 0;i < segmentation.len; i++) {
    const text = segmentation.texts[i];
    texts.push(text);
    isWordLike.push(segmentation.isWordLike[i]);
    kinds.push(segmentation.kinds[i]);
    starts.push(segmentation.starts[i]);
    if (!isUrlQueryBoundarySegment(text))
      continue;
    const nextIndex = i + 1;
    if (nextIndex >= segmentation.len || isTextRunBoundary(segmentation.kinds[nextIndex])) {
      continue;
    }
    let queryText = "";
    const queryStart = segmentation.starts[nextIndex];
    let j = nextIndex;
    while (j < segmentation.len && !isTextRunBoundary(segmentation.kinds[j])) {
      queryText += segmentation.texts[j];
      j++;
    }
    if (queryText.length > 0) {
      texts.push(queryText);
      isWordLike.push(true);
      kinds.push("text");
      starts.push(queryStart);
      i = j - 1;
    }
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
var numericJoinerChars = new Set([
  ":",
  "-",
  "/",
  "×",
  ",",
  ".",
  "+",
  "–",
  "—"
]);
var asciiPunctuationChainSegmentRe = /^[A-Za-z0-9_]+[,:;]*$/;
var asciiPunctuationChainTrailingJoinersRe = /[,:;]+$/;
function segmentContainsDecimalDigit(text) {
  for (const ch of text) {
    if (decimalDigitRe.test(ch))
      return true;
  }
  return false;
}
function isNumericRunSegment(text) {
  if (text.length === 0)
    return false;
  for (const ch of text) {
    if (decimalDigitRe.test(ch) || numericJoinerChars.has(ch))
      continue;
    return false;
  }
  return true;
}
function mergeNumericRuns(segmentation) {
  const texts = [];
  const isWordLike = [];
  const kinds = [];
  const starts = [];
  for (let i = 0;i < segmentation.len; i++) {
    const text = segmentation.texts[i];
    const kind = segmentation.kinds[i];
    if (kind === "text" && isNumericRunSegment(text) && segmentContainsDecimalDigit(text)) {
      let mergedText = text;
      let j = i + 1;
      while (j < segmentation.len && segmentation.kinds[j] === "text" && isNumericRunSegment(segmentation.texts[j])) {
        mergedText += segmentation.texts[j];
        j++;
      }
      texts.push(mergedText);
      isWordLike.push(true);
      kinds.push("text");
      starts.push(segmentation.starts[i]);
      i = j - 1;
      continue;
    }
    texts.push(text);
    isWordLike.push(segmentation.isWordLike[i]);
    kinds.push(kind);
    starts.push(segmentation.starts[i]);
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function mergeAsciiPunctuationChains(segmentation) {
  const texts = [];
  const isWordLike = [];
  const kinds = [];
  const starts = [];
  for (let i = 0;i < segmentation.len; i++) {
    const text = segmentation.texts[i];
    const kind = segmentation.kinds[i];
    const wordLike = segmentation.isWordLike[i];
    if (kind === "text" && wordLike && asciiPunctuationChainSegmentRe.test(text)) {
      let mergedText = text;
      let j = i + 1;
      while (asciiPunctuationChainTrailingJoinersRe.test(mergedText) && j < segmentation.len && segmentation.kinds[j] === "text" && segmentation.isWordLike[j] && asciiPunctuationChainSegmentRe.test(segmentation.texts[j])) {
        mergedText += segmentation.texts[j];
        j++;
      }
      texts.push(mergedText);
      isWordLike.push(true);
      kinds.push("text");
      starts.push(segmentation.starts[i]);
      i = j - 1;
      continue;
    }
    texts.push(text);
    isWordLike.push(wordLike);
    kinds.push(kind);
    starts.push(segmentation.starts[i]);
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function splitHyphenatedNumericRuns(segmentation) {
  const texts = [];
  const isWordLike = [];
  const kinds = [];
  const starts = [];
  for (let i = 0;i < segmentation.len; i++) {
    const text = segmentation.texts[i];
    if (segmentation.kinds[i] === "text" && text.includes("-")) {
      const parts = text.split("-");
      let shouldSplit = parts.length > 1;
      for (let j = 0;j < parts.length; j++) {
        const part = parts[j];
        if (!shouldSplit)
          break;
        if (part.length === 0 || !segmentContainsDecimalDigit(part) || !isNumericRunSegment(part)) {
          shouldSplit = false;
        }
      }
      if (shouldSplit) {
        let offset = 0;
        for (let j = 0;j < parts.length; j++) {
          const part = parts[j];
          const splitText = j < parts.length - 1 ? `${part}-` : part;
          texts.push(splitText);
          isWordLike.push(true);
          kinds.push("text");
          starts.push(segmentation.starts[i] + offset);
          offset += splitText.length;
        }
        continue;
      }
    }
    texts.push(text);
    isWordLike.push(segmentation.isWordLike[i]);
    kinds.push(segmentation.kinds[i]);
    starts.push(segmentation.starts[i]);
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function mergeGlueConnectedTextRuns(segmentation) {
  const texts = [];
  const isWordLike = [];
  const kinds = [];
  const starts = [];
  let read = 0;
  while (read < segmentation.len) {
    let text = segmentation.texts[read];
    let wordLike = segmentation.isWordLike[read];
    let kind = segmentation.kinds[read];
    let start = segmentation.starts[read];
    if (kind === "glue") {
      let glueText = text;
      const glueStart = start;
      read++;
      while (read < segmentation.len && segmentation.kinds[read] === "glue") {
        glueText += segmentation.texts[read];
        read++;
      }
      if (read < segmentation.len && segmentation.kinds[read] === "text") {
        text = glueText + segmentation.texts[read];
        wordLike = segmentation.isWordLike[read];
        kind = "text";
        start = glueStart;
        read++;
      } else {
        texts.push(glueText);
        isWordLike.push(false);
        kinds.push("glue");
        starts.push(glueStart);
        continue;
      }
    } else {
      read++;
    }
    if (kind === "text") {
      while (read < segmentation.len && segmentation.kinds[read] === "glue") {
        let glueText = "";
        while (read < segmentation.len && segmentation.kinds[read] === "glue") {
          glueText += segmentation.texts[read];
          read++;
        }
        if (read < segmentation.len && segmentation.kinds[read] === "text") {
          text += glueText + segmentation.texts[read];
          wordLike = wordLike || segmentation.isWordLike[read];
          read++;
          continue;
        }
        text += glueText;
      }
    }
    texts.push(text);
    isWordLike.push(wordLike);
    kinds.push(kind);
    starts.push(start);
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function carryTrailingForwardStickyAcrossCJKBoundary(segmentation) {
  const texts = segmentation.texts.slice();
  const isWordLike = segmentation.isWordLike.slice();
  const kinds = segmentation.kinds.slice();
  const starts = segmentation.starts.slice();
  for (let i = 0;i < texts.length - 1; i++) {
    if (kinds[i] !== "text" || kinds[i + 1] !== "text")
      continue;
    if (!isCJK(texts[i]) || !isCJK(texts[i + 1]))
      continue;
    const split = splitTrailingForwardStickyCluster(texts[i]);
    if (split === null)
      continue;
    texts[i] = split.head;
    texts[i + 1] = split.tail + texts[i + 1];
    starts[i + 1] = starts[i] + split.head.length;
  }
  return {
    len: texts.length,
    texts,
    isWordLike,
    kinds,
    starts
  };
}
function buildMergedSegmentation(normalized, profile, whiteSpaceProfile) {
  const wordSegmenter = getSharedWordSegmenter();
  let mergedLen = 0;
  const mergedTexts = [];
  const mergedWordLike = [];
  const mergedKinds = [];
  const mergedStarts = [];
  for (const s of wordSegmenter.segment(normalized)) {
    for (const piece of splitSegmentByBreakKind(s.segment, s.isWordLike ?? false, s.index, whiteSpaceProfile)) {
      const isText = piece.kind === "text";
      if (profile.carryCJKAfterClosingQuote && isText && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && isCJK(piece.text) && isCJK(mergedTexts[mergedLen - 1]) && endsWithClosingQuote(mergedTexts[mergedLen - 1])) {
        mergedTexts[mergedLen - 1] += piece.text;
        mergedWordLike[mergedLen - 1] = mergedWordLike[mergedLen - 1] || piece.isWordLike;
      } else if (isText && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && isCJKLineStartProhibitedSegment(piece.text) && isCJK(mergedTexts[mergedLen - 1])) {
        mergedTexts[mergedLen - 1] += piece.text;
        mergedWordLike[mergedLen - 1] = mergedWordLike[mergedLen - 1] || piece.isWordLike;
      } else if (isText && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && endsWithMyanmarMedialGlue(mergedTexts[mergedLen - 1])) {
        mergedTexts[mergedLen - 1] += piece.text;
        mergedWordLike[mergedLen - 1] = mergedWordLike[mergedLen - 1] || piece.isWordLike;
      } else if (isText && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && piece.isWordLike && containsArabicScript(piece.text) && endsWithArabicNoSpacePunctuation(mergedTexts[mergedLen - 1])) {
        mergedTexts[mergedLen - 1] += piece.text;
        mergedWordLike[mergedLen - 1] = true;
      } else if (isText && !piece.isWordLike && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && piece.text.length === 1 && piece.text !== "-" && piece.text !== "—" && isRepeatedSingleCharRun(mergedTexts[mergedLen - 1], piece.text)) {
        mergedTexts[mergedLen - 1] += piece.text;
      } else if (isText && !piece.isWordLike && mergedLen > 0 && mergedKinds[mergedLen - 1] === "text" && (isLeftStickyPunctuationSegment(piece.text) || piece.text === "-" && mergedWordLike[mergedLen - 1])) {
        mergedTexts[mergedLen - 1] += piece.text;
      } else {
        mergedTexts[mergedLen] = piece.text;
        mergedWordLike[mergedLen] = piece.isWordLike;
        mergedKinds[mergedLen] = piece.kind;
        mergedStarts[mergedLen] = piece.start;
        mergedLen++;
      }
    }
  }
  for (let i = 1;i < mergedLen; i++) {
    if (mergedKinds[i] === "text" && !mergedWordLike[i] && isEscapedQuoteClusterSegment(mergedTexts[i]) && mergedKinds[i - 1] === "text") {
      mergedTexts[i - 1] += mergedTexts[i];
      mergedWordLike[i - 1] = mergedWordLike[i - 1] || mergedWordLike[i];
      mergedTexts[i] = "";
    }
  }
  for (let i = mergedLen - 2;i >= 0; i--) {
    if (mergedKinds[i] === "text" && !mergedWordLike[i] && isForwardStickyClusterSegment(mergedTexts[i])) {
      let j = i + 1;
      while (j < mergedLen && mergedTexts[j] === "")
        j++;
      if (j < mergedLen && mergedKinds[j] === "text") {
        mergedTexts[j] = mergedTexts[i] + mergedTexts[j];
        mergedStarts[j] = mergedStarts[i];
        mergedTexts[i] = "";
      }
    }
  }
  let compactLen = 0;
  for (let read = 0;read < mergedLen; read++) {
    const text = mergedTexts[read];
    if (text.length === 0)
      continue;
    if (compactLen !== read) {
      mergedTexts[compactLen] = text;
      mergedWordLike[compactLen] = mergedWordLike[read];
      mergedKinds[compactLen] = mergedKinds[read];
      mergedStarts[compactLen] = mergedStarts[read];
    }
    compactLen++;
  }
  mergedTexts.length = compactLen;
  mergedWordLike.length = compactLen;
  mergedKinds.length = compactLen;
  mergedStarts.length = compactLen;
  const compacted = mergeGlueConnectedTextRuns({
    len: compactLen,
    texts: mergedTexts,
    isWordLike: mergedWordLike,
    kinds: mergedKinds,
    starts: mergedStarts
  });
  const withMergedUrls = carryTrailingForwardStickyAcrossCJKBoundary(mergeAsciiPunctuationChains(splitHyphenatedNumericRuns(mergeNumericRuns(mergeUrlQueryRuns(mergeUrlLikeRuns(compacted))))));
  for (let i = 0;i < withMergedUrls.len - 1; i++) {
    const split = splitLeadingSpaceAndMarks(withMergedUrls.texts[i]);
    if (split === null)
      continue;
    if (withMergedUrls.kinds[i] !== "space" && withMergedUrls.kinds[i] !== "preserved-space" || withMergedUrls.kinds[i + 1] !== "text" || !containsArabicScript(withMergedUrls.texts[i + 1])) {
      continue;
    }
    withMergedUrls.texts[i] = split.space;
    withMergedUrls.isWordLike[i] = false;
    withMergedUrls.kinds[i] = withMergedUrls.kinds[i] === "preserved-space" ? "preserved-space" : "space";
    withMergedUrls.texts[i + 1] = split.marks + withMergedUrls.texts[i + 1];
    withMergedUrls.starts[i + 1] = withMergedUrls.starts[i] + split.space.length;
  }
  return withMergedUrls;
}
function compileAnalysisChunks(segmentation, whiteSpaceProfile) {
  if (segmentation.len === 0)
    return [];
  if (!whiteSpaceProfile.preserveHardBreaks) {
    return [{
      startSegmentIndex: 0,
      endSegmentIndex: segmentation.len,
      consumedEndSegmentIndex: segmentation.len
    }];
  }
  const chunks = [];
  let startSegmentIndex = 0;
  for (let i = 0;i < segmentation.len; i++) {
    if (segmentation.kinds[i] !== "hard-break")
      continue;
    chunks.push({
      startSegmentIndex,
      endSegmentIndex: i,
      consumedEndSegmentIndex: i + 1
    });
    startSegmentIndex = i + 1;
  }
  if (startSegmentIndex < segmentation.len) {
    chunks.push({
      startSegmentIndex,
      endSegmentIndex: segmentation.len,
      consumedEndSegmentIndex: segmentation.len
    });
  }
  return chunks;
}
function analyzeText(text, profile, whiteSpace = "normal") {
  const whiteSpaceProfile = getWhiteSpaceProfile(whiteSpace);
  const normalized = whiteSpaceProfile.mode === "pre-wrap" ? normalizeWhitespacePreWrap(text) : normalizeWhitespaceNormal(text);
  if (normalized.length === 0) {
    return {
      normalized,
      chunks: [],
      len: 0,
      texts: [],
      isWordLike: [],
      kinds: [],
      starts: []
    };
  }
  const segmentation = buildMergedSegmentation(normalized, profile, whiteSpaceProfile);
  return {
    normalized,
    chunks: compileAnalysisChunks(segmentation, whiteSpaceProfile),
    ...segmentation
  };
}

// node_modules/@chenglou/pretext/dist/measurement.js
var measureContext = null;
var segmentMetricCaches = new Map;
var cachedEngineProfile = null;
var emojiPresentationRe = /\p{Emoji_Presentation}/u;
var maybeEmojiRe = /[\p{Emoji_Presentation}\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\u20E3]/u;
var sharedGraphemeSegmenter = null;
var emojiCorrectionCache = new Map;
function getMeasureContext() {
  if (measureContext !== null)
    return measureContext;
  if (typeof OffscreenCanvas !== "undefined") {
    measureContext = new OffscreenCanvas(1, 1).getContext("2d");
    return measureContext;
  }
  if (typeof document !== "undefined") {
    measureContext = document.createElement("canvas").getContext("2d");
    return measureContext;
  }
  throw new Error("Text measurement requires OffscreenCanvas or a DOM canvas context.");
}
function getSegmentMetricCache(font) {
  let cache = segmentMetricCaches.get(font);
  if (!cache) {
    cache = new Map;
    segmentMetricCaches.set(font, cache);
  }
  return cache;
}
function getSegmentMetrics(seg, cache) {
  let metrics = cache.get(seg);
  if (metrics === undefined) {
    const ctx = getMeasureContext();
    metrics = {
      width: ctx.measureText(seg).width,
      containsCJK: isCJK(seg)
    };
    cache.set(seg, metrics);
  }
  return metrics;
}
function getEngineProfile() {
  if (cachedEngineProfile !== null)
    return cachedEngineProfile;
  if (typeof navigator === "undefined") {
    cachedEngineProfile = {
      lineFitEpsilon: 0.005,
      carryCJKAfterClosingQuote: false,
      preferPrefixWidthsForBreakableRuns: false,
      preferEarlySoftHyphenBreak: false
    };
    return cachedEngineProfile;
  }
  const ua = navigator.userAgent;
  const vendor = navigator.vendor;
  const isSafari = vendor === "Apple Computer, Inc." && ua.includes("Safari/") && !ua.includes("Chrome/") && !ua.includes("Chromium/") && !ua.includes("CriOS/") && !ua.includes("FxiOS/") && !ua.includes("EdgiOS/");
  const isChromium = ua.includes("Chrome/") || ua.includes("Chromium/") || ua.includes("CriOS/") || ua.includes("Edg/");
  cachedEngineProfile = {
    lineFitEpsilon: isSafari ? 1 / 64 : 0.005,
    carryCJKAfterClosingQuote: isChromium,
    preferPrefixWidthsForBreakableRuns: isSafari,
    preferEarlySoftHyphenBreak: isSafari
  };
  return cachedEngineProfile;
}
function parseFontSize(font) {
  const m = font.match(/(\d+(?:\.\d+)?)\s*px/);
  return m ? parseFloat(m[1]) : 16;
}
function getSharedGraphemeSegmenter() {
  if (sharedGraphemeSegmenter === null) {
    sharedGraphemeSegmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  }
  return sharedGraphemeSegmenter;
}
function isEmojiGrapheme(g) {
  return emojiPresentationRe.test(g) || g.includes("️");
}
function textMayContainEmoji(text) {
  return maybeEmojiRe.test(text);
}
function getEmojiCorrection(font, fontSize) {
  let correction = emojiCorrectionCache.get(font);
  if (correction !== undefined)
    return correction;
  const ctx = getMeasureContext();
  ctx.font = font;
  const canvasW = ctx.measureText("\uD83D\uDE00").width;
  correction = 0;
  if (canvasW > fontSize + 0.5 && typeof document !== "undefined" && document.body !== null) {
    const span = document.createElement("span");
    span.style.font = font;
    span.style.display = "inline-block";
    span.style.visibility = "hidden";
    span.style.position = "absolute";
    span.textContent = "\uD83D\uDE00";
    document.body.appendChild(span);
    const domW = span.getBoundingClientRect().width;
    document.body.removeChild(span);
    if (canvasW - domW > 0.5) {
      correction = canvasW - domW;
    }
  }
  emojiCorrectionCache.set(font, correction);
  return correction;
}
function countEmojiGraphemes(text) {
  let count = 0;
  const graphemeSegmenter = getSharedGraphemeSegmenter();
  for (const g of graphemeSegmenter.segment(text)) {
    if (isEmojiGrapheme(g.segment))
      count++;
  }
  return count;
}
function getEmojiCount(seg, metrics) {
  if (metrics.emojiCount === undefined) {
    metrics.emojiCount = countEmojiGraphemes(seg);
  }
  return metrics.emojiCount;
}
function getCorrectedSegmentWidth(seg, metrics, emojiCorrection) {
  if (emojiCorrection === 0)
    return metrics.width;
  return metrics.width - getEmojiCount(seg, metrics) * emojiCorrection;
}
function getSegmentGraphemeWidths(seg, metrics, cache, emojiCorrection) {
  if (metrics.graphemeWidths !== undefined)
    return metrics.graphemeWidths;
  const widths = [];
  const graphemeSegmenter = getSharedGraphemeSegmenter();
  for (const gs of graphemeSegmenter.segment(seg)) {
    const graphemeMetrics = getSegmentMetrics(gs.segment, cache);
    widths.push(getCorrectedSegmentWidth(gs.segment, graphemeMetrics, emojiCorrection));
  }
  metrics.graphemeWidths = widths.length > 1 ? widths : null;
  return metrics.graphemeWidths;
}
function getSegmentGraphemePrefixWidths(seg, metrics, cache, emojiCorrection) {
  if (metrics.graphemePrefixWidths !== undefined)
    return metrics.graphemePrefixWidths;
  const prefixWidths = [];
  const graphemeSegmenter = getSharedGraphemeSegmenter();
  let prefix = "";
  for (const gs of graphemeSegmenter.segment(seg)) {
    prefix += gs.segment;
    const prefixMetrics = getSegmentMetrics(prefix, cache);
    prefixWidths.push(getCorrectedSegmentWidth(prefix, prefixMetrics, emojiCorrection));
  }
  metrics.graphemePrefixWidths = prefixWidths.length > 1 ? prefixWidths : null;
  return metrics.graphemePrefixWidths;
}
function getFontMeasurementState(font, needsEmojiCorrection) {
  const ctx = getMeasureContext();
  ctx.font = font;
  const cache = getSegmentMetricCache(font);
  const fontSize = parseFontSize(font);
  const emojiCorrection = needsEmojiCorrection ? getEmojiCorrection(font, fontSize) : 0;
  return { cache, fontSize, emojiCorrection };
}

// node_modules/@chenglou/pretext/dist/line-break.js
function canBreakAfter(kind) {
  return kind === "space" || kind === "preserved-space" || kind === "tab" || kind === "zero-width-break" || kind === "soft-hyphen";
}
function isSimpleCollapsibleSpace(kind) {
  return kind === "space";
}
function getTabAdvance(lineWidth, tabStopAdvance) {
  if (tabStopAdvance <= 0)
    return 0;
  const remainder = lineWidth % tabStopAdvance;
  if (Math.abs(remainder) <= 0.000001)
    return tabStopAdvance;
  return tabStopAdvance - remainder;
}
function getBreakableAdvance(graphemeWidths, graphemePrefixWidths, graphemeIndex, preferPrefixWidths) {
  if (!preferPrefixWidths || graphemePrefixWidths === null) {
    return graphemeWidths[graphemeIndex];
  }
  return graphemePrefixWidths[graphemeIndex] - (graphemeIndex > 0 ? graphemePrefixWidths[graphemeIndex - 1] : 0);
}
function fitSoftHyphenBreak(graphemeWidths, initialWidth, maxWidth, lineFitEpsilon, discretionaryHyphenWidth, cumulativeWidths) {
  let fitCount = 0;
  let fittedWidth = initialWidth;
  while (fitCount < graphemeWidths.length) {
    const nextWidth = cumulativeWidths ? initialWidth + graphemeWidths[fitCount] : fittedWidth + graphemeWidths[fitCount];
    const nextLineWidth = fitCount + 1 < graphemeWidths.length ? nextWidth + discretionaryHyphenWidth : nextWidth;
    if (nextLineWidth > maxWidth + lineFitEpsilon)
      break;
    fittedWidth = nextWidth;
    fitCount++;
  }
  return { fitCount, fittedWidth };
}
function findChunkIndexForStart(prepared, segmentIndex) {
  for (let i = 0;i < prepared.chunks.length; i++) {
    const chunk = prepared.chunks[i];
    if (segmentIndex < chunk.consumedEndSegmentIndex)
      return i;
  }
  return -1;
}
function normalizeLineStart(prepared, start) {
  let segmentIndex = start.segmentIndex;
  const graphemeIndex = start.graphemeIndex;
  if (segmentIndex >= prepared.widths.length)
    return null;
  if (graphemeIndex > 0)
    return start;
  const chunkIndex = findChunkIndexForStart(prepared, segmentIndex);
  if (chunkIndex < 0)
    return null;
  const chunk = prepared.chunks[chunkIndex];
  if (chunk.startSegmentIndex === chunk.endSegmentIndex && segmentIndex === chunk.startSegmentIndex) {
    return { segmentIndex, graphemeIndex: 0 };
  }
  if (segmentIndex < chunk.startSegmentIndex)
    segmentIndex = chunk.startSegmentIndex;
  while (segmentIndex < chunk.endSegmentIndex) {
    const kind = prepared.kinds[segmentIndex];
    if (kind !== "space" && kind !== "zero-width-break" && kind !== "soft-hyphen") {
      return { segmentIndex, graphemeIndex: 0 };
    }
    segmentIndex++;
  }
  if (chunk.consumedEndSegmentIndex >= prepared.widths.length)
    return null;
  return { segmentIndex: chunk.consumedEndSegmentIndex, graphemeIndex: 0 };
}
function countPreparedLines(prepared, maxWidth) {
  if (prepared.simpleLineWalkFastPath) {
    return countPreparedLinesSimple(prepared, maxWidth);
  }
  return walkPreparedLines(prepared, maxWidth);
}
function countPreparedLinesSimple(prepared, maxWidth) {
  const { widths, kinds, breakableWidths, breakablePrefixWidths } = prepared;
  if (widths.length === 0)
    return 0;
  const engineProfile = getEngineProfile();
  const lineFitEpsilon = engineProfile.lineFitEpsilon;
  let lineCount = 0;
  let lineW = 0;
  let hasContent = false;
  function placeOnFreshLine(segmentIndex) {
    const w = widths[segmentIndex];
    if (w > maxWidth && breakableWidths[segmentIndex] !== null) {
      const gWidths = breakableWidths[segmentIndex];
      const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null;
      lineW = 0;
      for (let g = 0;g < gWidths.length; g++) {
        const gw = getBreakableAdvance(gWidths, gPrefixWidths, g, engineProfile.preferPrefixWidthsForBreakableRuns);
        if (lineW > 0 && lineW + gw > maxWidth + lineFitEpsilon) {
          lineCount++;
          lineW = gw;
        } else {
          if (lineW === 0)
            lineCount++;
          lineW += gw;
        }
      }
    } else {
      lineW = w;
      lineCount++;
    }
    hasContent = true;
  }
  for (let i = 0;i < widths.length; i++) {
    const w = widths[i];
    const kind = kinds[i];
    if (!hasContent) {
      placeOnFreshLine(i);
      continue;
    }
    const newW = lineW + w;
    if (newW > maxWidth + lineFitEpsilon) {
      if (isSimpleCollapsibleSpace(kind))
        continue;
      lineW = 0;
      hasContent = false;
      placeOnFreshLine(i);
      continue;
    }
    lineW = newW;
  }
  if (!hasContent)
    return lineCount + 1;
  return lineCount;
}
function walkPreparedLinesSimple(prepared, maxWidth, onLine) {
  const { widths, kinds, breakableWidths, breakablePrefixWidths } = prepared;
  if (widths.length === 0)
    return 0;
  const engineProfile = getEngineProfile();
  const lineFitEpsilon = engineProfile.lineFitEpsilon;
  let lineCount = 0;
  let lineW = 0;
  let hasContent = false;
  let lineStartSegmentIndex = 0;
  let lineStartGraphemeIndex = 0;
  let lineEndSegmentIndex = 0;
  let lineEndGraphemeIndex = 0;
  let pendingBreakSegmentIndex = -1;
  let pendingBreakPaintWidth = 0;
  function clearPendingBreak() {
    pendingBreakSegmentIndex = -1;
    pendingBreakPaintWidth = 0;
  }
  function emitCurrentLine(endSegmentIndex = lineEndSegmentIndex, endGraphemeIndex = lineEndGraphemeIndex, width = lineW) {
    lineCount++;
    onLine?.({
      startSegmentIndex: lineStartSegmentIndex,
      startGraphemeIndex: lineStartGraphemeIndex,
      endSegmentIndex,
      endGraphemeIndex,
      width
    });
    lineW = 0;
    hasContent = false;
    clearPendingBreak();
  }
  function startLineAtSegment(segmentIndex, width) {
    hasContent = true;
    lineStartSegmentIndex = segmentIndex;
    lineStartGraphemeIndex = 0;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
    lineW = width;
  }
  function startLineAtGrapheme(segmentIndex, graphemeIndex, width) {
    hasContent = true;
    lineStartSegmentIndex = segmentIndex;
    lineStartGraphemeIndex = graphemeIndex;
    lineEndSegmentIndex = segmentIndex;
    lineEndGraphemeIndex = graphemeIndex + 1;
    lineW = width;
  }
  function appendWholeSegment(segmentIndex, width) {
    if (!hasContent) {
      startLineAtSegment(segmentIndex, width);
      return;
    }
    lineW += width;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
  }
  function updatePendingBreak(segmentIndex, segmentWidth) {
    if (!canBreakAfter(kinds[segmentIndex]))
      return;
    pendingBreakSegmentIndex = segmentIndex + 1;
    pendingBreakPaintWidth = lineW - segmentWidth;
  }
  function appendBreakableSegment(segmentIndex) {
    appendBreakableSegmentFrom(segmentIndex, 0);
  }
  function appendBreakableSegmentFrom(segmentIndex, startGraphemeIndex) {
    const gWidths = breakableWidths[segmentIndex];
    const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null;
    for (let g = startGraphemeIndex;g < gWidths.length; g++) {
      const gw = getBreakableAdvance(gWidths, gPrefixWidths, g, engineProfile.preferPrefixWidthsForBreakableRuns);
      if (!hasContent) {
        startLineAtGrapheme(segmentIndex, g, gw);
        continue;
      }
      if (lineW + gw > maxWidth + lineFitEpsilon) {
        emitCurrentLine();
        startLineAtGrapheme(segmentIndex, g, gw);
      } else {
        lineW += gw;
        lineEndSegmentIndex = segmentIndex;
        lineEndGraphemeIndex = g + 1;
      }
    }
    if (hasContent && lineEndSegmentIndex === segmentIndex && lineEndGraphemeIndex === gWidths.length) {
      lineEndSegmentIndex = segmentIndex + 1;
      lineEndGraphemeIndex = 0;
    }
  }
  let i = 0;
  while (i < widths.length) {
    const w = widths[i];
    const kind = kinds[i];
    if (!hasContent) {
      if (w > maxWidth && breakableWidths[i] !== null) {
        appendBreakableSegment(i);
      } else {
        startLineAtSegment(i, w);
      }
      updatePendingBreak(i, w);
      i++;
      continue;
    }
    const newW = lineW + w;
    if (newW > maxWidth + lineFitEpsilon) {
      if (canBreakAfter(kind)) {
        appendWholeSegment(i, w);
        emitCurrentLine(i + 1, 0, lineW - w);
        i++;
        continue;
      }
      if (pendingBreakSegmentIndex >= 0) {
        emitCurrentLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
        continue;
      }
      if (w > maxWidth && breakableWidths[i] !== null) {
        emitCurrentLine();
        appendBreakableSegment(i);
        i++;
        continue;
      }
      emitCurrentLine();
      continue;
    }
    appendWholeSegment(i, w);
    updatePendingBreak(i, w);
    i++;
  }
  if (hasContent)
    emitCurrentLine();
  return lineCount;
}
function walkPreparedLines(prepared, maxWidth, onLine) {
  if (prepared.simpleLineWalkFastPath) {
    return walkPreparedLinesSimple(prepared, maxWidth, onLine);
  }
  const { widths, lineEndFitAdvances, lineEndPaintAdvances, kinds, breakableWidths, breakablePrefixWidths, discretionaryHyphenWidth, tabStopAdvance, chunks } = prepared;
  if (widths.length === 0 || chunks.length === 0)
    return 0;
  const engineProfile = getEngineProfile();
  const lineFitEpsilon = engineProfile.lineFitEpsilon;
  let lineCount = 0;
  let lineW = 0;
  let hasContent = false;
  let lineStartSegmentIndex = 0;
  let lineStartGraphemeIndex = 0;
  let lineEndSegmentIndex = 0;
  let lineEndGraphemeIndex = 0;
  let pendingBreakSegmentIndex = -1;
  let pendingBreakFitWidth = 0;
  let pendingBreakPaintWidth = 0;
  let pendingBreakKind = null;
  function clearPendingBreak() {
    pendingBreakSegmentIndex = -1;
    pendingBreakFitWidth = 0;
    pendingBreakPaintWidth = 0;
    pendingBreakKind = null;
  }
  function emitCurrentLine(endSegmentIndex = lineEndSegmentIndex, endGraphemeIndex = lineEndGraphemeIndex, width = lineW) {
    lineCount++;
    onLine?.({
      startSegmentIndex: lineStartSegmentIndex,
      startGraphemeIndex: lineStartGraphemeIndex,
      endSegmentIndex,
      endGraphemeIndex,
      width
    });
    lineW = 0;
    hasContent = false;
    clearPendingBreak();
  }
  function startLineAtSegment(segmentIndex, width) {
    hasContent = true;
    lineStartSegmentIndex = segmentIndex;
    lineStartGraphemeIndex = 0;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
    lineW = width;
  }
  function startLineAtGrapheme(segmentIndex, graphemeIndex, width) {
    hasContent = true;
    lineStartSegmentIndex = segmentIndex;
    lineStartGraphemeIndex = graphemeIndex;
    lineEndSegmentIndex = segmentIndex;
    lineEndGraphemeIndex = graphemeIndex + 1;
    lineW = width;
  }
  function appendWholeSegment(segmentIndex, width) {
    if (!hasContent) {
      startLineAtSegment(segmentIndex, width);
      return;
    }
    lineW += width;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
  }
  function updatePendingBreakForWholeSegment(segmentIndex, segmentWidth) {
    if (!canBreakAfter(kinds[segmentIndex]))
      return;
    const fitAdvance = kinds[segmentIndex] === "tab" ? 0 : lineEndFitAdvances[segmentIndex];
    const paintAdvance = kinds[segmentIndex] === "tab" ? segmentWidth : lineEndPaintAdvances[segmentIndex];
    pendingBreakSegmentIndex = segmentIndex + 1;
    pendingBreakFitWidth = lineW - segmentWidth + fitAdvance;
    pendingBreakPaintWidth = lineW - segmentWidth + paintAdvance;
    pendingBreakKind = kinds[segmentIndex];
  }
  function appendBreakableSegment(segmentIndex) {
    appendBreakableSegmentFrom(segmentIndex, 0);
  }
  function appendBreakableSegmentFrom(segmentIndex, startGraphemeIndex) {
    const gWidths = breakableWidths[segmentIndex];
    const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null;
    for (let g = startGraphemeIndex;g < gWidths.length; g++) {
      const gw = getBreakableAdvance(gWidths, gPrefixWidths, g, engineProfile.preferPrefixWidthsForBreakableRuns);
      if (!hasContent) {
        startLineAtGrapheme(segmentIndex, g, gw);
        continue;
      }
      if (lineW + gw > maxWidth + lineFitEpsilon) {
        emitCurrentLine();
        startLineAtGrapheme(segmentIndex, g, gw);
      } else {
        lineW += gw;
        lineEndSegmentIndex = segmentIndex;
        lineEndGraphemeIndex = g + 1;
      }
    }
    if (hasContent && lineEndSegmentIndex === segmentIndex && lineEndGraphemeIndex === gWidths.length) {
      lineEndSegmentIndex = segmentIndex + 1;
      lineEndGraphemeIndex = 0;
    }
  }
  function continueSoftHyphenBreakableSegment(segmentIndex) {
    if (pendingBreakKind !== "soft-hyphen")
      return false;
    const gWidths = breakableWidths[segmentIndex];
    if (gWidths === null)
      return false;
    const fitWidths = engineProfile.preferPrefixWidthsForBreakableRuns ? breakablePrefixWidths[segmentIndex] ?? gWidths : gWidths;
    const usesPrefixWidths = fitWidths !== gWidths;
    const { fitCount, fittedWidth } = fitSoftHyphenBreak(fitWidths, lineW, maxWidth, lineFitEpsilon, discretionaryHyphenWidth, usesPrefixWidths);
    if (fitCount === 0)
      return false;
    lineW = fittedWidth;
    lineEndSegmentIndex = segmentIndex;
    lineEndGraphemeIndex = fitCount;
    clearPendingBreak();
    if (fitCount === gWidths.length) {
      lineEndSegmentIndex = segmentIndex + 1;
      lineEndGraphemeIndex = 0;
      return true;
    }
    emitCurrentLine(segmentIndex, fitCount, fittedWidth + discretionaryHyphenWidth);
    appendBreakableSegmentFrom(segmentIndex, fitCount);
    return true;
  }
  function emitEmptyChunk(chunk) {
    lineCount++;
    onLine?.({
      startSegmentIndex: chunk.startSegmentIndex,
      startGraphemeIndex: 0,
      endSegmentIndex: chunk.consumedEndSegmentIndex,
      endGraphemeIndex: 0,
      width: 0
    });
    clearPendingBreak();
  }
  for (let chunkIndex = 0;chunkIndex < chunks.length; chunkIndex++) {
    const chunk = chunks[chunkIndex];
    if (chunk.startSegmentIndex === chunk.endSegmentIndex) {
      emitEmptyChunk(chunk);
      continue;
    }
    hasContent = false;
    lineW = 0;
    lineStartSegmentIndex = chunk.startSegmentIndex;
    lineStartGraphemeIndex = 0;
    lineEndSegmentIndex = chunk.startSegmentIndex;
    lineEndGraphemeIndex = 0;
    clearPendingBreak();
    let i = chunk.startSegmentIndex;
    while (i < chunk.endSegmentIndex) {
      const kind = kinds[i];
      const w = kind === "tab" ? getTabAdvance(lineW, tabStopAdvance) : widths[i];
      if (kind === "soft-hyphen") {
        if (hasContent) {
          lineEndSegmentIndex = i + 1;
          lineEndGraphemeIndex = 0;
          pendingBreakSegmentIndex = i + 1;
          pendingBreakFitWidth = lineW + discretionaryHyphenWidth;
          pendingBreakPaintWidth = lineW + discretionaryHyphenWidth;
          pendingBreakKind = kind;
        }
        i++;
        continue;
      }
      if (!hasContent) {
        if (w > maxWidth && breakableWidths[i] !== null) {
          appendBreakableSegment(i);
        } else {
          startLineAtSegment(i, w);
        }
        updatePendingBreakForWholeSegment(i, w);
        i++;
        continue;
      }
      const newW = lineW + w;
      if (newW > maxWidth + lineFitEpsilon) {
        const currentBreakFitWidth = lineW + (kind === "tab" ? 0 : lineEndFitAdvances[i]);
        const currentBreakPaintWidth = lineW + (kind === "tab" ? w : lineEndPaintAdvances[i]);
        if (pendingBreakKind === "soft-hyphen" && engineProfile.preferEarlySoftHyphenBreak && pendingBreakFitWidth <= maxWidth + lineFitEpsilon) {
          emitCurrentLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
          continue;
        }
        if (pendingBreakKind === "soft-hyphen" && continueSoftHyphenBreakableSegment(i)) {
          i++;
          continue;
        }
        if (canBreakAfter(kind) && currentBreakFitWidth <= maxWidth + lineFitEpsilon) {
          appendWholeSegment(i, w);
          emitCurrentLine(i + 1, 0, currentBreakPaintWidth);
          i++;
          continue;
        }
        if (pendingBreakSegmentIndex >= 0 && pendingBreakFitWidth <= maxWidth + lineFitEpsilon) {
          emitCurrentLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
          continue;
        }
        if (w > maxWidth && breakableWidths[i] !== null) {
          emitCurrentLine();
          appendBreakableSegment(i);
          i++;
          continue;
        }
        emitCurrentLine();
        continue;
      }
      appendWholeSegment(i, w);
      updatePendingBreakForWholeSegment(i, w);
      i++;
    }
    if (hasContent) {
      const finalPaintWidth = pendingBreakSegmentIndex === chunk.consumedEndSegmentIndex ? pendingBreakPaintWidth : lineW;
      emitCurrentLine(chunk.consumedEndSegmentIndex, 0, finalPaintWidth);
    }
  }
  return lineCount;
}
function layoutNextLineRange(prepared, start, maxWidth) {
  const normalizedStart = normalizeLineStart(prepared, start);
  if (normalizedStart === null)
    return null;
  if (prepared.simpleLineWalkFastPath) {
    return layoutNextLineRangeSimple(prepared, normalizedStart, maxWidth);
  }
  const chunkIndex = findChunkIndexForStart(prepared, normalizedStart.segmentIndex);
  if (chunkIndex < 0)
    return null;
  const chunk = prepared.chunks[chunkIndex];
  if (chunk.startSegmentIndex === chunk.endSegmentIndex) {
    return {
      startSegmentIndex: chunk.startSegmentIndex,
      startGraphemeIndex: 0,
      endSegmentIndex: chunk.consumedEndSegmentIndex,
      endGraphemeIndex: 0,
      width: 0
    };
  }
  const { widths, lineEndFitAdvances, lineEndPaintAdvances, kinds, breakableWidths, breakablePrefixWidths, discretionaryHyphenWidth, tabStopAdvance } = prepared;
  const engineProfile = getEngineProfile();
  const lineFitEpsilon = engineProfile.lineFitEpsilon;
  let lineW = 0;
  let hasContent = false;
  const lineStartSegmentIndex = normalizedStart.segmentIndex;
  const lineStartGraphemeIndex = normalizedStart.graphemeIndex;
  let lineEndSegmentIndex = lineStartSegmentIndex;
  let lineEndGraphemeIndex = lineStartGraphemeIndex;
  let pendingBreakSegmentIndex = -1;
  let pendingBreakFitWidth = 0;
  let pendingBreakPaintWidth = 0;
  let pendingBreakKind = null;
  function clearPendingBreak() {
    pendingBreakSegmentIndex = -1;
    pendingBreakFitWidth = 0;
    pendingBreakPaintWidth = 0;
    pendingBreakKind = null;
  }
  function finishLine(endSegmentIndex = lineEndSegmentIndex, endGraphemeIndex = lineEndGraphemeIndex, width = lineW) {
    if (!hasContent)
      return null;
    return {
      startSegmentIndex: lineStartSegmentIndex,
      startGraphemeIndex: lineStartGraphemeIndex,
      endSegmentIndex,
      endGraphemeIndex,
      width
    };
  }
  function startLineAtSegment(segmentIndex, width) {
    hasContent = true;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
    lineW = width;
  }
  function startLineAtGrapheme(segmentIndex, graphemeIndex, width) {
    hasContent = true;
    lineEndSegmentIndex = segmentIndex;
    lineEndGraphemeIndex = graphemeIndex + 1;
    lineW = width;
  }
  function appendWholeSegment(segmentIndex, width) {
    if (!hasContent) {
      startLineAtSegment(segmentIndex, width);
      return;
    }
    lineW += width;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
  }
  function updatePendingBreakForWholeSegment(segmentIndex, segmentWidth) {
    if (!canBreakAfter(kinds[segmentIndex]))
      return;
    const fitAdvance = kinds[segmentIndex] === "tab" ? 0 : lineEndFitAdvances[segmentIndex];
    const paintAdvance = kinds[segmentIndex] === "tab" ? segmentWidth : lineEndPaintAdvances[segmentIndex];
    pendingBreakSegmentIndex = segmentIndex + 1;
    pendingBreakFitWidth = lineW - segmentWidth + fitAdvance;
    pendingBreakPaintWidth = lineW - segmentWidth + paintAdvance;
    pendingBreakKind = kinds[segmentIndex];
  }
  function appendBreakableSegmentFrom(segmentIndex, startGraphemeIndex) {
    const gWidths = breakableWidths[segmentIndex];
    const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null;
    for (let g = startGraphemeIndex;g < gWidths.length; g++) {
      const gw = getBreakableAdvance(gWidths, gPrefixWidths, g, engineProfile.preferPrefixWidthsForBreakableRuns);
      if (!hasContent) {
        startLineAtGrapheme(segmentIndex, g, gw);
        continue;
      }
      if (lineW + gw > maxWidth + lineFitEpsilon) {
        return finishLine();
      }
      lineW += gw;
      lineEndSegmentIndex = segmentIndex;
      lineEndGraphemeIndex = g + 1;
    }
    if (hasContent && lineEndSegmentIndex === segmentIndex && lineEndGraphemeIndex === gWidths.length) {
      lineEndSegmentIndex = segmentIndex + 1;
      lineEndGraphemeIndex = 0;
    }
    return null;
  }
  function maybeFinishAtSoftHyphen(segmentIndex) {
    if (pendingBreakKind !== "soft-hyphen" || pendingBreakSegmentIndex < 0)
      return null;
    const gWidths = breakableWidths[segmentIndex] ?? null;
    if (gWidths !== null) {
      const fitWidths = engineProfile.preferPrefixWidthsForBreakableRuns ? breakablePrefixWidths[segmentIndex] ?? gWidths : gWidths;
      const usesPrefixWidths = fitWidths !== gWidths;
      const { fitCount, fittedWidth } = fitSoftHyphenBreak(fitWidths, lineW, maxWidth, lineFitEpsilon, discretionaryHyphenWidth, usesPrefixWidths);
      if (fitCount === gWidths.length) {
        lineW = fittedWidth;
        lineEndSegmentIndex = segmentIndex + 1;
        lineEndGraphemeIndex = 0;
        clearPendingBreak();
        return null;
      }
      if (fitCount > 0) {
        return finishLine(segmentIndex, fitCount, fittedWidth + discretionaryHyphenWidth);
      }
    }
    if (pendingBreakFitWidth <= maxWidth + lineFitEpsilon) {
      return finishLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
    }
    return null;
  }
  for (let i = normalizedStart.segmentIndex;i < chunk.endSegmentIndex; i++) {
    const kind = kinds[i];
    const startGraphemeIndex = i === normalizedStart.segmentIndex ? normalizedStart.graphemeIndex : 0;
    const w = kind === "tab" ? getTabAdvance(lineW, tabStopAdvance) : widths[i];
    if (kind === "soft-hyphen" && startGraphemeIndex === 0) {
      if (hasContent) {
        lineEndSegmentIndex = i + 1;
        lineEndGraphemeIndex = 0;
        pendingBreakSegmentIndex = i + 1;
        pendingBreakFitWidth = lineW + discretionaryHyphenWidth;
        pendingBreakPaintWidth = lineW + discretionaryHyphenWidth;
        pendingBreakKind = kind;
      }
      continue;
    }
    if (!hasContent) {
      if (startGraphemeIndex > 0) {
        const line = appendBreakableSegmentFrom(i, startGraphemeIndex);
        if (line !== null)
          return line;
      } else if (w > maxWidth && breakableWidths[i] !== null) {
        const line = appendBreakableSegmentFrom(i, 0);
        if (line !== null)
          return line;
      } else {
        startLineAtSegment(i, w);
      }
      updatePendingBreakForWholeSegment(i, w);
      continue;
    }
    const newW = lineW + w;
    if (newW > maxWidth + lineFitEpsilon) {
      const currentBreakFitWidth = lineW + (kind === "tab" ? 0 : lineEndFitAdvances[i]);
      const currentBreakPaintWidth = lineW + (kind === "tab" ? w : lineEndPaintAdvances[i]);
      if (pendingBreakKind === "soft-hyphen" && engineProfile.preferEarlySoftHyphenBreak && pendingBreakFitWidth <= maxWidth + lineFitEpsilon) {
        return finishLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
      }
      const softBreakLine = maybeFinishAtSoftHyphen(i);
      if (softBreakLine !== null)
        return softBreakLine;
      if (canBreakAfter(kind) && currentBreakFitWidth <= maxWidth + lineFitEpsilon) {
        appendWholeSegment(i, w);
        return finishLine(i + 1, 0, currentBreakPaintWidth);
      }
      if (pendingBreakSegmentIndex >= 0 && pendingBreakFitWidth <= maxWidth + lineFitEpsilon) {
        return finishLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
      }
      if (w > maxWidth && breakableWidths[i] !== null) {
        const currentLine = finishLine();
        if (currentLine !== null)
          return currentLine;
        const line = appendBreakableSegmentFrom(i, 0);
        if (line !== null)
          return line;
      }
      return finishLine();
    }
    appendWholeSegment(i, w);
    updatePendingBreakForWholeSegment(i, w);
  }
  if (pendingBreakSegmentIndex === chunk.consumedEndSegmentIndex && lineEndGraphemeIndex === 0) {
    return finishLine(chunk.consumedEndSegmentIndex, 0, pendingBreakPaintWidth);
  }
  return finishLine(chunk.consumedEndSegmentIndex, 0, lineW);
}
function layoutNextLineRangeSimple(prepared, normalizedStart, maxWidth) {
  const { widths, kinds, breakableWidths, breakablePrefixWidths } = prepared;
  const engineProfile = getEngineProfile();
  const lineFitEpsilon = engineProfile.lineFitEpsilon;
  let lineW = 0;
  let hasContent = false;
  const lineStartSegmentIndex = normalizedStart.segmentIndex;
  const lineStartGraphemeIndex = normalizedStart.graphemeIndex;
  let lineEndSegmentIndex = lineStartSegmentIndex;
  let lineEndGraphemeIndex = lineStartGraphemeIndex;
  let pendingBreakSegmentIndex = -1;
  let pendingBreakPaintWidth = 0;
  function finishLine(endSegmentIndex = lineEndSegmentIndex, endGraphemeIndex = lineEndGraphemeIndex, width = lineW) {
    if (!hasContent)
      return null;
    return {
      startSegmentIndex: lineStartSegmentIndex,
      startGraphemeIndex: lineStartGraphemeIndex,
      endSegmentIndex,
      endGraphemeIndex,
      width
    };
  }
  function startLineAtSegment(segmentIndex, width) {
    hasContent = true;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
    lineW = width;
  }
  function startLineAtGrapheme(segmentIndex, graphemeIndex, width) {
    hasContent = true;
    lineEndSegmentIndex = segmentIndex;
    lineEndGraphemeIndex = graphemeIndex + 1;
    lineW = width;
  }
  function appendWholeSegment(segmentIndex, width) {
    if (!hasContent) {
      startLineAtSegment(segmentIndex, width);
      return;
    }
    lineW += width;
    lineEndSegmentIndex = segmentIndex + 1;
    lineEndGraphemeIndex = 0;
  }
  function updatePendingBreak(segmentIndex, segmentWidth) {
    if (!canBreakAfter(kinds[segmentIndex]))
      return;
    pendingBreakSegmentIndex = segmentIndex + 1;
    pendingBreakPaintWidth = lineW - segmentWidth;
  }
  function appendBreakableSegmentFrom(segmentIndex, startGraphemeIndex) {
    const gWidths = breakableWidths[segmentIndex];
    const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null;
    for (let g = startGraphemeIndex;g < gWidths.length; g++) {
      const gw = getBreakableAdvance(gWidths, gPrefixWidths, g, engineProfile.preferPrefixWidthsForBreakableRuns);
      if (!hasContent) {
        startLineAtGrapheme(segmentIndex, g, gw);
        continue;
      }
      if (lineW + gw > maxWidth + lineFitEpsilon) {
        return finishLine();
      }
      lineW += gw;
      lineEndSegmentIndex = segmentIndex;
      lineEndGraphemeIndex = g + 1;
    }
    if (hasContent && lineEndSegmentIndex === segmentIndex && lineEndGraphemeIndex === gWidths.length) {
      lineEndSegmentIndex = segmentIndex + 1;
      lineEndGraphemeIndex = 0;
    }
    return null;
  }
  for (let i = normalizedStart.segmentIndex;i < widths.length; i++) {
    const w = widths[i];
    const kind = kinds[i];
    const startGraphemeIndex = i === normalizedStart.segmentIndex ? normalizedStart.graphemeIndex : 0;
    if (!hasContent) {
      if (startGraphemeIndex > 0) {
        const line = appendBreakableSegmentFrom(i, startGraphemeIndex);
        if (line !== null)
          return line;
      } else if (w > maxWidth && breakableWidths[i] !== null) {
        const line = appendBreakableSegmentFrom(i, 0);
        if (line !== null)
          return line;
      } else {
        startLineAtSegment(i, w);
      }
      updatePendingBreak(i, w);
      continue;
    }
    const newW = lineW + w;
    if (newW > maxWidth + lineFitEpsilon) {
      if (canBreakAfter(kind)) {
        appendWholeSegment(i, w);
        return finishLine(i + 1, 0, lineW - w);
      }
      if (pendingBreakSegmentIndex >= 0) {
        return finishLine(pendingBreakSegmentIndex, 0, pendingBreakPaintWidth);
      }
      if (w > maxWidth && breakableWidths[i] !== null) {
        const currentLine = finishLine();
        if (currentLine !== null)
          return currentLine;
        const line = appendBreakableSegmentFrom(i, 0);
        if (line !== null)
          return line;
      }
      return finishLine();
    }
    appendWholeSegment(i, w);
    updatePendingBreak(i, w);
  }
  return finishLine();
}

// node_modules/@chenglou/pretext/dist/layout.js
var sharedGraphemeSegmenter2 = null;
var sharedLineTextCaches = new WeakMap;
function getSharedGraphemeSegmenter2() {
  if (sharedGraphemeSegmenter2 === null) {
    sharedGraphemeSegmenter2 = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  }
  return sharedGraphemeSegmenter2;
}
function createEmptyPrepared(includeSegments) {
  if (includeSegments) {
    return {
      widths: [],
      lineEndFitAdvances: [],
      lineEndPaintAdvances: [],
      kinds: [],
      simpleLineWalkFastPath: true,
      segLevels: null,
      breakableWidths: [],
      breakablePrefixWidths: [],
      discretionaryHyphenWidth: 0,
      tabStopAdvance: 0,
      chunks: [],
      segments: []
    };
  }
  return {
    widths: [],
    lineEndFitAdvances: [],
    lineEndPaintAdvances: [],
    kinds: [],
    simpleLineWalkFastPath: true,
    segLevels: null,
    breakableWidths: [],
    breakablePrefixWidths: [],
    discretionaryHyphenWidth: 0,
    tabStopAdvance: 0,
    chunks: []
  };
}
function measureAnalysis(analysis, font, includeSegments) {
  const graphemeSegmenter = getSharedGraphemeSegmenter2();
  const engineProfile = getEngineProfile();
  const { cache, emojiCorrection } = getFontMeasurementState(font, textMayContainEmoji(analysis.normalized));
  const discretionaryHyphenWidth = getCorrectedSegmentWidth("-", getSegmentMetrics("-", cache), emojiCorrection);
  const spaceWidth = getCorrectedSegmentWidth(" ", getSegmentMetrics(" ", cache), emojiCorrection);
  const tabStopAdvance = spaceWidth * 8;
  if (analysis.len === 0)
    return createEmptyPrepared(includeSegments);
  const widths = [];
  const lineEndFitAdvances = [];
  const lineEndPaintAdvances = [];
  const kinds = [];
  let simpleLineWalkFastPath = analysis.chunks.length <= 1;
  const segStarts = includeSegments ? [] : null;
  const breakableWidths = [];
  const breakablePrefixWidths = [];
  const segments = includeSegments ? [] : null;
  const preparedStartByAnalysisIndex = Array.from({ length: analysis.len });
  const preparedEndByAnalysisIndex = Array.from({ length: analysis.len });
  function pushMeasuredSegment(text, width, lineEndFitAdvance, lineEndPaintAdvance, kind, start, breakable, breakablePrefix) {
    if (kind !== "text" && kind !== "space" && kind !== "zero-width-break") {
      simpleLineWalkFastPath = false;
    }
    widths.push(width);
    lineEndFitAdvances.push(lineEndFitAdvance);
    lineEndPaintAdvances.push(lineEndPaintAdvance);
    kinds.push(kind);
    segStarts?.push(start);
    breakableWidths.push(breakable);
    breakablePrefixWidths.push(breakablePrefix);
    if (segments !== null)
      segments.push(text);
  }
  for (let mi = 0;mi < analysis.len; mi++) {
    preparedStartByAnalysisIndex[mi] = widths.length;
    const segText = analysis.texts[mi];
    const segWordLike = analysis.isWordLike[mi];
    const segKind = analysis.kinds[mi];
    const segStart = analysis.starts[mi];
    if (segKind === "soft-hyphen") {
      pushMeasuredSegment(segText, 0, discretionaryHyphenWidth, discretionaryHyphenWidth, segKind, segStart, null, null);
      preparedEndByAnalysisIndex[mi] = widths.length;
      continue;
    }
    if (segKind === "hard-break") {
      pushMeasuredSegment(segText, 0, 0, 0, segKind, segStart, null, null);
      preparedEndByAnalysisIndex[mi] = widths.length;
      continue;
    }
    if (segKind === "tab") {
      pushMeasuredSegment(segText, 0, 0, 0, segKind, segStart, null, null);
      preparedEndByAnalysisIndex[mi] = widths.length;
      continue;
    }
    const segMetrics = getSegmentMetrics(segText, cache);
    if (segKind === "text" && segMetrics.containsCJK) {
      let unitText = "";
      let unitStart = 0;
      for (const gs of graphemeSegmenter.segment(segText)) {
        const grapheme = gs.segment;
        if (unitText.length === 0) {
          unitText = grapheme;
          unitStart = gs.index;
          continue;
        }
        if (kinsokuEnd.has(unitText) || kinsokuStart.has(grapheme) || leftStickyPunctuation.has(grapheme) || engineProfile.carryCJKAfterClosingQuote && isCJK(grapheme) && endsWithClosingQuote(unitText)) {
          unitText += grapheme;
          continue;
        }
        const unitMetrics = getSegmentMetrics(unitText, cache);
        const w2 = getCorrectedSegmentWidth(unitText, unitMetrics, emojiCorrection);
        pushMeasuredSegment(unitText, w2, w2, w2, "text", segStart + unitStart, null, null);
        unitText = grapheme;
        unitStart = gs.index;
      }
      if (unitText.length > 0) {
        const unitMetrics = getSegmentMetrics(unitText, cache);
        const w2 = getCorrectedSegmentWidth(unitText, unitMetrics, emojiCorrection);
        pushMeasuredSegment(unitText, w2, w2, w2, "text", segStart + unitStart, null, null);
      }
      preparedEndByAnalysisIndex[mi] = widths.length;
      continue;
    }
    const w = getCorrectedSegmentWidth(segText, segMetrics, emojiCorrection);
    const lineEndFitAdvance = segKind === "space" || segKind === "preserved-space" || segKind === "zero-width-break" ? 0 : w;
    const lineEndPaintAdvance = segKind === "space" || segKind === "zero-width-break" ? 0 : w;
    if (segWordLike && segText.length > 1) {
      const graphemeWidths = getSegmentGraphemeWidths(segText, segMetrics, cache, emojiCorrection);
      const graphemePrefixWidths = engineProfile.preferPrefixWidthsForBreakableRuns ? getSegmentGraphemePrefixWidths(segText, segMetrics, cache, emojiCorrection) : null;
      pushMeasuredSegment(segText, w, lineEndFitAdvance, lineEndPaintAdvance, segKind, segStart, graphemeWidths, graphemePrefixWidths);
    } else {
      pushMeasuredSegment(segText, w, lineEndFitAdvance, lineEndPaintAdvance, segKind, segStart, null, null);
    }
    preparedEndByAnalysisIndex[mi] = widths.length;
  }
  const chunks = mapAnalysisChunksToPreparedChunks(analysis.chunks, preparedStartByAnalysisIndex, preparedEndByAnalysisIndex);
  const segLevels = segStarts === null ? null : computeSegmentLevels(analysis.normalized, segStarts);
  if (segments !== null) {
    return {
      widths,
      lineEndFitAdvances,
      lineEndPaintAdvances,
      kinds,
      simpleLineWalkFastPath,
      segLevels,
      breakableWidths,
      breakablePrefixWidths,
      discretionaryHyphenWidth,
      tabStopAdvance,
      chunks,
      segments
    };
  }
  return {
    widths,
    lineEndFitAdvances,
    lineEndPaintAdvances,
    kinds,
    simpleLineWalkFastPath,
    segLevels,
    breakableWidths,
    breakablePrefixWidths,
    discretionaryHyphenWidth,
    tabStopAdvance,
    chunks
  };
}
function mapAnalysisChunksToPreparedChunks(chunks, preparedStartByAnalysisIndex, preparedEndByAnalysisIndex) {
  const preparedChunks = [];
  for (let i = 0;i < chunks.length; i++) {
    const chunk = chunks[i];
    const startSegmentIndex = chunk.startSegmentIndex < preparedStartByAnalysisIndex.length ? preparedStartByAnalysisIndex[chunk.startSegmentIndex] : preparedEndByAnalysisIndex[preparedEndByAnalysisIndex.length - 1] ?? 0;
    const endSegmentIndex = chunk.endSegmentIndex < preparedStartByAnalysisIndex.length ? preparedStartByAnalysisIndex[chunk.endSegmentIndex] : preparedEndByAnalysisIndex[preparedEndByAnalysisIndex.length - 1] ?? 0;
    const consumedEndSegmentIndex = chunk.consumedEndSegmentIndex < preparedStartByAnalysisIndex.length ? preparedStartByAnalysisIndex[chunk.consumedEndSegmentIndex] : preparedEndByAnalysisIndex[preparedEndByAnalysisIndex.length - 1] ?? 0;
    preparedChunks.push({
      startSegmentIndex,
      endSegmentIndex,
      consumedEndSegmentIndex
    });
  }
  return preparedChunks;
}
function prepareInternal(text, font, includeSegments, options) {
  const analysis = analyzeText(text, getEngineProfile(), options?.whiteSpace);
  return measureAnalysis(analysis, font, includeSegments);
}
function prepare(text, font, options) {
  return prepareInternal(text, font, false, options);
}
function prepareWithSegments(text, font, options) {
  return prepareInternal(text, font, true, options);
}
function getInternalPrepared(prepared) {
  return prepared;
}
function layout(prepared, maxWidth, lineHeight) {
  const lineCount = countPreparedLines(getInternalPrepared(prepared), maxWidth);
  return { lineCount, height: lineCount * lineHeight };
}
function getSegmentGraphemes(segmentIndex, segments, cache) {
  let graphemes = cache.get(segmentIndex);
  if (graphemes !== undefined)
    return graphemes;
  graphemes = [];
  const graphemeSegmenter = getSharedGraphemeSegmenter2();
  for (const gs of graphemeSegmenter.segment(segments[segmentIndex])) {
    graphemes.push(gs.segment);
  }
  cache.set(segmentIndex, graphemes);
  return graphemes;
}
function getLineTextCache(prepared) {
  let cache = sharedLineTextCaches.get(prepared);
  if (cache !== undefined)
    return cache;
  cache = new Map;
  sharedLineTextCaches.set(prepared, cache);
  return cache;
}
function lineHasDiscretionaryHyphen(kinds, startSegmentIndex, startGraphemeIndex, endSegmentIndex) {
  return endSegmentIndex > 0 && kinds[endSegmentIndex - 1] === "soft-hyphen" && !(startSegmentIndex === endSegmentIndex && startGraphemeIndex > 0);
}
function buildLineTextFromRange(segments, kinds, cache, startSegmentIndex, startGraphemeIndex, endSegmentIndex, endGraphemeIndex) {
  let text = "";
  const endsWithDiscretionaryHyphen = lineHasDiscretionaryHyphen(kinds, startSegmentIndex, startGraphemeIndex, endSegmentIndex);
  for (let i = startSegmentIndex;i < endSegmentIndex; i++) {
    if (kinds[i] === "soft-hyphen" || kinds[i] === "hard-break")
      continue;
    if (i === startSegmentIndex && startGraphemeIndex > 0) {
      text += getSegmentGraphemes(i, segments, cache).slice(startGraphemeIndex).join("");
    } else {
      text += segments[i];
    }
  }
  if (endGraphemeIndex > 0) {
    if (endsWithDiscretionaryHyphen)
      text += "-";
    text += getSegmentGraphemes(endSegmentIndex, segments, cache).slice(startSegmentIndex === endSegmentIndex ? startGraphemeIndex : 0, endGraphemeIndex).join("");
  } else if (endsWithDiscretionaryHyphen) {
    text += "-";
  }
  return text;
}
function createLayoutLine(prepared, cache, width, startSegmentIndex, startGraphemeIndex, endSegmentIndex, endGraphemeIndex) {
  return {
    text: buildLineTextFromRange(prepared.segments, prepared.kinds, cache, startSegmentIndex, startGraphemeIndex, endSegmentIndex, endGraphemeIndex),
    width,
    start: {
      segmentIndex: startSegmentIndex,
      graphemeIndex: startGraphemeIndex
    },
    end: {
      segmentIndex: endSegmentIndex,
      graphemeIndex: endGraphemeIndex
    }
  };
}
function toLayoutLineRange(line) {
  return {
    width: line.width,
    start: {
      segmentIndex: line.startSegmentIndex,
      graphemeIndex: line.startGraphemeIndex
    },
    end: {
      segmentIndex: line.endSegmentIndex,
      graphemeIndex: line.endGraphemeIndex
    }
  };
}
function stepLineRange(prepared, start, maxWidth) {
  const line = layoutNextLineRange(prepared, start, maxWidth);
  if (line === null)
    return null;
  return toLayoutLineRange(line);
}
function materializeLine(prepared, line) {
  return createLayoutLine(prepared, getLineTextCache(prepared), line.width, line.start.segmentIndex, line.start.graphemeIndex, line.end.segmentIndex, line.end.graphemeIndex);
}
function layoutNextLine(prepared, start, maxWidth) {
  const line = stepLineRange(prepared, start, maxWidth);
  if (line === null)
    return null;
  return materializeLine(prepared, line);
}

// src/renderer/theme.ts
var theme = {
  colors: {
    primary: "#c8c8d0",
    dim: "#6a6a78",
    npc: "#d4a574",
    damage: "#e05050",
    heal: "#50c878",
    system: "#5a5a70",
    location: "#7aa2d4",
    accent: "#8b5cf6",
    bg: "#0a0a0f"
  },
  fonts: {
    narrative: "'Georgia', 'Times New Roman', serif",
    ui: "system-ui, -apple-system, sans-serif",
    mono: "'Fira Code', 'Cascadia Code', monospace"
  },
  sizes: {
    narrativeText: 16,
    uiText: 13,
    lineHeight: 1.7
  }
};
function narrativeFont() {
  return `${theme.sizes.narrativeText}px ${theme.fonts.narrative}`;
}

// src/renderer/line-cache.ts
class NarrativeStore {
  blocks = [];
  _totalHeight = 0;
  paneWidth;
  font;
  lineHeight;
  blockMargin = 20;
  constructor(paneWidth) {
    this.paneWidth = Math.max(paneWidth - 64, 200);
    this.font = narrativeFont();
    this.lineHeight = 16 * 1.7;
  }
  add(text, html, type) {
    let height;
    try {
      const prepared = prepare(text, this.font);
      const result = layout(prepared, this.paneWidth, this.lineHeight);
      height = result.height + this.blockMargin;
    } catch {
      const lines = Math.max(1, Math.ceil(text.length / 80));
      height = lines * this.lineHeight + this.blockMargin;
    }
    const block = {
      id: `b-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      text,
      html,
      type,
      height,
      y: this._totalHeight,
      timestamp: Date.now()
    };
    this.blocks.push(block);
    this._totalHeight += height;
    return block;
  }
  get totalHeight() {
    return this._totalHeight;
  }
  get length() {
    return this.blocks.length;
  }
  getVisibleRange(scrollTop, viewportHeight) {
    if (this.blocks.length === 0)
      return { start: 0, end: 0 };
    let lo = 0;
    let hi = this.blocks.length - 1;
    while (lo < hi) {
      const mid = lo + hi >> 1;
      if (this.blocks[mid].y + this.blocks[mid].height <= scrollTop) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    const start = lo;
    const bottom = scrollTop + viewportHeight;
    let end = start;
    while (end < this.blocks.length && this.blocks[end].y < bottom) {
      end++;
    }
    return {
      start: Math.max(0, start - 3),
      end: Math.min(this.blocks.length, end + 3)
    };
  }
  getBlock(index) {
    return this.blocks[index];
  }
  getAll() {
    return this.blocks;
  }
  removeById(id) {
    const idx = this.blocks.findIndex((b) => b.id === id);
    if (idx === -1)
      return false;
    this.blocks.splice(idx, 1);
    this._totalHeight = idx > 0 ? this.blocks[idx - 1].y + this.blocks[idx - 1].height : 0;
    for (let i = idx;i < this.blocks.length; i++) {
      this.blocks[i].y = this._totalHeight;
      this._totalHeight += this.blocks[i].height;
    }
    return true;
  }
  remeasure(newWidth) {
    this.paneWidth = Math.max(newWidth - 64, 200);
    this._totalHeight = 0;
    for (const block of this.blocks) {
      try {
        const prepared = prepare(block.text, this.font);
        const result = layout(prepared, this.paneWidth, this.lineHeight);
        block.height = result.height + this.blockMargin;
      } catch {
        const lines = Math.max(1, Math.ceil(block.text.length / 80));
        block.height = lines * this.lineHeight + this.blockMargin;
      }
      block.y = this._totalHeight;
      this._totalHeight += block.height;
    }
  }
}

// src/panels/narrative.ts
function initNarrative(container) {
  const store = new NarrativeStore(container.clientWidth);
  let userAtBottom = true;
  let renderScheduled = false;
  let thinkingBlockId = null;
  const spacer = document.createElement("div");
  spacer.style.position = "relative";
  spacer.style.minHeight = "100%";
  container.innerHTML = "";
  container.appendChild(spacer);
  container.addEventListener("scroll", () => {
    const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
    userAtBottom = atBottom;
    scheduleRender();
  });
  const resizeObserver = new ResizeObserver(() => {
    store.remeasure(container.clientWidth);
    spacer.style.height = `${store.totalHeight}px`;
    scheduleRender();
  });
  resizeObserver.observe(container);
  function scheduleRender() {
    if (renderScheduled)
      return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      renderVisible();
    });
  }
  function renderVisible() {
    const scrollTop = container.scrollTop;
    const viewportHeight = container.clientHeight;
    const { start, end } = store.getVisibleRange(scrollTop, viewportHeight);
    const existingBlocks = spacer.querySelectorAll(".narrative-block");
    existingBlocks.forEach((el) => el.remove());
    for (let i = start;i < end; i++) {
      const block = store.getBlock(i);
      if (!block)
        continue;
      const el = document.createElement("div");
      el.className = `narrative-block ${block.type}`;
      el.style.position = "absolute";
      el.style.top = `${block.y}px`;
      el.style.left = "0";
      el.style.right = "0";
      el.innerHTML = block.html;
      spacer.appendChild(el);
    }
  }
  function addBlockInternal(text, html, type) {
    const block = store.add(text, html, type);
    spacer.style.height = `${store.totalHeight}px`;
    if (userAtBottom) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
    scheduleRender();
    return block.id;
  }
  return {
    addBlock(text, type) {
      let html;
      if (type === "thinking") {
        html = "The world responds";
      } else if (type === "player-action" || type === "system") {
        html = text.replace(/\n/g, "<br>").replace(/"([^"]+)"/g, '<span class="npc-name">"$1"</span>');
      } else {
        const segments = parseNarrative(text);
        html = renderSegments(segments);
      }
      addBlockInternal(text, html, type);
    },
    addHtml(html, type) {
      const temp = document.createElement("div");
      temp.innerHTML = html;
      const text = temp.textContent || temp.innerText || html;
      addBlockInternal(text, html, type);
    },
    showThinking() {
      thinkingBlockId = addBlockInternal("The world responds", "The world responds", "thinking");
    },
    removeThinking() {
      if (thinkingBlockId) {
        store.removeById(thinkingBlockId);
        thinkingBlockId = null;
        spacer.style.height = `${store.totalHeight}px`;
        scheduleRender();
      }
    }
  };
}

// src/panels/input.ts
function initInput(inputEl, onSubmit) {
  const history = [];
  let historyIndex = -1;
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = "";
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = "";
      }
    }
  });
}

// src/map/colors.ts
var TILE_COLORS = {
  "#": ["#3a3a48", "#1a1a22"],
  ".": ["#2a2a35", "#0a0a0f"],
  "+": ["#50c8c8", "#0a0a0f"],
  T: ["#8b6914", "#0a0a0f"],
  B: ["#8b6914", "#0a0a0f"],
  "~": ["#3060c0", "#0a0a0f"],
  ",": ["#2a5a2a", "#0a0a0f"],
  ":": ["#555550", "#0a0a0f"],
  "=": ["#666660", "#0a0a0f"],
  "^": ["#888880", "#0a0a0f"],
  " ": ["#0a0a0f", "#0a0a0f"]
};
var DEFAULT_COLORS = ["#555555", "#0a0a0f"];
function tileColors(ch) {
  return TILE_COLORS[ch] || DEFAULT_COLORS;
}
var ENTITY_COLORS = {
  player: "#ffd700",
  npc: "#d4a574",
  item: "#a335ee",
  exit: "#50c8c8"
};

// src/map/card-renderer.ts
var CARD_FONT = "13px monospace";
var CARD_BOLD_FONT = "bold 14px monospace";
var CARD_DIM_FONT = "11px monospace";
var CHAR_W = 8.4;
var LINE_H = 18;
var CARD_COLS = 28;
var CARD_W = CARD_COLS * CHAR_W + 16;
var PAD = 8;
var BOX = {
  tl: "╔",
  tr: "╗",
  bl: "╚",
  br: "╝",
  h: "═",
  v: "║",
  ml: "╠",
  mr: "╣",
  mh: "═"
};
var COLORS = {
  border: "#2a2a38",
  bg: "#0e0e15",
  name: "#d4a574",
  label: "#5a5a70",
  text: "#c8c8d0",
  dim: "#4a4a58",
  hint: "#5a5a70",
  hpFull: "#50c878",
  hpLow: "#e05050",
  item: "#a335ee",
  exit: "#50c8c8"
};
function drawCard(ctx, x, y, content) {
  const maxTextW = (CARD_COLS - 2) * CHAR_W;
  let curY = y;
  let summaryLines = [];
  if (content.summary) {
    const prepared = prepare(content.summary, CARD_FONT);
    const result = layout(prepared, maxTextW, LINE_H);
    summaryLines = wrapText(content.summary, CARD_COLS - 4);
  }
  const nameLines = wrapText(content.name, CARD_COLS - 4);
  const hasLabels = content.labels.length > 0;
  const hasHealth = content.health != null;
  const hasXp = content.xp != null;
  const hasHint = !!content.hint;
  let totalLines = nameLines.length;
  if (hasLabels)
    totalLines += 1;
  totalLines += 1;
  if (summaryLines.length)
    totalLines += summaryLines.length + 1;
  if (hasHealth)
    totalLines += 1;
  if (hasXp)
    totalLines += 1;
  if (hasHint)
    totalLines += 2;
  const cardH = (totalLines + 2) * LINE_H;
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(x, curY, CARD_W, cardH);
  drawBoxLine(ctx, x, curY, BOX.tl, BOX.h, BOX.tr);
  curY += LINE_H;
  ctx.fillStyle = COLORS.name;
  ctx.font = CARD_BOLD_FONT;
  for (const line of nameLines) {
    drawTextLine(ctx, x, curY, line, COLORS.name, CARD_BOLD_FONT);
    curY += LINE_H;
  }
  if (hasLabels) {
    const labelText = content.labels.join(" · ");
    drawTextLine(ctx, x, curY, labelText, COLORS.label, CARD_DIM_FONT);
    curY += LINE_H;
  }
  drawBoxLine(ctx, x, curY, BOX.ml, BOX.mh, BOX.mr);
  curY += LINE_H;
  if (summaryLines.length) {
    for (const line of summaryLines) {
      drawTextLine(ctx, x, curY, line, COLORS.text, CARD_FONT);
      curY += LINE_H;
    }
    curY += LINE_H * 0.5;
  }
  if (hasHealth && content.maxHealth) {
    const pct = content.health / content.maxHealth;
    const barLen = CARD_COLS - 8;
    const filled = Math.round(pct * barLen);
    const bar = "█".repeat(filled) + "░".repeat(barLen - filled);
    const hpColor = pct > 0.3 ? COLORS.hpFull : COLORS.hpLow;
    drawTextLine(ctx, x, curY, `HP ${bar} ${content.health}`, hpColor, CARD_FONT);
    curY += LINE_H;
  }
  if (hasXp && content.xpThreshold) {
    const pct = content.xp / content.xpThreshold;
    const barLen = CARD_COLS - 8;
    const filled = Math.round(pct * barLen);
    const bar = "█".repeat(filled) + "░".repeat(barLen - filled);
    drawTextLine(ctx, x, curY, `XP ${bar} ${content.xp}`, COLORS.dim, CARD_FONT);
    curY += LINE_H;
  }
  if (hasHint) {
    curY += LINE_H * 0.5;
    drawTextLine(ctx, x, curY, content.hint, COLORS.hint, CARD_DIM_FONT);
    curY += LINE_H;
  }
  drawBoxLine(ctx, x, curY, BOX.bl, BOX.h, BOX.br);
  curY += LINE_H;
  ctx.fillStyle = COLORS.border;
  ctx.font = CARD_FONT;
  const rows = Math.floor((curY - y) / LINE_H);
  for (let i = 1;i < rows - 1; i++) {
    const rowY = y + i * LINE_H;
    ctx.fillText(BOX.v, x + PAD, rowY + LINE_H / 2);
    ctx.fillText(BOX.v, x + CARD_W - PAD, rowY + LINE_H / 2);
  }
  return curY - y;
}
function drawBoxLine(ctx, x, y, left, fill, right) {
  ctx.font = CARD_FONT;
  ctx.fillStyle = COLORS.border;
  const line = left + fill.repeat(CARD_COLS - 2) + right;
  ctx.textAlign = "left";
  ctx.fillText(line, x + PAD, y + LINE_H / 2);
  ctx.textAlign = "center";
}
function drawTextLine(ctx, x, y, text, color, font) {
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = "left";
  ctx.fillText(text, x + PAD + CHAR_W * 2, y + LINE_H / 2);
  ctx.textAlign = "center";
}
function wrapText(text, maxCols) {
  const words = text.split(" ");
  const lines = [];
  let current = "";
  for (const word of words) {
    if (current.length + word.length + 1 > maxCols) {
      if (current)
        lines.push(current);
      current = word;
    } else {
      current = current ? current + " " + word : word;
    }
  }
  if (current)
    lines.push(current);
  return lines;
}

// src/map/renderer.ts
var TILE_W = 14;
var TILE_H = 18;
var FONT = "15px monospace";
var GAP = 8;

class MapRenderer {
  canvas;
  ctx;
  dpr;
  cardContent = null;
  constructor(container) {
    this.dpr = Math.min(devicePixelRatio, 2);
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.background = "#0a0a0f";
    this.ctx = this.canvas.getContext("2d");
    container.appendChild(this.canvas);
  }
  get element() {
    return this.canvas;
  }
  setCard(content) {
    this.cardContent = content;
  }
  render(map, playerX, playerY) {
    const mapW = map.width * TILE_W;
    const mapH = map.height * TILE_H;
    const totalW = mapW + (this.cardContent ? GAP + CARD_W : 0);
    this.canvas.width = totalW * this.dpr;
    this.canvas.height = mapH * this.dpr;
    this.canvas.style.width = `${totalW}px`;
    this.canvas.style.height = `${mapH}px`;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(0, 0, totalW, mapH);
    ctx.font = FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let y = 0;y < map.height; y++) {
      for (let x = 0;x < map.width; x++) {
        const ch = map.tiles[y * map.width + x] || " ";
        const [fg, bg] = tileColors(ch);
        ctx.fillStyle = bg;
        ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
        if (ch !== " ") {
          ctx.fillStyle = fg;
          ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
        }
      }
    }
    for (const exit of map.exits) {
      this.drawEntity(exit.x, exit.y, exit.ch || "+", ENTITY_COLORS.exit);
    }
    for (const item of map.items) {
      this.drawEntity(item.x, item.y, item.ch, ENTITY_COLORS.item);
    }
    for (const npc of map.npcs) {
      this.drawEntity(npc.x, npc.y, npc.ch, ENTITY_COLORS.npc);
    }
    this.drawEntity(playerX, playerY, "@", ENTITY_COLORS.player);
    if (this.cardContent) {
      drawCard(ctx, mapW + GAP, 8, this.cardContent);
    }
  }
  drawEntity(x, y, ch, color) {
    const ctx = this.ctx;
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
    ctx.fillStyle = color;
    ctx.font = FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(ch, x * TILE_W + TILE_W / 2, y * TILE_H + TILE_H / 2);
  }
  gridToScreen(gridX, gridY) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: rect.left + gridX * TILE_W + TILE_W / 2,
      y: rect.top + gridY * TILE_H
    };
  }
}

// src/map/movement.ts
class PlayerController {
  x;
  y;
  map;
  onInteract;
  onProximity;
  lastProximity = "";
  constructor(map, onInteract, onProximity) {
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.map = map;
    this.onInteract = onInteract;
    this.onProximity = onProximity;
  }
  move(dx, dy) {
    const nx = this.x + dx;
    const ny = this.y + dy;
    if (!this.isWalkable(nx, ny))
      return false;
    this.x = nx;
    this.y = ny;
    this.checkProximity();
    return true;
  }
  interact() {
    const dirs = [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;
      const exit = this.map.exits.find((e) => e.x === tx && e.y === ty);
      if (exit) {
        this.onInteract("exit", exit);
        return;
      }
      const npc = this.map.npcs.find((n) => n.x === tx && n.y === ty);
      if (npc) {
        this.onInteract("npc", npc);
        return;
      }
      const item = this.map.items.find((i) => i.x === tx && i.y === ty);
      if (item) {
        this.onInteract("item", item);
        return;
      }
    }
  }
  checkProximity() {
    const dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    for (const [dx, dy] of dirs) {
      const tx = this.x + dx;
      const ty = this.y + dy;
      const npc = this.map.npcs.find((n) => n.x === tx && n.y === ty);
      if (npc && this.lastProximity !== npc.id) {
        this.lastProximity = npc.id;
        this.onProximity("npc", npc);
        return;
      }
      const item = this.map.items.find((i) => i.x === tx && i.y === ty);
      if (item && this.lastProximity !== item.id) {
        this.lastProximity = item.id;
        this.onProximity("item", item);
        return;
      }
      const exit = this.map.exits.find((e) => e.x === tx && e.y === ty);
      if (exit) {
        const exitId = `exit-${exit.direction}`;
        if (this.lastProximity !== exitId) {
          this.lastProximity = exitId;
          this.onProximity("exit", exit);
          return;
        }
      }
    }
    if (this.lastProximity !== "") {
      this.lastProximity = "";
      this.onProximity(null, null);
    }
  }
  isWalkable(x, y) {
    if (x < 0 || x >= this.map.width || y < 0 || y >= this.map.height)
      return false;
    const ch = this.map.tiles[y * this.map.width + x];
    return ch !== "#" && ch !== undefined && ch !== " ";
  }
  loadMap(map) {
    this.map = map;
    this.x = map.spawn?.x ?? Math.floor(map.width / 2);
    this.y = map.spawn?.y ?? Math.floor(map.height / 2);
    this.lastProximity = "";
  }
}
var MOVE_KEYS = {
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  w: [0, -1],
  s: [0, 1],
  a: [-1, 0],
  d: [1, 0],
  k: [0, -1],
  j: [0, 1],
  h: [-1, 0],
  l: [1, 0]
};
function setupMapInput(controller, renderer, map) {
  const handler = (e) => {
    if (e.target?.tagName === "INPUT")
      return;
    const delta = MOVE_KEYS[e.key];
    if (delta) {
      e.preventDefault();
      if (controller.move(delta[0], delta[1]) && map.current) {
        renderer.render(map.current, controller.x, controller.y);
      }
    } else if (e.key === "Enter" || e.key === " ") {
      if (e.target?.tagName === "INPUT")
        return;
      e.preventDefault();
      controller.interact();
    }
  };
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}

// src/panels/map.ts
var renderer = null;
var controller = null;
var cleanupInput = null;
var mapRef = { current: null };
var entityCache = new Map;
var UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
async function fetchEntityData(id, name) {
  const cached = entityCache.get(id);
  if (cached)
    return cached;
  if (UUID_RE.test(id)) {
    try {
      const resp = await fetch(`/api/entity/${id}`);
      const data = await resp.json();
      if (data && data.name && !data.error) {
        entityCache.set(id, data);
        return data;
      }
    } catch {}
  }
  try {
    const resp = await fetch(`/api/entity/search/${encodeURIComponent(name)}`);
    const data = await resp.json();
    if (data && data.name && !data.error) {
      entityCache.set(id, data);
      return data;
    }
  } catch {}
  const fallback = { id, name, labels: [], summary: "" };
  entityCache.set(id, fallback);
  return fallback;
}
function initMapPanel(mapContainer, _onAction) {
  renderer = new MapRenderer(mapContainer);
}
function updateMap(state, onAction) {
  if (!state.roomMap || !renderer)
    return;
  const map = state.roomMap;
  mapRef.current = map;
  if (!controller) {
    controller = new PlayerController(map, (type, entity) => {
      if (type === "npc")
        onAction(`talk to ${entity.name}`);
      else if (type === "item")
        onAction(`examine ${entity.name}`);
      else if (type === "exit")
        onAction(`go ${entity.direction}`);
    }, (type, entity) => {
      if (!renderer)
        return;
      if (type && entity) {
        const entityId = entity.id || entity.name;
        fetchEntityData(entityId, entity.name).then((data) => {
          const typeLabels = {
            npc: ["NPC"],
            item: ["Item"],
            exit: ["Exit"]
          };
          const hints = {
            npc: "[Enter] Talk",
            item: "[Enter] Examine",
            exit: "[Enter] Travel"
          };
          const card = {
            type: "entity",
            name: data.name || entity.name,
            labels: data.labels.length ? data.labels : typeLabels[type] || [],
            summary: data.summary || "",
            hint: hints[type] || "[Enter] Interact"
          };
          renderer.setCard(card);
          if (mapRef.current && controller) {
            renderer.render(mapRef.current, controller.x, controller.y);
          }
        });
      } else {
        showPlayerCard(state);
      }
    });
    cleanupInput?.();
    cleanupInput = setupMapInput(controller, renderer, mapRef);
  } else {
    controller.loadMap(map);
  }
  showPlayerCard(state);
  renderer.render(map, controller.x, controller.y);
}
function showPlayerCard(state) {
  if (!renderer)
    return;
  const card = {
    type: "player",
    name: state.player.name,
    labels: ["Player"],
    summary: state.location.name,
    health: state.player.health,
    maxHealth: state.player.maxHealth,
    level: state.player.level,
    xp: state.player.xp,
    xpThreshold: state.player.xpThreshold
  };
  renderer.setCard(card);
}

// src/map/world-renderer.ts
var NODE_RADIUS = 18;
var LABEL_FONT = "11px monospace";
var NODE_FONT = "13px monospace";
var PADDING = 40;
var COLORS2 = {
  bg: "#0a0a0f",
  nodeBg: "#16161f",
  nodeBorder: "#2a2a38",
  currentBg: "#1a1a35",
  currentBorder: "#8b5cf6",
  connection: "#2a2a38",
  connectionActive: "#3a3a50",
  text: "#c8c8d0",
  textDim: "#6a6a78",
  current: "#8b5cf6",
  discovered: "#50c878",
  undiscovered: "#3a3a48"
};
var DIR_OFFSETS = {
  north: { dx: 0, dy: -1 },
  south: { dx: 0, dy: 1 },
  east: { dx: 1, dy: 0 },
  west: { dx: -1, dy: 0 },
  northeast: { dx: 0.7, dy: -0.7 },
  northwest: { dx: -0.7, dy: -0.7 },
  southeast: { dx: 0.7, dy: 0.7 },
  southwest: { dx: -0.7, dy: 0.7 },
  up: { dx: 0.3, dy: -1 },
  down: { dx: -0.3, dy: 1 }
};

class WorldMapRenderer {
  canvas;
  ctx;
  dpr;
  onClick = null;
  lastMap = null;
  nodePositions = new Map;
  constructor(container) {
    this.dpr = Math.min(devicePixelRatio, 2);
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.background = COLORS2.bg;
    this.canvas.style.cursor = "pointer";
    this.ctx = this.canvas.getContext("2d");
    container.appendChild(this.canvas);
    this.canvas.addEventListener("click", (e) => this.handleClick(e));
  }
  setClickHandler(handler) {
    this.onClick = handler;
  }
  render(map) {
    this.lastMap = map;
    this.layoutNodes(map);
    const { width, height } = this.computeBounds();
    this.canvas.width = width * this.dpr;
    this.canvas.height = height * this.dpr;
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = COLORS2.bg;
    ctx.fillRect(0, 0, width, height);
    for (const conn of map.connections) {
      const from = this.nodePositions.get(conn.from);
      const to = this.nodePositions.get(conn.to);
      if (!from || !to)
        continue;
      const isActive = conn.from === map.currentRoom || conn.to === map.currentRoom;
      ctx.strokeStyle = isActive ? COLORS2.connectionActive : COLORS2.connection;
      ctx.lineWidth = isActive ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
      if (conn.direction) {
        const mx = (from.x + to.x) / 2;
        const my = (from.y + to.y) / 2;
        ctx.font = "9px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = COLORS2.textDim;
        ctx.fillText(conn.direction[0].toUpperCase(), mx, my);
      }
    }
    for (const room of map.rooms) {
      const pos = this.nodePositions.get(room.id);
      if (!pos)
        continue;
      const isCurrent = room.id === map.currentRoom;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, NODE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = isCurrent ? COLORS2.currentBg : COLORS2.nodeBg;
      ctx.fill();
      ctx.strokeStyle = isCurrent ? COLORS2.currentBorder : COLORS2.nodeBorder;
      ctx.lineWidth = isCurrent ? 2.5 : 1;
      ctx.stroke();
      ctx.font = NODE_FONT;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isCurrent ? COLORS2.current : COLORS2.discovered;
      ctx.fillText(isCurrent ? "@" : "●", pos.x, pos.y);
      ctx.font = LABEL_FONT;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = isCurrent ? COLORS2.text : COLORS2.textDim;
      const label = room.name.length > 16 ? room.name.slice(0, 14) + ".." : room.name;
      ctx.fillText(label, pos.x, pos.y + NODE_RADIUS + 4);
    }
  }
  layoutNodes(map) {
    this.nodePositions.clear();
    if (map.rooms.length === 0)
      return;
    const hasCoords = map.rooms.some((r) => r.x !== 0 || r.y !== 0);
    if (hasCoords) {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const r of map.rooms) {
        minX = Math.min(minX, r.x);
        minY = Math.min(minY, r.y);
        maxX = Math.max(maxX, r.x);
        maxY = Math.max(maxY, r.y);
      }
      const rangeX = maxX - minX || 1;
      const rangeY = maxY - minY || 1;
      const areaW = 400;
      const areaH = 300;
      for (const r of map.rooms) {
        this.nodePositions.set(r.id, {
          x: PADDING + (r.x - minX) / rangeX * areaW,
          y: PADDING + (r.y - minY) / rangeY * areaH
        });
      }
    } else {
      this.autoLayout(map);
    }
  }
  autoLayout(map) {
    const spacing = 100;
    const placed = new Set;
    const startId = map.currentRoom || map.rooms[0]?.id;
    if (!startId)
      return;
    const centerX = 220;
    const centerY = 180;
    this.nodePositions.set(startId, { x: centerX, y: centerY });
    placed.add(startId);
    const queue = [startId];
    while (queue.length > 0) {
      const nodeId = queue.shift();
      const nodePos = this.nodePositions.get(nodeId);
      for (const conn of map.connections) {
        let neighborId = "";
        let direction = conn.direction;
        if (conn.from === nodeId && !placed.has(conn.to)) {
          neighborId = conn.to;
        } else if (conn.to === nodeId && !placed.has(conn.from)) {
          neighborId = conn.from;
          const reverseDir = {
            north: "south",
            south: "north",
            east: "west",
            west: "east",
            northeast: "southwest",
            northwest: "southeast",
            southeast: "northwest",
            southwest: "northeast"
          };
          direction = reverseDir[direction] || direction;
        }
        if (!neighborId)
          continue;
        const offset = DIR_OFFSETS[direction] || { dx: 0, dy: -1 };
        const nx = nodePos.x + offset.dx * spacing;
        const ny = nodePos.y + offset.dy * spacing;
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
    let orphanX = PADDING;
    for (const room of map.rooms) {
      if (!placed.has(room.id)) {
        this.nodePositions.set(room.id, { x: orphanX, y: centerY + spacing });
        orphanX += spacing;
        placed.add(room.id);
      }
    }
  }
  computeBounds() {
    let maxX = 200, maxY = 200;
    for (const pos of this.nodePositions.values()) {
      maxX = Math.max(maxX, pos.x + PADDING + NODE_RADIUS);
      maxY = Math.max(maxY, pos.y + PADDING + NODE_RADIUS + 20);
    }
    return { width: Math.ceil(maxX), height: Math.ceil(maxY) };
  }
  handleClick(e) {
    if (!this.lastMap || !this.onClick)
      return;
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    for (const room of this.lastMap.rooms) {
      const pos = this.nodePositions.get(room.id);
      if (!pos)
        continue;
      const dist = Math.hypot(mx - pos.x, my - pos.y);
      if (dist <= NODE_RADIUS + 4) {
        this.onClick(room.id);
        return;
      }
    }
  }
}

// src/panels/character.ts
function renderSkills(skills) {
  const entries = Object.entries(skills).filter(([, v]) => v > 0);
  if (entries.length === 0)
    return "";
  const lines = entries.map(([name, level]) => {
    const dots = "●".repeat(level) + "○".repeat(Math.max(0, 5 - level));
    return `<div class="skill-row"><span class="skill-name">${name}</span> <span class="skill-dots">${dots}</span></div>`;
  });
  return `<div class="skills-section">${lines.join("")}</div>`;
}
function renderCharacterPanel(body, state) {
  const p = state.player;
  const hpPct = p.maxHealth > 0 ? Math.round(p.health / p.maxHealth * 100) : 0;
  const xpPct = p.xpThreshold > 0 ? Math.round(p.xp / p.xpThreshold * 100) : 0;
  const hpFill = Math.round(hpPct / 10);
  const xpFill = Math.round(xpPct / 10);
  const archLabel = p.archetype ? `<div class="archetype-label">${p.archetype}</div>` : "";
  const skillsHtml = renderSkills(p.skills);
  body.innerHTML = `
    ${archLabel}
    <div><span class="stat-label">HP</span> <span class="bar-fill-hp">${"█".repeat(hpFill)}</span><span class="bar-empty">${"░".repeat(10 - hpFill)}</span> <span style="color:var(--text-dim)">${p.health}/${p.maxHealth}</span></div>
    <div><span class="stat-label">XP</span> <span class="bar-fill-xp">${"█".repeat(xpFill)}</span><span class="bar-empty">${"░".repeat(10 - xpFill)}</span> <span style="color:var(--text-dim)">${p.xp}/${p.xpThreshold}</span></div>
    <div><span class="stat-label">Lv</span> ${p.level}</div>
    ${skillsHtml}
  `;
}

// src/panels/inventory.ts
var RARITY_COLORS = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
function renderInventoryPanel(body, state) {
  if (state.inventory.length === 0) {
    body.innerHTML = '<div class="empty-msg">Empty</div>';
    return;
  }
  body.innerHTML = state.inventory.map((item) => {
    const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
    const equip = item.equipped ? '<span class="item-equip">E</span>' : "";
    return `<div class="item-row"><span class="item-bullet">·</span> <span style="color:${color}">${item.name}</span>${equip}</div>`;
  }).join("");
}

// src/panels/exits.ts
function renderExitsPanel(body, state, onAction) {
  if (state.location.exits.length === 0) {
    body.innerHTML = '<div class="empty-msg">None</div>';
    return;
  }
  body.innerHTML = state.location.exits.map((e) => {
    const dir = typeof e === "string" ? e : e.direction;
    const dest = typeof e === "string" ? "" : e.name;
    const label = dir.charAt(0).toUpperCase() + dir.slice(1);
    return `<div class="exit-row" data-dir="${dir}"><span class="exit-dir">→ ${label}</span>${dest ? `<span class="exit-dest">${dest}</span>` : ""}</div>`;
  }).join("");
  body.querySelectorAll(".exit-row").forEach((row) => {
    row.addEventListener("click", () => onAction(`go ${row.dataset.dir}`));
  });
}

// src/panels/present.ts
function renderPresentPanel(body, state, onAction) {
  const npcs = state.location.npcs || [];
  const items = state.location.items || [];
  if (npcs.length === 0 && items.length === 0) {
    body.innerHTML = '<div class="empty-msg">Nothing here</div>';
    return;
  }
  let html = "";
  for (const npc of npcs) {
    const name = typeof npc === "string" ? npc : npc.name;
    const role = typeof npc === "string" ? "" : npc.role || "";
    html += `<div class="npc-row" data-action="talk to ${name}" style="cursor:pointer"><span class="npc-diamond">◆</span><span class="npc">${name}</span>${role ? `<span class="npc-role">— ${role}</span>` : ""}</div>`;
  }
  for (const item of items) {
    const name = typeof item === "string" ? item : item.name;
    html += `<div class="item-row" data-action="examine ${name}" style="cursor:pointer"><span class="item-bullet">·</span> ${name}</div>`;
  }
  body.innerHTML = html;
  body.querySelectorAll("[data-action]").forEach((el) => {
    el.addEventListener("click", () => onAction(el.dataset.action));
  });
}

// src/panels/questlog.ts
function renderQuestLogPanel(body, quests) {
  if (!quests || quests.length === 0) {
    body.innerHTML = '<div class="empty-msg">No active quests</div>';
    return;
  }
  const html = quests.map((q) => {
    const progress = q.totalStages > 0 ? Math.round(q.currentStage / q.totalStages * 10) : 0;
    const progressBar = "█".repeat(progress) + "░".repeat(10 - progress);
    const statusLabel = q.completed ? '<span class="quest-done">[DONE]</span>' : "";
    return `
      <div class="quest-entry${q.completed ? " completed" : ""}">
        <div class="quest-name">${q.name} ${statusLabel}</div>
        ${q.giver ? `<div class="quest-giver">from ${q.giver}</div>` : ""}
        <div class="quest-progress">
          <span class="bar-fill-xp">${progressBar}</span>
          <span class="quest-stage">${q.currentStage}/${q.totalStages}</span>
        </div>
        ${q.description ? `<div class="quest-desc">${q.description.slice(0, 120)}${q.description.length > 120 ? "..." : ""}</div>` : ""}
      </div>
    `;
  }).join("");
  body.innerHTML = html;
}

// src/panels/factions.ts
function dispositionColor(disposition) {
  switch (disposition) {
    case "hostile":
      return "faction-hostile";
    case "unfriendly":
      return "faction-hostile";
    case "friendly":
      return "faction-friendly";
    case "allied":
      return "faction-friendly";
    default:
      return "faction-neutral";
  }
}
function renderFactionsPanel(body, factions) {
  if (!factions || factions.length === 0) {
    body.innerHTML = '<div class="empty-msg">No known factions</div>';
    return;
  }
  const html = factions.map((f) => {
    const normalized = Math.round((f.reputation + 1) * 5);
    const clamped = Math.max(0, Math.min(10, normalized));
    const colorClass = dispositionColor(f.disposition);
    const bar = "█".repeat(clamped) + "░".repeat(10 - clamped);
    return `
      <div class="faction-entry">
        <div class="faction-name">${f.name}</div>
        <div class="faction-bar">
          <span class="${colorClass}">${bar}</span>
          <span class="faction-disposition">${f.disposition}</span>
        </div>
      </div>
    `;
  }).join("");
  body.innerHTML = html;
}

// src/ui/window.ts
function createWindow(opts) {
  const el = document.createElement("div");
  el.className = `win${opts.className ? ` ${opts.className}` : ""}`;
  if (opts.id)
    el.id = opts.id;
  const titleBar = document.createElement("div");
  titleBar.className = "win-title";
  titleBar.textContent = `─ ${opts.title} ─`;
  const body = document.createElement("div");
  body.className = "win-body";
  if (opts.scrollable)
    body.style.overflowY = "auto";
  el.appendChild(titleBar);
  el.appendChild(body);
  return {
    el,
    body,
    setTitle(title) {
      titleBar.textContent = `─ ${title} ─`;
    },
    show() {
      el.style.display = "";
    },
    hide() {
      el.style.display = "none";
    },
    toggle() {
      el.style.display = el.style.display === "none" ? "" : "none";
    },
    get visible() {
      return el.style.display !== "none";
    }
  };
}

// src/ui/header.ts
function createHeader() {
  const el = document.createElement("div");
  el.className = "tui-header";
  el.innerHTML = `
    <span class="header-time">
      <span class="header-moon">☽</span>
      <span class="header-date">—</span>
    </span>
    <span class="header-title">MEMENTO MORI</span>
  `;
  const moonEl = el.querySelector(".header-moon");
  const dateEl = el.querySelector(".header-date");
  return {
    el,
    updateTime(time) {
      moonEl.textContent = time.moon_icon;
      dateEl.textContent = `${time.moon_phase}  ·  ${ordinal(time.day_number)} of ${time.month}  ·  ${time.time_of_day}`;
    }
  };
}
function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

// src/ui/typewriter.ts
function createTypewriter(opts) {
  const {
    text,
    font,
    maxWidth,
    container,
    charDelay = 25,
    lineClass = "tw-line",
    cursorClass = "tw-cursor"
  } = opts;
  let completeCb = null;
  let timer = null;
  let cancelled = false;
  let started = false;
  const prepared = prepareWithSegments(text, font);
  const lines = [];
  let cursor = { segmentIndex: 0, graphemeIndex: 0 };
  while (true) {
    const line = layoutNextLine(prepared, cursor, maxWidth);
    if (!line)
      break;
    lines.push(line.text);
    cursor = line.end;
  }
  let lineIdx = 0;
  let charIdx = 0;
  let currentLineEl = null;
  let cursorEl = null;
  function ensureCursor() {
    if (!cursorEl) {
      cursorEl = document.createElement("span");
      cursorEl.className = cursorClass;
      cursorEl.textContent = "█";
    }
    return cursorEl;
  }
  function tick() {
    if (cancelled || lineIdx >= lines.length) {
      finish();
      return;
    }
    if (!currentLineEl) {
      currentLineEl = document.createElement("div");
      currentLineEl.className = lineClass;
      container.appendChild(currentLineEl);
    }
    const line = lines[lineIdx];
    if (charIdx < line.length) {
      ensureCursor().remove();
      currentLineEl.textContent = line.slice(0, charIdx + 1);
      currentLineEl.appendChild(ensureCursor());
      charIdx++;
      timer = setTimeout(tick, charDelay);
    } else {
      ensureCursor().remove();
      lineIdx++;
      charIdx = 0;
      currentLineEl = null;
      timer = setTimeout(tick, charDelay);
    }
  }
  function finish() {
    if (cursorEl)
      cursorEl.remove();
    cursorEl = null;
    if (completeCb)
      completeCb();
  }
  function showAll() {
    if (timer)
      clearTimeout(timer);
    container.innerHTML = "";
    for (const line of lines) {
      const div = document.createElement("div");
      div.className = lineClass;
      div.textContent = line;
      container.appendChild(div);
    }
    finish();
  }
  return {
    start() {
      if (started)
        return;
      started = true;
      container.innerHTML = "";
      tick();
    },
    skip() {
      if (cancelled)
        return;
      showAll();
    },
    cancel() {
      cancelled = true;
      if (timer)
        clearTimeout(timer);
      if (cursorEl)
        cursorEl.remove();
    },
    onComplete(cb) {
      completeCb = cb;
    }
  };
}

// src/ui/dialog.ts
var DIALOG_FONT = '15px Georgia, "Times New Roman", serif';
var DIALOG_MAX_WIDTH = 440;
function createDialog() {
  const backdrop = document.createElement("div");
  backdrop.className = "dialog-backdrop";
  backdrop.style.display = "none";
  const win = document.createElement("div");
  win.className = "dialog-win";
  const titleBar = document.createElement("div");
  titleBar.className = "win-title dialog-title";
  const body = document.createElement("div");
  body.className = "win-body dialog-body";
  win.appendChild(titleBar);
  win.appendChild(body);
  backdrop.appendChild(win);
  let currentTw = null;
  function dismiss() {
    if (currentTw) {
      currentTw.cancel();
      currentTw = null;
    }
    backdrop.style.display = "none";
    body.innerHTML = "";
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || backdrop.style.display === "none")
      return;
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    } else {
      dismiss();
    }
  });
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop)
      dismiss();
  });
  body.addEventListener("click", () => {
    if (currentTw) {
      currentTw.skip();
      currentTw = null;
    }
  });
  return {
    el: backdrop,
    show(npcName, npcRole, text) {
      if (currentTw)
        currentTw.cancel();
      titleBar.textContent = `─ ${npcName}${npcRole ? ` — ${npcRole}` : ""} ─`;
      body.innerHTML = "";
      backdrop.style.display = "";
      currentTw = createTypewriter({
        text,
        font: DIALOG_FONT,
        maxWidth: DIALOG_MAX_WIDTH,
        container: body,
        charDelay: 25,
        lineClass: "tw-line",
        cursorClass: "tw-cursor"
      });
      currentTw.onComplete(() => {
        currentTw = null;
      });
      currentTw.start();
    },
    dismiss,
    get active() {
      return backdrop.style.display !== "none";
    }
  };
}

// src/ui/wiki.ts
var GATEWAY = "";
var SUMMARY_MAX = 150;
var ITEMS_PER_PAGE = 8;
var LABEL_TABLE_MAP = {
  Character: ["Characters", "Deaths"],
  Player: ["Characters", "Deaths"],
  Item: ["Items"],
  Weapon: ["Items"],
  Armor: ["Items"],
  Consumable: ["Items"],
  Location: ["Locations"],
  Room: ["Locations"],
  Region: ["Locations"]
};
function tablesForLabels(labels) {
  for (const label of labels) {
    if (label in LABEL_TABLE_MAP)
      return LABEL_TABLE_MAP[label];
  }
  return [];
}
async function fetchChainData(table, entityId) {
  try {
    const resp = await fetch(`${GATEWAY}/api/chain/${table}/${entityId}`);
    if (resp.status === 200)
      return resp.json();
    return null;
  } catch {
    return null;
  }
}
function formatTimestamp(ts) {
  if (!ts)
    return "Unknown";
  return new Date(ts * 1000).toLocaleDateString();
}
function formatAddr(addr) {
  if (!addr || addr.length < 10 || addr === "0x0000000000000000000000000000000000000000")
    return "None";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
function renderCharacterChain(data, deaths) {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Status</span> ${data.alive ? "Alive" : "Dead"}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Level</span> ${data.level ?? "?"}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Wallet</span> ${formatAddr(String(data.wallet || ""))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Created</span> ${formatTimestamp(Number(data.createdAt || 0))}</div>`;
  if (deaths && Array.isArray(deaths) && deaths.length > 0) {
    html += '<div class="wiki-page-heading" style="margin-top:8px">DEATHS</div>';
    for (const d of deaths) {
      html += `<div class="wiki-chain-death">`;
      html += `<div>☠ ${esc(String(d.cause || "Unknown"))}</div>`;
      html += `<div class="wiki-fact">${esc(String(d.location || ""))} · Lv${d.level} · Tick ${d.tick}</div>`;
      html += `</div>`;
    }
  }
  return html;
}
function renderItemChain(data) {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Rarity</span> ${esc(String(data.rarity || "Common"))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Owner</span> ${formatAddr(String(data.ownerId || ""))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Location</span> ${formatAddr(String(data.locationId || ""))}</div>`;
  return html;
}
function renderLocationChain(data) {
  let html = '<div class="wiki-page-heading">ONCHAIN RECORD</div>';
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Region</span> ${esc(String(data.region || "Unknown"))}</div>`;
  html += `<div class="wiki-chain-row"><span class="wiki-chain-label">Discovered by</span> ${formatAddr(String(data.discoveredBy || ""))}</div>`;
  return html;
}
function createWikiPanel() {
  const el = document.createElement("div");
  el.className = "wiki-panel";
  el.innerHTML = '<div class="wiki-empty">Click an entity to browse</div>';
  const cache = new Map;
  const navStack = [];
  let currentId = "";
  let pages = [];
  let pageIdx = 0;
  let activeTab = "lore";
  let currentLabels = [];
  async function fetchEntity(id) {
    if (cache.has(id))
      return cache.get(id);
    try {
      const resp = await fetch(`${GATEWAY}/api/entity/${id}/neighbors`);
      const data = await resp.json();
      if (data.entity.name !== "Unknown") {
        cache.set(id, data);
        return data;
      }
    } catch {}
    return null;
  }
  async function fetchByName(name) {
    try {
      const resp = await fetch(`${GATEWAY}/api/entity/search/${encodeURIComponent(name)}`);
      const data = await resp.json();
      if (data && data.id && !data.error) {
        return fetchEntity(data.id);
      }
    } catch {}
    return null;
  }
  function cleanSummary(raw) {
    if (raw.startsWith("{") || raw.startsWith("[") || raw.startsWith('"'))
      return "";
    if (raw.length > SUMMARY_MAX)
      return raw.slice(0, SUMMARY_MAX) + "…";
    return raw;
  }
  function buildPages(data) {
    const { entity, neighbors, edges } = data;
    const result = [];
    let overviewHtml = "";
    overviewHtml += `<div class="wiki-name">${esc(entity.name)}</div>`;
    if (entity.labels.length) {
      overviewHtml += `<div class="wiki-labels">${entity.labels.map((l) => esc(l)).join(" · ")}</div>`;
    }
    const summary = cleanSummary(entity.summary);
    if (summary) {
      overviewHtml += `<div class="wiki-summary">${esc(summary)}</div>`;
    }
    const grouped = new Map;
    for (const edge of edges) {
      const key = edge.relationship || "connected";
      if (!grouped.has(key))
        grouped.set(key, []);
      grouped.get(key).push(edge);
    }
    const edgeNames = new Set(edges.flatMap((e) => [e.source, e.target]));
    const extraNeighbors = neighbors.filter((n) => !edgeNames.has(n.name) && n.id !== entity.id);
    if (grouped.size > 0 || extraNeighbors.length > 0) {
      overviewHtml += '<div class="wiki-toc-label">Connections:</div>';
      let tocIdx = 2;
      for (const [rel, group] of grouped) {
        overviewHtml += `<div class="wiki-toc-item" data-page="${tocIdx}">${formatRel(rel)} (${group.length})</div>`;
        tocIdx += Math.ceil(group.length / ITEMS_PER_PAGE);
      }
      if (extraNeighbors.length) {
        overviewHtml += `<div class="wiki-toc-item" data-page="${tocIdx}">Nearby (${extraNeighbors.length})</div>`;
      }
    }
    result.push({ title: entity.name, html: overviewHtml, links: [] });
    for (const [rel, group] of grouped) {
      const chunks = chunk(group, ITEMS_PER_PAGE);
      for (let ci = 0;ci < chunks.length; ci++) {
        const label = formatRel(rel);
        const suffix = chunks.length > 1 ? ` ${ci + 1}/${chunks.length}` : "";
        let html = `<div class="wiki-page-heading">${esc(label)}${suffix}</div>`;
        const links = [];
        for (const edge of chunks[ci]) {
          const other = edge.source === entity.name ? edge.target : edge.source;
          html += `<div class="wiki-link" data-name="${esc(other)}">· ${esc(other)}</div>`;
          if (edge.fact) {
            const cleanFact = edge.fact.length > 80 ? edge.fact.slice(0, 80) + "…" : edge.fact;
            html += `<div class="wiki-fact">${esc(cleanFact)}</div>`;
          }
          links.push({ name: other });
        }
        result.push({ title: label, html, links });
      }
    }
    if (extraNeighbors.length) {
      const chunks = chunk(extraNeighbors, ITEMS_PER_PAGE);
      for (let ci = 0;ci < chunks.length; ci++) {
        const suffix = chunks.length > 1 ? ` ${ci + 1}/${chunks.length}` : "";
        let html = `<div class="wiki-page-heading">Nearby${suffix}</div>`;
        const links = [];
        for (const n of chunks[ci]) {
          html += `<div class="wiki-link" data-name="${esc(n.name)}" data-id="${esc(n.id)}">· ${esc(n.name)}</div>`;
          links.push({ name: n.name, id: n.id });
        }
        result.push({ title: "Nearby", html, links });
      }
    }
    return result;
  }
  function renderPage() {
    if (!pages.length)
      return;
    const page = pages[pageIdx];
    const total = pages.length;
    let html = "";
    const hasTabs = tablesForLabels(currentLabels).length > 0;
    if (hasTabs)
      html = renderTabBar() + html;
    if (navStack.length > 1) {
      const prev = navStack[navStack.length - 2];
      html += `<div class="wiki-back" data-id="${esc(prev.id)}" data-name="${esc(prev.name)}">← ${esc(prev.name)}</div>`;
    }
    html += page.html;
    if (total > 1) {
      html += '<div class="wiki-pagination">';
      html += `<span class="wiki-page-btn wiki-prev ${pageIdx === 0 ? "disabled" : ""}">◀</span>`;
      html += `<span class="wiki-page-num">${pageIdx + 1}/${total}</span>`;
      html += `<span class="wiki-page-btn wiki-next ${pageIdx >= total - 1 ? "disabled" : ""}">▶</span>`;
      html += "</div>";
    }
    el.innerHTML = html;
    if (hasTabs)
      wireTabClicks();
    const prevBtn = el.querySelector(".wiki-prev");
    const nextBtn = el.querySelector(".wiki-next");
    if (prevBtn && pageIdx > 0) {
      prevBtn.addEventListener("click", () => {
        pageIdx--;
        renderPage();
      });
    }
    if (nextBtn && pageIdx < total - 1) {
      nextBtn.addEventListener("click", () => {
        pageIdx++;
        renderPage();
      });
    }
    el.querySelectorAll(".wiki-toc-item").forEach((item) => {
      item.addEventListener("click", () => {
        const target = parseInt(item.dataset.page || "1", 10) - 1;
        if (target >= 0 && target < total) {
          pageIdx = target;
          renderPage();
        }
      });
    });
    el.querySelectorAll(".wiki-link").forEach((link) => {
      link.addEventListener("click", () => {
        const id = link.dataset.id;
        const name = link.dataset.name;
        if (id)
          show(id, name);
        else
          showByName(name);
      });
    });
    el.querySelectorAll(".wiki-back").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.id;
        const name = btn.dataset.name;
        navStack.pop();
        show(id, name);
      });
    });
    el.scrollTop = 0;
  }
  function renderFallback(name) {
    el.innerHTML = `
      <div class="wiki-name">${esc(name)}</div>
      <div class="wiki-summary wiki-empty">No knowledge graph data available</div>
    `;
  }
  function renderTabBar() {
    return `<div class="wiki-tabs">
      <span class="wiki-tab ${activeTab === "lore" ? "active" : ""}" data-tab="lore">Lore</span>
      <span class="wiki-tab ${activeTab === "chain" ? "active" : ""}" data-tab="chain">Chain</span>
    </div>`;
  }
  function wireTabClicks() {
    el.querySelectorAll(".wiki-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const t = tab.dataset.tab;
        if (t === activeTab)
          return;
        activeTab = t;
        if (t === "lore")
          renderPage();
        else
          renderChainTab(currentId, currentLabels);
      });
    });
  }
  async function renderChainTab(entityId, labels) {
    const tables = tablesForLabels(labels);
    if (!tables.length) {
      el.innerHTML = '<div class="wiki-empty">No onchain data for this entity type</div>';
      return;
    }
    el.innerHTML = '<div class="wiki-loading">Loading chain data…</div>';
    let html = renderTabBar();
    if (tables.includes("Characters")) {
      const charData = await fetchChainData("Characters", entityId);
      const deathData = await fetchChainData("Deaths", entityId);
      if (charData) {
        html += renderCharacterChain(charData.data, deathData ? Array.isArray(deathData.data) ? deathData.data : [deathData.data] : null);
      } else {
        html += '<div class="wiki-empty">No onchain data</div>';
      }
    } else if (tables.includes("Items")) {
      const itemData = await fetchChainData("Items", entityId);
      html += itemData ? renderItemChain(itemData.data) : '<div class="wiki-empty">No onchain data</div>';
    } else if (tables.includes("Locations")) {
      const locData = await fetchChainData("Locations", entityId);
      html += locData ? renderLocationChain(locData.data) : '<div class="wiki-empty">No onchain data</div>';
    }
    el.innerHTML = html;
    wireTabClicks();
  }
  async function show(entityId, entityName) {
    if (entityId === currentId)
      return;
    currentId = entityId;
    navStack.push({ id: entityId, name: entityName });
    el.innerHTML = '<div class="wiki-loading">Loading…</div>';
    const data = await fetchEntity(entityId);
    activeTab = "lore";
    if (data)
      currentLabels = data.entity.labels;
    if (data) {
      pages = buildPages(data);
      pageIdx = 0;
      renderPage();
    } else {
      renderFallback(entityName);
    }
  }
  async function showByName(name) {
    el.innerHTML = '<div class="wiki-loading">Loading…</div>';
    const data = await fetchByName(name);
    activeTab = "lore";
    if (data)
      currentLabels = data.entity.labels;
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
      currentId = "";
      navStack.length = 0;
      pages = [];
      pageIdx = 0;
      activeTab = "lore";
      currentLabels = [];
      el.innerHTML = '<div class="wiki-empty">Click an entity to browse</div>';
    }
  };
}
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function formatRel(rel) {
  return rel.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function chunk(arr, size) {
  const result = [];
  for (let i = 0;i < arr.length; i += size) {
    result.push(arr.slice(i, i + size));
  }
  return result;
}

// src/ui/status.ts
var CLEAR_DELAY = 4000;
function createStatusBar() {
  const el = document.createElement("div");
  el.className = "status-bar";
  el.innerHTML = `
    <span class="status-phase">✓ Ready</span>
    <span class="status-chain">◇ Redstone: offline</span>
    <span class="status-tick">☽ Tick 0</span>
  `;
  const phaseEl = el.querySelector(".status-phase");
  const chainEl = el.querySelector(".status-chain");
  const tickEl = el.querySelector(".status-tick");
  let clearTimer = null;
  function scheduleClear() {
    if (clearTimer)
      clearTimeout(clearTimer);
    clearTimer = setTimeout(() => {
      phaseEl.textContent = "✓ Synced";
      phaseEl.className = "status-phase synced";
    }, CLEAR_DELAY);
  }
  return {
    el,
    setPhase(phase) {
      const icons = {
        processing: "⟳ Processing turn...",
        extracting: "⟳ Extracting episode...",
        fetching: "⟳ Fetching episode...",
        pushing: "⟳ Pushing onchain...",
        synced: "✓ Synced",
        thinking: "⟳ The world responds...",
        error: "✗ Sync error"
      };
      phaseEl.textContent = icons[phase] || phase;
      phaseEl.className = `status-phase ${phase}`;
      if (phase === "synced") {} else {
        scheduleClear();
      }
    },
    setChain(connected) {
      chainEl.textContent = connected ? "◆ Redstone: synced" : "◇ Redstone: offline";
      chainEl.className = `status-chain ${connected ? "connected" : ""}`;
    },
    setTick(tick) {
      tickEl.textContent = `☽ Tick ${tick}`;
    },
    clear() {
      phaseEl.textContent = "✓ Ready";
      phaseEl.className = "status-phase";
      chainEl.textContent = "◇ Redstone: offline";
      chainEl.className = "status-chain";
      tickEl.textContent = "☽ Tick 0";
    }
  };
}

// src/chain/wallet.ts
var connectedAddress = null;
function hasProvider() {
  return typeof window.ethereum !== "undefined";
}
async function connectWallet() {
  if (!window.ethereum) {
    throw new Error("No wallet provider found");
  }
  const accounts = await window.ethereum.request({
    method: "eth_requestAccounts"
  });
  if (!accounts.length) {
    throw new Error("No accounts returned");
  }
  connectedAddress = accounts[0];
  localStorage.setItem("mm_wallet", connectedAddress);
  return connectedAddress;
}
function getAddress() {
  if (connectedAddress)
    return connectedAddress;
  return localStorage.getItem("mm_wallet");
}
function formatAddress(addr) {
  if (addr.length < 10)
    return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

// src/app.ts
var gameState;
var narrative;
var header;
var npcDialog;
var wiki;
var statusBar;
var narrativeWin;
var mapWin;
var characterWin;
var inventoryWin;
var exitsWin;
var presentWin;
var questWin;
var factionWin;
var commandWin;
function registerMapEntities(map) {
  if (!map)
    return;
  const entities = [];
  for (const npc of map.npcs)
    entities.push({ name: npc.name, id: npc.id, type: "npc" });
  for (const item of map.items)
    entities.push({ name: item.name, id: item.id, type: "item" });
  for (const exit of map.exits)
    entities.push({ name: exit.target, id: exit.target, type: "location" });
  entities.push({ name: map.name, id: map.id, type: "location" });
  setKnownEntities(entities);
}
function renderAllPanels() {
  if (!gameState)
    return;
  characterWin.setTitle(gameState.player.name || "Character");
  renderCharacterPanel(characterWin.body, gameState);
  renderInventoryPanel(inventoryWin.body, gameState);
  exitsWin.setTitle(gameState.location.name || "Exits");
  renderExitsPanel(exitsWin.body, gameState, handleAction);
  renderPresentPanel(presentWin.body, gameState, handleAction);
  renderQuestLogPanel(questWin.body, gameState.quests);
  renderFactionsPanel(factionWin.body, gameState.factions);
  updateMap(gameState, handleAction);
  if (wiki && gameState.roomMap) {
    wiki.show(gameState.roomMap.id, gameState.roomMap.name);
  }
}
function getThresholdMap() {
  const w = 35, h = 18;
  const tiles = [];
  for (let y = 0;y < h; y++) {
    for (let x = 0;x < w; x++) {
      if (y === 0 || y === h - 1 || x === 0 || x === w - 1)
        tiles.push("#");
      else if (x >= 5 && x <= 7 && y >= 3 && y <= 7)
        tiles.push("B");
      else if (x === 12 && (y === 4 || y === 5) || x === 20 && (y === 4 || y === 5))
        tiles.push("T");
      else if (x === 12 && (y === 9 || y === 10) || x === 20 && (y === 9 || y === 10))
        tiles.push("T");
      else if (y === 14 && x >= 14 && x <= 20)
        tiles.push(":");
      else
        tiles.push(".");
    }
  }
  tiles[9 * w + (w - 1)] = "+";
  tiles[0 * w + 17] = "+";
  tiles[(h - 1) * w + 17] = "+";
  return {
    id: "c800dabf-b1ef-4033-a594-b1d7f80ee316",
    name: "The Threshold",
    width: w,
    height: h,
    tiles,
    npcs: [
      { x: 6, y: 5, ch: "G", name: "Grumlock Stonebrow", id: "7c167ff0-d4c1-479f-b61d-22f108213575" },
      { x: 22, y: 6, ch: "R", name: "Roric the Sly", id: "d4566673-e13a-4adc-9e35-2f6e45750664" },
      { x: 15, y: 10, ch: "E", name: "Elara Brightwood", id: "0b3dc518-1420-4741-8fb6-72e7e75ca370" }
    ],
    items: [
      { x: 13, y: 9, ch: "?", name: "Tattered Journal", id: "8fe4b8d7-f31e-4cf5-ae64-e74c566e8c4a" },
      { x: 28, y: 3, ch: "!", name: "Dull Iron Dagger", id: "306b569d-c2d6-4c02-8ad5-e881969827b4" }
    ],
    exits: [
      { x: 34, y: 9, ch: "+", direction: "east", target: "The Fog Road" },
      { x: 17, y: 0, ch: "+", direction: "north", target: "The Skeletal Woods" },
      { x: 17, y: 17, ch: "+", direction: "south", target: "The Wastes" }
    ],
    spawn: { x: 17, y: 15 }
  };
}
async function handleAction(action) {
  if (!action.trim() || action.length > 500)
    return;
  narrative.addBlock(`> ${action}`, "player-action");
  await sendAction(action);
}
function showDeathScreen(cause) {
  const overlay = document.getElementById("death-overlay");
  const causeEl = document.getElementById("death-cause");
  const statsEl = document.getElementById("death-stats");
  causeEl.textContent = cause || "The world continues without you.";
  statsEl.innerHTML = gameState ? `
    <div>Name: ${gameState.player.name}</div>
    <div>Level: ${gameState.player.level}</div>
    <div>Last Location: ${gameState.location.name}</div>
  ` : "";
  overlay.classList.remove("hidden");
}
function handleMessage(msg) {
  switch (msg.type) {
    case "narrative": {
      narrative.removeThinking();
      statusBar.setPhase("synced");
      const segments = parseNarrative(msg.text || "");
      const html = renderSegments(segments);
      narrative.addHtml(html, "narrative");
      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        const session2 = getSession();
        session2.currentLocation = gameState.location.name;
        if (gameState.roomMap)
          registerMapEntities(gameState.roomMap);
        if (msg.state_update.world_time) {
          header.updateTime(msg.state_update.world_time);
          statusBar.setTick(msg.state_update.world_time.tick || 0);
        }
        renderAllPanels();
        if (msg.state_update.events) {
          const events = msg.state_update.events;
          if (events.combat) {
            const c = events.combat;
            if (c.damage_dealt != null) {
              narrative.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ""}`, "event-combat");
            }
            if (c.xp_gained) {
              narrative.addBlock(`[+${c.xp_gained} XP]`, "event-xp");
            }
            if (c.target_dead) {
              narrative.addBlock(`${c.target_name || "Target"} has been slain.`, "event-death");
            }
          }
          if (events.inventory_changes) {
            for (const inv of events.inventory_changes) {
              const prefix = inv.event_type === "DROP" ? "-" : "+";
              narrative.addBlock(`[${prefix}${inv.item_name}]`, "event-item");
            }
          }
        }
      }
      if (msg.state_update?.status === "dead" || msg.state_update?.events?.combat?.target_dead || msg.text && msg.text.toLowerCase().includes("you have died")) {
        showDeathScreen(msg.state_update?.cause || "");
      }
      break;
    }
    case "thinking":
      narrative.showThinking();
      statusBar.setPhase("thinking");
      break;
    case "death_feed": {
      const skull = "☠";
      const deathMsg = `${skull} ${msg.player_name || "Unknown"} (Level ${msg.level || "?"}) fell at ${msg.location || "unknown"}. ${msg.cause || ""}`;
      narrative.addBlock(deathMsg, "death-feed");
      break;
    }
    case "status":
      if (msg.phase)
        statusBar.setPhase(msg.phase);
      if (msg.tick != null)
        statusBar.setTick(msg.tick);
      if (msg.chain != null)
        statusBar.setChain(msg.chain);
      break;
    default:
      console.log("Unknown message:", msg);
  }
}
var selectedArchetype = "";
async function loadArchetypes() {
  const container = document.getElementById("archetype-cards");
  if (!container)
    return;
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/archetypes`);
    const archetypes = await resp.json();
    container.innerHTML = archetypes.map((a) => `
      <div class="archetype-card" data-archetype="${a.name}">
        <div class="archetype-name">${a.name}</div>
        <div class="archetype-desc">${a.description}</div>
        <div class="archetype-stats">HP: ${a.stats.health || 100} | Skills: ${Object.keys(a.skills).join(", ")}</div>
        <div class="archetype-items">${a.starting_items.join(", ")}</div>
      </div>
    `).join("");
    container.addEventListener("click", (e) => {
      const card = e.target.closest(".archetype-card");
      if (!card)
        return;
      container.querySelectorAll(".archetype-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      selectedArchetype = card.dataset.archetype || "";
    });
  } catch {
    container.innerHTML = '<div style="color:var(--text-dim)">Archetypes unavailable</div>';
  }
}
async function enterWorld(playerName, walletAddress) {
  const overlay = document.getElementById("char-create-overlay");
  overlay.classList.add("hidden");
  const session2 = await initSession(playerName, walletAddress, selectedArchetype);
  gameState = createInitialState(playerName);
  gameState.location.name = session2.currentLocation;
  if (session2.archetype)
    gameState.player.archetype = session2.archetype;
  if (session2.health)
    gameState.player.health = session2.health;
  if (session2.max_health)
    gameState.player.maxHealth = session2.max_health;
  if (session2.skills)
    gameState.player.skills = session2.skills;
  if (!gameState.roomMap) {
    applyStateUpdate(gameState, { room_map: getThresholdMap() });
  }
  registerMapEntities(gameState.roomMap);
  renderAllPanels();
  narrative.addBlock(`Welcome, ${playerName}. You find yourself at ${session2.currentLocation}.`, "system");
  if (session2.openingNarrative) {
    const segments = parseNarrative(session2.openingNarrative);
    narrative.addHtml(renderSegments(segments), "narrative");
  }
  document.getElementById("action-input").focus();
}
function mount(mountId, el) {
  const mountEl = document.getElementById(mountId);
  if (mountEl && mountEl.parentElement) {
    mountEl.parentElement.replaceChild(el, mountEl);
  }
}
document.addEventListener("DOMContentLoaded", () => {
  header = createHeader();
  mount("tui-header", header.el);
  narrativeWin = createWindow({ title: "Narrative", id: "narrative-win", className: "resizable", scrollable: true });
  mapWin = createWindow({ title: "Map", id: "map-win" });
  characterWin = createWindow({ title: "Character", id: "character-win", className: "sidebar-win resizable" });
  inventoryWin = createWindow({ title: "Inventory", id: "inventory-win", className: "sidebar-win resizable" });
  exitsWin = createWindow({ title: "Exits", id: "exits-win", className: "sidebar-win resizable" });
  presentWin = createWindow({ title: "Present", id: "present-win", className: "sidebar-win resizable" });
  questWin = createWindow({ title: "Quests", id: "quest-win", className: "sidebar-win resizable" });
  factionWin = createWindow({ title: "Factions", id: "faction-win", className: "sidebar-win resizable" });
  commandWin = createWindow({ title: "Command", id: "command-win" });
  mount("narrative-mount", narrativeWin.el);
  mount("map-mount", mapWin.el);
  mount("character-mount", characterWin.el);
  mount("inventory-mount", inventoryWin.el);
  mount("exits-mount", exitsWin.el);
  mount("present-mount", presentWin.el);
  mount("quest-mount", questWin.el);
  mount("faction-mount", factionWin.el);
  mount("command-mount", commandWin.el);
  statusBar = createStatusBar();
  mount("status-mount", statusBar.el);
  document.addEventListener("keydown", (e) => {
    if (e.key === "m" && document.activeElement?.tagName !== "INPUT") {
      mapWin.toggle();
    }
  });
  npcDialog = createDialog();
  mount("dialog-mount", npcDialog.el);
  narrative = initNarrative(narrativeWin.body);
  narrativeWin.body.addEventListener("click", (e) => {
    const link = e.target.closest(".entity-link");
    if (!link)
      return;
    const name = link.dataset.entityName;
    const id = link.dataset.entityId;
    if (name) {
      if (id) {
        wiki.show(id, name);
      } else {
        wiki.showByName(name);
      }
    }
  });
  commandWin.body.innerHTML = `
    <span class="prompt-char">&gt;</span>
    <input type="text" id="action-input" placeholder="What do you do?" autocomplete="off" spellcheck="false" />
  `;
  const actionInput = commandWin.body.querySelector("#action-input");
  initInput(actionInput, handleAction);
  const mapCanvasWrap = document.createElement("div");
  mapCanvasWrap.className = "map-canvas-wrap";
  const worldMapWrap = document.createElement("div");
  worldMapWrap.className = "map-canvas-wrap";
  worldMapWrap.style.display = "none";
  wiki = createWikiPanel();
  mapWin.body.appendChild(mapCanvasWrap);
  mapWin.body.appendChild(worldMapWrap);
  mapWin.body.appendChild(wiki.el);
  initMapPanel(mapCanvasWrap, handleAction);
  const worldRenderer = new WorldMapRenderer(worldMapWrap);
  let worldMapData = null;
  let showingWorldMap = false;
  worldRenderer.setClickHandler((roomId) => {
    if (roomId && wiki) {
      const room = worldMapData?.rooms.find((r) => r.id === roomId);
      if (room)
        wiki.show(roomId, room.name);
    }
  });
  async function fetchWorldMap() {
    try {
      const resp = await fetch(`${GATEWAY_URL}/api/worldmap`);
      const data = await resp.json();
      if (data.rooms && data.rooms.length > 0) {
        worldMapData = {
          rooms: data.rooms,
          connections: data.connections,
          currentRoom: gameState?.location?.name || ""
        };
      }
    } catch {}
  }
  function toggleWorldMap() {
    showingWorldMap = !showingWorldMap;
    mapCanvasWrap.style.display = showingWorldMap ? "none" : "";
    worldMapWrap.style.display = showingWorldMap ? "" : "none";
    mapWin.setTitle(showingWorldMap ? "World Map" : "Map");
    if (showingWorldMap && worldMapData) {
      worldMapData.currentRoom = gameState?.location?.name || "";
      worldRenderer.render(worldMapData);
    }
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "w" && document.activeElement?.tagName !== "INPUT") {
      if (!worldMapData)
        fetchWorldMap().then(() => toggleWorldMap());
      else
        toggleWorldMap();
    }
  });
  setMessageHandler(handleMessage);
  setConnectionHandler((connected) => {
    if (connected) {
      narrative.addBlock("Reconnected.", "system");
    } else {
      narrative.addBlock("Connection lost. Reconnecting...", "system");
    }
  });
  document.getElementById("death-restart-btn").addEventListener("click", () => {
    document.getElementById("death-overlay").classList.add("hidden");
    document.getElementById("char-create-overlay").classList.remove("hidden");
    narrativeWin.body.innerHTML = "";
    document.getElementById("char-name-input").focus();
  });
  const walletConnectBtn = document.getElementById("wallet-connect-btn");
  const walletStep = document.getElementById("wallet-step");
  const nameStep = document.getElementById("name-step");
  const walletPrompt = document.getElementById("wallet-prompt");
  const walletNoProvider = document.getElementById("wallet-no-provider");
  const walletAddressEl = document.getElementById("wallet-address");
  const nameInput = document.getElementById("char-name-input");
  const enterBtn = document.getElementById("char-create-btn");
  if (!hasProvider()) {
    walletConnectBtn.classList.add("hidden");
    walletNoProvider.classList.remove("hidden");
  }
  const archetypeStep = document.getElementById("archetype-step");
  walletConnectBtn.addEventListener("click", async () => {
    try {
      walletPrompt.textContent = "Connecting...";
      const addr = await connectWallet();
      walletStep.classList.add("hidden");
      walletAddressEl.textContent = `✓ ${formatAddress(addr)}`;
      if (archetypeStep) {
        archetypeStep.classList.remove("hidden");
        loadArchetypes();
      } else {
        nameStep.classList.remove("hidden");
        nameInput.focus();
      }
    } catch {
      walletPrompt.textContent = "Connection rejected. Try again.";
    }
  });
  const archetypeNextBtn = document.getElementById("archetype-next-btn");
  if (archetypeNextBtn) {
    archetypeNextBtn.addEventListener("click", () => {
      if (archetypeStep)
        archetypeStep.classList.add("hidden");
      nameStep.classList.remove("hidden");
      nameInput.focus();
    });
  }
  enterBtn.addEventListener("click", () => {
    const name = nameInput.value.trim() || "Wanderer";
    const wallet = getAddress();
    if (wallet)
      enterWorld(name, wallet);
  });
  nameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const name = nameInput.value.trim() || "Wanderer";
      const wallet = getAddress();
      if (wallet)
        enterWorld(name, wallet);
    }
  });
});
