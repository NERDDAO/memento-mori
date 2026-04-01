// src/state/game-state.ts
function createInitialState(playerName) {
  return {
    player: {
      name: playerName,
      level: 1,
      health: 100,
      maxHealth: 100,
      xp: 0,
      xpThreshold: 100
    },
    location: {
      name: "Unknown",
      description: "",
      exits: [],
      npcs: [],
      items: []
    },
    inventory: [],
    roomMap: null
  };
}
function applyStateUpdate(state, update) {
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
  if (update.room_map) {
    state.roomMap = update.room_map;
  }
}

// src/state/session.ts
var GATEWAY_URL = "http://localhost:8080";
var WS_URL = "ws://localhost:8080/ws";
var session = {
  playerId: "",
  sessionId: "",
  playerName: "",
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
async function initSession(playerName) {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName })
  });
  const data = await resp.json();
  session.playerId = data.player_id;
  session.sessionId = data.session_id;
  session.playerName = playerName;
  session.currentLocation = data.location;
  session.openingNarrative = data.opening_narrative || "";
  localStorage.setItem("mm_player_id", session.playerId);
  localStorage.setItem("mm_player_name", playerName);
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
function parseNarrative(text) {
  const segments = [];
  const pattern = /"([^"]+)"|(\d+ damage)|(\d+ health|\d+ HP)/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: text.slice(lastIndex, match.index), style: "normal" });
    }
    if (match[1]) {
      segments.push({ text: `"${match[1]}"`, style: "npc" });
    } else if (match[2]) {
      segments.push({ text: match[2], style: "damage" });
    } else if (match[3]) {
      segments.push({ text: match[3], style: "heal" });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ text: text.slice(lastIndex), style: "normal" });
  }
  return segments.length ? segments : [{ text, style: "normal" }];
}
function renderSegments(segments) {
  return segments.map((seg) => {
    const cls = seg.style === "normal" ? "" : seg.style;
    return cls ? `<span class="${cls}">${escapeHtml(seg.text)}</span>` : escapeHtml(seg.text);
  }).join("");
}
function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
function getInternalPrepared(prepared) {
  return prepared;
}
function layout(prepared, maxWidth, lineHeight) {
  const lineCount = countPreparedLines(getInternalPrepared(prepared), maxWidth);
  return { lineCount, height: lineCount * lineHeight };
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
    store.add(text, html, type);
    spacer.style.height = `${store.totalHeight}px`;
    if (userAtBottom) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
    scheduleRender();
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
      this.addBlock("The world responds", "thinking");
    },
    removeThinking() {
      const el = spacer.querySelector(".thinking");
      if (el)
        el.remove();
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

// src/panels/character.ts
function renderCharacterPanel(_container, state) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el)
      el.textContent = text;
  };
  set("char-name", state.player.name);
  set("char-level", String(state.player.level));
  set("char-health", `${state.player.health}/${state.player.maxHealth}`);
  set("char-xp", `${state.player.xp}/${state.player.xpThreshold}`);
  const fill = document.getElementById("health-fill");
  if (fill) {
    const pct = Math.max(0, Math.min(100, state.player.health / state.player.maxHealth * 100));
    fill.style.width = `${pct}%`;
  }
}

