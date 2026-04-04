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
      items: [],
      players: []
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
  if (update.npcs) {
    state.location.npcs = update.npcs.map((n) => {
      const existing = state.location.npcs.find((e) => e.id === n.id);
      return {
        name: n.name || "",
        id: n.id || "",
        role: n.role || "",
        ascii_art: existing?.ascii_art
      };
    });
  }
  if (update.items) {
    state.location.items = update.items.map((i) => {
      const existing = state.location.items.find((e) => e.id === i.id);
      return {
        name: i.name || "",
        id: i.id || "",
        role: i.role || "",
        ascii_art: existing?.ascii_art
      };
    });
  }
  if (update.inventory) {
    state.inventory = update.inventory.map((i) => ({
      id: i.id || "",
      name: i.name || "?",
      rarity: i.rarity || "common",
      slot_type: i.slot_type || "",
      equipped: i.equipped || false,
      is_consumable: i.is_consumable || false,
      is_quest_item: i.is_quest_item || false,
      effects: i.effects || [],
      quantity: i.quantity || 1
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
      state.location.npcs = rm.npcs.map((n) => {
        const existing = state.location.npcs.find((e) => e.id === n.id);
        return {
          name: n.name || "",
          id: n.id || "",
          role: n.role || "",
          ascii_art: existing?.ascii_art
        };
      });
    }
    if (rm.items) {
      state.location.items = rm.items.map((i) => {
        const existing = state.location.items.find((e) => e.id === i.id);
        return {
          name: i.name || "",
          id: i.id || "",
          ascii_art: existing?.ascii_art
        };
      });
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
  return data;
}
async function joinSession(playerId) {
  const resp = await fetch(`${GATEWAY_URL}/api/session/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: playerId })
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.currentLocation = data.location;
  localStorage.setItem("mm_player_id", session.playerId);
  connectWebSocket();
  return data;
}
function connectWebSocket() {
  if (ws) {
    ws.onclose = null;
    ws.close();
  }
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

// src/state/round-state.ts
var listeners = [];
var countdownTimer = null;
var safetyTimer = null;
var SAFETY_TIMEOUT_MS = 120000;
var state = {
  phase: "ready"
};
function getRoundState() {
  return state;
}
function onRoundStateChange(listener) {
  listeners.push(listener);
  return () => {
    const idx = listeners.indexOf(listener);
    if (idx >= 0)
      listeners.splice(idx, 1);
  };
}
function notify() {
  for (const fn of listeners)
    fn(state);
}
function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
  state.secondsLeft = undefined;
  state.deadline = undefined;
}
function startCountdown(deadline) {
  stopCountdown();
  state.deadline = deadline;
  state.secondsLeft = Math.ceil((deadline - Date.now()) / 1000);
  countdownTimer = setInterval(() => {
    if (!state.deadline) {
      stopCountdown();
      return;
    }
    const left = Math.ceil((state.deadline - Date.now()) / 1000);
    state.secondsLeft = Math.max(0, left);
    notify();
  }, 1000);
}
function clearSafetyTimer() {
  if (safetyTimer) {
    clearTimeout(safetyTimer);
    safetyTimer = null;
  }
}
function startSafetyTimer() {
  clearSafetyTimer();
  safetyTimer = setTimeout(() => {
    safetyTimer = null;
    if (state.phase === "resolving" || state.phase === "npc_response") {
      console.warn(`[round-state] safety timeout — forcing ready (was ${state.phase})`);
      state.phase = "ready";
      state.crew = undefined;
      stopCountdown();
      notify();
    }
  }, SAFETY_TIMEOUT_MS);
}
function updateRoundState(msg) {
  state.phase = msg.phase;
  state.crew = msg.crew;
  if (msg.location)
    state.location = msg.location;
  if (msg.action_count != null)
    state.actionCount = msg.action_count;
  if (msg.phase === "collecting" && msg.deadline) {
    startCountdown(msg.deadline);
  } else if (msg.phase !== "collecting") {
    stopCountdown();
    state.actionCount = undefined;
  }
  if (msg.phase === "resolving" || msg.phase === "npc_response") {
    startSafetyTimer();
  } else {
    clearSafetyTimer();
  }
  notify();
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

// src/renderer/canvas-text.ts
var ATTR_BOLD = 1;
var ATTR_ITALIC = 2;
var ATTR_UNDERLINE = 4;
var MONO_FONT = "13px monospace";
function fontForAttrs(baseFont, attrs) {
  if (!attrs)
    return baseFont;
  const sizeMatch = baseFont.match(/(\d+px\s+.+)$/);
  const sizeAndFamily = sizeMatch ? sizeMatch[1] : baseFont;
  const parts = [];
  if (attrs & ATTR_ITALIC)
    parts.push("italic");
  if (attrs & ATTR_BOLD)
    parts.push("bold");
  parts.push(sizeAndFamily);
  return parts.join(" ");
}
function measureChar(ctx, font) {
  ctx.font = font;
  const metrics = ctx.measureText("M");
  const width = metrics.width;
  const ascent = metrics.actualBoundingBoxAscent ?? 0;
  const descent = metrics.actualBoundingBoxDescent ?? 0;
  const measured = ascent + descent;
  const height = measured > 0 ? Math.ceil(measured * 1.38) : 18;
  return { width, height };
}
function fillCell(ctx, col, row, cell, charSize) {
  const px = col * charSize.width;
  const py = row * charSize.height;
  if (cell.bg) {
    ctx.fillStyle = cell.bg;
    ctx.fillRect(px, py, charSize.width, charSize.height);
  }
  if (cell.char && cell.char !== " ") {
    ctx.font = fontForAttrs(MONO_FONT, cell.attrs);
    ctx.fillStyle = cell.fg;
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    const fontSize = parseInt(ctx.font.replace(/^[^\d]*/, "")) || 13;
    const yOffset = (charSize.height - fontSize) * 0.35;
    ctx.fillText(cell.char, px, py + yOffset);
  }
  if (cell.attrs && cell.attrs & ATTR_UNDERLINE) {
    ctx.strokeStyle = cell.fg;
    ctx.lineWidth = 1;
    const underY = py + charSize.height - 2;
    ctx.beginPath();
    ctx.moveTo(px, underY);
    ctx.lineTo(px + charSize.width, underY);
    ctx.stroke();
  }
}

// src/panels/narrative.ts
var BLOCK_TYPE_COLORS = {
  narrative: theme.colors.primary,
  "player-action": theme.colors.dim,
  system: theme.colors.system,
  thinking: theme.colors.system,
  event: theme.colors.dim,
  "event-combat": theme.colors.damage,
  "event-xp": theme.colors.heal,
  "event-death": theme.colors.damage,
  "event-item": theme.colors.npc,
  ooc: theme.colors.accent,
  divider: theme.colors.dim,
  "death-feed": theme.colors.damage,
  "scene-art": theme.colors.dim,
  "npc-name": theme.colors.npc,
  "npc-dialogue": theme.colors.npc,
  "npc-status": theme.colors.system
};
var ENTITY_TYPE_COLORS = {
  npc: theme.colors.npc,
  item: theme.colors.heal,
  location: theme.colors.location,
  exit: theme.colors.location
};
function segmentColor(seg, blockColor) {
  switch (seg.style) {
    case "npc":
      return { fg: theme.colors.npc };
    case "damage":
      return { fg: theme.colors.damage, attrs: ATTR_BOLD };
    case "heal":
      return { fg: theme.colors.heal, attrs: ATTR_BOLD };
    case "system":
      return { fg: theme.colors.system };
    case "location":
      return { fg: theme.colors.location };
    case "italic":
      return { fg: blockColor, attrs: ATTR_ITALIC };
    case "bold":
      return { fg: blockColor, attrs: ATTR_BOLD };
    case "entity":
      return {
        fg: ENTITY_TYPE_COLORS[seg.entityType || ""] || theme.colors.npc,
        attrs: ATTR_UNDERLINE
      };
    case "normal":
    default:
      return { fg: blockColor };
  }
}
function initNarrative(container) {
  const store = new NarrativeStore(container.clientWidth);
  let userAtBottom = true;
  let renderScheduled = false;
  let thinkingBlockId = null;
  let scrollOffset = 0;
  let hitRegions = [];
  let thinkingDots = 0;
  let thinkingTimer = null;
  container.innerHTML = "";
  const canvas = document.createElement("canvas");
  canvas.style.display = "block";
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.cursor = "default";
  container.appendChild(canvas);
  container.style.overflowY = "hidden";
  const maybeCtx = canvas.getContext("2d");
  if (!maybeCtx)
    throw new Error("Narrative: failed to get 2d context");
  const ctx = maybeCtx;
  const charSize = measureChar(ctx, MONO_FONT);
  const segmentCache = new Map;
  const layoutCache = new Map;
  let canvasW = 0;
  let canvasH = 0;
  let cols = 0;
  function resize() {
    const rect = container.getBoundingClientRect();
    if (!rect.width || !rect.height)
      return;
    const dpr = window.devicePixelRatio || 1;
    canvasW = rect.width;
    canvasH = rect.height;
    canvas.width = Math.floor(canvasW * dpr);
    canvas.height = Math.floor(canvasH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.floor(canvasW / charSize.width);
    store.remeasure(container.clientWidth);
    clampScroll();
    scheduleRender();
  }
  const resizeObserver = new ResizeObserver(() => resize());
  resizeObserver.observe(container);
  resize();
  function clampScroll() {
    const maxScroll = Math.max(0, store.totalHeight - canvasH);
    scrollOffset = Math.max(0, Math.min(scrollOffset, maxScroll));
  }
  function scrollToBottom() {
    scrollOffset = Math.max(0, store.totalHeight - canvasH);
  }
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    scrollOffset += e.deltaY;
    clampScroll();
    const maxScroll = Math.max(0, store.totalHeight - canvasH);
    userAtBottom = scrollOffset >= maxScroll - 30;
    scheduleRender();
  }, { passive: false });
  function scheduleRender() {
    if (renderScheduled)
      return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      renderVisible();
    });
  }
  function layoutBlock(blockId, blockText, blockType) {
    const cached = layoutCache.get(blockId);
    if (cached && cached.cols === cols && blockType !== "thinking") {
      return cached.placed;
    }
    const blockColor = BLOCK_TYPE_COLORS[blockType] || theme.colors.primary;
    const padding = 2;
    const maxCol = Math.max(cols - padding * 2, 10);
    if (blockType === "divider") {
      const rule = "─".repeat(Math.min(maxCol, cols - padding * 2));
      return [{ text: rule, col: padding, row: 0, fg: theme.colors.dim }];
    }
    if (blockType === "npc-name") {
      return [{ text: `◆ ${blockText}`, col: padding, row: 0, fg: theme.colors.npc, attrs: 1 }];
    }
    if (blockType === "npc-dialogue") {
      const dialogPadding = padding + 2;
      const dialogMaxCol = Math.max(cols - dialogPadding - padding, 10);
      const words = blockText.split(" ");
      const placed2 = [];
      let col2 = dialogPadding;
      let row2 = 0;
      for (let r = 0;r < 20; r++) {
        placed2.push({ text: "│", col: padding, row: r, fg: theme.colors.npc });
      }
      for (const word of words) {
        if (col2 + word.length > dialogPadding + dialogMaxCol && col2 > dialogPadding) {
          row2++;
          col2 = dialogPadding;
        }
        placed2.push({ text: word + " ", col: col2, row: row2, fg: theme.colors.npc, attrs: 2 });
        col2 += word.length + 1;
      }
      const actualRows = row2 + 1;
      return placed2.filter((p) => !(p.text === "│" && p.row >= actualRows));
    }
    let segments = segmentCache.get(blockId);
    if (!segments) {
      if (blockType === "thinking") {
        const dots = ".".repeat(thinkingDots % 4);
        segments = [{ text: `The world responds${dots}`, style: "normal" }];
      } else if (blockType === "player-action" || blockType === "system") {
        segments = [{ text: blockText, style: "normal" }];
      } else {
        segments = parseNarrative(blockText);
      }
      if (blockType !== "thinking") {
        segmentCache.set(blockId, segments);
      }
    }
    const placed = [];
    let col = padding;
    let row = 0;
    for (const seg of segments) {
      const { fg, attrs } = segmentColor(seg, blockColor);
      const lines = seg.text.split(`
`);
      for (let li = 0;li < lines.length; li++) {
        if (li > 0) {
          col = padding;
          row++;
        }
        const words = lines[li].split(/( +)/);
        for (const word of words) {
          if (!word)
            continue;
          if (col + word.length > padding + maxCol && col > padding) {
            col = padding;
            row++;
          }
          if (word.length > maxCol) {
            let pos = 0;
            while (pos < word.length) {
              const chunk = word.slice(pos, pos + maxCol - (col - padding));
              placed.push({
                text: chunk,
                col,
                row,
                fg,
                attrs,
                entityId: seg.entityId,
                entityName: seg.style === "entity" ? seg.text : undefined
              });
              col += chunk.length;
              pos += chunk.length;
              if (pos < word.length) {
                col = padding;
                row++;
              }
            }
          } else {
            placed.push({
              text: word,
              col,
              row,
              fg,
              attrs,
              entityId: seg.entityId,
              entityName: seg.style === "entity" ? seg.text : undefined
            });
            col += word.length;
          }
        }
      }
    }
    if (blockType !== "thinking") {
      layoutCache.set(blockId, { cols, placed });
    }
    return placed;
  }
  function renderVisible() {
    ctx.clearRect(0, 0, canvasW, canvasH);
    ctx.fillStyle = theme.colors.bg;
    ctx.fillRect(0, 0, canvasW, canvasH);
    if (store.length === 0)
      return;
    const { start, end } = store.getVisibleRange(scrollOffset, canvasH);
    hitRegions = [];
    for (let i = start;i < end; i++) {
      const block = store.getBlock(i);
      if (!block)
        continue;
      const blockScreenY = block.y - scrollOffset;
      if (blockScreenY + block.height < 0 || blockScreenY > canvasH)
        continue;
      const placed = layoutBlock(block.id, block.text, block.type);
      for (const seg of placed) {
        const segPixelY = blockScreenY + seg.row * charSize.height;
        if (segPixelY + charSize.height < 0 || segPixelY > canvasH)
          continue;
        drawTextAtPixel(ctx, seg.col, segPixelY, seg.text, seg.fg, charSize, seg.attrs);
        if (seg.entityId) {
          hitRegions.push({
            x: seg.col * charSize.width,
            y: segPixelY,
            w: seg.text.length * charSize.width,
            h: charSize.height,
            entityId: seg.entityId,
            entityName: seg.entityName || seg.text
          });
        }
      }
    }
  }
  function drawTextAtPixel(ctx2, col, pixelY, text, fg, cs, attrs) {
    ctx2.font = fontForAttrs(MONO_FONT, attrs);
    ctx2.fillStyle = fg;
    ctx2.textBaseline = "top";
    ctx2.textAlign = "left";
    const yOffset = (cs.height - 13) * 0.35;
    for (let i = 0;i < text.length; i++) {
      const px = (col + i) * cs.width;
      ctx2.fillText(text[i], px, pixelY + yOffset);
    }
    if (attrs && attrs & ATTR_UNDERLINE) {
      ctx2.strokeStyle = fg;
      ctx2.lineWidth = 1;
      const underY = pixelY + cs.height - 2;
      const startX = col * cs.width;
      ctx2.beginPath();
      ctx2.moveTo(startX, underY);
      ctx2.lineTo(startX + text.length * cs.width, underY);
      ctx2.stroke();
    }
  }
  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    for (const region of hitRegions) {
      if (mx >= region.x && mx < region.x + region.w && my >= region.y && my < region.y + region.h) {
        canvas.dispatchEvent(new CustomEvent("narrative-entity-click", {
          detail: { entityId: region.entityId, entityName: region.entityName },
          bubbles: true
        }));
        return;
      }
    }
  });
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let overEntity = false;
    for (const region of hitRegions) {
      if (mx >= region.x && mx < region.x + region.w && my >= region.y && my < region.y + region.h) {
        overEntity = true;
        break;
      }
    }
    canvas.style.cursor = overEntity ? "pointer" : "default";
  });
  const namedBlockIds = new Map;
  function addBlockInternal(text, type, customId) {
    const block = store.add(text, "", type);
    if (customId) {
      namedBlockIds.set(customId, block.id);
    }
    if (userAtBottom) {
      requestAnimationFrame(() => {
        scrollToBottom();
        scheduleRender();
      });
    }
    scheduleRender();
    return block.id;
  }
  function removeNamedBlock(customId) {
    const blockId = namedBlockIds.get(customId);
    if (blockId) {
      segmentCache.delete(blockId);
      layoutCache.delete(blockId);
      store.removeById(blockId);
      namedBlockIds.delete(customId);
    }
  }
  function startThinkingAnimation() {
    if (thinkingTimer)
      return;
    thinkingDots = 0;
    thinkingTimer = setInterval(() => {
      thinkingDots = (thinkingDots + 1) % 4;
      if (thinkingBlockId)
        segmentCache.delete(thinkingBlockId);
      scheduleRender();
    }, 500);
  }
  function stopThinkingAnimation() {
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
  }
  let lastPhase = "";
  onRoundStateChange((rs) => {
    if (rs.phase === "resolving" && lastPhase !== "resolving") {
      addBlockInternal("", "divider");
    }
    lastPhase = rs.phase;
  });
  return {
    addBlock(text, type) {
      addBlockInternal(text, type);
    },
    addHtml(html, type) {
      const temp = document.createElement("div");
      temp.innerHTML = html;
      const text = temp.textContent || temp.innerText || html;
      addBlockInternal(text, type);
    },
    replaceBlock(id, text, type) {
      removeNamedBlock(id);
      addBlockInternal(text, type, id);
    },
    removeBlockById(id) {
      removeNamedBlock(id);
      clampScroll();
      scheduleRender();
    },
    showThinking() {
      thinkingBlockId = addBlockInternal("The world responds", "thinking");
      startThinkingAnimation();
    },
    removeThinking() {
      stopThinkingAnimation();
      if (thinkingBlockId) {
        segmentCache.delete(thinkingBlockId);
        layoutCache.delete(thinkingBlockId);
        store.removeById(thinkingBlockId);
        thinkingBlockId = null;
        clampScroll();
        scheduleRender();
      }
    },
    canvas
  };
}

// src/ui/mention-dropdown.ts
function createMentionDropdown() {
  const el = document.createElement("div");
  el.className = "mention-dropdown";
  el.style.display = "none";
  document.body.appendChild(el);
  let items = [];
  let filtered = [];
  let selectedIndex = 0;
  let selectCallback = null;
  function render() {
    el.innerHTML = filtered.map((s, i) => {
      const icon = s.type === "npc" ? "◆" : "@";
      const cls = i === selectedIndex ? "mention-item selected" : "mention-item";
      const typeCls = s.type === "npc" ? "mention-npc" : "mention-player";
      return `<div class="${cls} ${typeCls}" data-index="${i}"><span class="mention-icon">${icon}</span>${s.name}</div>`;
    }).join("");
    el.querySelectorAll(".mention-item").forEach((row) => {
      row.addEventListener("click", () => {
        const idx = parseInt(row.dataset.index || "0", 10);
        if (filtered[idx] && selectCallback)
          selectCallback(filtered[idx].name);
        dropdown.hide();
      });
    });
  }
  const dropdown = {
    el,
    onSelect: null,
    show(suggestions, anchor) {
      items = suggestions;
      filtered = [...items];
      selectedIndex = 0;
      selectCallback = this.onSelect;
      const rect = anchor.getBoundingClientRect();
      el.style.position = "fixed";
      el.style.bottom = `${window.innerHeight - rect.top + 4}px`;
      el.style.left = `${rect.left}px`;
      el.style.display = "";
      render();
    },
    hide() {
      el.style.display = "none";
      items = [];
      filtered = [];
    },
    isVisible() {
      return el.style.display !== "none";
    },
    filter(query) {
      const q = query.toLowerCase();
      filtered = q ? items.filter((s) => s.name.toLowerCase().startsWith(q)) : [...items];
      selectedIndex = 0;
      render();
      el.style.display = filtered.length > 0 ? "" : "none";
    },
    handleKey(e) {
      if (!this.isVisible())
        return false;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = Math.max(0, selectedIndex - 1);
        render();
        return true;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = Math.min(filtered.length - 1, selectedIndex + 1);
        render();
        return true;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        if (filtered[selectedIndex] && selectCallback) {
          e.preventDefault();
          selectCallback(filtered[selectedIndex].name);
          this.hide();
          return true;
        }
      }
      if (e.key === "Escape") {
        this.hide();
        return true;
      }
      return false;
    }
  };
  return dropdown;
}

// src/panels/input.ts
function initInput(inputEl, onSubmit, getContext) {
  const history = [];
  let historyIndex = -1;
  let locked = false;
  const defaultPlaceholder = inputEl.placeholder || "What do you do?";
  function setLocked(isLocked) {
    locked = isLocked;
    inputEl.disabled = isLocked;
    inputEl.classList.toggle("input-locked", isLocked);
  }
  onRoundStateChange((rs) => {
    switch (rs.phase) {
      case "ready":
        setLocked(false);
        inputEl.placeholder = defaultPlaceholder;
        break;
      case "collecting": {
        setLocked(false);
        const timer = rs.secondsLeft != null ? `${rs.secondsLeft}s left to act...` : "Round open...";
        inputEl.placeholder = timer;
        break;
      }
      case "resolving":
        setLocked(true);
        inputEl.placeholder = "Resolving...";
        break;
      case "npc_response":
        setLocked(true);
        inputEl.placeholder = "NPCs responding...";
        break;
    }
  });
  const dropdown = createMentionDropdown();
  let mentionActive = false;
  let mentionStart = -1;
  function getMentionSuggestions() {
    if (!getContext)
      return [];
    const ctx = getContext();
    const suggestions = [];
    for (const npc of ctx.npcs) {
      const name = typeof npc === "string" ? npc : npc.name;
      suggestions.push({ name, type: "npc" });
    }
    for (const p of ctx.players) {
      const name = typeof p === "string" ? p : p.name;
      suggestions.push({ name, type: "player" });
    }
    return suggestions;
  }
  dropdown.onSelect = (name) => {
    const before = inputEl.value.slice(0, mentionStart);
    const after = inputEl.value.slice(inputEl.selectionStart || inputEl.value.length);
    inputEl.value = `${before}@${name} ${after}`;
    inputEl.focus();
    mentionActive = false;
    mentionStart = -1;
  };
  inputEl.addEventListener("keydown", (e) => {
    if (locked)
      return;
    if (mentionActive && dropdown.handleKey(e))
      return;
    if (e.key === "Enter") {
      if (mentionActive) {
        dropdown.hide();
        mentionActive = false;
      }
      const action = inputEl.value.trim();
      if (action) {
        history.unshift(action);
        historyIndex = -1;
        onSubmit(action);
        inputEl.value = "";
      }
    } else if (e.key === "ArrowUp" && !mentionActive) {
      e.preventDefault();
      if (historyIndex < history.length - 1) {
        historyIndex++;
        inputEl.value = history[historyIndex];
      }
    } else if (e.key === "ArrowDown" && !mentionActive) {
      e.preventDefault();
      if (historyIndex > 0) {
        historyIndex--;
        inputEl.value = history[historyIndex];
      } else {
        historyIndex = -1;
        inputEl.value = "";
      }
    } else if (e.key === "Escape" && mentionActive) {
      dropdown.hide();
      mentionActive = false;
    }
  });
  inputEl.addEventListener("input", () => {
    const val = inputEl.value;
    const cursor = inputEl.selectionStart || val.length;
    if (!mentionActive) {
      if (cursor > 0 && val[cursor - 1] === "@") {
        const charBefore = cursor > 1 ? val[cursor - 2] : " ";
        if (charBefore === " " || charBefore === undefined || cursor === 1) {
          mentionActive = true;
          mentionStart = cursor - 1;
          const suggestions = getMentionSuggestions();
          dropdown.show(suggestions, inputEl);
          dropdown.filter("");
        }
      }
    } else {
      const query = val.slice(mentionStart + 1, cursor);
      if (query.includes(" ") || cursor <= mentionStart) {
        dropdown.hide();
        mentionActive = false;
      } else {
        dropdown.filter(query);
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
function updateMap(state2, onAction) {
  if (!state2.roomMap || !renderer)
    return;
  const map = state2.roomMap;
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
        const entityId = "id" in entity ? entity.id : ("target" in entity) ? entity.target : "";
        const entityName = "name" in entity ? entity.name : ("target" in entity) ? entity.target : "";
        fetchEntityData(entityId || entityName, entityName).then((data) => {
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
            name: data.name || entityName,
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
        showPlayerCard(state2);
      }
    });
    cleanupInput?.();
    cleanupInput = setupMapInput(controller, renderer, mapRef);
  } else {
    controller.loadMap(map);
  }
  showPlayerCard(state2);
  renderer.render(map, controller.x, controller.y);
}
function showPlayerCard(state2) {
  if (!renderer)
    return;
  const card = {
    type: "player",
    name: state2.player.name,
    labels: ["Player"],
    summary: state2.location.name,
    health: state2.player.health,
    maxHealth: state2.player.maxHealth,
    level: state2.player.level,
    xp: state2.player.xp,
    xpThreshold: state2.player.xpThreshold
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

// src/panels/panel-utils.ts
function textRow(text, fg, cols, attrs) {
  const row = [];
  for (let i = 0;i < cols; i++) {
    row.push({ char: i < text.length ? text[i] : " ", fg, attrs });
  }
  return row;
}
function coloredRow(segments, cols) {
  const row = [];
  for (const seg of segments) {
    for (const ch of seg.text) {
      row.push({ char: ch, fg: seg.fg, attrs: seg.attrs });
    }
  }
  while (row.length < cols) {
    row.push({ char: " ", fg: theme.colors.primary });
  }
  return row;
}
function emptyRow(cols) {
  return Array.from({ length: cols }, () => ({ char: " ", fg: theme.colors.primary }));
}

// src/panels/character.ts
function barRow(label, value, max, barLen, fullColor, emptyColor, cols) {
  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const filled = Math.round(pct * barLen);
  const empty = barLen - filled;
  const valText = ` ${value}/${max}`;
  const segments = [
    { text: label + " ", fg: theme.colors.dim },
    { text: "█".repeat(filled), fg: fullColor },
    { text: "░".repeat(empty), fg: emptyColor },
    { text: valText, fg: theme.colors.primary }
  ];
  return coloredRow(segments, cols);
}
function renderCharacterPanel(panel, state2) {
  const p = state2.player;
  const cols = panel.cols;
  const cells = [];
  if (p.archetype) {
    cells.push(textRow(p.archetype, theme.colors.accent, cols));
    cells.push(emptyRow(cols));
  }
  const hpColor = p.health / p.maxHealth > 0.3 ? theme.colors.heal : theme.colors.damage;
  cells.push(barRow("HP", p.health, p.maxHealth, 10, hpColor, theme.colors.dim, cols));
  cells.push(barRow("XP", p.xp, p.xpThreshold, 10, theme.colors.accent, theme.colors.dim, cols));
  cells.push(coloredRow([
    { text: "Lv ", fg: theme.colors.dim },
    { text: String(p.level), fg: theme.colors.primary }
  ], cols));
  const skillEntries = Object.entries(p.skills).filter(([, v]) => v > 0);
  if (skillEntries.length > 0) {
    cells.push(emptyRow(cols));
    for (const [name, level] of skillEntries) {
      const dots = "●".repeat(level) + "○".repeat(Math.max(0, 5 - level));
      cells.push(coloredRow([
        { text: name + " ", fg: theme.colors.primary },
        { text: dots, fg: theme.colors.accent }
      ], cols));
    }
  }
  panel.paint(cells);
}

// src/panels/inventory.ts
var RARITY_COLORS = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
var SLOT_GLYPHS = {
  weapon: "⚔",
  armor: "\uD83D\uDEE1",
  accessory: "◇",
  ring: "○"
};
var SLOT_ORDER = ["weapon", "armor", "accessory", "ring"];
var onManageInventory = null;
function setManageInventoryCallback(fn) {
  onManageInventory = fn;
}
function renderInventoryPanel(panel, state2) {
  const cols = panel.cols;
  const cells = [];
  cells.push(coloredRow([{ text: "EQUIPPED", fg: theme.colors.dim }], cols));
  for (const slot of SLOT_ORDER) {
    const glyph = SLOT_GLYPHS[slot] || "?";
    const item = state2.inventory.find((i) => i.equipped && i.slot_type === slot);
    if (item) {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      cells.push(coloredRow([
        { text: `${glyph} `, fg: theme.colors.dim },
        { text: item.name, fg: color }
      ], cols));
    } else {
      cells.push(coloredRow([
        { text: `${glyph} `, fg: theme.colors.dim },
        { text: "- empty -", fg: "#3a3a48" }
      ], cols));
    }
  }
  cells.push(emptyRow(cols));
  const backpack = state2.inventory.filter((i) => !i.equipped);
  const count = backpack.length;
  cells.push(coloredRow([
    { text: "PACK", fg: theme.colors.dim },
    { text: ` ${count}/10`, fg: theme.colors.primary }
  ], cols));
  if (count === 0) {
    cells.push(textRow("  Empty", theme.colors.dim, cols));
  } else {
    for (const item of backpack) {
      const color = RARITY_COLORS[item.rarity] || RARITY_COLORS.common;
      const segments = [
        { text: "· ", fg: theme.colors.dim },
        { text: item.name, fg: color }
      ];
      if (item.quantity > 1) {
        segments.push({ text: ` ×${item.quantity}`, fg: theme.colors.heal });
      }
      cells.push(coloredRow(segments, cols));
    }
  }
  cells.push(emptyRow(cols));
  cells.push(coloredRow([
    { text: "  [manage inventory]", fg: theme.colors.accent }
  ], cols));
  panel.paint(cells);
}

// src/panels/exits.ts
function renderExitsPanel(panel, state2, onAction) {
  const cols = panel.cols;
  const cells = [];
  panel.clearHitRegions();
  if (state2.location.exits.length === 0) {
    cells.push(textRow("None", theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }
  for (const e of state2.location.exits) {
    const dir = typeof e === "string" ? e : e.direction;
    const dest = typeof e === "string" ? "" : e.name;
    const label = dir.charAt(0).toUpperCase() + dir.slice(1);
    const segments = [
      { text: "→ " + label, fg: theme.colors.location }
    ];
    if (dest) {
      segments.push({ text: "  " + dest, fg: theme.colors.dim });
    }
    const rowIdx = cells.length;
    cells.push(coloredRow(segments, cols));
    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `go ${dir}` }
    });
  }
  panel.paint(cells);
}

// src/panels/present.ts
function renderPresentPanel(panel, state2, onAction) {
  const cols = panel.cols;
  const cells = [];
  const npcs = state2.location.npcs || [];
  const items = state2.location.items || [];
  const players = state2.location.players || [];
  panel.clearHitRegions();
  if (npcs.length === 0 && items.length === 0 && players.length === 0) {
    cells.push(textRow("Nothing here", theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }
  const rs = getRoundState();
  const isThinking = rs.phase === "npc_response";
  const npcColor = isThinking ? theme.colors.system : theme.colors.npc;
  for (const npc of npcs) {
    const name = typeof npc === "string" ? npc : npc.name;
    const role = typeof npc === "string" ? "" : npc.role || "";
    const segments = [
      { text: "◆ ", fg: npcColor },
      { text: name, fg: npcColor }
    ];
    if (role) {
      segments.push({ text: " — " + role, fg: theme.colors.dim });
    }
    const rowIdx = cells.length;
    cells.push(coloredRow(segments, cols));
    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `talk to ${name}` }
    });
  }
  for (const p of players) {
    const name = typeof p === "string" ? p : p.name;
    cells.push(coloredRow([
      { text: "@ ", fg: theme.colors.heal },
      { text: name, fg: theme.colors.primary }
    ], cols));
  }
  for (const item of items) {
    const name = typeof item === "string" ? item : item.name;
    const rowIdx = cells.length;
    cells.push(coloredRow([
      { text: "· ", fg: theme.colors.dim },
      { text: name, fg: theme.colors.primary }
    ], cols));
    panel.registerHitRegion({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `examine ${name}` }
    });
  }
  panel.paint(cells);
}

// src/panels/questlog.ts
function renderQuestLogPanel(panel, quests) {
  const cols = panel.cols;
  const cells = [];
  panel.clearHitRegions();
  if (!quests || quests.length === 0) {
    cells.push(textRow("No active quests", theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }
  for (let i = 0;i < quests.length; i++) {
    const q = quests[i];
    if (i > 0)
      cells.push(emptyRow(cols));
    const questStartRow = cells.length;
    const nameSegs = [
      { text: q.name, fg: q.completed ? theme.colors.dim : theme.colors.primary, attrs: 1 }
    ];
    if (q.completed) {
      nameSegs.push({ text: " [DONE]", fg: theme.colors.heal });
    }
    cells.push(coloredRow(nameSegs, cols));
    if (q.giver) {
      cells.push(coloredRow([
        { text: "from ", fg: theme.colors.dim },
        { text: q.giver, fg: theme.colors.npc }
      ], cols));
    }
    const progress = q.totalStages > 0 ? Math.round(q.currentStage / q.totalStages * 10) : 0;
    const filled = Math.min(10, Math.max(0, progress));
    const empty = 10 - filled;
    const stageText = ` ${q.currentStage}/${q.totalStages}`;
    cells.push(coloredRow([
      { text: "█".repeat(filled), fg: theme.colors.accent },
      { text: "░".repeat(empty), fg: theme.colors.dim },
      { text: stageText, fg: theme.colors.primary }
    ], cols));
    if (q.description) {
      const desc = q.description.length > 60 ? q.description.slice(0, 57) + "..." : q.description;
      cells.push(textRow(desc, theme.colors.dim, cols));
    }
    const questEndRow = cells.length;
    panel.registerHitRegion({
      col: 0,
      row: questStartRow,
      width: cols,
      height: questEndRow - questStartRow,
      data: { questName: q.name }
    });
  }
  panel.paint(cells);
}

// src/panels/factions.ts
function dispositionColor(disposition) {
  switch (disposition) {
    case "hostile":
      return theme.colors.damage;
    case "unfriendly":
      return theme.colors.damage;
    case "friendly":
      return theme.colors.heal;
    case "allied":
      return theme.colors.heal;
    default:
      return theme.colors.primary;
  }
}
function renderFactionsPanel(panel, factions) {
  const cols = panel.cols;
  const cells = [];
  if (!factions || factions.length === 0) {
    cells.push(textRow("No known factions", theme.colors.dim, cols));
    panel.paint(cells);
    return;
  }
  for (let i = 0;i < factions.length; i++) {
    const f = factions[i];
    if (i > 0)
      cells.push(emptyRow(cols));
    cells.push(textRow(f.name, theme.colors.primary, cols));
    const normalized = Math.round((f.reputation + 1) * 5);
    const clamped = Math.max(0, Math.min(10, normalized));
    const barColor = dispositionColor(f.disposition);
    cells.push(coloredRow([
      { text: "█".repeat(clamped), fg: barColor },
      { text: "░".repeat(10 - clamped), fg: theme.colors.dim },
      { text: " " + f.disposition, fg: barColor }
    ], cols));
  }
  panel.paint(cells);
}

// src/ui/terminal-panel.ts
class TerminalPanel {
  canvas;
  ctx;
  charSize;
  cols = 0;
  rows = 0;
  font;
  prevCells = [];
  lastCells = [];
  hitRegions = [];
  resizeObserver;
  boundClick;
  constructor(opts) {
    this.font = opts.font ?? MONO_FONT;
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    opts.container.appendChild(this.canvas);
    const ctx = this.canvas.getContext("2d");
    if (!ctx)
      throw new Error("TerminalPanel: failed to get 2d context");
    this.ctx = ctx;
    this.charSize = measureChar(this.ctx, this.font);
    this.resize();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(opts.container);
    this.boundClick = (e) => this.handleClick(e);
    this.canvas.addEventListener("click", this.boundClick);
  }
  resize() {
    const rect = this.canvas.parentElement?.getBoundingClientRect();
    if (!rect)
      return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = rect.width;
    const cssH = rect.height;
    this.canvas.width = Math.floor(cssW * dpr);
    this.canvas.height = Math.floor(cssH * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.cols = Math.floor(cssW / this.charSize.width);
    this.rows = Math.floor(cssH / this.charSize.height);
    this.prevCells = [];
    if (this.lastCells.length > 0) {
      this.paint(this.lastCells);
    }
  }
  paint(cells) {
    const rows = Math.min(cells.length, this.rows);
    for (let r = 0;r < rows; r++) {
      const row = cells[r];
      const prevRow = this.prevCells[r];
      const cols = Math.min(row?.length ?? 0, this.cols);
      for (let c = 0;c < cols; c++) {
        const cell = row[c];
        const prev = prevRow?.[c];
        if (prev && prev.char === cell.char && prev.fg === cell.fg && prev.bg === cell.bg && prev.attrs === cell.attrs) {
          continue;
        }
        const px = c * this.charSize.width;
        const py = r * this.charSize.height;
        this.ctx.clearRect(px, py, this.charSize.width, this.charSize.height);
        fillCell(this.ctx, c, r, cell, this.charSize);
      }
    }
    this.prevCells = cells.map((row) => row.map((cell) => ({ ...cell })));
    this.lastCells = cells;
  }
  registerHitRegion(region) {
    this.hitRegions.push(region);
  }
  clearHitRegions() {
    this.hitRegions = [];
  }
  handleClick(e) {
    const rect = this.canvas.getBoundingClientRect();
    const col = Math.floor((e.clientX - rect.left) / this.charSize.width);
    const row = Math.floor((e.clientY - rect.top) / this.charSize.height);
    for (const region of this.hitRegions) {
      if (col >= region.col && col < region.col + region.width && row >= region.row && row < region.row + region.height) {
        this.canvas.dispatchEvent(new CustomEvent("panel-click", {
          detail: region.data,
          bubbles: true
        }));
        return;
      }
    }
  }
  destroy() {
    this.resizeObserver.disconnect();
    this.canvas.removeEventListener("click", this.boundClick);
  }
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
  let panel;
  if (opts.canvas) {
    panel = new TerminalPanel({ container: body });
  }
  return {
    el,
    body,
    panel,
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
    showQuest(quest) {
      if (currentTw)
        currentTw.cancel();
      const status = quest.completed ? " [COMPLETE]" : "";
      titleBar.textContent = `─ ${quest.name}${status} ─`;
      body.innerHTML = "";
      backdrop.style.display = "";
      const lines = [];
      if (quest.giver)
        lines.push(`Quest giver: ${quest.giver}`);
      lines.push("");
      lines.push(quest.description);
      lines.push("");
      const filled = quest.totalStages > 0 ? Math.round(quest.currentStage / quest.totalStages * 10) : 0;
      const bar = "█".repeat(Math.min(10, filled)) + "░".repeat(10 - Math.min(10, filled));
      lines.push(`Progress: ${bar} ${quest.currentStage}/${quest.totalStages}`);
      const text = lines.join(`
`);
      currentTw = createTypewriter({
        text,
        font: DIALOG_FONT,
        maxWidth: DIALOG_MAX_WIDTH,
        container: body,
        charDelay: 15,
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

// src/state/inventory-api.ts
var API_BASE = "/api/inventory";
var _state = null;
var _playerId = "";
var _onRender = null;
var _onEvent = null;
function initInventoryApi(state2, playerId, onRender, onEvent) {
  _state = state2;
  _playerId = playerId;
  _onRender = onRender;
  _onEvent = onEvent || null;
}
function emitEvent(text, style = "event-item") {
  if (_onEvent)
    _onEvent(text, style);
}
function rerender() {
  if (_onRender)
    _onRender();
}
function snapshot() {
  return _state ? _state.inventory.map((i) => ({ ...i })) : [];
}
function rollback(saved) {
  if (_state) {
    _state.inventory = saved;
    rerender();
  }
}
function locationUuid() {
  return _state?.roomMap?.id || "";
}
async function post(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { ok: false, detail: err.detail || `HTTP ${res.status}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, detail: String(e) };
  }
}
async function equipItem(itemId, slot) {
  if (!_state)
    return "Not initialized";
  const saved = snapshot();
  const item = _state.inventory.find((i) => i.id === itemId);
  if (!item)
    return "Item not found";
  const current = _state.inventory.find((i) => i.equipped && i.slot_type === slot);
  if (current)
    current.equipped = false;
  item.equipped = true;
  item.slot_type = slot;
  rerender();
  const result = await post("/equip", { player_id: _playerId, item_id: itemId, slot });
  if (!result.ok) {
    rollback(saved);
    return result.detail || "Equip failed";
  }
  emitEvent(`[equipped ${item.name} → ${slot}]`, "event-item");
  return null;
}
async function unequipItem(slot) {
  if (!_state)
    return "Not initialized";
  const saved = snapshot();
  const item = _state.inventory.find((i) => i.equipped && i.slot_type === slot);
  if (!item)
    return "No item in slot";
  item.equipped = false;
  rerender();
  const result = await post("/unequip", { player_id: _playerId, slot });
  if (!result.ok) {
    rollback(saved);
    return result.detail || "Unequip failed";
  }
  emitEvent(`[unequipped ${item.name}]`, "event-item");
  return null;
}
async function dropItem(itemId, quantity) {
  if (!_state)
    return "Not initialized";
  const saved = snapshot();
  const idx = _state.inventory.findIndex((i) => i.id === itemId);
  if (idx === -1)
    return "Item not found";
  const item = _state.inventory[idx];
  if (quantity && item.quantity > quantity) {
    item.quantity -= quantity;
  } else {
    _state.inventory.splice(idx, 1);
  }
  _state.location.items.push({ name: item.name, id: item.id });
  rerender();
  const result = await post("/drop", { player_id: _playerId, item_id: itemId, location_uuid: locationUuid(), quantity });
  if (!result.ok) {
    rollback(saved);
    return result.detail || "Drop failed";
  }
  emitEvent(`[-${item.name}] dropped`, "event-item");
  return null;
}
async function useItem(itemId) {
  if (!_state)
    return "Not initialized";
  const saved = snapshot();
  const idx = _state.inventory.findIndex((i) => i.id === itemId);
  if (idx === -1)
    return "Item not found";
  const item = _state.inventory[idx];
  if (item.quantity > 1) {
    item.quantity -= 1;
  } else {
    _state.inventory.splice(idx, 1);
  }
  rerender();
  const result = await post("/use", { player_id: _playerId, item_id: itemId });
  if (!result.ok) {
    rollback(saved);
    return result.detail || "Use failed";
  }
  emitEvent(`[used ${item.name}]`, "event-item");
  return null;
}
async function pickupItem(itemId) {
  if (!_state)
    return "Not initialized";
  const saved = snapshot();
  const groundIdx = _state.location.items.findIndex((i) => i.id === itemId);
  const groundItem = groundIdx >= 0 ? _state.location.items[groundIdx] : null;
  if (groundIdx >= 0)
    _state.location.items.splice(groundIdx, 1);
  _state.inventory.push({
    id: itemId,
    name: groundItem?.name || "...",
    rarity: "common",
    slot_type: "",
    equipped: false,
    is_consumable: false,
    is_quest_item: false,
    effects: [],
    quantity: 1
  });
  rerender();
  const result = await post("/pickup", { player_id: _playerId, item_id: itemId, location_uuid: locationUuid() });
  if (!result.ok) {
    rollback(saved);
    return result.detail || "Pickup failed";
  }
  emitEvent(`[+${groundItem?.name || "item"}] picked up`, "event-item");
  return null;
}

// src/ui/inventory-modal.ts
var RARITY_COLORS2 = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
var SLOT_LABELS = {
  weapon: "WPN",
  armor: "ARM",
  accessory: "ACC",
  ring: "RNG"
};
var SLOT_ORDER2 = ["weapon", "armor", "accessory", "ring"];
function createInventoryModal(getState) {
  const backdrop = document.createElement("div");
  backdrop.className = "dialog-backdrop";
  backdrop.style.display = "none";
  const win = document.createElement("div");
  win.className = "dialog-win";
  win.style.maxWidth = "600px";
  win.style.width = "90vw";
  backdrop.appendChild(win);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop)
      close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && backdrop.style.display !== "none")
      close();
  });
  function close() {
    backdrop.style.display = "none";
  }
  function open() {
    backdrop.style.display = "";
    refresh();
  }
  function refresh() {
    const state2 = getState();
    win.innerHTML = "";
    const header = document.createElement("div");
    header.className = "win-title dialog-title";
    header.style.display = "flex";
    header.style.justifyContent = "space-between";
    header.style.alignItems = "center";
    const title = document.createElement("span");
    title.style.color = "#8b5cf6";
    title.textContent = "INVENTORY";
    const meta = document.createElement("span");
    meta.style.color = "#6a6a78";
    meta.style.fontSize = "12px";
    const total = state2.inventory.length;
    const weight = total * 5;
    meta.textContent = `${weight}/50 wt · ${total} items`;
    const closeBtn = document.createElement("span");
    closeBtn.textContent = "[×]";
    closeBtn.style.color = "#e05050";
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = close;
    header.appendChild(title);
    const rightSpan = document.createElement("span");
    rightSpan.appendChild(meta);
    rightSpan.appendChild(document.createTextNode(" "));
    rightSpan.appendChild(closeBtn);
    header.appendChild(rightSpan);
    win.appendChild(header);
    const body = document.createElement("div");
    body.className = "win-body";
    body.style.display = "flex";
    body.style.gap = "16px";
    body.style.fontFamily = "'Fira Code', monospace";
    body.style.fontSize = "12px";
    body.style.lineHeight = "1.6";
    const slotsCol = document.createElement("div");
    slotsCol.style.flex = "1";
    slotsCol.style.minWidth = "0";
    const slotsLabel = document.createElement("div");
    slotsLabel.style.color = "#6a6a78";
    slotsLabel.style.fontSize = "11px";
    slotsLabel.style.marginBottom = "6px";
    slotsLabel.textContent = "EQUIPMENT SLOTS";
    slotsCol.appendChild(slotsLabel);
    for (const slot of SLOT_ORDER2) {
      const label = SLOT_LABELS[slot];
      const item = state2.inventory.find((i) => i.equipped && i.slot_type === slot);
      const card = createSlotCard(label, slot, item);
      slotsCol.appendChild(card);
    }
    const packCol = document.createElement("div");
    packCol.style.flex = "1";
    packCol.style.minWidth = "0";
    const backpack = state2.inventory.filter((i) => !i.equipped);
    const packLabel = document.createElement("div");
    packLabel.style.color = "#6a6a78";
    packLabel.style.fontSize = "11px";
    packLabel.style.marginBottom = "6px";
    packLabel.textContent = `BACKPACK (${backpack.length}/10)`;
    packCol.appendChild(packLabel);
    if (backpack.length === 0) {
      const empty = document.createElement("div");
      empty.style.color = "#3a3a48";
      empty.style.padding = "8px";
      empty.textContent = "Empty";
      packCol.appendChild(empty);
    } else {
      for (const item of backpack) {
        packCol.appendChild(createBackpackCard(item));
      }
    }
    const groundItems = state2.location.items;
    if (groundItems.length > 0) {
      const divider = document.createElement("div");
      divider.style.borderTop = "1px solid #1a1a24";
      divider.style.marginTop = "8px";
      divider.style.paddingTop = "8px";
      packCol.appendChild(divider);
      const groundLabel = document.createElement("div");
      groundLabel.style.color = "#6a6a78";
      groundLabel.style.fontSize = "10px";
      groundLabel.textContent = "GROUND (this room)";
      packCol.appendChild(groundLabel);
      for (const gi of groundItems) {
        const row = document.createElement("div");
        row.style.marginTop = "4px";
        const name = document.createElement("span");
        name.style.color = "#808080";
        name.textContent = gi.name;
        row.appendChild(name);
        const pickup = createActionLink("pickup", "#50c878", async () => {
          const err = await pickupItem(gi.id);
          if (err)
            console.warn("Pickup failed:", err);
          else
            refresh();
        });
        row.appendChild(document.createTextNode(" "));
        row.appendChild(pickup);
        packCol.appendChild(row);
      }
    }
    body.appendChild(slotsCol);
    body.appendChild(packCol);
    win.appendChild(body);
  }
  function createSlotCard(label, slot, item) {
    const card = document.createElement("div");
    card.style.border = "1px solid #1a1a24";
    card.style.padding = "8px";
    card.style.marginBottom = "6px";
    card.style.borderRadius = "3px";
    card.style.background = item ? "#12121a" : "#0a0a0f";
    if (item) {
      const color = RARITY_COLORS2[item.rarity] || "#808080";
      const top = document.createElement("div");
      top.innerHTML = `<span style="color:#6a6a78">${label}</span> <span style="color:${color}">${item.name}</span>`;
      card.appendChild(top);
      const details = document.createElement("div");
      details.style.color = "#6a6a78";
      details.style.fontSize = "10px";
      details.style.marginTop = "2px";
      const parts = [];
      if (item.effects.length)
        parts.push(item.effects[0]);
      parts.push(item.rarity);
      const unequipLink = createActionLink("unequip", "#e05050", async () => {
        const err = await unequipItem(slot);
        if (err)
          console.warn("Unequip failed:", err);
        else
          refresh();
      });
      details.textContent = parts.join(" · ") + " · ";
      details.appendChild(unequipLink);
      card.appendChild(details);
    } else {
      card.innerHTML = `<span style="color:#6a6a78">${label}</span> <span style="color:#3a3a48">— empty —</span>`;
    }
    return card;
  }
  function createBackpackCard(item) {
    const card = document.createElement("div");
    card.style.border = "1px solid #1a1a24";
    card.style.padding = "8px";
    card.style.marginBottom = "6px";
    card.style.borderRadius = "3px";
    card.style.background = "#12121a";
    const color = RARITY_COLORS2[item.rarity] || "#808080";
    const top = document.createElement("div");
    const nameSpan = `<span style="color:${color}">${item.name}</span>`;
    const qty = item.quantity > 1 ? ` <span style="color:#50c878;font-size:10px">×${item.quantity}</span>` : "";
    const tag = item.slot_type ? ` <span style="color:#6a6a78;font-size:10px">${item.slot_type}</span>` : "";
    top.innerHTML = nameSpan + qty + tag;
    card.appendChild(top);
    const actions = document.createElement("div");
    actions.style.color = "#6a6a78";
    actions.style.fontSize = "10px";
    actions.style.marginTop = "2px";
    const parts = [];
    if (item.effects.length)
      parts.push(item.effects[0]);
    actions.textContent = parts.length ? parts.join(" · ") + " · " : "";
    if (item.slot_type) {
      actions.appendChild(createActionLink("equip", "#8b5cf6", async () => {
        const err = await equipItem(item.id, item.slot_type);
        if (err)
          console.warn("Equip failed:", err);
        else
          refresh();
      }));
      actions.appendChild(document.createTextNode(" · "));
    }
    if (item.is_consumable) {
      actions.appendChild(createActionLink("use", "#50c878", async () => {
        const err = await useItem(item.id);
        if (err)
          console.warn("Use failed:", err);
        else
          refresh();
      }));
      actions.appendChild(document.createTextNode(" · "));
    }
    if (!item.is_quest_item) {
      actions.appendChild(createActionLink("drop", "#e05050", async () => {
        const err = await dropItem(item.id);
        if (err)
          console.warn("Drop failed:", err);
        else
          refresh();
      }));
    }
    card.appendChild(actions);
    return card;
  }
  function createActionLink(text, color, onClick) {
    const link = document.createElement("span");
    link.textContent = text;
    link.style.color = color;
    link.style.cursor = "pointer";
    link.addEventListener("click", (e) => {
      e.stopPropagation();
      onClick();
    });
    return link;
  }
  return {
    el: backdrop,
    open,
    close,
    refresh,
    get active() {
      return backdrop.style.display !== "none";
    }
  };
}

