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
    inventory: []
  };
}
function renderState(state) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el)
      el.textContent = text;
  };
  set("char-name", state.player.name);
  set("char-level", String(state.player.level));
  set("char-health", `${state.player.health}/${state.player.maxHealth}`);
  set("char-xp", `${state.player.xp}/${state.player.xpThreshold}`);
  set("location-name", state.location.name);
  const fill = document.getElementById("health-fill");
  if (fill) {
    const pct = Math.max(0, Math.min(100, state.player.health / state.player.maxHealth * 100));
    fill.style.width = `${pct}%`;
  }
  const exitsEl = document.getElementById("location-exits");
  if (exitsEl) {
    exitsEl.textContent = state.location.exits.length ? `Exits: ${state.location.exits.join(", ")}` : "";
  }
  const invEl = document.getElementById("inventory-list");
  if (invEl) {
    if (state.inventory.length === 0) {
      invEl.innerHTML = '<div class="inventory-item" style="color: var(--text-dim);">Empty</div>';
    } else {
      invEl.innerHTML = state.inventory.map((item) => `<div class="inventory-item">${item.name} <span style="color: var(--text-dim);">[${item.rarity}]</span></div>`).join("");
    }
  }
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

// src/app.ts
var GATEWAY_URL = "http://localhost:8080";
var WS_URL = "ws://localhost:8080/ws";
var playerId = "";
var sessionId = "";
var currentLocation = "";
var ws = null;
var gameState;
var commandHistory = [];
var historyIndex = -1;
var narrativePane = document.getElementById("narrative-pane");
var actionInput = document.getElementById("action-input");
async function createSession(playerName) {
  const resp = await fetch(`${GATEWAY_URL}/api/session/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName })
  });
  const data = await resp.json();
  playerId = data.player_id;
  sessionId = data.session_id;
  currentLocation = data.location;
  document.getElementById("char-name").textContent = playerName;
  document.getElementById("location-name").textContent = currentLocation;
  gameState = createInitialState(playerName);
  gameState.location.name = currentLocation;
  renderState(gameState);
  connectWebSocket();
  addNarrative(`Welcome, ${playerName}. You find yourself at ${currentLocation}.`, "system");
  if (data.opening_narrative) {
    addNarrative(data.opening_narrative, "narrative");
  }
}
function connectWebSocket() {
  ws = new WebSocket(`${WS_URL}/${playerId}`);
  ws.onopen = () => {
    addNarrative("Connected.", "system");
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };
  ws.onclose = () => {
    addNarrative("Connection lost. Refresh to reconnect.", "system");
  };
}
function handleMessage(msg) {
  switch (msg.type) {
    case "narrative": {
      const thinking = narrativePane.querySelector(".thinking");
      if (thinking)
        thinking.remove();
      const segments = parseNarrative(msg.text || "");
      const html = renderSegments(segments);
      addNarrativeHtml(html, "narrative");
      const stateUpdate = msg.state_update;
      if (stateUpdate && gameState) {
        if (stateUpdate.location) {
          gameState.location.name = stateUpdate.location;
          currentLocation = stateUpdate.location;
        }
        renderState(gameState);
      }
      break;
    }
    case "thinking":
      addNarrative("The world responds", "thinking");
      break;
    default:
      console.log("Unknown message:", msg);
  }
}
function addNarrativeHtml(html, type) {
  const block = document.createElement("div");
  block.className = `narrative-block ${type}`;
  block.innerHTML = html;
  narrativePane.appendChild(block);
  narrativePane.scrollTop = narrativePane.scrollHeight;
}
function addNarrative(text, type) {
  const block = document.createElement("div");
  block.className = `narrative-block ${type}`;
  if (type === "thinking") {
    block.className = "narrative-block thinking";
  }
  const html = text.replace(/\n/g, "<br>").replace(/"([^"]+)"/g, '<span class="npc-name">"$1"</span>');
  block.innerHTML = html;
  narrativePane.appendChild(block);
  narrativePane.scrollTop = narrativePane.scrollHeight;
}
async function submitAction(action) {
  if (!action.trim())
    return;
  addNarrative(`> ${action}`, "player-action");
  commandHistory.unshift(action);
  historyIndex = -1;
  await fetch(`${GATEWAY_URL}/api/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      player_id: playerId,
      action,
      location: currentLocation
    })
  });
}
window.submitAction = submitAction;
actionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const action = actionInput.value.trim();
    if (action) {
      submitAction(action);
      actionInput.value = "";
    }
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (historyIndex < commandHistory.length - 1) {
      historyIndex++;
      actionInput.value = commandHistory[historyIndex];
    }
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    if (historyIndex > 0) {
      historyIndex--;
      actionInput.value = commandHistory[historyIndex];
    } else {
      historyIndex = -1;
      actionInput.value = "";
    }
  }
});
var urlParams = new URLSearchParams(window.location.search);
var playerName = urlParams.get("name") || "Wanderer";
createSession(playerName);
