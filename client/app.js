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
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (onMessage)
      onMessage(msg);
  };
  ws.onclose = () => {
    session.connected = false;
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

// src/panels/narrative.ts
function initNarrative(container) {
  return {
    addBlock(text, type) {
      const block = document.createElement("div");
      block.className = `narrative-block ${type}`;
      if (type === "thinking") {
        block.textContent = "The world responds";
      } else if (type === "player-action") {
        block.innerHTML = text.replace(/\n/g, "<br>");
      } else {
        const segments = parseNarrative(text);
        block.innerHTML = renderSegments(segments);
      }
      container.appendChild(block);
      container.scrollTop = container.scrollHeight;
    },
    addHtml(html, type) {
      const block = document.createElement("div");
      block.className = `narrative-block ${type}`;
      block.innerHTML = html;
      container.appendChild(block);
      container.scrollTop = container.scrollHeight;
    },
    showThinking() {
      this.addBlock("The world responds", "thinking");
    },
    removeThinking() {
      const el = container.querySelector(".thinking");
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
function renderCharacterPanel(container, state) {
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

// src/panels/map.ts
function renderLocationPanel(container, state, onAction) {
  let html = `<div id="location-name" style="color: var(--text-location); margin-bottom: 8px; font-size: 15px;">${state.location.name}</div>`;
  if (state.location.exits.length) {
    html += '<div id="location-exits" style="margin-bottom: 8px;">';
    state.location.exits.forEach((exit) => {
      html += `<button class="action-btn" data-action="go ${exit}">Go ${exit}</button>`;
    });
    html += "</div>";
  } else {
    html += '<div id="location-exits" style="font-size: 13px; color: var(--text-dim); font-family: system-ui, sans-serif;"></div>';
  }
  if (state.location.npcs.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Present:</span></div>';
    state.location.npcs.forEach((npc) => {
      html += `<div style="font-size: 13px; color: var(--text-npc); padding: 2px 0;">${npc}</div>`;
    });
  }
  if (state.location.items.length) {
    html += '<div style="margin-top: 8px;"><span class="stat-label">Visible:</span></div>';
    state.location.items.forEach((item) => {
      html += `<div style="font-size: 13px; color: var(--text-primary); padding: 2px 0;">${item}</div>`;
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
}
async function handleAction(action) {
  if (!action.trim())
    return;
  narrative.addBlock(`> ${action}`, "player-action");
  await sendAction(action);
}
function handleMessage(msg) {
  switch (msg.type) {
    case "narrative": {
      narrative.removeThinking();
      const segments = parseNarrative(msg.text || "");
      const html = renderSegments(segments);
      narrative.addHtml(html, "narrative");
      if (msg.state_update && gameState) {
        const u = msg.state_update;
        if (u.location) {
          gameState.location.name = u.location;
          const session2 = getSession();
          session2.currentLocation = u.location;
        }
        renderAllPanels();
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
  const actionInput = document.getElementById("action-input");
  initInput(actionInput, handleAction);
  setMessageHandler(handleMessage);
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