// src/panels/inventory.ts
var RARITY_COLORS = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
function renderInventoryPanel(container, state) {
  if (state.inventory.length === 0) {
    container.innerHTML = '<div class="inventory-item" style="color: var(--text-dim);">Empty</div>';
    return;
  }
  container.innerHTML = state.inventory.map((item) => {
    const color = RARITY_COLORS[item.rarity] || "var(--text-dim)";
    return `<div class="inventory-item">
      ${item.name} <span style="color: ${color};">[${item.rarity}]</span>
      ${item.equipped ? ' <span style="color: var(--accent);">equipped</span>' : ""}
    </div>`;
  }).join("");
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

// src/map/renderer.ts
var TILE_W = 14;
var TILE_H = 18;
var FONT = "15px monospace";

class MapRenderer {
  canvas;
  ctx;
  dpr;
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
  render(map, playerX, playerY) {
    const w = map.width * TILE_W;
    const h = map.height * TILE_H;
    this.canvas.width = w * this.dpr;
    this.canvas.height = h * this.dpr;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
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
  }
  drawEntity(x, y, ch, color) {
    const ctx = this.ctx;
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(x * TILE_W, y * TILE_H, TILE_W, TILE_H);
    ctx.fillStyle = color;
    ctx.font = FONT;
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

// src/map/entity-card.ts
var CARD_MAX_WIDTH = 260;
var CARD_FONT = "13px system-ui, sans-serif";
var CARD_NAME_FONT = "15px Georgia, 'Times New Roman', serif";
var CARD_LINE_HEIGHT = 18;
var CARD_NAME_LINE_HEIGHT = 22;

class EntityCardManager {
  container;
  cardEl;
  cache = new Map;
  currentId = "";
  constructor(container) {
    this.container = container;
    this.cardEl = document.createElement("div");
    this.cardEl.className = "entity-card";
    this.cardEl.style.display = "none";
    this.container.appendChild(this.cardEl);
  }
  async show(entityId, entityName, screenX, screenY) {
    if (this.currentId === entityId && this.cardEl.style.display !== "none")
      return;
    this.currentId = entityId;
    let card = this.cache.get(entityId);
    if (!card) {
      try {
        const endpoint = entityId.includes("-") ? `/api/entity/${entityId}` : `/api/entity/search/${encodeURIComponent(entityName)}`;
        const resp = await fetch(endpoint);
        card = await resp.json();
        if (card && card.name) {
          this.cache.set(entityId, card);
        }
      } catch {
        card = { id: entityId, name: entityName, labels: [], summary: "Unknown entity." };
      }
    }
    if (!card)
      return;
    const namePrepared = prepare(card.name, CARD_NAME_FONT);
    const nameResult = layout(namePrepared, CARD_MAX_WIDTH, CARD_NAME_LINE_HEIGHT);
    let descHeight = 0;
    if (card.summary) {
      const descPrepared = prepare(card.summary, CARD_FONT);
      const descResult = layout(descPrepared, CARD_MAX_WIDTH, CARD_LINE_HEIGHT);
      descHeight = descResult.height;
    }
    const totalHeight = 12 + nameResult.height + (card.labels.length ? 20 : 0) + (descHeight ? descHeight + 8 : 0) + 24 + 12;
    this.cardEl.style.left = `${screenX - 130}px`;
    this.cardEl.style.top = `${screenY - totalHeight - 8}px`;
    this.cardEl.style.width = `${CARD_MAX_WIDTH + 24}px`;
    const labelsHtml = card.labels.length ? `<div class="card-labels">${card.labels.join(" · ")}</div>` : "";
    const descHtml = card.summary ? `<div class="card-desc">${card.summary}</div>` : "";
    this.cardEl.innerHTML = `
      <div class="card-name">${card.name}</div>
      ${labelsHtml}
      ${descHtml}
      <div class="card-hint">Enter to interact</div>
    `;
    this.cardEl.style.display = "block";
  }
  hide() {
    this.cardEl.style.display = "none";
    this.currentId = "";
  }
  clearCache() {
    this.cache.clear();
  }
}

// src/panels/map.ts
var renderer = null;
var controller = null;
var cardManager = null;
var cleanupInput = null;
var mapRef = { current: null };
function initMapPanel(mapContainer, _onAction) {
  renderer = new MapRenderer(mapContainer);
  cardManager = new EntityCardManager(document.body);
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
      if (!cardManager || !renderer)
        return;
      if (type && entity) {
        const screen = renderer.gridToScreen(entity.x, entity.y);
        cardManager.show(entity.id || entity.name, entity.name, screen.x, screen.y);
      } else {
        cardManager.hide();
      }
    });
    cleanupInput?.();
    cleanupInput = setupMapInput(controller, renderer, mapRef);
  } else {
    controller.loadMap(map);
  }
  renderer.render(map, controller.x, controller.y);
}
function renderLocationPanel(container, state, onAction) {
  let html = `<div style="color: var(--text-location); margin-bottom: 8px; font-size: 15px;">${state.location.name}</div>`;
  if (state.location.exits.length) {
    html += '<div style="margin-bottom: 8px;">';
    state.location.exits.forEach((exit) => {
      html += `<button class="action-btn" data-action="go ${exit}">Go ${exit}</button>`;
    });
    html += "</div>";
  }
  if (state.location.npcs.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Present:</span></div>';
    state.location.npcs.forEach((npc) => {
      html += `<div style="font-size: 13px; color: var(--text-npc); padding: 2px 0;">${npc}</div>`;
    });
  }
  container.innerHTML = html;
  container.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-action");
      if (action)
        onAction(action);
    });
  });
}

// src/panels/actions.ts
function renderActionsPanel(container, state, onAction) {
  const actions = [
    { label: "Look around", action: "look around" }
  ];
  state.location.npcs.forEach((npc) => {
    actions.push({ label: `Talk to ${npc}`, action: `talk to ${npc}` });
  });
  state.location.items.forEach((item) => {
    actions.push({ label: `Examine ${item}`, action: `examine ${item}` });
    actions.push({ label: `Pick up ${item}`, action: `pick up ${item}` });
  });
  container.innerHTML = actions.map((a) => `<button class="action-btn" data-action="${a.action}">${a.label}</button>`).join("");
  container.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-action");
      if (action)
        onAction(action);
    });
  });
}