// src/ui/codex-modal.ts
var TYPE_COLORS = {
  npc: "#d4a574",
  item: "#808080",
  location: "#7aa2d4",
  player: "#8b5cf6"
};
var RARITY_COLORS3 = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
function itemColor(entity) {
  if (entity.rarity && RARITY_COLORS3[entity.rarity])
    return RARITY_COLORS3[entity.rarity];
  return TYPE_COLORS.item;
}
function entityColor(entity) {
  if (entity.type === "item")
    return itemColor(entity);
  return TYPE_COLORS[entity.type] || "#c8c8d0";
}
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function formatAddr(addr) {
  if (!addr || addr.length < 10 || addr === "0x0000000000000000000000000000000000000000")
    return "None";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
function createCodexModal(getState, playerId) {
  const backdrop = document.createElement("div");
  backdrop.className = "dialog-backdrop";
  backdrop.style.display = "none";
  const win = document.createElement("div");
  win.className = "dialog-win";
  win.style.maxWidth = "700px";
  win.style.width = "90vw";
  backdrop.appendChild(win);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop)
      close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && backdrop.style.display !== "none")
      close();
  });
  let _codexData = null;
  let _selectedId = null;
  let _allEntities = [];
  let _detailPage = 0;
  function close() {
    backdrop.style.display = "none";
  }
  async function open(entityId) {
    backdrop.style.display = "";
    win.innerHTML = "";
    const loading = document.createElement("div");
    loading.style.color = "#6a6a78";
    loading.style.fontStyle = "italic";
    loading.style.padding = "16px";
    loading.textContent = "Loading...";
    win.appendChild(loading);
    try {
      const pid = playerId();
      const state2 = getState();
      const locId = state2?.roomMap?.id || "";
      const url = locId ? `/api/codex/${pid}?location_uuid=${locId}` : `/api/codex/${pid}`;
      const resp = await fetch(url);
      _codexData = await resp.json();
    } catch {
      _codexData = null;
    }
    _allEntities = [];
    const seen = new Set;
    if (_codexData) {
      for (const npc of _codexData.npcs || []) {
        if (!seen.has(npc.id)) {
          seen.add(npc.id);
          _allEntities.push({ ...npc, type: "npc" });
        }
      }
      for (const gi of _codexData.ground_items || []) {
        if (!seen.has(gi.id)) {
          seen.add(gi.id);
          _allEntities.push({ ...gi, type: "item" });
        }
      }
      for (const loc of _codexData.locations || []) {
        if (!seen.has(loc.id)) {
          seen.add(loc.id);
          _allEntities.push({ ...loc, type: "location", labels: loc.labels || ["Location"] });
        }
      }
      if (_codexData.player) {
        const p = _codexData.player;
        if (!seen.has(p.id)) {
          seen.add(p.id);
          _allEntities.push({ id: p.id, name: p.name, type: "player", labels: [p.archetype || "Player"], summary: "" });
        }
      }
    }
    if (entityId) {
      _selectedId = entityId;
    } else {
      const currentLoc = (_codexData?.locations || []).find((l) => l.current);
      _selectedId = currentLoc?.id || (_allEntities.length ? _allEntities[0].id : null);
    }
    if (_selectedId && !_allEntities.find((e) => e.id === _selectedId)) {
      _selectedId = _allEntities.length ? _allEntities[0].id : null;
    } else {
      _selectedId = null;
    }
    render();
  }
  function render() {
    win.innerHTML = "";
    const header = document.createElement("div");
    header.className = "win-title dialog-title";
    header.style.display = "flex";
    header.style.justifyContent = "space-between";
    header.style.alignItems = "center";
    const title = document.createElement("span");
    title.style.color = "#8b5cf6";
    title.textContent = "CODEX";
    const closeBtn = document.createElement("span");
    closeBtn.textContent = "[×]";
    closeBtn.style.color = "#e05050";
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = close;
    header.appendChild(title);
    header.appendChild(closeBtn);
    win.appendChild(header);
    const body = document.createElement("div");
    body.style.display = "flex";
    body.style.gap = "0";
    body.style.fontFamily = "'Fira Code', monospace";
    body.style.fontSize = "12px";
    body.style.lineHeight = "1.6";
    body.style.minHeight = "300px";
    body.style.maxHeight = "60vh";
    const sidebar = document.createElement("div");
    sidebar.style.width = "140px";
    sidebar.style.flexShrink = "0";
    sidebar.style.borderRight = "1px solid #1a1a24";
    sidebar.style.overflowY = "auto";
    sidebar.style.padding = "8px 0";
    const npcs = _codexData?.npcs || [];
    const groundItems = _codexData?.ground_items || [];
    const invItems = _codexData?.inventory || [];
    const locations = _codexData?.locations || [];
    const currentLoc = locations.find((l) => l.current);
    const exitLocs = locations.filter((l) => !l.current);
    if (currentLoc) {
      const locHeader = createSectionHeader(`◉ ${currentLoc.name}`, TYPE_COLORS.location, true);
      locHeader.addEventListener("click", () => {
        _selectedId = currentLoc.id;
        render();
      });
      sidebar.appendChild(locHeader);
      for (const npc of npcs) {
        sidebar.appendChild(createSidebarItem(npc, TYPE_COLORS.npc, "  "));
      }
      for (const gi of groundItems) {
        sidebar.appendChild(createSidebarItem(gi, itemColor(gi), "  "));
      }
    }
    if (exitLocs.length) {
      const exitHeader = createSectionHeader("EXITS", "#6a6a78");
      sidebar.appendChild(exitHeader);
      for (const loc of exitLocs) {
        const label = loc.direction ? `${loc.direction} → ${loc.name}` : loc.name;
        sidebar.appendChild(createSidebarItem({ ...loc, name: label }, TYPE_COLORS.location));
      }
    }
    const playerData = _codexData?.player;
    if (playerData) {
      if (!_allEntities.find((e) => e.id === playerData.id)) {
        _allEntities.push({
          id: playerData.id,
          name: playerData.name,
          type: "player",
          labels: [playerData.archetype || "Player"],
          summary: ""
        });
      }
      const playerHeader = createSectionHeader(`♣ ${playerData.name}`, TYPE_COLORS.player, true);
      playerHeader.addEventListener("click", () => {
        _selectedId = playerData.id;
        render();
      });
      sidebar.appendChild(playerHeader);
    }
    const detail = document.createElement("div");
    detail.style.flex = "1";
    detail.style.minWidth = "0";
    detail.style.display = "flex";
    detail.style.flexDirection = "column";
    detail.style.padding = "8px 12px";
    const selected = _allEntities.find((e) => e.id === _selectedId);
    if (selected) {
      const sections = [];
      renderDetailSections(sections, selected);
      const SECTIONS_PER_PAGE = 4;
      const totalPages = Math.max(1, Math.ceil(sections.length / SECTIONS_PER_PAGE));
      _detailPage = Math.min(_detailPage, totalPages - 1);
      const contentArea = document.createElement("div");
      contentArea.style.flex = "1";
      contentArea.style.overflowY = "hidden";
      const start = _detailPage * SECTIONS_PER_PAGE;
      const pageSections = sections.slice(start, start + SECTIONS_PER_PAGE);
      for (const sec of pageSections) {
        contentArea.appendChild(sec);
      }
      detail.appendChild(contentArea);
      if (totalPages > 1) {
        const pager = document.createElement("div");
        pager.style.display = "flex";
        pager.style.justifyContent = "center";
        pager.style.alignItems = "center";
        pager.style.gap = "12px";
        pager.style.padding = "6px 0 2px";
        pager.style.borderTop = "1px solid #1a1a24";
        pager.style.color = "#6a6a78";
        pager.style.fontSize = "11px";
        const prev = document.createElement("span");
        prev.textContent = "◀";
        prev.style.cursor = _detailPage > 0 ? "pointer" : "default";
        prev.style.color = _detailPage > 0 ? "#8b5cf6" : "#3a3a48";
        if (_detailPage > 0) {
          prev.addEventListener("click", () => {
            _detailPage--;
            render();
          });
        }
        const info = document.createElement("span");
        info.textContent = `${_detailPage + 1}/${totalPages}`;
        const next = document.createElement("span");
        next.textContent = "▶";
        next.style.cursor = _detailPage < totalPages - 1 ? "pointer" : "default";
        next.style.color = _detailPage < totalPages - 1 ? "#8b5cf6" : "#3a3a48";
        if (_detailPage < totalPages - 1) {
          next.addEventListener("click", () => {
            _detailPage++;
            render();
          });
        }
        pager.appendChild(prev);
        pager.appendChild(info);
        pager.appendChild(next);
        detail.appendChild(pager);
      }
    } else {
      detail.style.color = "#6a6a78";
      detail.style.fontStyle = "italic";
      detail.style.paddingTop = "16px";
      detail.textContent = "No entities to display";
    }
    body.appendChild(sidebar);
    body.appendChild(detail);
    win.appendChild(body);
  }
  function createSectionHeader(text, color, bold = false) {
    const el = document.createElement("div");
    el.style.color = color;
    el.style.fontSize = "10px";
    el.style.letterSpacing = "1px";
    el.style.padding = "6px 8px 2px";
    el.style.cursor = "pointer";
    if (bold) {
      el.style.fontWeight = "bold";
      el.style.fontSize = "11px";
    }
    el.textContent = text;
    return el;
  }
  function createSidebarItem(entity, color, prefix = "") {
    const item = document.createElement("div");
    item.style.padding = "2px 8px";
    item.style.cursor = "pointer";
    item.style.color = color;
    item.style.fontSize = "11px";
    item.style.whiteSpace = "nowrap";
    item.style.overflow = "hidden";
    item.style.textOverflow = "ellipsis";
    if (entity.id === _selectedId) {
      item.style.background = "#1a1a24";
    }
    item.textContent = prefix + entity.name;
    item.addEventListener("click", () => {
      _selectedId = entity.id;
      _detailPage = 0;
      render();
    });
    return item;
  }
  function renderDetailSections(sections, entity) {
    const container = { appendChild(el) {
      sections.push(el);
    } };
    renderDetailInto(container, entity);
  }
  function renderDetailInto(container, entity) {
    const attrs = entity.attributes || {};
    const headerSection = document.createElement("div");
    headerSection.style.marginBottom = "8px";
    const name = document.createElement("div");
    name.style.color = entityColor(entity);
    name.style.fontWeight = "bold";
    name.style.fontSize = "15px";
    name.style.marginBottom = "4px";
    name.textContent = entity.name;
    headerSection.appendChild(name);
    if (entity.labels.length) {
      const labels = document.createElement("div");
      labels.style.color = "#6a6a78";
      labels.style.fontSize = "10px";
      labels.style.marginBottom = "8px";
      labels.textContent = entity.labels.join(" · ");
      headerSection.appendChild(labels);
    }
    let summaryText = entity.summary || "";
    if (summaryText.startsWith("{")) {
      summaryText = attrs.description || attrs.personality || "";
    }
    if (!summaryText && attrs.description) {
      summaryText = attrs.description;
    }
    if (summaryText) {
      const summary = document.createElement("div");
      summary.style.color = "#c8c8d0";
      summary.style.lineHeight = "1.5";
      summary.textContent = summaryText;
      headerSection.appendChild(summary);
    }
    container.appendChild(headerSection);
    if (Object.keys(attrs).length > 0) {
      if (entity.type === "npc") {
        if (attrs.personality)
          addSection(container, "PERSONALITY", attrs.personality);
        if (attrs.backstory)
          addSection(container, "BACKSTORY", attrs.backstory);
        if (attrs.stats && Object.keys(attrs.stats).length) {
          const statsText = Object.entries(attrs.stats).map(([k, v]) => `${k} ${v}`).join(" · ");
          addSection(container, "STATS", statsText);
        }
        if (attrs.skills && Object.keys(attrs.skills).length) {
          const skillsText = Object.entries(attrs.skills).map(([k, v]) => `${k}: ${v}`).join(", ");
          addSection(container, "SKILLS", skillsText);
        }
        if (attrs.abilities?.length) {
          const abDiv = document.createElement("div");
          abDiv.style.marginBottom = "8px";
          const abHeader = document.createElement("div");
          abHeader.style.color = "#6a6a78";
          abHeader.style.fontSize = "10px";
          abHeader.style.letterSpacing = "1px";
          abHeader.style.marginBottom = "4px";
          abHeader.textContent = "ABILITIES";
          abDiv.appendChild(abHeader);
          for (const ab of attrs.abilities) {
            const row = document.createElement("div");
            row.style.marginBottom = "4px";
            row.innerHTML = `<span style="color:#8b5cf6">${esc(ab.name)}</span> <span style="color:#6a6a78">— ${esc(ab.description)}</span>`;
            abDiv.appendChild(row);
          }
          container.appendChild(abDiv);
        }
        if (attrs.traits?.length)
          addSection(container, "TRAITS", attrs.traits.join(", "));
        if (attrs.disposition)
          addSection(container, "DISPOSITION", attrs.disposition);
        if (attrs.motivation)
          addSection(container, "MOTIVATION", attrs.motivation);
      }
      if (entity.type === "item") {
        const parts = [];
        if (attrs.damage)
          parts.push(`Damage: ${attrs.damage}`);
        if (attrs.defense)
          parts.push(`Defense: ${attrs.defense}`);
        if (attrs.weight)
          parts.push(`Weight: ${attrs.weight}`);
        if (parts.length)
          addSection(container, "MECHANICS", parts.join(" · "));
        if (attrs.lore)
          addSection(container, "LORE", attrs.lore);
        if (attrs.effects?.length)
          addSection(container, "EFFECTS", attrs.effects.join(", "));
      }
      if (entity.type === "location") {
        if (attrs.biome)
          addSection(container, "BIOME", attrs.biome);
        if (attrs.atmosphere)
          addSection(container, "ATMOSPHERE", attrs.atmosphere);
        if (attrs.culture)
          addSection(container, "CULTURE", attrs.culture);
        if (attrs.threats?.length)
          addSection(container, "THREATS", attrs.threats.join(", "));
        if (attrs.danger_level) {
          const skulls = "☠".repeat(Math.min(attrs.danger_level, 5));
          addSection(container, "DANGER", `${skulls} (${attrs.danger_level}/10)`);
        }
      }
    }
    if (entity.type === "player") {
      const playerData = _codexData?.player;
      if (playerData) {
        const statsDiv = document.createElement("div");
        statsDiv.style.marginBottom = "12px";
        statsDiv.innerHTML = `
          <div style="color:#6a6a78;font-size:10px;letter-spacing:1px;margin-bottom:4px">STATS</div>
          <div>Level: <span style="color:#c8c8d0">${playerData.level || 1}</span></div>
          <div>Health: <span style="color:#50c878">${playerData.health || 100}</span></div>
          <div>Archetype: <span style="color:#8b5cf6">${esc(playerData.archetype || "Unknown")}</span></div>
        `;
        container.appendChild(statsDiv);
      }
      const spacer = document.createElement("div");
      spacer.style.marginTop = "12px";
      container.appendChild(spacer);
    }
    if (entity.type === "location" && entity.exits) {
      const exitsHeader = document.createElement("div");
      exitsHeader.style.color = "#6a6a78";
      exitsHeader.style.fontSize = "10px";
      exitsHeader.style.letterSpacing = "1px";
      exitsHeader.style.marginBottom = "4px";
      exitsHeader.textContent = "EXITS";
      container.appendChild(exitsHeader);
      for (const ex of entity.exits) {
        const row = document.createElement("div");
        row.style.marginBottom = "4px";
        row.innerHTML = `<span style="color:#8b5cf6">${esc(ex.direction || "?")}</span> <span style="color:#6a6a78">→</span> <span style="color:#7aa2d4;cursor:pointer">${esc(ex.target || "?")}</span>`;
        const targetSpan = row.querySelector("span:last-child");
        if (targetSpan) {
          targetSpan.addEventListener("click", () => {
            const linked = _allEntities.find((e) => e.name === ex.target);
            if (linked) {
              _selectedId = linked.id;
              render();
            }
          });
        }
        container.appendChild(row);
      }
      if (entity.current) {
        const npcsHere = _codexData?.npcs || [];
        const itemsHere = _codexData?.ground_items || [];
        const playerHere = _codexData?.player;
        const presHeader = document.createElement("div");
        presHeader.style.color = "#6a6a78";
        presHeader.style.fontSize = "10px";
        presHeader.style.letterSpacing = "1px";
        presHeader.style.margin = "12px 0 4px";
        presHeader.textContent = "PRESENT";
        container.appendChild(presHeader);
        if (playerHere) {
          const row = document.createElement("div");
          row.style.color = TYPE_COLORS.player;
          row.style.cursor = "pointer";
          row.textContent = `♣ ${playerHere.name} (you)`;
          row.addEventListener("click", () => {
            _selectedId = playerHere.id;
            render();
          });
          container.appendChild(row);
        }
        for (const npc of npcsHere) {
          const row = document.createElement("div");
          row.style.color = TYPE_COLORS.npc;
          row.style.cursor = "pointer";
          row.textContent = `● ${npc.name}`;
          row.addEventListener("click", () => {
            _selectedId = npc.id;
            render();
          });
          container.appendChild(row);
        }
        for (const item of itemsHere) {
          const row = document.createElement("div");
          row.style.color = itemColor(item);
          row.style.cursor = "pointer";
          row.textContent = `• ${item.name}`;
          row.addEventListener("click", () => {
            _selectedId = item.id;
            render();
          });
          container.appendChild(row);
        }
      }
      const spacer = document.createElement("div");
      spacer.style.marginTop = "12px";
      container.appendChild(spacer);
    }
    if (entity.relationships?.length) {
      const connHeader = document.createElement("div");
      connHeader.style.color = "#6a6a78";
      connHeader.style.fontSize = "10px";
      connHeader.style.letterSpacing = "1px";
      connHeader.style.marginBottom = "4px";
      connHeader.textContent = "CONNECTIONS";
      container.appendChild(connHeader);
      for (const rel of entity.relationships) {
        const row = document.createElement("div");
        row.style.marginBottom = "4px";
        const relType = document.createElement("span");
        relType.style.color = "#6a6a78";
        relType.style.fontSize = "10px";
        relType.textContent = rel.relationship.replace(/_/g, " ") + " ";
        const target = document.createElement("span");
        const other = rel.source === entity.name ? rel.target : rel.source;
        target.style.color = "#7aa2d4";
        target.style.cursor = "pointer";
        target.style.textDecoration = "underline dotted";
        target.textContent = other;
        target.addEventListener("click", () => {
          const linked = _allEntities.find((e) => e.name === other);
          if (linked) {
            _selectedId = linked.id;
            render();
          }
        });
        row.appendChild(relType);
        row.appendChild(target);
        if (rel.fact) {
          const fact = document.createElement("div");
          fact.style.color = "#6a6a78";
          fact.style.fontSize = "11px";
          fact.style.fontStyle = "italic";
          fact.style.marginLeft = "8px";
          fact.textContent = rel.fact.length > 100 ? rel.fact.slice(0, 100) + "…" : rel.fact;
          row.appendChild(fact);
        }
        container.appendChild(row);
      }
      const spacer = document.createElement("div");
      spacer.style.marginTop = "12px";
      container.appendChild(spacer);
    }
    if (entity.chain_data) {
      renderChainSection(container, entity);
    }
  }
  function renderChainSection(container, entity) {
    const chain = entity.chain_data;
    const card = document.createElement("div");
    card.style.border = "1px solid #1a3a1a";
    card.style.borderRadius = "3px";
    card.style.padding = "8px";
    card.style.marginTop = "4px";
    const cardHeader = document.createElement("div");
    cardHeader.style.color = "#50c878";
    cardHeader.style.fontSize = "10px";
    cardHeader.style.letterSpacing = "1px";
    cardHeader.style.marginBottom = "4px";
    cardHeader.textContent = "ONCHAIN";
    card.appendChild(cardHeader);
    if (entity.type === "npc" || entity.type === "player") {
      if (chain.level != null)
        addChainRow(card, "Level", String(chain.level));
      if (chain.alive != null)
        addChainRow(card, "Status", chain.alive ? "Alive" : "Dead");
      if (chain.wallet)
        addChainRow(card, "Wallet", formatAddr(chain.wallet));
    } else if (entity.type === "item") {
      if (chain.rarity)
        addChainRow(card, "Rarity", String(chain.rarity));
      if (chain.ownerId)
        addChainRow(card, "Owner", formatAddr(chain.ownerId));
      if (chain.locationId)
        addChainRow(card, "Location", formatAddr(chain.locationId));
    }
    container.appendChild(card);
  }
  function addChainRow(container, label, value) {
    const row = document.createElement("div");
    row.style.padding = "1px 0";
    row.style.fontSize = "12px";
    const lbl = document.createElement("span");
    lbl.style.color = "#6a6a78";
    lbl.style.display = "inline-block";
    lbl.style.width = "70px";
    lbl.style.fontSize = "10px";
    lbl.style.letterSpacing = "0.5px";
    lbl.style.textTransform = "uppercase";
    lbl.textContent = label;
    const val = document.createElement("span");
    val.style.color = "#c8c8d0";
    val.textContent = value;
    row.appendChild(lbl);
    row.appendChild(val);
    container.appendChild(row);
  }
  function addSection(container, label, text) {
    const section = document.createElement("div");
    section.style.marginBottom = "8px";
    const header = document.createElement("div");
    header.style.color = "#6a6a78";
    header.style.fontSize = "10px";
    header.style.letterSpacing = "1px";
    header.style.marginBottom = "2px";
    header.textContent = label;
    section.appendChild(header);
    const body = document.createElement("div");
    body.style.color = "#c8c8d0";
    body.style.fontSize = "12px";
    body.textContent = text;
    section.appendChild(body);
    container.appendChild(section);
  }
  return {
    el: backdrop,
    open,
    close,
    get active() {
      return backdrop.style.display !== "none";
    }
  };
}

