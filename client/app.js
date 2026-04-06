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
var errorHandler = null;
function setErrorHandler(handler) {
  errorHandler = handler;
}
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
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: session.playerId,
        action,
        location: session.currentLocation
      })
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "Unknown error");
      if (errorHandler)
        errorHandler(`Action failed: ${text}`);
    }
  } catch (e) {
    if (errorHandler)
      errorHandler("Connection lost — action not sent.");
  }
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
    roomMap: null,
    worldMap: null
  };
}
function applyStateUpdate(state2, update) {
  if (update.schema_version && update.schema_version > SCHEMA_VERSION) {
    console.warn(`Server schema version ${update.schema_version} > client ${SCHEMA_VERSION}. Please refresh.`);
  }
  if (update.location)
    state2.location.name = update.location;
  if (update.health != null)
    state2.player.health = update.health;
  if (update.max_health != null)
    state2.player.maxHealth = update.max_health;
  if (update.level != null)
    state2.player.level = update.level;
  if (update.xp != null)
    state2.player.xp = update.xp;
  if (update.exits)
    state2.location.exits = update.exits;
  if (update.npcs) {
    state2.location.npcs = update.npcs.map((n) => {
      const existing = state2.location.npcs.find((e) => e.id === n.id);
      return {
        name: n.name || "",
        id: n.id || "",
        role: n.role || "",
        ascii_art: existing?.ascii_art,
        x: n.x,
        y: n.y
      };
    });
  }
  if (update.items) {
    state2.location.items = update.items.map((i) => {
      const existing = state2.location.items.find((e) => e.id === i.id);
      return {
        name: i.name || "",
        id: i.id || "",
        role: i.role || "",
        ascii_art: existing?.ascii_art,
        x: i.x,
        y: i.y
      };
    });
  }
  if (update.inventory) {
    state2.inventory = update.inventory.map((i) => ({
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
    state2.player.skills = update.skills;
  if (update.room_map) {
    state2.roomMap = update.room_map;
    const rm = update.room_map;
    if (rm.name)
      state2.location.name = rm.name;
    if (rm.exits) {
      state2.location.exits = rm.exits.map((e) => ({
        direction: e.direction || "",
        name: e.target || e.name || ""
      }));
    }
    if (rm.npcs) {
      state2.location.npcs = rm.npcs.map((n) => {
        const existing = state2.location.npcs.find((e) => e.id === n.id);
        return {
          name: n.name || "",
          id: n.id || "",
          role: n.role || "",
          ascii_art: existing?.ascii_art,
          x: n.x,
          y: n.y
        };
      });
    }
    if (rm.items) {
      state2.location.items = rm.items.map((i) => {
        const existing = state2.location.items.find((e) => e.id === i.id);
        return {
          name: i.name || "",
          id: i.id || "",
          ascii_art: existing?.ascii_art,
          x: i.x,
          y: i.y
        };
      });
    }
  }
  if (update.active_quests) {
    state2.quests = update.active_quests.map((q) => ({
      name: q.name || "",
      description: q.description || "",
      currentStage: q.current_stage || 0,
      totalStages: q.total_stages || 0,
      giver: q.giver || "",
      completed: q.completed || false
    }));
  }
  if (update.factions) {
    state2.factions = update.factions.map((f) => ({
      name: f.name || "",
      reputation: f.reputation || 0,
      disposition: f.disposition || "neutral"
    }));
  }
}
function syncEntityField(gs, entityId, updates) {
  const locEntity = gs.location.npcs.find((n) => n.id === entityId) || gs.location.items.find((i) => i.id === entityId);
  if (locEntity)
    Object.assign(locEntity, updates);
  if (gs.roomMap) {
    const rmEntity = gs.roomMap.npcs.find((n) => n.id === entityId) || gs.roomMap.items.find((i) => i.id === entityId);
    if (rmEntity)
      Object.assign(rmEntity, updates);
  }
}

// src/message-handler.ts
var lastNpcMessages = new Map;
function getLastNpcMessage(npcName) {
  return lastNpcMessages.get(npcName) || "";
}
function createMessageHandler(refs) {
  return function handleMessage(msg) {
    const gameState = refs.getGameState();
    switch (msg.type) {
      case "narrative": {
        refs.narrative.removeThinking();
        const channel = msg.channel || "narrative";
        if (channel === "events") {
          refs.eventsFeed.addBlock(msg.text || "", "event");
        } else if (channel === "ooc") {
          refs.eventsFeed.addBlock(msg.text || "", "ooc");
        } else if (msg.npc) {
          lastNpcMessages.set(msg.npc, msg.text || "");
          const npcKey = msg.npc_username || msg.npc.toLowerCase().replace(/\s+/g, "-");
          refs.narrative.removeBlockById(`npc-status-${npcKey}`);
          refs.narrative.addBlock(`${msg.npc}`, "npc-name");
          refs.narrative.addBlock(msg.text || "", "npc-dialogue");
        } else {
          refs.narrative.addBlock(msg.text || "", "narrative");
        }
        if (msg.state_update && gameState) {
          applyStateUpdate(gameState, msg.state_update);
          const session2 = getSession();
          session2.currentLocation = gameState.location.name;
          if (gameState.roomMap)
            refs.registerMapEntities(gameState.roomMap);
          if (msg.state_update.world_time) {
            refs.header.updateTime(msg.state_update.world_time);
            refs.statusBar.setTick(msg.state_update.world_time.tick || 0);
          }
          refs.renderAllPanels();
          refs.fetchPlayerWorldMap();
          if (msg.state_update.events) {
            const events = msg.state_update.events;
            if (events.combat) {
              const c = events.combat;
              if (c.damage_dealt != null) {
                refs.eventsFeed.addBlock(`[-${c.damage_dealt} HP] ${c.target_name || ""}`, "event-combat");
              }
              if (c.xp_gained) {
                refs.eventsFeed.addBlock(`[+${c.xp_gained} XP]`, "event-xp");
              }
              if (c.target_dead) {
                refs.eventsFeed.addBlock(`${c.target_name || "Target"} has been slain.`, "event-death");
              }
            }
            if (events.inventory_changes) {
              for (const inv of events.inventory_changes) {
                const prefix = inv.event_type === "DROP" ? "-" : "+";
                refs.eventsFeed.addBlock(`[${prefix}${inv.item_name}]`, "event-item");
              }
            }
          }
        }
        if (msg.state_update?.status === "dead" || msg.state_update?.events?.combat?.target_dead || msg.text && msg.text.toLowerCase().includes("you have died")) {
          refs.showDeathScreen(msg.state_update?.cause || "");
        }
        break;
      }
      case "death_feed": {
        const skull = "☠";
        const deathMsg = `${skull} ${msg.player_name || "Unknown"} (Level ${msg.level || "?"}) fell at ${msg.location || "unknown"}. ${msg.cause || ""}`;
        refs.narrative.addBlock(deathMsg, "death-feed");
        break;
      }
      case "scene_art": {
        const artLines = msg.lines || [];
        if (artLines.length > 0) {
          refs.setViewportScene?.(artLines);
        }
        break;
      }
      case "entity_art": {
        const artLines = msg.lines || [];
        if (msg.entity_id && gameState) {
          syncEntityField(gameState, msg.entity_id, { ascii_art: artLines.join(`
`) });
        }
        if (msg.entity_id && refs.codex?.active) {
          refs.codex.refreshEntityArt(msg.entity_id, artLines);
        }
        break;
      }
      case "codex_refresh": {
        break;
      }
      case "npc_status": {
        const npcKey = msg.npc_username || msg.npc || "unknown";
        refs.narrative.replaceBlock(`npc-status-${npcKey}`, `${msg.npc}: ${msg.text}`, "npc-status");
        break;
      }
      case "phase": {
        updateRoundState(msg);
        const phase = msg.phase || "";
        const crew = msg.crew || "";
        if (phase === "resolving" && crew) {
          refs.eventsFeed.replaceBlock("phase-progress", `[${crew}]`, "event");
        } else if (phase === "npc_response") {
          refs.eventsFeed.replaceBlock("phase-progress", "[waiting for NPCs]", "event");
        } else if (phase === "ready") {
          refs.eventsFeed.removeBlockById("phase-progress");
        }
        break;
      }
      case "status":
        if (msg.tick != null)
          refs.statusBar.setTick(msg.tick);
        if (msg.chain != null)
          refs.statusBar.setChain(msg.chain);
        if (msg.activity)
          refs.statusBar.setActivity(msg.activity);
        break;
      case "player_joined": {
        if (gameState) {
          const exists = gameState.location.players.some((p) => p.id === msg.player_id);
          if (!exists) {
            gameState.location.players.push({ name: msg.player_name, id: msg.player_id });
            refs.renderAllPanels();
            refs.narrative.addBlock(`${msg.player_name} arrived.`, "system");
          }
        }
        break;
      }
      case "player_left": {
        if (gameState) {
          gameState.location.players = gameState.location.players.filter((p) => p.id !== msg.player_id);
          refs.renderAllPanels();
          refs.narrative.addBlock(`${msg.player_name} departed.`, "system");
        }
        break;
      }
      case "position_update": {
        if (gameState && msg.entity_id) {
          syncEntityField(gameState, msg.entity_id, { x: msg.x, y: msg.y });
          refs.renderAllPanels();
        }
        break;
      }
      case "npc_left": {
        if (gameState) {
          const leftName = msg.npc_name.toLowerCase();
          gameState.location.npcs = gameState.location.npcs.filter((n) => n.name.toLowerCase() !== leftName && !n.name.toLowerCase().startsWith(leftName));
          refs.renderAllPanels();
        }
        break;
      }
      case "npc_joined": {
        if (gameState && msg.npc_name) {
          const joinName = msg.npc_name.toLowerCase();
          const exists = gameState.location.npcs.some((n) => n.name.toLowerCase() === joinName || n.name.toLowerCase().startsWith(joinName));
          if (!exists) {
            gameState.location.npcs.push({ name: msg.npc_name, id: msg.npc_id || "", role: "" });
            refs.renderAllPanels();
          }
        }
        break;
      }
      case "presence": {
        if (gameState) {
          gameState.location.players = (msg.players || []).map((p) => ({
            name: p.player_name,
            id: p.player_id
          }));
          refs.renderAllPanels();
        }
        break;
      }
      case "state_update": {
        if (msg.state_update && gameState) {
          applyStateUpdate(gameState, msg.state_update);
          refs.renderAllPanels();
          refs.fetchPlayerWorldMap();
          if (refs.invModal.active)
            refs.invModal.refresh();
        }
        break;
      }
      case "room_items_changed": {
        if (refs.invModal.active)
          refs.invModal.refresh();
        break;
      }
      case "episode_feed": {
        const label = msg.location ? `[Chronicle · ${msg.location}]` : "[Chronicle]";
        refs.eventsFeed.addBlock(`${label} ${msg.name}: ${msg.summary}`, "event");
        break;
      }
      default:
        console.log("Unknown message:", msg);
    }
  };
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
      return [{ text: `◆ ${blockText}`, col: padding, row: 0, fg: theme.colors.npc, attrs: ATTR_BOLD | ATTR_UNDERLINE, npcName: blockText }];
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
        if (seg.npcName) {
          hitRegions.push({
            x: seg.col * charSize.width,
            y: segPixelY,
            w: seg.text.length * charSize.width,
            h: charSize.height,
            npcName: seg.npcName
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
        if (region.npcName) {
          canvas.dispatchEvent(new CustomEvent("npc-name-click", {
            detail: { npcName: region.npcName },
            bubbles: true
          }));
        } else {
          canvas.dispatchEvent(new CustomEvent("narrative-entity-click", {
            detail: { entityId: region.entityId, entityName: region.entityName },
            bubbles: true
          }));
        }
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
    scroll(deltaY) {
      scrollOffset += deltaY;
      clampScroll();
      const maxScroll = Math.max(0, store.totalHeight - canvasH);
      userAtBottom = scrollOffset >= maxScroll - 30;
      scheduleRender();
    },
    canvas
  };
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
        this.syncPosition();
        return;
      }
      const npc = this.map.npcs.find((n) => n.x === tx && n.y === ty);
      if (npc) {
        this.onInteract("npc", npc);
        this.syncPosition();
        return;
      }
      const item = this.map.items.find((i) => i.x === tx && i.y === ty);
      if (item) {
        this.onInteract("item", item);
        this.syncPosition();
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
  syncPosition() {
    const pid = window.__mmPlayerId;
    if (!pid)
      return;
    fetch("/api/position/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: pid, x: this.x, y: this.y })
    }).catch(() => {});
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
var viewportCallback = null;
function setViewportCallback(cb) {
  viewportCallback = cb;
}
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
function getMapCanvas() {
  return renderer?.element ?? null;
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
      if (type === "npc") {
        const npc = entity;
        document.dispatchEvent(new CustomEvent("narrative-entity-click", {
          detail: { entityId: npc.id, entityName: npc.name },
          bubbles: true
        }));
      } else if (type === "item") {
        const item = entity;
        document.dispatchEvent(new CustomEvent("narrative-entity-click", {
          detail: { entityId: item.id, entityName: item.name },
          bubbles: true
        }));
      } else if (type === "exit") {
        onAction(`go ${entity.direction}`);
      }
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
          viewportCallback?.(card);
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
  viewportCallback?.(card);
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
function renderCharacterPanel(cols, _rows, state2) {
  const p = state2.player;
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
  return { cells };
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
function renderInventoryPanel(cols, _rows, state2) {
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
  return { cells };
}

// src/panels/present.ts
function renderPresentPanel(cols, _rows, state2) {
  const cells = [];
  const hitRegions = [];
  const npcs = state2.location.npcs || [];
  const items = state2.location.items || [];
  const players = state2.location.players || [];
  if (npcs.length === 0 && items.length === 0 && players.length === 0) {
    cells.push(textRow("Nothing here", theme.colors.dim, cols));
    return { cells };
  }
  const rs = getRoundState();
  const isThinking = rs.phase === "npc_response";
  const npcColor = isThinking ? theme.colors.system : theme.colors.npc;
  for (const npc of npcs) {
    const name = typeof npc === "string" ? npc : npc.name;
    const role = typeof npc === "string" ? "" : npc.role || "";
    const startRow = cells.length;
    cells.push(coloredRow([
      { text: "◆ ", fg: npcColor },
      { text: name, fg: npcColor, attrs: ATTR_BOLD }
    ], cols));
    if (role) {
      cells.push(coloredRow([
        { text: "  ", fg: theme.colors.dim },
        { text: role, fg: theme.colors.dim }
      ], cols));
    }
    const sep = [];
    for (let i = 0;i < cols; i++) {
      sep.push({ char: i < cols - 1 ? "─" : " ", fg: "#1a1a25" });
    }
    cells.push(sep);
    hitRegions.push({
      col: 0,
      row: startRow,
      width: cols,
      height: cells.length - startRow,
      data: { action: `talk to ${name}` }
    });
  }
  if (players.length > 0) {
    for (const p of players) {
      const name = typeof p === "string" ? p : p.name;
      cells.push(coloredRow([
        { text: "@ ", fg: theme.colors.heal },
        { text: name, fg: theme.colors.primary }
      ], cols));
    }
    cells.push(emptyRow(cols));
  }
  for (const item of items) {
    const name = typeof item === "string" ? item : item.name;
    const rowIdx = cells.length;
    cells.push(coloredRow([
      { text: "· ", fg: theme.colors.dim },
      { text: name, fg: theme.colors.primary }
    ], cols));
    hitRegions.push({
      col: 0,
      row: rowIdx,
      width: cols,
      height: 1,
      data: { action: `examine ${name}` }
    });
  }
  return { cells, hitRegions };
}

// src/panels/questlog.ts
function renderQuestLogPanel(cols, _rows, quests) {
  const cells = [];
  const hitRegions = [];
  if (!quests || quests.length === 0) {
    cells.push(textRow("No active quests", theme.colors.dim, cols));
    return { cells };
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
    hitRegions.push({
      col: 0,
      row: questStartRow,
      width: cols,
      height: questEndRow - questStartRow,
      data: { questName: q.name }
    });
  }
  return { cells, hitRegions };
}

// src/panels/viewport.ts
var BAR_FULL = "█";
var BAR_EMPTY = "░";
var BAR_WIDTH = 12;
function renderViewport(cols, _rows, card, sceneArt) {
  const cells = [];
  if (cols < 10)
    return { cells };
  if (sceneArt && sceneArt.length > 0) {
    const artColor = theme.colors.dim;
    for (const line of sceneArt) {
      const row = [];
      for (let c = 0;c < cols; c++) {
        row.push({ char: line[c] || " ", fg: artColor });
      }
      cells.push(row);
    }
  } else if (card) {
    renderCard(cells, cols, card);
  } else {
    const msg = "~ nothing in focus ~";
    const row = [];
    const pad = Math.max(0, Math.floor((cols - msg.length) / 2));
    for (let c = 0;c < cols; c++) {
      const ch = c >= pad && c < pad + msg.length ? msg[c - pad] : " ";
      row.push({ char: ch, fg: theme.colors.dim });
    }
    cells.push(row);
  }
  return { cells };
}
function renderCard(cells, cols, card) {
  const { colors } = theme;
  const nameRow = [];
  const nameColor = card.type === "player" ? colors.accent : colors.npc;
  writeText(nameRow, cols, `◆ ${card.name}`, nameColor, ATTR_BOLD);
  cells.push(nameRow);
  if (card.labels.length > 0) {
    const labelRow = [];
    const labelText = card.labels.map((l) => `[${l}]`).join(" ");
    writeText(labelRow, cols, `  ${labelText}`, colors.dim);
    cells.push(labelRow);
  }
  if (card.summary) {
    const maxLen = cols - 2;
    const summary = card.summary.length > maxLen ? card.summary.slice(0, maxLen - 3) + "..." : card.summary;
    const summaryRow = [];
    writeText(summaryRow, cols, `  ${summary}`, colors.primary);
    cells.push(summaryRow);
  }
  if (card.health !== undefined && card.maxHealth !== undefined) {
    const hpRow = [];
    const hpPct = Math.max(0, Math.min(1, card.health / card.maxHealth));
    const hpColor = hpPct > 0.3 ? colors.heal : colors.damage;
    const filled = Math.round(hpPct * BAR_WIDTH);
    const barStr = BAR_FULL.repeat(filled) + BAR_EMPTY.repeat(BAR_WIDTH - filled);
    writeText(hpRow, cols, `  HP `, colors.dim);
    appendText(hpRow, barStr, hpColor);
    appendText(hpRow, ` ${card.health}/${card.maxHealth}`, colors.primary);
    padRow(hpRow, cols);
    cells.push(hpRow);
  }
  if (card.xp !== undefined && card.xpThreshold !== undefined) {
    const xpRow = [];
    const xpPct = Math.max(0, Math.min(1, card.xp / card.xpThreshold));
    const filled = Math.round(xpPct * BAR_WIDTH);
    const barStr = BAR_FULL.repeat(filled) + BAR_EMPTY.repeat(BAR_WIDTH - filled);
    writeText(xpRow, cols, `  XP `, colors.dim);
    appendText(xpRow, barStr, colors.accent);
    appendText(xpRow, ` ${card.xp}/${card.xpThreshold}`, colors.primary);
    padRow(xpRow, cols);
    cells.push(xpRow);
  }
  if (card.level !== undefined) {
    const lvRow = [];
    writeText(lvRow, cols, `  Lv ${card.level}`, colors.dim);
    cells.push(lvRow);
  }
  if (card.hint) {
    const hintRow = [];
    writeText(hintRow, cols, `  ${card.hint}`, colors.dim);
    cells.push(hintRow);
  }
}
function writeText(row, cols, text, fg, attrs) {
  for (let i = 0;i < cols; i++) {
    row.push({ char: text[i] || " ", fg, attrs });
  }
}
function appendText(row, text, fg, attrs) {
  for (const ch of text) {
    row.push({ char: ch, fg, attrs });
  }
}
function padRow(row, cols) {
  while (row.length < cols) {
    row.push({ char: " ", fg: "#0a0a0f" });
  }
}

// src/ui/header.ts
function renderHeader(cols, state2) {
  const titleText = state2.title;
  let timeText = "";
  if (state2.worldTime) {
    const wt = state2.worldTime;
    timeText = `${wt.moon_icon} ${wt.moon_phase}  ·  ${ordinal(wt.day_number)} of ${wt.month}  ·  ${wt.time_of_day}`;
  }
  const spacerLen = Math.max(1, cols - titleText.length - timeText.length);
  const spacer = " ".repeat(spacerLen);
  const segments = [
    { text: titleText, fg: theme.colors.npc },
    { text: spacer, fg: theme.colors.primary }
  ];
  if (timeText) {
    segments.push({ text: timeText, fg: theme.colors.dim });
  }
  return { cells: [coloredRow(segments, cols)] };
}
function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

// src/ui/status.ts
function renderStatusBar(cols, state2) {
  let phaseText;
  switch (state2.phase) {
    case "ready":
      phaseText = state2.location ? `✓ Ready · ${state2.location}` : "✓ Ready";
      break;
    case "collecting":
      phaseText = `⟳ Collecting · ${state2.tick}s`;
      break;
    case "resolving":
      phaseText = "⟳ Resolving";
      break;
    case "npc_response":
      phaseText = "⟳ NPCs Responding";
      break;
    default:
      phaseText = state2.phase;
  }
  if (state2.activity) {
    phaseText += `  ✨ ${state2.activity}`;
  }
  const chainText = state2.chain ? "◆ Redstone: synced" : "◇ Redstone: offline";
  const chainColor = state2.chain ? theme.colors.heal : theme.colors.dim;
  const tickText = `☽ Tick ${state2.tick}`;
  const innerSpace = cols - phaseText.length - chainText.length - tickText.length;
  const leftPad = Math.max(1, Math.floor(innerSpace / 2));
  const rightPad = Math.max(1, innerSpace - leftPad);
  const segments = [
    { text: phaseText, fg: theme.colors.system },
    { text: " ".repeat(leftPad), fg: theme.colors.primary },
    { text: chainText, fg: chainColor },
    { text: " ".repeat(rightPad), fg: theme.colors.primary },
    { text: tickText, fg: theme.colors.dim }
  ];
  return { cells: [coloredRow(segments, cols)] };
}

// src/canvas/region-manager.ts
var PRESENT_COLS = 20;
var SIDEBAR_COLS = 32;
function computeRegions(totalCols, totalRows) {
  const regions = new Map;
  const innerCols = totalCols - 2;
  const presentCols = Math.min(PRESENT_COLS, Math.floor(innerCols * 0.2));
  const sidebarCols = Math.min(SIDEBAR_COLS, Math.floor(innerCols * 0.25));
  const viewportCols = innerCols - presentCols - sidebarCols - 2;
  const colPresent = 1;
  const colVDiv0 = colPresent + presentCols;
  const colViewport = colVDiv0 + 1;
  const colVDiv1 = colViewport + viewportCols;
  const colSidebar = colVDiv1 + 1;
  const contentZoneRows = Math.max(totalRows - 9, 2);
  const topZoneRows = Math.max(Math.floor(contentZoneRows * 2 / 3), 3);
  const bottomZoneRows = Math.max(contentZoneRows - topZoneRows, 1);
  const rowHeader = 1;
  const rowHDiv0 = 2;
  const rowTopStart = 3;
  const rowHDiv1 = rowTopStart + topZoneRows;
  const rowBotStart = rowHDiv1 + 1;
  const rowHDiv2 = rowBotStart + bottomZoneRows;
  const rowInput = rowHDiv2 + 1;
  const rowHDiv3 = rowInput + 1;
  const rowStatus = rowHDiv3 + 1;
  const sidebarContentRows = topZoneRows - 2;
  const charRows = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const questRows = Math.max(Math.floor(sidebarContentRows * 2 / 7), 1);
  const inventoryRows = Math.max(sidebarContentRows - charRows - questRows, 1);
  const rowSDiv0 = rowTopStart + charRows;
  const rowSDiv1 = rowSDiv0 + 1 + inventoryRows;
  function add(r) {
    regions.set(r.name, r);
  }
  add({
    name: "header",
    col: colPresent,
    row: rowHeader,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "input",
    col: colPresent,
    row: rowInput,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "status",
    col: colPresent,
    row: rowStatus,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "present",
    col: colPresent,
    row: rowTopStart,
    cols: presentCols,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "viewport",
    col: colViewport,
    row: rowTopStart,
    cols: viewportCols,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "character",
    col: colSidebar,
    row: rowTopStart,
    cols: sidebarCols,
    rows: charRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "inventory",
    col: colSidebar,
    row: rowSDiv0 + 1,
    cols: sidebarCols,
    rows: inventoryRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "quests",
    col: colSidebar,
    row: rowSDiv1 + 1,
    cols: sidebarCols,
    rows: questRows,
    type: "grid",
    scrollOffset: 0
  });
  const narrativeCols = presentCols + 1 + viewportCols;
  add({
    name: "narrative",
    col: colPresent,
    row: rowBotStart,
    cols: narrativeCols,
    rows: bottomZoneRows,
    type: "pixel",
    scrollOffset: 0
  });
  add({
    name: "events",
    col: colSidebar,
    row: rowBotStart,
    cols: sidebarCols,
    rows: bottomZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv0",
    col: colPresent,
    row: rowHDiv0,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv1",
    col: colPresent,
    row: rowHDiv1,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv2",
    col: colPresent,
    row: rowHDiv2,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_hDiv3",
    col: colPresent,
    row: rowHDiv3,
    cols: innerCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDiv0",
    col: colVDiv0,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_vDiv1",
    col: colVDiv1,
    row: rowTopStart,
    cols: 1,
    rows: topZoneRows + 1 + bottomZoneRows,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_sDiv0",
    col: colSidebar,
    row: rowSDiv0,
    cols: sidebarCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  add({
    name: "_sDiv1",
    col: colSidebar,
    row: rowSDiv1,
    cols: sidebarCols,
    rows: 1,
    type: "grid",
    scrollOffset: 0
  });
  return regions;
}

// src/canvas/border-renderer.ts
var D_TL = "╔";
var D_TR = "╗";
var D_BL = "╚";
var D_BR = "╝";
var D_H = "═";
var D_V = "║";
var D_ML = "╠";
var D_MR = "╣";
var D_MT = "╦";
var S_H = "─";
var S_V = "│";
var S_ML = "├";
var M_SH_DV_R = "╡";
function setCell(grid, row, col, char, fg) {
  if (row < 0 || col < 0 || row >= grid.length || col >= (grid[0]?.length ?? 0))
    return;
  grid[row][col] = { char, fg };
}
function hLine(grid, row, colStart, colEnd, char, fg) {
  for (let c = colStart;c <= colEnd; c++)
    setCell(grid, row, c, char, fg);
}
function vLine(grid, col, rowStart, rowEnd, char, fg) {
  for (let r = rowStart;r <= rowEnd; r++)
    setCell(grid, r, col, char, fg);
}
function drawBorders(grid, regions, totalCols, totalRows) {
  const fg = theme.colors.dim;
  const hDiv0 = regions.get("_hDiv0");
  const hDiv1 = regions.get("_hDiv1");
  const hDiv2 = regions.get("_hDiv2");
  const hDiv3 = regions.get("_hDiv3");
  const vDiv0 = regions.get("_vDiv0");
  const vDiv1 = regions.get("_vDiv1");
  const sDiv0 = regions.get("_sDiv0");
  const sDiv1 = regions.get("_sDiv1");
  if (!hDiv0 || !hDiv1 || !hDiv2 || !hDiv3 || !vDiv0 || !vDiv1 || !sDiv0 || !sDiv1) {
    console.warn("[border-renderer] Missing divider metadata regions — skipping border draw");
    return;
  }
  const vd0 = vDiv0;
  const vd1 = vDiv1;
  const lastCol = totalCols - 1;
  const lastRow = totalRows - 1;
  const innerColStart = 1;
  const innerColEnd = lastCol - 1;
  setCell(grid, 0, 0, D_TL, fg);
  setCell(grid, 0, lastCol, D_TR, fg);
  setCell(grid, lastRow, 0, D_BL, fg);
  setCell(grid, lastRow, lastCol, D_BR, fg);
  hLine(grid, 0, 1, lastCol - 1, D_H, fg);
  hLine(grid, lastRow, 1, lastCol - 1, D_H, fg);
  vLine(grid, 0, 1, lastRow - 1, D_V, fg);
  vLine(grid, lastCol, 1, lastRow - 1, D_V, fg);
  function drawHDiv(row) {
    setCell(grid, row, 0, D_ML, fg);
    setCell(grid, row, lastCol, D_MR, fg);
    hLine(grid, row, innerColStart, innerColEnd, D_H, fg);
    if (row >= vd0.row && row < vd0.row + vd0.rows) {
      setCell(grid, row, vd0.col, D_MT, fg);
    }
    if (row >= vd1.row && row < vd1.row + vd1.rows) {
      setCell(grid, row, vd1.col, D_MT, fg);
    }
  }
  drawHDiv(hDiv0.row);
  drawHDiv(hDiv1.row);
  drawHDiv(hDiv2.row);
  drawHDiv(hDiv3.row);
  setCell(grid, hDiv2.row, vDiv0.col, "╧", fg);
  setCell(grid, hDiv2.row, vDiv1.col, "╪", fg);
  vLine(grid, vDiv0.col, vDiv0.row, vDiv0.row + vDiv0.rows - 1, S_V, fg);
  vLine(grid, vDiv1.col, vDiv1.row, vDiv1.row + vDiv1.rows - 1, S_V, fg);
  const vDivCols = [vDiv0.col, vDiv1.col];
  const hDivRows = [hDiv0.row, hDiv1.row, hDiv3.row];
  for (const vc of vDivCols) {
    for (const hr of hDivRows) {
      const vr = vc === vDiv0.col ? vDiv0 : vDiv1;
      if (hr >= vr.row && hr < vr.row + vr.rows) {
        setCell(grid, hr, vc, "╪", fg);
      }
    }
  }
  const sCol = sDiv0.col;
  const sEnd = sDiv0.col + sDiv0.cols - 1;
  setCell(grid, sDiv0.row, vDiv1.col, S_ML, fg);
  hLine(grid, sDiv0.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv0.row, lastCol, M_SH_DV_R, fg);
  setCell(grid, sDiv1.row, vDiv1.col, S_ML, fg);
  hLine(grid, sDiv1.row, sCol, sEnd, S_H, fg);
  setCell(grid, sDiv1.row, lastCol, M_SH_DV_R, fg);
  setCell(grid, hDiv3.row, vDiv1.col, "╧", fg);
}

// src/canvas/hit-registry.ts
class HitRegistry {
  entries = [];
  clear(z) {
    if (z === undefined) {
      this.entries = [];
    } else {
      this.entries = this.entries.filter((e) => e.z !== z);
    }
  }
  clearRegion(regionName, z) {
    this.entries = this.entries.filter((e) => !(e.region === regionName && e.z === z));
  }
  registerPanel(regionName, region, localRegions, z = 0) {
    for (const local of localRegions) {
      this.entries.push({
        region: regionName,
        col: region.col + local.col,
        row: region.row + local.row,
        width: local.width,
        height: local.height,
        z,
        data: local.data
      });
    }
  }
  register(entry) {
    this.entries.push(entry);
  }
  hitTest(col, row) {
    let best = null;
    for (const e of this.entries) {
      if (col >= e.col && col < e.col + e.width && row >= e.row && row < e.row + e.height) {
        if (best === null || e.z > best.z) {
          best = e;
        }
      }
    }
    if (best === null)
      return null;
    return { region: best.region, data: best.data };
  }
  hasModalLayer() {
    return this.entries.some((e) => e.z > 0);
  }
}

// src/canvas/modal-manager.ts
class ModalManager {
  stack = [];
  uc;
  constructor(uc) {
    this.uc = uc;
  }
  open(name, widthPct, heightPct) {
    this.close(name);
    const totalCols = this.uc.totalCols;
    const totalRows = this.uc.totalRows;
    const innerCols = Math.floor((totalCols - 2) * widthPct);
    const innerRows = Math.floor((totalRows - 2) * heightPct);
    const cols = innerCols + 2;
    const rows = innerRows + 2;
    const col = Math.floor((totalCols - cols) / 2);
    const row = Math.floor((totalRows - rows) / 2);
    const z = this.stack.length + 1;
    const state2 = {
      name,
      region: { name: `modal_${name}`, col, row, cols, rows, type: "grid", scrollOffset: 0 },
      z,
      cells: [],
      hitRegions: [],
      scrollOffset: 0,
      totalContentRows: 0
    };
    this.stack.push(state2);
    this.uc.markAllDirty();
    return state2;
  }
  setContent(name, result) {
    const modal = this.stack.find((m) => m.name === name);
    if (!modal)
      return;
    modal.cells = result.cells;
    modal.hitRegions = result.hitRegions || [];
    modal.totalContentRows = result.cells.length;
    this.uc.hitRegistry.clear(modal.z);
    if (modal.hitRegions.length > 0) {
      const contentRegion = {
        ...modal.region,
        name: `modal_${name}_content`,
        col: modal.region.col + 1,
        row: modal.region.row + 1,
        cols: modal.region.cols - 2,
        rows: modal.region.rows - 2
      };
      this.uc.hitRegistry.registerPanel(`modal_${name}`, contentRegion, modal.hitRegions, modal.z);
    }
    this.uc.markAllDirty();
  }
  close(name) {
    const idx = this.stack.findIndex((m) => m.name === name);
    if (idx === -1)
      return;
    const modal = this.stack[idx];
    this.uc.hitRegistry.clear(modal.z);
    this.stack.splice(idx, 1);
    this.uc.markAllDirty();
  }
  closeTopmost() {
    if (this.stack.length === 0)
      return null;
    const top = this.stack.pop();
    this.uc.hitRegistry.clear(top.z);
    this.uc.markAllDirty();
    return top.name;
  }
  get active() {
    return this.stack.length > 0;
  }
  get topmost() {
    return this.stack[this.stack.length - 1] || null;
  }
  getStack() {
    return this.stack;
  }
  isOpen(name) {
    return this.stack.some((m) => m.name === name);
  }
  renderInto(grid, totalCols, totalRows) {
    for (const modal of this.stack) {
      const { region, cells, scrollOffset } = modal;
      for (let r = 0;r < totalRows; r++) {
        for (let c = 0;c < totalCols; c++) {
          if (r >= region.row && r < region.row + region.rows && c >= region.col && c < region.col + region.cols)
            continue;
          if (grid[r] && grid[r][c]) {
            grid[r][c] = { ...grid[r][c], fg: theme.colors.dim, bg: undefined };
          }
        }
      }
      const D = {
        H: "═",
        V: "║",
        TL: "╔",
        TR: "╗",
        BL: "╚",
        BR: "╝"
      };
      const borderFg = theme.colors.accent;
      const bg = theme.colors.bg;
      if (region.row < totalRows && region.col + region.cols <= totalCols) {
        grid[region.row][region.col] = { char: D.TL, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[region.row][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[region.row][region.col + region.cols - 1] = { char: D.TR, fg: borderFg, bg };
      }
      const botRow = region.row + region.rows - 1;
      if (botRow < totalRows && region.col + region.cols <= totalCols) {
        grid[botRow][region.col] = { char: D.BL, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[botRow][region.col + c] = { char: D.H, fg: borderFg, bg };
        }
        grid[botRow][region.col + region.cols - 1] = { char: D.BR, fg: borderFg, bg };
      }
      for (let r = 1;r < region.rows - 1; r++) {
        const gr = region.row + r;
        if (gr >= totalRows)
          break;
        grid[gr][region.col] = { char: D.V, fg: borderFg, bg };
        grid[gr][region.col + region.cols - 1] = { char: D.V, fg: borderFg, bg };
        for (let c = 1;c < region.cols - 1; c++) {
          grid[gr][region.col + c] = { char: " ", fg: theme.colors.primary, bg };
        }
      }
      const contentCol = region.col + 1;
      const contentRow = region.row + 1;
      const contentCols = region.cols - 2;
      const contentRows = region.rows - 2;
      for (let r = 0;r < contentRows; r++) {
        const srcRow = r + scrollOffset;
        if (srcRow >= cells.length)
          break;
        const srcRowCells = cells[srcRow];
        if (!srcRowCells)
          continue;
        for (let c = 0;c < Math.min(srcRowCells.length, contentCols); c++) {
          const gr = contentRow + r;
          const gc = contentCol + c;
          if (gr < totalRows && gc < totalCols) {
            grid[gr][gc] = { ...srcRowCells[c], bg };
          }
        }
      }
    }
  }
  scroll(deltaRows) {
    const modal = this.topmost;
    if (!modal)
      return;
    const maxScroll = Math.max(0, modal.totalContentRows - (modal.region.rows - 2));
    modal.scrollOffset = Math.max(0, Math.min(modal.scrollOffset + deltaRows, maxScroll));
    this.uc.markAllDirty();
  }
}

// src/canvas/unified-canvas.ts
class UnifiedCanvas {
  canvas;
  regions;
  hitRegistry;
  modalManager;
  totalCols;
  totalRows;
  ctx;
  charSize;
  grid;
  borderGrid;
  dirtySet = new Set;
  allDirty = true;
  renderScheduled = false;
  clickHandlers = [];
  wheelHandlers = [];
  pixelRenderers = [];
  offscreenSlots = [];
  observer;
  constructor(container) {
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    container.appendChild(this.canvas);
    const ctx = this.canvas.getContext("2d");
    if (!ctx)
      throw new Error("UnifiedCanvas: failed to get 2d context");
    this.ctx = ctx;
    this.charSize = measureChar(this.ctx, MONO_FONT);
    this.totalCols = 1;
    this.totalRows = 1;
    this.grid = [[{ char: " ", fg: theme.colors.primary }]];
    this.borderGrid = [[{ char: " ", fg: theme.colors.primary }]];
    this.regions = new Map;
    this.hitRegistry = new HitRegistry;
    this.modalManager = new ModalManager(this);
    this.canvas.addEventListener("click", this._onClick.bind(this));
    this.canvas.addEventListener("mousemove", this._onMouseMove.bind(this));
    this.canvas.addEventListener("mouseleave", this._onMouseLeave.bind(this));
    this.canvas.addEventListener("wheel", this._onWheel.bind(this), { passive: false });
    this.observer = new ResizeObserver(() => this._resize());
    this.observer.observe(container);
    this._resize();
  }
  _resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0)
      return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(rect.width * dpr);
    this.canvas.height = Math.floor(rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.charSize = measureChar(this.ctx, MONO_FONT);
    const { width: cw, height: ch } = this.charSize;
    this.totalCols = Math.max(Math.floor(rect.width / cw), 10);
    this.totalRows = Math.max(Math.floor(rect.height / ch), 5);
    this.grid = this._allocGrid(this.totalRows, this.totalCols);
    this.borderGrid = this._allocGrid(this.totalRows, this.totalCols);
    this.regions = computeRegions(this.totalCols, this.totalRows);
    drawBorders(this.borderGrid, this.regions, this.totalCols, this.totalRows);
    this.markAllDirty();
  }
  _allocGrid(rows, cols) {
    const empty = { char: " ", fg: theme.colors.primary };
    return Array.from({ length: rows }, () => Array.from({ length: cols }, () => ({ ...empty })));
  }
  setRegionContent(name, result) {
    const region = this.regions.get(name);
    if (!region)
      return;
    const { cells, hitRegions } = result;
    for (let r = 0;r < cells.length && r < region.rows; r++) {
      const row = cells[r];
      for (let c = 0;c < row.length && c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr < this.totalRows && gc < this.totalCols) {
          this.grid[gr][gc] = row[c];
        }
      }
    }
    this.hitRegistry.clearRegion(name, 0);
    if (hitRegions && hitRegions.length > 0) {
      this.hitRegistry.registerPanel(name, region, hitRegions, 0);
    }
    this.markDirty(name);
  }
  setOffscreen(regionName, offscreenCanvas) {
    const existing = this.offscreenSlots.findIndex((s) => s.regionName === regionName);
    if (existing >= 0) {
      this.offscreenSlots[existing] = { regionName, canvas: offscreenCanvas };
    } else {
      this.offscreenSlots.push({ regionName, canvas: offscreenCanvas });
    }
    this.markDirty(regionName);
  }
  setPixelRenderer(regionName, renderer2) {
    const existing = this.pixelRenderers.findIndex((p) => p.regionName === regionName);
    if (existing >= 0) {
      this.pixelRenderers[existing] = { regionName, renderer: renderer2 };
    } else {
      this.pixelRenderers.push({ regionName, renderer: renderer2 });
    }
    this.markDirty(regionName);
  }
  onClick(handler) {
    this.clickHandlers.push(handler);
  }
  onWheel(handler) {
    this.wheelHandlers.push(handler);
  }
  markDirty(name) {
    this.dirtySet.add(name);
    this._scheduleRender();
  }
  markAllDirty() {
    this.allDirty = true;
    this._scheduleRender();
  }
  _scheduleRender() {
    if (this.renderScheduled)
      return;
    this.renderScheduled = true;
    requestAnimationFrame(() => {
      this.renderScheduled = false;
      this._paint();
    });
  }
  getRegion(name) {
    return this.regions.get(name);
  }
  getCharSize() {
    return this.charSize;
  }
  _paint() {
    const ctx = this.ctx;
    const cs = this.charSize;
    if (this.allDirty) {
      ctx.fillStyle = theme.colors.bg;
      ctx.fillRect(0, 0, this.totalCols * cs.width, this.totalRows * cs.height);
      for (let r = 0;r < this.totalRows; r++) {
        for (let c = 0;c < this.totalCols; c++) {
          const cell = this.borderGrid[r][c];
          if (cell.char !== " ")
            fillCell(ctx, c, r, cell, cs);
        }
      }
      for (const region of this.regions.values()) {
        if (region.name.startsWith("_") || region.type !== "grid")
          continue;
        this._paintGridRegion(region);
      }
      for (const entry of this.pixelRenderers) {
        const region = this.regions.get(entry.regionName);
        if (!region)
          continue;
        this._paintPixelRegion(region, entry.renderer);
      }
      for (const slot of this.offscreenSlots) {
        const region = this.regions.get(slot.regionName);
        if (!region)
          continue;
        this._blitOffscreen(region, slot.canvas);
      }
      if (this.modalManager.active) {
        this.modalManager.renderInto(this.grid, this.totalCols, this.totalRows);
        for (let r = 0;r < this.totalRows; r++) {
          for (let c = 0;c < this.totalCols; c++) {
            const cell = this.grid[r][c];
            const px = c * cs.width;
            const py = r * cs.height;
            ctx.fillStyle = cell.bg || theme.colors.bg;
            ctx.fillRect(px, py, cs.width, cs.height);
            if (cell.char !== " " || cell.bg) {
              fillCell(ctx, c, r, cell, cs);
            }
          }
        }
      }
      this.allDirty = false;
      this.dirtySet.clear();
    } else if (this.modalManager.active) {
      this.allDirty = true;
      this.dirtySet.clear();
      this._paint();
      return;
    } else {
      for (const name of this.dirtySet) {
        const region = this.regions.get(name);
        if (!region || region.name.startsWith("_"))
          continue;
        const px = region.col * cs.width;
        const py = region.row * cs.height;
        const pw = region.cols * cs.width;
        const ph = region.rows * cs.height;
        ctx.fillStyle = theme.colors.bg;
        ctx.fillRect(px, py, pw, ph);
        for (let r = region.row;r < region.row + region.rows && r < this.totalRows; r++) {
          for (let c = region.col;c < region.col + region.cols && c < this.totalCols; c++) {
            const cell = this.borderGrid[r][c];
            if (cell.char !== " ")
              fillCell(ctx, c, r, cell, cs);
          }
        }
        if (region.type === "grid") {
          this._paintGridRegion(region);
        }
        const pixEntry = this.pixelRenderers.find((p) => p.regionName === name);
        if (pixEntry)
          this._paintPixelRegion(region, pixEntry.renderer);
        const offEntry = this.offscreenSlots.find((s) => s.regionName === name);
        if (offEntry)
          this._blitOffscreen(region, offEntry.canvas);
      }
      this.dirtySet.clear();
    }
  }
  _paintGridRegion(region) {
    const ctx = this.ctx;
    const cs = this.charSize;
    for (let r = 0;r < region.rows; r++) {
      for (let c = 0;c < region.cols; c++) {
        const gr = region.row + r;
        const gc = region.col + c;
        if (gr >= this.totalRows || gc >= this.totalCols)
          continue;
        const cell = this.grid[gr][gc];
        if (cell.char !== " " || cell.bg) {
          fillCell(ctx, gc, gr, cell, cs);
        }
      }
    }
  }
  _paintPixelRegion(region, renderer2) {
    const ctx = this.ctx;
    const cs = this.charSize;
    const px = region.col * cs.width;
    const py = region.row * cs.height;
    const pw = region.cols * cs.width;
    const ph = region.rows * cs.height;
    ctx.save();
    ctx.beginPath();
    ctx.rect(px, py, pw, ph);
    ctx.clip();
    renderer2(ctx, region, cs);
    ctx.restore();
  }
  _blitOffscreen(region, offscreen) {
    const ctx = this.ctx;
    const cs = this.charSize;
    const px = region.col * cs.width;
    const py = region.row * cs.height;
    const pw = region.cols * cs.width;
    const ph = region.rows * cs.height;
    ctx.drawImage(offscreen, px, py, pw, ph);
  }
  _pixelToGrid(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    return {
      col: Math.floor(x / this.charSize.width),
      row: Math.floor(y / this.charSize.height)
    };
  }
  _pointToRegion(col, row) {
    for (const region of this.regions.values()) {
      if (region.name.startsWith("_"))
        continue;
      if (col >= region.col && col < region.col + region.cols && row >= region.row && row < region.row + region.rows) {
        return region.name;
      }
    }
    return null;
  }
  _onClick(e) {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    if (hit) {
      for (const h of this.clickHandlers)
        h(hit.region, hit.data);
    }
  }
  _onMouseMove(e) {
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const hit = this.hitRegistry.hitTest(col, row);
    this.canvas.style.cursor = hit ? "pointer" : "default";
  }
  _onMouseLeave(_e) {
    this.canvas.style.cursor = "default";
  }
  _onWheel(e) {
    e.preventDefault();
    if (this.modalManager.active) {
      const delta = e.deltaY > 0 ? 3 : -3;
      this.modalManager.scroll(delta);
      return;
    }
    const { col, row } = this._pixelToGrid(e.clientX, e.clientY);
    const regionName = this._pointToRegion(col, row);
    if (regionName) {
      for (const h of this.wheelHandlers)
        h(regionName, e.deltaY);
    }
  }
}

// src/ui/dialog-renderer.ts
var MODAL_NAME = "dialog";
var CHAR_DELAY = 25;
var QUEST_CHAR_DELAY = 15;
function wordWrap(text, cols) {
  const lines = [];
  for (const paragraph of text.split(`
`)) {
    if (paragraph.length === 0) {
      lines.push("");
      continue;
    }
    const words = paragraph.split(/\s+/);
    let current = "";
    for (const word of words) {
      if (current.length === 0) {
        current = word;
      } else if (current.length + 1 + word.length <= cols) {
        current += " " + word;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current.length > 0)
      lines.push(current);
  }
  return lines;
}
function renderDialogContent(cols, npcName, npcRole, wrappedLines, visibleChars) {
  const cells = [];
  const titleText = npcRole ? `${npcName} — ${npcRole}` : npcName;
  cells.push(coloredRow([{ text: titleText, fg: theme.colors.npc, attrs: ATTR_BOLD }], cols));
  const sepLen = Math.min(titleText.length + 2, cols);
  cells.push(coloredRow([{ text: "─".repeat(sepLen), fg: theme.colors.dim }], cols));
  cells.push(emptyRow(cols));
  let charsShown = 0;
  const totalVisible = visibleChars ?? Infinity;
  for (const line of wrappedLines) {
    if (charsShown >= totalVisible && visibleChars !== undefined)
      break;
    const row = [];
    for (let i = 0;i < line.length; i++) {
      if (charsShown < totalVisible) {
        row.push({ char: line[i], fg: theme.colors.primary });
        charsShown++;
      }
    }
    while (row.length < cols) {
      row.push({ char: " ", fg: theme.colors.primary });
    }
    cells.push(row);
  }
  if (visibleChars !== undefined && charsShown < totalCharsInLines(wrappedLines)) {
    for (let r = cells.length - 1;r >= 3; r--) {
      const lastCharIdx = cells[r].findIndex((c, i) => i > 0 && cells[r][i - 1].char !== " " && c.char === " ");
      if (lastCharIdx > 0) {
        cells[r][lastCharIdx] = { char: "█", fg: theme.colors.accent };
        break;
      } else if (cells[r].some((c) => c.char !== " ")) {
        const len = cells[r].filter((c) => c.char !== " ").length;
        if (len < cols) {
          cells[r][len] = { char: "█", fg: theme.colors.accent };
        }
        break;
      }
    }
  }
  cells.push(emptyRow(cols));
  cells.push(coloredRow([{ text: "[Esc] dismiss  [click] skip", fg: theme.colors.dim }], cols));
  return { cells };
}
function totalCharsInLines(lines) {
  let total = 0;
  for (const line of lines)
    total += line.length;
  return total;
}
function renderQuestContent(cols, quest, wrappedLines, visibleChars) {
  const cells = [];
  const status = quest.completed ? " [COMPLETE]" : "";
  const titleText = `${quest.name}${status}`;
  cells.push(coloredRow([{ text: titleText, fg: theme.colors.accent, attrs: ATTR_BOLD }], cols));
  const sepLen = Math.min(titleText.length + 2, cols);
  cells.push(coloredRow([{ text: "─".repeat(sepLen), fg: theme.colors.dim }], cols));
  cells.push(emptyRow(cols));
  let charsShown = 0;
  const totalVisible = visibleChars ?? Infinity;
  for (const line of wrappedLines) {
    if (charsShown >= totalVisible && visibleChars !== undefined)
      break;
    const row = [];
    for (let i = 0;i < line.length; i++) {
      if (charsShown < totalVisible) {
        const isBarChar = line[i] === "█" || line[i] === "░";
        const fg = isBarChar ? line[i] === "█" ? theme.colors.heal : theme.colors.dim : theme.colors.primary;
        row.push({ char: line[i], fg });
        charsShown++;
      }
    }
    while (row.length < cols) {
      row.push({ char: " ", fg: theme.colors.primary });
    }
    cells.push(row);
  }
  cells.push(emptyRow(cols));
  cells.push(coloredRow([{ text: "[Esc] dismiss", fg: theme.colors.dim }], cols));
  return { cells };
}
function createDialogController(mm) {
  let _timer = null;
  let _visibleChars = 0;
  let _totalChars = 0;
  let _animating = false;
  function stopAnimation() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    _animating = false;
  }
  function skipAnimation() {
    if (!_animating)
      return;
    stopAnimation();
    _visibleChars = _totalChars;
    const modal = mm.getStack().find((m) => m.name === MODAL_NAME);
    if (modal?.renderFn) {
      mm.setContent(MODAL_NAME, modal.renderFn());
    }
  }
  function dismiss() {
    stopAnimation();
    mm.close(MODAL_NAME);
  }
  function show(npcName, npcRole, text) {
    stopAnimation();
    const state2 = mm.open(MODAL_NAME, 0.5, 0.4);
    const contentCols = state2.region.cols - 2;
    const wrappedLines = wordWrap(text, contentCols);
    _totalChars = totalCharsInLines(wrappedLines);
    _visibleChars = 0;
    _animating = true;
    const renderFn = () => renderDialogContent(contentCols, npcName, npcRole, wrappedLines, _animating ? _visibleChars : undefined);
    state2.renderFn = renderFn;
    mm.setContent(MODAL_NAME, renderFn());
    _timer = setInterval(() => {
      _visibleChars++;
      if (_visibleChars >= _totalChars) {
        stopAnimation();
      }
      mm.setContent(MODAL_NAME, renderFn());
    }, CHAR_DELAY);
  }
  function showQuest(quest) {
    stopAnimation();
    const state2 = mm.open(MODAL_NAME, 0.5, 0.4);
    const contentCols = state2.region.cols - 2;
    const lines = [];
    if (quest.giver)
      lines.push(`Quest giver: ${quest.giver}`);
    lines.push("");
    lines.push(quest.description);
    lines.push("");
    const filled = quest.totalStages > 0 ? Math.round(quest.currentStage / quest.totalStages * 10) : 0;
    const bar = "█".repeat(Math.min(10, filled)) + "░".repeat(10 - Math.min(10, filled));
    lines.push(`Progress: ${bar} ${quest.currentStage}/${quest.totalStages}`);
    const wrappedLines = wordWrap(lines.join(`
`), contentCols);
    _totalChars = totalCharsInLines(wrappedLines);
    _visibleChars = 0;
    _animating = true;
    const renderFn = () => renderQuestContent(contentCols, quest, wrappedLines, _animating ? _visibleChars : undefined);
    state2.renderFn = renderFn;
    mm.setContent(MODAL_NAME, renderFn());
    _timer = setInterval(() => {
      _visibleChars++;
      if (_visibleChars >= _totalChars) {
        stopAnimation();
      }
      mm.setContent(MODAL_NAME, renderFn());
    }, QUEST_CHAR_DELAY);
  }
  return {
    show,
    showQuest,
    dismiss,
    get active() {
      return mm.isOpen(MODAL_NAME);
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

// src/ui/inventory-renderer.ts
var MODAL_NAME2 = "inventory";
var RARITY_COLORS2 = {
  common: "#808080",
  uncommon: "#1eff00",
  rare: "#0070dd",
  epic: "#a335ee",
  legendary: "#ff8000"
};
var SLOT_ORDER2 = ["weapon", "armor", "accessory", "ring"];
var SLOT_LABELS = {
  weapon: "WPN",
  armor: "ARM",
  accessory: "ACC",
  ring: "RNG"
};
function itemColor(item) {
  return RARITY_COLORS2[item.rarity] || "#808080";
}
function renderInventoryContent(cols, rows, state2) {
  const cells = [];
  const hitRegions = [];
  const total = state2.inventory.length;
  const weight = total * 5;
  cells.push(coloredRow([
    { text: "INVENTORY", fg: theme.colors.accent, attrs: ATTR_BOLD },
    { text: `  ${weight}/50 wt · ${total} items`, fg: theme.colors.dim },
    { text: "  ", fg: theme.colors.dim },
    { text: "[×]", fg: theme.colors.damage }
  ], cols));
  const closeStart = "INVENTORY".length + `  ${weight}/50 wt · ${total} items`.length + 2;
  hitRegions.push({
    col: closeStart,
    row: 0,
    width: 3,
    height: 1,
    data: { modalAction: "close", modal: MODAL_NAME2 }
  });
  cells.push(coloredRow([{ text: "─".repeat(cols), fg: theme.colors.dim }], cols));
  const leftCols = Math.floor(cols / 2) - 1;
  const rightCols = cols - leftCols - 1;
  const leftRows = [];
  const rightRows = [];
  const leftHits = [];
  const rightHits = [];
  leftRows.push(coloredRow([{ text: "EQUIPMENT SLOTS", fg: theme.colors.dim }], leftCols));
  leftRows.push(emptyRow(leftCols));
  for (const slot of SLOT_ORDER2) {
    const label = SLOT_LABELS[slot];
    const item = state2.inventory.find((i) => i.equipped && i.slot_type === slot);
    if (item) {
      const color = itemColor(item);
      leftRows.push(coloredRow([
        { text: `${label} `, fg: theme.colors.dim },
        { text: item.name, fg: color }
      ], leftCols));
      const detailParts = [];
      if (item.effects.length) {
        detailParts.push({ text: item.effects[0], fg: theme.colors.dim });
        detailParts.push({ text: " · ", fg: theme.colors.dim });
      }
      detailParts.push({ text: item.rarity, fg: theme.colors.dim });
      detailParts.push({ text: " · ", fg: theme.colors.dim });
      detailParts.push({ text: "unequip", fg: theme.colors.damage });
      const detailRow = coloredRow(detailParts, leftCols);
      const unequipCol = detailRow.findIndex((c, i) => c.char === "u" && detailRow[i + 1]?.char === "n" && detailRow[i + 2]?.char === "e");
      if (unequipCol >= 0) {
        leftHits.push({
          col: unequipCol,
          row: leftRows.length,
          width: 7,
          height: 1,
          data: { inventoryAction: "unequip", slot }
        });
      }
      leftRows.push(detailRow);
    } else {
      leftRows.push(coloredRow([
        { text: `${label} `, fg: theme.colors.dim },
        { text: "— empty —", fg: "#3a3a48" }
      ], leftCols));
    }
    leftRows.push(emptyRow(leftCols));
  }
  const backpack = state2.inventory.filter((i) => !i.equipped);
  rightRows.push(coloredRow([{ text: `BACKPACK (${backpack.length}/10)`, fg: theme.colors.dim }], rightCols));
  rightRows.push(emptyRow(rightCols));
  if (backpack.length === 0) {
    rightRows.push(coloredRow([{ text: "Empty", fg: "#3a3a48" }], rightCols));
  } else {
    for (const item of backpack) {
      const color = itemColor(item);
      const nameParts = [
        { text: item.name, fg: color }
      ];
      if (item.quantity > 1) {
        nameParts.push({ text: ` ×${item.quantity}`, fg: theme.colors.heal });
      }
      if (item.slot_type) {
        nameParts.push({ text: ` ${item.slot_type}`, fg: theme.colors.dim });
      }
      rightRows.push(coloredRow(nameParts, rightCols));
      const actionParts = [];
      if (item.effects.length) {
        actionParts.push({ text: item.effects[0], fg: theme.colors.dim });
        actionParts.push({ text: " · ", fg: theme.colors.dim });
      }
      const actionRow = [...actionParts];
      if (item.slot_type) {
        actionRow.push({ text: "equip", fg: theme.colors.accent, action: "equip" });
        actionRow.push({ text: " · ", fg: theme.colors.dim });
      }
      if (item.is_consumable) {
        actionRow.push({ text: "use", fg: theme.colors.heal, action: "use" });
        actionRow.push({ text: " · ", fg: theme.colors.dim });
      }
      if (!item.is_quest_item) {
        actionRow.push({ text: "drop", fg: theme.colors.damage, action: "drop" });
      }
      const rowCells = coloredRow(actionRow.map((a) => ({ text: a.text, fg: a.fg })), rightCols);
      rightRows.push(rowCells);
      let offset = 0;
      for (const part of actionRow) {
        if ("action" in part && part.action) {
          rightHits.push({
            col: offset + leftCols + 1,
            row: rightRows.length - 1,
            width: part.text.length,
            height: 1,
            data: { inventoryAction: part.action, itemId: item.id, slot: item.slot_type }
          });
        }
        offset += part.text.length;
      }
      rightRows.push(emptyRow(rightCols));
    }
  }
  const groundItems = state2.location.items;
  if (groundItems.length > 0) {
    rightRows.push(coloredRow([{ text: "─".repeat(rightCols), fg: theme.colors.dim }], rightCols));
    rightRows.push(coloredRow([{ text: "GROUND (this room)", fg: theme.colors.dim }], rightCols));
    rightRows.push(emptyRow(rightCols));
    for (const gi of groundItems) {
      const row = coloredRow([
        { text: gi.name, fg: "#808080" },
        { text: " ", fg: theme.colors.dim },
        { text: "pickup", fg: theme.colors.heal }
      ], rightCols);
      rightRows.push(row);
      const pickupCol = gi.name.length + 1;
      rightHits.push({
        col: pickupCol + leftCols + 1,
        row: rightRows.length - 1,
        width: 6,
        height: 1,
        data: { inventoryAction: "pickup", itemId: gi.id }
      });
    }
  }
  const maxRows = Math.max(leftRows.length, rightRows.length);
  const dividerChar = { char: "│", fg: theme.colors.dim };
  for (let r = 0;r < maxRows; r++) {
    const left = leftRows[r] || emptyRow(leftCols);
    const right = rightRows[r] || emptyRow(rightCols);
    const combinedRow = [
      ...left.slice(0, leftCols),
      dividerChar,
      ...right.slice(0, rightCols)
    ];
    while (combinedRow.length < cols) {
      combinedRow.push({ char: " ", fg: theme.colors.primary });
    }
    cells.push(combinedRow);
  }
  const headerRowCount = 2;
  for (const h of leftHits) {
    h.row += headerRowCount;
  }
  for (const h of rightHits) {
    h.row += headerRowCount;
  }
  hitRegions.push(...leftHits, ...rightHits);
  return { cells, hitRegions };
}
function createInventoryController(mm, getState, renderAllPanels, addEvent) {
  function refresh() {
    if (!mm.isOpen(MODAL_NAME2))
      return;
    const state2 = getState();
    const modal = mm.getStack().find((m) => m.name === MODAL_NAME2);
    if (!modal)
      return;
    const contentCols = modal.region.cols - 2;
    const contentRows = modal.region.rows - 2;
    mm.setContent(MODAL_NAME2, renderInventoryContent(contentCols, contentRows, state2));
  }
  function open() {
    mm.open(MODAL_NAME2, 0.6, 0.6);
    refresh();
  }
  function close() {
    mm.close(MODAL_NAME2);
  }
  return {
    open,
    close,
    refresh,
    get active() {
      return mm.isOpen(MODAL_NAME2);
    }
  };
}
async function handleInventoryAction(data, refreshFn) {
  const action = data.inventoryAction;
  let err = null;
  switch (action) {
    case "equip":
      err = await equipItem(data.itemId, data.slot);
      break;
    case "unequip":
      err = await unequipItem(data.slot);
      break;
    case "drop":
      err = await dropItem(data.itemId);
      break;
    case "use":
      err = await useItem(data.itemId);
      break;
    case "pickup":
      err = await pickupItem(data.itemId);
      break;
  }
  if (err) {
    console.warn(`Inventory ${action} failed:`, err);
  } else {
    refreshFn();
  }
}

// src/ui/codex-renderer.ts
var MODAL_NAME3 = "codex";
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
function itemColor2(entity) {
  if (entity.rarity && RARITY_COLORS3[entity.rarity])
    return RARITY_COLORS3[entity.rarity];
  return TYPE_COLORS.item;
}
function entityColor(entity) {
  if (entity.type === "item")
    return itemColor2(entity);
  return TYPE_COLORS[entity.type] || "#c8c8d0";
}
function formatAddr(addr) {
  if (!addr || addr.length < 10 || addr === "0x0000000000000000000000000000000000000000")
    return "None";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
function wordWrap2(text, cols) {
  const lines = [];
  for (const paragraph of text.split(`
`)) {
    if (paragraph.length === 0) {
      lines.push("");
      continue;
    }
    const words = paragraph.split(/\s+/);
    let current = "";
    for (const word of words) {
      if (current.length === 0) {
        current = word;
      } else if (current.length + 1 + word.length <= cols) {
        current += " " + word;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current.length > 0)
      lines.push(current);
  }
  return lines;
}
function renderCodexContent(cols, _rows, codexData, allEntities, selectedId) {
  const cells = [];
  const hitRegions = [];
  cells.push(coloredRow([
    { text: "CODEX", fg: theme.colors.accent, attrs: ATTR_BOLD },
    { text: " ".repeat(Math.max(0, cols - 8)), fg: theme.colors.dim },
    { text: "[×]", fg: theme.colors.damage }
  ], cols));
  hitRegions.push({
    col: cols - 3,
    row: 0,
    width: 3,
    height: 1,
    data: { modalAction: "close", modal: MODAL_NAME3 }
  });
  cells.push(coloredRow([{ text: "─".repeat(cols), fg: theme.colors.dim }], cols));
  if (!codexData) {
    cells.push(coloredRow([{ text: "Loading...", fg: theme.colors.dim }], cols));
    return { cells, hitRegions };
  }
  const sidebarCols = Math.min(24, Math.floor(cols * 0.3));
  const detailCols = cols - sidebarCols - 1;
  const sidebarRows = [];
  const sidebarHits = [];
  const detailRows = [];
  const npcs = codexData.npcs || [];
  const groundItems = codexData.ground_items || [];
  const locations = codexData.locations || [];
  const currentLoc = locations.find((l) => l.current);
  const exitLocs = locations.filter((l) => !l.current);
  if (currentLoc) {
    const locText = truncate(`◉ ${currentLoc.name}`, sidebarCols);
    const isSelected = currentLoc.id === selectedId;
    sidebarRows.push(coloredRow([
      {
        text: locText,
        fg: TYPE_COLORS.location,
        attrs: isSelected ? ATTR_BOLD : undefined
      }
    ], sidebarCols));
    sidebarHits.push({
      col: 0,
      row: sidebarRows.length - 1,
      width: sidebarCols,
      height: 1,
      data: { codexSelect: currentLoc.id }
    });
    for (const npc of npcs) {
      const npcText = truncate(`  ${npc.name}`, sidebarCols);
      const sel = npc.id === selectedId;
      sidebarRows.push(coloredRow([
        {
          text: npcText,
          fg: TYPE_COLORS.npc,
          attrs: sel ? ATTR_BOLD : undefined
        }
      ], sidebarCols));
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: npc.id }
      });
    }
    for (const gi of groundItems) {
      const giText = truncate(`  ${gi.name}`, sidebarCols);
      const sel = gi.id === selectedId;
      sidebarRows.push(coloredRow([
        {
          text: giText,
          fg: itemColor2(gi),
          attrs: sel ? ATTR_BOLD : undefined
        }
      ], sidebarCols));
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: gi.id }
      });
    }
  }
  if (exitLocs.length > 0) {
    sidebarRows.push(emptyRow(sidebarCols));
    sidebarRows.push(coloredRow([{ text: "EXITS", fg: theme.colors.dim }], sidebarCols));
    for (const loc of exitLocs) {
      const label = loc.direction ? truncate(`${loc.direction} → ${loc.name}`, sidebarCols) : truncate(loc.name, sidebarCols);
      const sel = loc.id === selectedId;
      sidebarRows.push(coloredRow([
        {
          text: label,
          fg: TYPE_COLORS.location,
          attrs: sel ? ATTR_BOLD : undefined
        }
      ], sidebarCols));
      sidebarHits.push({
        col: 0,
        row: sidebarRows.length - 1,
        width: sidebarCols,
        height: 1,
        data: { codexSelect: loc.id }
      });
    }
  }
  if (codexData.player) {
    sidebarRows.push(emptyRow(sidebarCols));
    const playerText = truncate(`♣ ${codexData.player.name}`, sidebarCols);
    const sel = codexData.player.id === selectedId;
    sidebarRows.push(coloredRow([
      {
        text: playerText,
        fg: TYPE_COLORS.player,
        attrs: sel ? ATTR_BOLD : undefined
      }
    ], sidebarCols));
    sidebarHits.push({
      col: 0,
      row: sidebarRows.length - 1,
      width: sidebarCols,
      height: 1,
      data: { codexSelect: codexData.player.id }
    });
  }
  const selected = allEntities.find((e) => e.id === selectedId);
  if (selected) {
    renderEntityDetail(detailRows, selected, detailCols, codexData, allEntities, sidebarCols);
  } else {
    detailRows.push(coloredRow([{ text: "No entities to display", fg: theme.colors.dim }], detailCols));
  }
  const maxRows = Math.max(sidebarRows.length, detailRows.length);
  const dividerChar = { char: "│", fg: theme.colors.dim };
  for (let r = 0;r < maxRows; r++) {
    const left = sidebarRows[r] || emptyRow(sidebarCols);
    const right = detailRows[r] || emptyRow(detailCols);
    const combinedRow = [
      ...left.slice(0, sidebarCols),
      dividerChar,
      ...right.slice(0, detailCols)
    ];
    while (combinedRow.length < cols) {
      combinedRow.push({ char: " ", fg: theme.colors.primary });
    }
    cells.push(combinedRow);
  }
  const headerRowCount = 2;
  for (const h of sidebarHits) {
    h.row += headerRowCount;
  }
  hitRegions.push(...sidebarHits);
  return { cells, hitRegions };
}
function renderEntityDetail(rows, entity, cols, codexData, allEntities, _sidebarCols) {
  const attrs = entity.attributes || {};
  rows.push(coloredRow([{ text: entity.name, fg: entityColor(entity), attrs: ATTR_BOLD }], cols));
  if (entity.labels.length) {
    rows.push(coloredRow([{ text: entity.labels.join(" · "), fg: theme.colors.dim }], cols));
  }
  rows.push(emptyRow(cols));
  let summaryText = entity.summary || "";
  if (summaryText.startsWith("{")) {
    summaryText = attrs.description || attrs.personality || "";
  }
  if (!summaryText && attrs.description) {
    summaryText = attrs.description;
  }
  if (summaryText) {
    const wrapped = wordWrap2(summaryText, cols);
    for (const line of wrapped) {
      rows.push(textRow(line, theme.colors.primary, cols));
    }
    rows.push(emptyRow(cols));
  }
  const asciiArt = attrs.ascii_art;
  if (asciiArt) {
    const artLines = asciiArt.split(`
`).slice(0, 8);
    for (const line of artLines) {
      rows.push(coloredRow([{ text: truncate(line, cols), fg: entityColor(entity) }], cols));
    }
    if (asciiArt.split(`
`).length > 8) {
      rows.push(coloredRow([{ text: "  ... (truncated)", fg: theme.colors.dim }], cols));
    }
    rows.push(emptyRow(cols));
  } else if (entity.type !== "player") {
    rows.push(coloredRow([{ text: "[ art pending ]", fg: "#3a3a48" }], cols));
    rows.push(emptyRow(cols));
  }
  if (entity.type === "npc") {
    if (attrs.personality)
      addSection(rows, cols, "PERSONALITY", attrs.personality);
    if (attrs.backstory)
      addSection(rows, cols, "BACKSTORY", attrs.backstory);
    if (attrs.stats && typeof attrs.stats === "object") {
      const statsText = Object.entries(attrs.stats).map(([k, v]) => `${k} ${v}`).join(" · ");
      addSection(rows, cols, "STATS", statsText);
    }
    if (attrs.skills && typeof attrs.skills === "object") {
      const skillsText = Object.entries(attrs.skills).map(([k, v]) => `${k}: ${v}`).join(", ");
      addSection(rows, cols, "SKILLS", skillsText);
    }
    if (Array.isArray(attrs.abilities) && attrs.abilities.length) {
      rows.push(coloredRow([{ text: "ABILITIES", fg: theme.colors.dim }], cols));
      for (const ab of attrs.abilities) {
        rows.push(coloredRow([
          { text: ab.name, fg: theme.colors.accent },
          { text: ` — ${ab.description}`, fg: theme.colors.dim }
        ], cols));
      }
      rows.push(emptyRow(cols));
    }
    if (Array.isArray(attrs.traits) && attrs.traits.length) {
      addSection(rows, cols, "TRAITS", attrs.traits.join(", "));
    }
    if (attrs.disposition)
      addSection(rows, cols, "DISPOSITION", attrs.disposition);
    if (attrs.motivation)
      addSection(rows, cols, "MOTIVATION", attrs.motivation);
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
      addSection(rows, cols, "MECHANICS", parts.join(" · "));
    if (attrs.lore)
      addSection(rows, cols, "LORE", attrs.lore);
    if (Array.isArray(attrs.effects) && attrs.effects.length) {
      addSection(rows, cols, "EFFECTS", attrs.effects.join(", "));
    }
  }
  if (entity.type === "location") {
    if (attrs.biome)
      addSection(rows, cols, "BIOME", attrs.biome);
    if (attrs.atmosphere)
      addSection(rows, cols, "ATMOSPHERE", attrs.atmosphere);
    if (attrs.culture)
      addSection(rows, cols, "CULTURE", attrs.culture);
    if (Array.isArray(attrs.threats) && attrs.threats.length) {
      addSection(rows, cols, "THREATS", attrs.threats.join(", "));
    }
    if (attrs.danger_level) {
      const dl = attrs.danger_level;
      const skulls = "☠".repeat(Math.min(dl, 5));
      addSection(rows, cols, "DANGER", `${skulls} (${dl}/10)`);
    }
    if (attrs.lore)
      addSection(rows, cols, "LORE", attrs.lore);
  }
  if (entity.type === "player" && codexData.player) {
    const p = codexData.player;
    rows.push(coloredRow([{ text: "STATS", fg: theme.colors.dim }], cols));
    rows.push(coloredRow([
      { text: "Level: ", fg: theme.colors.dim },
      { text: String(p.level || 1), fg: theme.colors.primary }
    ], cols));
    rows.push(coloredRow([
      { text: "Health: ", fg: theme.colors.dim },
      { text: String(p.health || 100), fg: theme.colors.heal }
    ], cols));
    rows.push(coloredRow([
      { text: "Archetype: ", fg: theme.colors.dim },
      { text: p.archetype || "Unknown", fg: theme.colors.accent }
    ], cols));
    rows.push(emptyRow(cols));
  }
  if (entity.type === "location" && entity.exits) {
    rows.push(coloredRow([{ text: "EXITS", fg: theme.colors.dim }], cols));
    for (const ex of entity.exits) {
      rows.push(coloredRow([
        { text: ex.direction || "?", fg: theme.colors.accent },
        { text: " → ", fg: theme.colors.dim },
        { text: ex.target || "?", fg: TYPE_COLORS.location }
      ], cols));
    }
    rows.push(emptyRow(cols));
    if (entity.current) {
      rows.push(coloredRow([{ text: "PRESENT", fg: theme.colors.dim }], cols));
      if (codexData.player) {
        rows.push(coloredRow([{ text: `♣ ${codexData.player.name} (you)`, fg: TYPE_COLORS.player }], cols));
      }
      for (const npc of codexData.npcs || []) {
        rows.push(coloredRow([{ text: `● ${npc.name}`, fg: TYPE_COLORS.npc }], cols));
      }
      for (const item of codexData.ground_items || []) {
        rows.push(coloredRow([{ text: `• ${item.name}`, fg: itemColor2(item) }], cols));
      }
      rows.push(emptyRow(cols));
    }
  }
  if (entity.relationships?.length) {
    rows.push(coloredRow([{ text: "CONNECTIONS", fg: theme.colors.dim }], cols));
    for (const rel of entity.relationships) {
      const relType = rel.relationship.replace(/_/g, " ");
      const other = rel.source === entity.name ? rel.target : rel.source;
      rows.push(coloredRow([
        { text: relType + " ", fg: theme.colors.dim },
        { text: other, fg: TYPE_COLORS.location, attrs: ATTR_UNDERLINE }
      ], cols));
      if (rel.fact) {
        const factText = rel.fact.length > 80 ? rel.fact.slice(0, 80) + "…" : rel.fact;
        const wrapped = wordWrap2(`  ${factText}`, cols);
        for (const line of wrapped) {
          rows.push(textRow(line, theme.colors.dim, cols));
        }
      }
    }
    rows.push(emptyRow(cols));
  }
  if (entity.chain_data) {
    const chain = entity.chain_data;
    rows.push(coloredRow([{ text: "ONCHAIN", fg: theme.colors.heal }], cols));
    if (entity.type === "npc" || entity.type === "player") {
      if (chain.level != null)
        addChainRow(rows, cols, "Level", String(chain.level));
      if (chain.alive != null)
        addChainRow(rows, cols, "Status", chain.alive ? "Alive" : "Dead");
      if (chain.wallet)
        addChainRow(rows, cols, "Wallet", formatAddr(chain.wallet));
    } else if (entity.type === "item") {
      if (chain.rarity)
        addChainRow(rows, cols, "Rarity", String(chain.rarity));
      if (chain.ownerId)
        addChainRow(rows, cols, "Owner", formatAddr(chain.ownerId));
      if (chain.locationId)
        addChainRow(rows, cols, "Location", formatAddr(chain.locationId));
    }
    rows.push(emptyRow(cols));
  }
}
function addSection(rows, cols, label, text) {
  rows.push(coloredRow([{ text: label, fg: theme.colors.dim }], cols));
  const wrapped = wordWrap2(text, cols);
  for (const line of wrapped) {
    rows.push(textRow(line, theme.colors.primary, cols));
  }
  rows.push(emptyRow(cols));
}
function addChainRow(rows, cols, label, value) {
  rows.push(coloredRow([
    { text: `${label.padEnd(10)}`, fg: theme.colors.dim },
    { text: value, fg: theme.colors.primary }
  ], cols));
}
function truncate(s, maxLen) {
  if (s.length <= maxLen)
    return s;
  return s.slice(0, maxLen - 1) + "…";
}
function createCodexController(mm, getState, playerId) {
  let _codexData = null;
  let _selectedId = null;
  let _allEntities = [];
  function render() {
    if (!mm.isOpen(MODAL_NAME3))
      return;
    const modal = mm.getStack().find((m) => m.name === MODAL_NAME3);
    if (!modal)
      return;
    const contentCols = modal.region.cols - 2;
    const contentRows = modal.region.rows - 2;
    mm.setContent(MODAL_NAME3, renderCodexContent(contentCols, contentRows, _codexData, _allEntities, _selectedId));
  }
  async function open(entityId) {
    mm.open(MODAL_NAME3, 0.7, 0.7);
    const modal = mm.getStack().find((m) => m.name === MODAL_NAME3);
    if (modal) {
      const contentCols = modal.region.cols - 2;
      mm.setContent(MODAL_NAME3, {
        cells: [
          coloredRow([{ text: "Loading...", fg: theme.colors.dim }], contentCols)
        ]
      });
    }
    try {
      const pid = playerId();
      const state2 = getState();
      const locId = state2?.roomMap?.id || "";
      const url = locId ? `${GATEWAY_URL}/api/codex/${pid}?location_uuid=${locId}` : `${GATEWAY_URL}/api/codex/${pid}`;
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
          _allEntities.push({
            ...loc,
            type: "location",
            labels: loc.labels || ["Location"]
          });
        }
      }
      if (_codexData.player && !seen.has(_codexData.player.id)) {
        seen.add(_codexData.player.id);
        _allEntities.push({
          id: _codexData.player.id,
          name: _codexData.player.name,
          type: "player",
          labels: [_codexData.player.archetype || "Player"],
          summary: ""
        });
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
    }
    render();
  }
  function close() {
    mm.close(MODAL_NAME3);
  }
  function refreshEntityArt(entityId, lines) {
    const artText = lines.join(`
`);
    const entity = _allEntities.find((e) => e.id === entityId);
    if (entity) {
      if (!entity.attributes)
        entity.attributes = {};
      entity.attributes.ascii_art = artText;
      if (_selectedId === entityId && mm.isOpen(MODAL_NAME3)) {
        render();
      }
    }
  }
  function handleSelect(entityId) {
    _selectedId = entityId;
    const modal = mm.getStack().find((m) => m.name === MODAL_NAME3);
    if (modal)
      modal.scrollOffset = 0;
    render();
  }
  return {
    open,
    close,
    refreshEntityArt,
    selectEntity: handleSelect,
    get active() {
      return mm.isOpen(MODAL_NAME3);
    }
  };
}

// src/ui/art-viewer.ts
function createArtViewer() {
  const backdrop = document.createElement("div");
  backdrop.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.85);" + "display:none;align-items:center;justify-content:center;z-index:200;" + "flex-direction:column;cursor:pointer;";
  const container = document.createElement("div");
  container.style.cssText = "display:flex;flex-direction:column;align-items:center;" + "max-width:90vw;max-height:90vh;";
  const title = document.createElement("div");
  title.style.cssText = "font-size:14px;letter-spacing:2px;margin-bottom:12px;text-align:center;";
  const pre = document.createElement("pre");
  pre.style.cssText = 'font-family:"Fira Code",Consolas,"Courier New",monospace;' + "font-size:15px;line-height:1.2;margin:0;padding:16px;" + "border-radius:3px;white-space:pre;overflow:auto;" + "max-height:80vh;";
  const hint = document.createElement("div");
  hint.style.cssText = "color:#4a4a58;font-size:11px;margin-top:12px;text-align:center;";
  hint.textContent = "[ESC] or click to close";
  container.appendChild(title);
  container.appendChild(pre);
  container.appendChild(hint);
  backdrop.appendChild(container);
  function close() {
    backdrop.style.display = "none";
    pre.textContent = "";
  }
  backdrop.addEventListener("click", close);
  container.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && backdrop.style.display !== "none") {
      e.stopImmediatePropagation();
      e.preventDefault();
      close();
    }
  }, true);
  return {
    el: backdrop,
    open(entityName, artText, color) {
      title.textContent = `─ ${entityName} ─`;
      title.style.color = color;
      pre.textContent = artText;
      pre.style.color = color;
      pre.style.border = `1px solid ${color}33`;
      backdrop.style.display = "flex";
    },
    close,
    get active() {
      return backdrop.style.display !== "none";
    }
  };
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

// src/hotkeys.ts
function initHotkeys(refs) {
  document.addEventListener("keydown", (e) => {
    if (document.activeElement?.tagName === "INPUT")
      return;
    switch (e.key) {
      case "i":
        if (refs.invModal.active)
          refs.invModal.close();
        else
          refs.invModal.open();
        break;
      case "k":
        if (refs.codex.active)
          refs.codex.close();
        else
          refs.codex.open();
        break;
      case "Escape":
        if (refs.modalManager.active) {
          refs.modalManager.closeTopmost();
        }
        break;
    }
  });
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

// src/char-creation.ts
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
function showCharacterPicker(characters, walletAddress, overlays, enterGame) {
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
function initCharCreation(enterGame, overlays) {
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
          showCharacterPicker(charData.characters, addr, overlays, enterGame);
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
}

// src/app.ts
var gameState;
var narrative;
var eventsFeed;
var uc;
var npcDialog;
var codex;
var artViewer;
var invModal;
var overlays;
var headerState = { title: "MEMENTO MORI", worldTime: undefined };
var statusState = { phase: "ready", tick: 0, chain: false, activity: "", location: "" };
var currentCard = null;
var currentScene = null;
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
async function fetchPlayerWorldMap() {
  try {
    const pid = getSession().playerId;
    if (!pid || !gameState)
      return;
    const resp = await fetch(`${GATEWAY_URL}/api/worldmap/${pid}`);
    if (resp.ok) {
      gameState.worldMap = await resp.json();
      renderAllPanels();
    }
  } catch {}
}
function renderAllPanels() {
  if (!uc)
    return;
  const r = (name) => uc.getRegion(name);
  const headerRegion = r("header");
  if (headerRegion) {
    uc.setRegionContent("header", renderHeader(headerRegion.cols, headerState));
  }
  const statusRegion = r("status");
  if (statusRegion) {
    uc.setRegionContent("status", renderStatusBar(statusRegion.cols, statusState));
  }
  if (!gameState)
    return;
  const charRegion = r("character");
  if (charRegion) {
    uc.setRegionContent("character", renderCharacterPanel(charRegion.cols, charRegion.rows, gameState));
  }
  const invRegion = r("inventory");
  if (invRegion) {
    uc.setRegionContent("inventory", renderInventoryPanel(invRegion.cols, invRegion.rows, gameState));
  }
  const questRegion = r("quests");
  if (questRegion) {
    uc.setRegionContent("quests", renderQuestLogPanel(questRegion.cols, questRegion.rows, gameState.quests));
  }
  const presentRegion = r("present");
  if (presentRegion) {
    uc.setRegionContent("present", renderPresentPanel(presentRegion.cols, presentRegion.rows, gameState));
  }
  const vpRegion = r("viewport");
  if (vpRegion) {
    uc.setRegionContent("viewport", renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }
  updateMap(gameState, handleAction);
  const mapCanvas = getMapCanvas();
  if (mapCanvas && mapCanvas.width > 0) {
    uc.setOffscreen("viewport", mapCanvas);
  }
}
async function handleAction(action) {
  if (!action.trim() || action.length > 500)
    return;
  const phase = getRoundState().phase;
  if (phase !== "ready" && phase !== "collecting")
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
function setViewportCard(card) {
  currentCard = card;
  currentScene = null;
  const vpRegion = uc?.getRegion("viewport");
  if (vpRegion) {
    uc.setRegionContent("viewport", renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }
}
function setViewportScene(lines) {
  currentScene = lines;
  currentCard = null;
  const vpRegion = uc?.getRegion("viewport");
  if (vpRegion) {
    uc.setRegionContent("viewport", renderViewport(vpRegion.cols, vpRegion.rows, currentCard, currentScene));
  }
}
function enterGame(config) {
  startGame({ ...config }, overlays, {
    onGameReady(state2, openingNarrative) {
      gameState = state2;
      const session2 = getSession();
      window.__mmPlayerId = session2.playerId;
      initInventoryApi(gameState, session2.playerId, renderAllPanels, (text, style) => {
        eventsFeed.addBlock(text, style);
      });
      if (gameState.roomMap)
        registerMapEntities(gameState.roomMap);
      renderAllPanels();
      fetchPlayerWorldMap();
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
function positionActionInput(inputEl) {
  const inputRegion = uc.getRegion("input");
  if (!inputRegion)
    return;
  const cs = uc.getCharSize();
  const canvasRect = uc.canvas.getBoundingClientRect();
  const appRect = uc.canvas.parentElement.getBoundingClientRect();
  const offsetX = canvasRect.left - appRect.left;
  const offsetY = canvasRect.top - appRect.top;
  const promptCols = 2;
  inputEl.style.left = `${offsetX + (inputRegion.col + promptCols) * cs.width}px`;
  inputEl.style.top = `${offsetY + inputRegion.row * cs.height}px`;
  inputEl.style.width = `${(inputRegion.cols - promptCols) * cs.width}px`;
  inputEl.style.height = `${cs.height}px`;
  inputEl.style.fontSize = `${cs.height - 2}px`;
}
document.addEventListener("DOMContentLoaded", () => {
  const tuiMain = document.getElementById("tui-main");
  uc = new UnifiedCanvas(tuiMain);
  const narrativeContainer = document.createElement("div");
  narrativeContainer.style.position = "absolute";
  narrativeContainer.style.left = "-9999px";
  document.body.appendChild(narrativeContainer);
  const eventsContainer = document.createElement("div");
  eventsContainer.style.position = "absolute";
  eventsContainer.style.left = "-9999px";
  document.body.appendChild(eventsContainer);
  function sizeNarrativeContainers() {
    const cs = uc.getCharSize();
    const narRegion = uc.getRegion("narrative");
    if (narRegion) {
      narrativeContainer.style.width = `${narRegion.cols * cs.width}px`;
      narrativeContainer.style.height = `${narRegion.rows * cs.height}px`;
    }
    const evtRegion = uc.getRegion("events");
    if (evtRegion) {
      eventsContainer.style.width = `${evtRegion.cols * cs.width}px`;
      eventsContainer.style.height = `${evtRegion.rows * cs.height}px`;
    }
  }
  sizeNarrativeContainers();
  narrative = initNarrative(narrativeContainer);
  eventsFeed = initNarrative(eventsContainer);
  uc.setPixelRenderer("narrative", (ctx, region, charSize) => {
    const px = region.col * charSize.width;
    const py = region.row * charSize.height;
    const pw = region.cols * charSize.width;
    const ph = region.rows * charSize.height;
    ctx.drawImage(narrative.canvas, 0, 0, narrative.canvas.width, narrative.canvas.height, px, py, pw, ph);
  });
  uc.setPixelRenderer("events", (ctx, region, charSize) => {
    const px = region.col * charSize.width;
    const py = region.row * charSize.height;
    const pw = region.cols * charSize.width;
    const ph = region.rows * charSize.height;
    ctx.drawImage(eventsFeed.canvas, 0, 0, eventsFeed.canvas.width, eventsFeed.canvas.height, px, py, pw, ph);
  });
  uc.onWheel((region, deltaY) => {
    if (region === "narrative") {
      narrative.scroll(deltaY);
      uc.markDirty("narrative");
    }
    if (region === "events") {
      eventsFeed.scroll(deltaY);
      uc.markDirty("events");
    }
  });
  uc.onClick((region, data) => {
    if (data.modalAction === "close") {
      const modal = data.modal;
      if (modal === "inventory")
        invModal.close();
      else if (modal === "codex")
        codex.close();
      else if (modal === "dialog")
        npcDialog.dismiss();
      return;
    }
    if (data.inventoryAction) {
      handleInventoryAction(data, () => invModal.refresh()).catch(console.error);
      return;
    }
    if (data.codexSelect) {
      codex.selectEntity(data.codexSelect);
      return;
    }
    if (data.action)
      handleAction(data.action);
    if (data.questName) {
      const quest = gameState?.quests.find((q) => q.name === data.questName);
      if (quest)
        npcDialog.showQuest(quest);
    }
    if (data.entityId)
      codex.open(data.entityId);
    if (data.npcName) {
      const lastMsg = getLastNpcMessage(data.npcName);
      if (lastMsg)
        npcDialog.show(data.npcName, "", lastMsg);
    }
  });
  setViewportCallback(setViewportCard);
  const mapContainer = document.createElement("div");
  mapContainer.style.position = "absolute";
  mapContainer.style.left = "-9999px";
  mapContainer.style.width = "400px";
  mapContainer.style.height = "300px";
  document.body.appendChild(mapContainer);
  initMapPanel(mapContainer, handleAction);
  const actionInput = document.getElementById("action-input");
  initInput(actionInput, handleAction, () => ({
    npcs: gameState?.location?.npcs || [],
    players: gameState?.location?.players || []
  }));
  positionActionInput(actionInput);
  const resizeObserver = new ResizeObserver(() => {
    sizeNarrativeContainers();
    positionActionInput(actionInput);
  });
  resizeObserver.observe(tuiMain);
  function renderInputPrompt() {
    const inputRegion = uc.getRegion("input");
    if (!inputRegion)
      return;
    const cells = [[
      { char: ">", fg: "#6a6a78" },
      { char: " ", fg: "#6a6a78" }
    ]];
    while (cells[0].length < inputRegion.cols) {
      cells[0].push({ char: " ", fg: "#6a6a78" });
    }
    uc.setRegionContent("input", { cells });
  }
  renderInputPrompt();
  setInterval(() => {
    uc.markDirty("narrative");
    uc.markDirty("events");
  }, 100);
  overlays = createOverlayManager(["char-create", "death", "loading", "intro"]);
  const mm = uc.modalManager;
  npcDialog = createDialogController(mm);
  invModal = createInventoryController(mm, () => gameState, renderAllPanels, (text, style) => {
    eventsFeed.addBlock(text, style);
  });
  setManageInventoryCallback(() => invModal.open());
  artViewer = createArtViewer();
  document.body.appendChild(artViewer.el);
  codex = createCodexController(mm, () => gameState, () => getSession().playerId);
  initHotkeys({ invModal, codex, npcDialog, modalManager: mm });
  const handleMessage = createMessageHandler({
    getGameState: () => gameState,
    narrative,
    eventsFeed,
    renderAllPanels,
    header: {
      updateTime(t) {
        headerState.worldTime = t;
        const headerRegion = uc.getRegion("header");
        if (headerRegion) {
          uc.setRegionContent("header", renderHeader(headerRegion.cols, headerState));
        }
      }
    },
    statusBar: {
      setTick(t) {
        statusState.tick = t;
        const region = uc.getRegion("status");
        if (region)
          uc.setRegionContent("status", renderStatusBar(region.cols, statusState));
      },
      setChain(c) {
        statusState.chain = c;
        const region = uc.getRegion("status");
        if (region)
          uc.setRegionContent("status", renderStatusBar(region.cols, statusState));
      },
      setActivity(a) {
        statusState.activity = a;
        const region = uc.getRegion("status");
        if (region)
          uc.setRegionContent("status", renderStatusBar(region.cols, statusState));
      }
    },
    codex,
    invModal,
    handleAction,
    registerMapEntities,
    fetchPlayerWorldMap,
    showDeathScreen,
    setViewportScene
  });
  setMessageHandler(handleMessage);
  setConnectionHandler((connected) => {
    if (connected) {
      narrative.addBlock("Reconnected.", "system");
    } else {
      narrative.addBlock("Connection lost. Reconnecting...", "system");
    }
  });
  setErrorHandler((msg) => eventsFeed.addBlock(msg, "error"));
  document.getElementById("death-restart-btn").addEventListener("click", () => {
    overlays.dismiss("death");
    overlays.show("char-create");
    narrativeContainer.innerHTML = "";
    narrative = initNarrative(narrativeContainer);
    uc.setPixelRenderer("narrative", (ctx, region, charSize) => {
      const px = region.col * charSize.width;
      const py = region.row * charSize.height;
      const pw = region.cols * charSize.width;
      const ph = region.rows * charSize.height;
      ctx.drawImage(narrative.canvas, 0, 0, narrative.canvas.width, narrative.canvas.height, px, py, pw, ph);
    });
    initHotkeys({ invModal, codex, npcDialog, modalManager: mm });
    document.getElementById("char-name-input").focus();
  });
  initCharCreation(enterGame, overlays);
  renderAllPanels();
});