// src/app.ts
var gameState;
var narrative;
function renderAllPanels() {
  if (!gameState)
    return;
  renderCharacterPanel(document.getElementById("character-panel"), gameState);
  renderInventoryPanel(document.getElementById("inventory-list"), gameState);
  renderLocationPanel(document.getElementById("location-panel"), gameState, handleAction);
  renderActionsPanel(document.getElementById("actions-list"), gameState, handleAction);
  updateMap(gameState, handleAction);
}
function getTestMap() {
  const w = 30, h = 15;
  const tiles = [];
  for (let y = 0;y < h; y++) {
    for (let x = 0;x < w; x++) {
      if (y === 0 || y === h - 1 || x === 0 || x === w - 1)
        tiles.push("#");
      else if (x === 5 && y >= 3 && y <= 5)
        tiles.push("B");
      else if ((x === 10 || x === 20) && (y === 4 || y === 8))
        tiles.push("T");
      else
        tiles.push(".");
    }
  }
  tiles[7 * w + (w - 1)] = "+";
  return {
    id: "test-tavern",
    name: "The Threshold",
    width: w,
    height: h,
    tiles,
    npcs: [
      { x: 6, y: 4, ch: "K", name: "Barkeeper", id: "npc-barkeeper" },
      { x: 15, y: 6, ch: "M", name: "Merchant", id: "npc-merchant" }
    ],
    items: [
      { x: 12, y: 9, ch: "!", name: "Health Potion", id: "item-potion" }
    ],
    exits: [
      { x: 29, y: 7, ch: "+", direction: "east", target: "unknown" }
    ],
    spawn: { x: 15, y: 12 }
  };
}
async function handleAction(action) {
  if (!action.trim())
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
      const segments = parseNarrative(msg.text || "");
      const html = renderSegments(segments);
      narrative.addHtml(html, "narrative");
      if (msg.state_update && gameState) {
        applyStateUpdate(gameState, msg.state_update);
        const session2 = getSession();
        session2.currentLocation = gameState.location.name;
        renderAllPanels();
      }
      if (msg.state_update?.status === "dead" || msg.text && msg.text.toLowerCase().includes("you have died")) {
        showDeathScreen(msg.state_update?.cause || "");
      }
      break;
    }
    case "thinking":
      narrative.showThinking();
      break;
    default:
      console.log("Unknown message:", msg);
  }
}
async function enterWorld(playerName) {
  const overlay = document.getElementById("char-create-overlay");
  overlay.classList.add("hidden");
  const session2 = await initSession(playerName);
  gameState = createInitialState(playerName);
  gameState.location.name = session2.currentLocation;
  if (!gameState.roomMap) {
    gameState.roomMap = getTestMap();
  }
  renderAllPanels();
  narrative.addBlock(`Welcome, ${playerName}. You find yourself at ${session2.currentLocation}.`, "system");
  if (session2.openingNarrative) {
    const segments = parseNarrative(session2.openingNarrative);
    narrative.addHtml(renderSegments(segments), "narrative");
  }
  document.getElementById("action-input").focus();
}
document.addEventListener("DOMContentLoaded", () => {
  narrative = initNarrative(document.getElementById("narrative-pane"));
  initMapPanel(document.getElementById("map-container"), handleAction);
  const actionInput = document.getElementById("action-input");
  initInput(actionInput, handleAction);
  setMessageHandler(handleMessage);
  setConnectionHandler((connected) => {
    if (connected) {
      narrative.addBlock("Reconnected.", "system");
    } else {
      narrative.addBlock("Connection lost. Reconnecting...", "system");
    }
  });
  document.getElementById("new-char-btn").addEventListener("click", () => {
    document.getElementById("death-overlay").classList.add("hidden");
    document.getElementById("char-create-overlay").classList.remove("hidden");
    document.getElementById("narrative-pane").innerHTML = "";
    document.getElementById("char-name-input").focus();
  });
  const nameInput = document.getElementById("char-name-input");
  const enterBtn = document.getElementById("enter-world-btn");
  enterBtn.addEventListener("click", () => {
    const name = nameInput.value.trim() || "Wanderer";
    enterWorld(name);
  });
  nameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const name = nameInput.value.trim() || "Wanderer";
      enterWorld(name);
    }
  });
  nameInput.focus();
});