// src/ui/status.ts
function createStatusBar() {
  const el = document.createElement("div");
  el.className = "status-bar";
  el.innerHTML = `
    <span class="status-phase">✓ Ready</span>
    <span class="status-activity"></span>
    <span class="status-chain">◇ Redstone: offline</span>
    <span class="status-tick">☽ Tick 0</span>
  `;
  const phaseEl = el.querySelector(".status-phase");
  const activityEl = el.querySelector(".status-activity");
  const chainEl = el.querySelector(".status-chain");
  const tickEl = el.querySelector(".status-tick");
  let activityTimer = null;
  function renderPhase(rs) {
    switch (rs.phase) {
      case "ready":
        phaseEl.textContent = rs.location ? `✓ Ready · ${rs.location}` : "✓ Ready";
        phaseEl.className = "status-phase ready";
        break;
      case "collecting": {
        const count = rs.actionCount ?? 0;
        const timer = rs.secondsLeft != null ? ` (${rs.secondsLeft}s)` : "";
        phaseEl.textContent = `⟳ Collecting · ${count} action${count !== 1 ? "s" : ""}${timer}`;
        phaseEl.className = "status-phase collecting";
        break;
      }
      case "resolving": {
        const crewLabel = rs.crew ? rs.crew.charAt(0).toUpperCase() + rs.crew.slice(1).replace("_", "-") : "";
        phaseEl.textContent = crewLabel ? `⟳ Resolving · ${crewLabel}` : "⟳ Resolving";
        phaseEl.className = "status-phase resolving";
        break;
      }
      case "npc_response":
        phaseEl.textContent = "⟳ NPCs Responding";
        phaseEl.className = "status-phase npc-response";
        break;
    }
  }
  onRoundStateChange(renderPhase);
  return {
    el,
    setChain(connected) {
      chainEl.textContent = connected ? "◆ Redstone: synced" : "◇ Redstone: offline";
      chainEl.className = `status-chain ${connected ? "connected" : ""}`;
    },
    setTick(tick) {
      tickEl.textContent = `☽ Tick ${tick}`;
    },
    setActivity(text) {
      if (activityTimer)
        clearTimeout(activityTimer);
      if (text) {
        activityEl.textContent = `✨ ${text}`;
        activityEl.style.color = "#8b5cf6";
        activityTimer = setTimeout(() => {
          activityEl.textContent = "";
          activityTimer = null;
        }, 5000);
      } else {
        activityEl.textContent = "";
      }
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

// src/ui/overlay.ts
function createOverlayManager(names) {
  const elements = new Map;
  const callbacks = new Map;
  let currentName = null;
  for (const name of names) {
    const el = document.getElementById(`${name}-overlay`);
    if (el)
      elements.set(name, el);
    callbacks.set(name, []);
  }
  function show(name) {
    if (currentName && currentName !== name) {
      const prev = elements.get(currentName);
      if (prev)
        prev.classList.add("hidden");
    }
    const el = elements.get(name);
    if (el) {
      el.classList.remove("hidden");
      currentName = name;
    }
  }
  function dismiss(name) {
    const el = elements.get(name);
    if (el)
      el.classList.add("hidden");
    if (currentName === name)
      currentName = null;
    for (const cb of callbacks.get(name) || [])
      cb();
  }
  function onDismiss(name, cb) {
    const list = callbacks.get(name);
    if (list)
      list.push(cb);
  }
  return {
    show,
    dismiss,
    onDismiss,
    current: () => currentName
  };
}

// src/flows/session-flow.ts
async function startGame(config, overlays, callbacks) {
  overlays.show("loading");
  let data;
  if (config.isReturning && config.playerId) {
    const session2 = getSession();
    session2.playerName = config.playerName;
    session2.walletAddress = config.walletAddress;
    localStorage.setItem("mm_player_name", config.playerName);
    localStorage.setItem("mm_wallet", config.walletAddress);
    data = await joinSession(config.playerId);
  } else {
    data = await initSession(config.playerName, config.walletAddress, config.archetype || "");
  }
  const gameState = createInitialState(config.playerName);
  gameState.location.name = data.location;
  if (data.archetype)
    gameState.player.archetype = data.archetype;
  if (data.health)
    gameState.player.health = data.health;
  if (data.max_health)
    gameState.player.maxHealth = data.max_health;
  if (data.skills)
    gameState.player.skills = data.skills;
  if (data.room_map)
    applyStateUpdate(gameState, { room_map: data.room_map });
  if (data.inventory) {
    gameState.inventory = data.inventory.map((item) => {
      if (typeof item === "string") {
        return { id: "", name: item, rarity: "common", slot_type: "", equipped: false, is_consumable: false, is_quest_item: false, effects: [], quantity: 1 };
      }
      return {
        id: item.id || "",
        name: item.name || "?",
        rarity: item.rarity || "common",
        slot_type: item.slot_type || "",
        equipped: item.equipped || false,
        is_consumable: item.is_consumable || false,
        is_quest_item: item.is_quest_item || false,
        effects: item.effects || [],
        quantity: item.quantity || 1
      };
    });
  }
  if (!getSession().connected) {
    await Promise.race([
      new Promise((resolve) => {
        if (getSession().connected) {
          resolve();
          return;
        }
        const prev = null;
        setConnectionHandler((connected) => {
          if (connected)
            resolve();
        });
      }),
      new Promise((resolve) => setTimeout(resolve, 1e4))
    ]);
  }
  overlays.dismiss("loading");
  if (!localStorage.getItem("mm_intro_seen")) {
    overlays.show("intro");
    await new Promise((resolve) => {
      initIntroNav(() => {
        localStorage.setItem("mm_intro_seen", "true");
        overlays.dismiss("intro");
        resolve();
      });
    });
  }
  updateRoundState({ type: "phase", phase: "ready", location: data.location });
  callbacks.onGameReady(gameState, data.opening_narrative || (config.isReturning ? `Welcome back, ${config.playerName}.` : ""));
}
function initIntroNav(onDone) {
  const pages = document.querySelectorAll(".intro-page");
  const dotsEl = document.getElementById("intro-dots");
  const nextBtn = document.getElementById("intro-next-btn");
  const skipBtn = document.getElementById("intro-skip-btn");
  let current = 0;
  const total = pages.length;
  function updateDots() {
    if (dotsEl) {
      dotsEl.textContent = Array.from({ length: total }, (_, i) => i === current ? "●" : "○").join(" ");
    }
  }
  function showPage(idx) {
    pages.forEach((p, i) => {
      p.classList.toggle("hidden", i !== idx);
    });
    current = idx;
    updateDots();
    if (nextBtn)
      nextBtn.textContent = idx >= total - 1 ? "Begin" : "Next";
  }
  nextBtn?.addEventListener("click", () => {
    if (current >= total - 1) {
      onDone();
    } else {
      showPage(current + 1);
    }
  });
  skipBtn?.addEventListener("click", () => onDone());
  showPage(0);
}

// src/app.ts
var gameState;
var narrative;
var eventsFeed;
var header;
var npcDialog;
var codex;
var statusBar;
var narrativeWin;
var eventsWin;
var mapWin;
var characterWin;
var inventoryWin;
var exitsWin;
var presentWin;
var questWin;
var factionWin;
var commandWin;
var overlays;
var invModal;
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
  renderCharacterPanel(characterWin.panel, gameState);
  renderInventoryPanel(inventoryWin.panel, gameState);
  exitsWin.setTitle(gameState.location.name || "Exits");
  renderExitsPanel(exitsWin.panel, gameState, handleAction);
  renderPresentPanel(presentWin.panel, gameState, handleAction);
  renderQuestLogPanel(questWin.panel, gameState.quests);
  renderFactionsPanel(factionWin.panel, gameState.factions);
  updateMap(gameState, handleAction);
}
async function handleAction(action) {
  if (!action.trim() || action.length > 500)
    return;
  narrative.addBlock(`> ${action}`, "player-action");
  await sendAction(action);
}
function showDeathScreen(cause) {
  const causeEl = document.getElementById("death-cause");
  const statsEl = document.getElementById("death-stats");
  causeEl.textContent = cause || "The world continues without you.";
  statsEl.innerHTML = gameState ? `
    <div>Name: ${gameState.player.name}</div>
    <div>Level: ${gameState.player.level}</div>
    <div>Last Location: ${gameState.location.name}</div>
  ` : "";
  overlays.show("death");
}
function handleMessage(msg) {
  switch (msg.type) {
    case "narrative": {
      narrative.removeThinking();
      const channel = msg.channel || "narrative";
      if (channel === "events") {
        eventsFeed.addBlock(msg.text || "", "event");
      } else if (channel === "ooc") {
        eventsFeed.addBlock(msg.text || "", "ooc");
      } else if (msg.npc) {
        const npcKey = msg.npc_username || msg.npc.toLowerCase().replace(/\s+/g, "-");
        narrative.removeBlockById(`npc-status-${npcKey}`);
        narrative.addBlock(`${msg.npc}`, "npc-name");
        narrative.addBlock(msg.text || "", "npc-dialogue");
      } else {
        narrative.addBlock(msg.text || "", "narrative");
      }
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
              eventsFeed.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ""}`, "event-combat");
            }
            if (c.xp_gained) {
              eventsFeed.addBlock(`[+${c.xp_gained} XP]`, "event-xp");
            }
            if (c.target_dead) {
              eventsFeed.addBlock(`${c.target_name || "Target"} has been slain.`, "event-death");
            }
          }
          if (events.inventory_changes) {
            for (const inv of events.inventory_changes) {
              const prefix = inv.event_type === "DROP" ? "-" : "+";
              eventsFeed.addBlock(`[${prefix}${inv.item_name}]`, "event-item");
            }
          }
        }
      }
      if (msg.state_update?.status === "dead" || msg.state_update?.events?.combat?.target_dead || msg.text && msg.text.toLowerCase().includes("you have died")) {
        showDeathScreen(msg.state_update?.cause || "");
      }
      break;
    }
    case "death_feed": {
      const skull = "☠";
      const deathMsg = `${skull} ${msg.player_name || "Unknown"} (Level ${msg.level || "?"}) fell at ${msg.location || "unknown"}. ${msg.cause || ""}`;
      narrative.addBlock(deathMsg, "death-feed");
      break;
    }
    case "scene_art": {
      const artText = (msg.lines || []).join(`
`);
      if (artText) {
        narrative.addBlock(artText, "scene-art");
      }
      break;
    }
    case "entity_art": {
      if (msg.entity_id && gameState) {
        const npc = gameState.location.npcs.find((n) => n.id === msg.entity_id);
        const item = gameState.location.items.find((i) => i.id === msg.entity_id);
        const entity = npc || item;
        if (entity) {
          entity.ascii_art = (msg.lines || []).join(`
`);
        }
      }
      break;
    }
    case "npc_status": {
      const npcKey = msg.npc_username || msg.npc || "unknown";
      narrative.replaceBlock(`npc-status-${npcKey}`, `${msg.npc}: ${msg.text}`, "npc-status");
      break;
    }
    case "phase": {
      updateRoundState(msg);
      const phase = msg.phase || "";
      const crew = msg.crew || "";
      if (phase === "resolving" && crew) {
        eventsFeed.replaceBlock("phase-progress", `[${crew}]`, "event");
      } else if (phase === "npc_response") {
        eventsFeed.replaceBlock("phase-progress", "[waiting for NPCs]", "event");
      } else if (phase === "ready") {
        eventsFeed.removeBlockById("phase-progress");
      }
      break;
    }
    case "status":
      if (msg.tick != null)
        statusBar.setTick(msg.tick);
      if (msg.chain != null)
        statusBar.setChain(msg.chain);
      if (msg.activity)
        statusBar.setActivity(msg.activity);
      break;
    case "player_joined": {
      if (gameState) {
        const exists = gameState.location.players.some((p) => p.id === msg.player_id);
        if (!exists) {
          gameState.location.players.push({ name: msg.player_name, id: msg.player_id });
          renderPresentPanel(presentWin.panel, gameState, handleAction);
          narrative.addBlock(`${msg.player_name} arrived.`, "system");
        }
      }
      break;
    }
    case "player_left": {
      if (gameState) {
        gameState.location.players = gameState.location.players.filter((p) => p.id !== msg.player_id);
        renderPresentPanel(presentWin.panel, gameState, handleAction);
        narrative.addBlock(`${msg.player_name} departed.`, "system");
      }
      break;
    }
    case "presence": {
      if (gameState) {
        gameState.location.players = (msg.players || []).map((p) => ({
          name: p.player_name,
          id: p.player_id
        }));
        renderPresentPanel(presentWin.panel, gameState, handleAction);
      }
      break;
    }
    case "state_update": {
      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        renderAllPanels();
        if (invModal.active)
          invModal.refresh();
      }
      break;
    }
    case "room_items_changed": {
      if (invModal.active)
        invModal.refresh();
      break;
    }
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
function enterGame(config) {
  startGame({ ...config }, overlays, {
    onGameReady(state2, openingNarrative) {
      gameState = state2;
      const session2 = getSession();
      initInventoryApi(gameState, session2.playerId, renderAllPanels, (text, style) => {
        eventsFeed.addBlock(text, style);
      });
      if (gameState.roomMap)
        registerMapEntities(gameState.roomMap);
      renderAllPanels();
      if (openingNarrative) {
        narrative.addBlock(openingNarrative, config.isReturning ? "system" : "narrative");
      }
      document.getElementById("action-input").focus();
    }
  }).catch((err) => {
    console.error("startGame failed:", err);
    overlays.dismiss("loading");
    overlays.show("char-create");
  });
}
function showCharacterPicker(characters, walletAddress) {
  const walletStepEl = document.getElementById("wallet-step");
  const pickerDiv = document.createElement("div");
  pickerDiv.id = "char-picker";
  const alive = characters.filter((c) => !c.is_dead);
  const dead = characters.filter((c) => c.is_dead);
  let html = '<div class="picker-title">Your Characters</div>';
  for (const c of alive) {
    html += `
      <div class="picker-card" data-player-id="${c.player_id}">
        <span class="picker-name">${c.player_name}</span>
        <span class="picker-info">${c.archetype || "Unknown"} · HP ${c.health}</span>
      </div>`;
  }
  for (const c of dead) {
    html += `
      <div class="picker-card picker-memorial">
        <span class="picker-name">☠ ${c.player_name}</span>
        <span class="picker-info">${c.death_cause || "Perished"} · Fell at ${c.death_location || "unknown"}</span>
      </div>`;
  }
  html += `
    <div class="picker-card picker-new">
      <span class="picker-name">+ New Character</span>
    </div>`;
  pickerDiv.innerHTML = html;
  walletStepEl.after(pickerDiv);
  pickerDiv.addEventListener("click", (e) => {
    const card = e.target.closest(".picker-card");
    if (!card || card.classList.contains("picker-memorial"))
      return;
    if (card.classList.contains("picker-new")) {
      pickerDiv.remove();
      const archStep = document.getElementById("archetype-step");
      if (archStep) {
        archStep.classList.remove("hidden");
        loadArchetypes();
      } else {
        document.getElementById("name-step").classList.remove("hidden");
      }
    } else {
      const playerId = card.dataset.playerId;
      const playerName = card.querySelector(".picker-name").textContent || "Wanderer";
      pickerDiv.remove();
      overlays.dismiss("char-create");
      enterGame({ playerName, walletAddress, isReturning: true, playerId });
    }
  });
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
  narrativeWin = createWindow({ title: "Narrative", id: "narrative-win", className: "resizable" });
  eventsWin = createWindow({ title: "Events", id: "events-win" });
  mapWin = createWindow({ title: "Map", id: "map-win" });
  characterWin = createWindow({ title: "Character", id: "character-win", className: "sidebar-win resizable", canvas: true });
  inventoryWin = createWindow({ title: "Inventory", id: "inventory-win", className: "sidebar-win resizable", canvas: true });
  exitsWin = createWindow({ title: "Exits", id: "exits-win", className: "sidebar-win resizable", canvas: true });
  presentWin = createWindow({ title: "Present", id: "present-win", className: "sidebar-win resizable", canvas: true });
  questWin = createWindow({ title: "Quests", id: "quest-win", className: "sidebar-win resizable", canvas: true });
  factionWin = createWindow({ title: "Factions", id: "faction-win", className: "sidebar-win resizable", canvas: true });
  commandWin = createWindow({ title: "Command", id: "command-win" });
  mount("narrative-mount", narrativeWin.el);
  mount("events-mount", eventsWin.el);
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
  overlays = createOverlayManager(["char-create", "death", "loading", "intro"]);
  exitsWin.panel.canvas.addEventListener("panel-click", (e) => {
    const detail = e.detail;
    if (detail.action)
      handleAction(detail.action);
  });
  presentWin.panel.canvas.addEventListener("panel-click", (e) => {
    const detail = e.detail;
    if (detail.action)
      handleAction(detail.action);
  });
  questWin.panel.canvas.addEventListener("panel-click", (e) => {
    const detail = e.detail;
    if (detail.questName && gameState) {
      const quest = gameState.quests.find((q) => q.name === detail.questName);
      if (quest)
        npcDialog.showQuest(quest);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "m" && document.activeElement?.tagName !== "INPUT") {
      mapWin.toggle();
    }
  });
  npcDialog = createDialog();
  mount("dialog-mount", npcDialog.el);
  invModal = createInventoryModal(() => gameState);
  document.body.appendChild(invModal.el);
  setManageInventoryCallback(() => invModal.open());
  document.addEventListener("keydown", (e) => {
    if (e.key === "i" && document.activeElement?.tagName !== "INPUT") {
      if (invModal.active)
        invModal.close();
      else
        invModal.open();
    }
  });
  narrative = initNarrative(narrativeWin.body);
  eventsFeed = initNarrative(eventsWin.body);
  narrative.canvas.addEventListener("narrative-entity-click", (e) => {
    const { entityId } = e.detail;
    codex.open(entityId || undefined);
  });
  commandWin.body.innerHTML = `
    <span class="prompt-char">&gt;</span>
    <input type="text" id="action-input" placeholder="What do you do?" autocomplete="off" spellcheck="false" />
  `;
  const actionInput = commandWin.body.querySelector("#action-input");
  initInput(actionInput, handleAction, () => ({
    npcs: gameState?.location?.npcs || [],
    players: gameState?.location?.players || []
  }));
  const mapCanvasWrap = document.createElement("div");
  mapCanvasWrap.className = "map-canvas-wrap";
  const worldMapWrap = document.createElement("div");
  worldMapWrap.className = "map-canvas-wrap";
  worldMapWrap.style.display = "none";
  mapWin.body.appendChild(mapCanvasWrap);
  mapWin.body.appendChild(worldMapWrap);
  initMapPanel(mapCanvasWrap, handleAction);
  codex = createCodexModal(() => gameState, () => getSession().playerId);
  document.body.appendChild(codex.el);
  document.addEventListener("keydown", (e) => {
    if (e.key === "k" && document.activeElement?.tagName !== "INPUT") {
      if (codex.active)
        codex.close();
      else
        codex.open();
    }
  });
  const worldRenderer = new WorldMapRenderer(worldMapWrap);
  let worldMapData = null;
  let showingWorldMap = false;
  worldRenderer.setClickHandler((roomId) => {
    if (roomId) {
      codex.open(roomId);
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
    overlays.dismiss("death");
    overlays.show("char-create");
    narrative = initNarrative(narrativeWin.body);
    narrative.canvas.addEventListener("narrative-entity-click", (e) => {
      const { entityId } = e.detail;
      codex.open(entityId || undefined);
    });
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
      try {
        const charResp = await fetch(`${GATEWAY_URL}/api/session/characters`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ wallet_address: addr })
        });
        const charData = await charResp.json();
        if (charData.characters && charData.characters.length > 0) {
          showCharacterPicker(charData.characters, addr);
          return;
        }
      } catch {}
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
    if (wallet) {
      overlays.dismiss("char-create");
      enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
    }
  });
  nameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const name = nameInput.value.trim() || "Wanderer";
      const wallet = getAddress();
      if (wallet) {
        overlays.dismiss("char-create");
        enterGame({ playerName: name, walletAddress: wallet, isReturning: false, archetype: selectedArchetype });
      }
    }
  });
});
