const $ = (sel) => document.querySelector(sel);
const eraInfo = $("#era-info");
const introEl = $("#intro");
const turnsEl = $("#turns");
const input = $("#player-input");
const btn = $("#submit-btn");

let state = null;

async function loadState() {
  try {
    const res = await fetch("/api/state");
    state = await res.json();
    renderIntro();
  } catch {
    introEl.innerHTML =
      '<p class="error-text">Could not connect to the server. Is it running?</p>';
  }
}

function renderIntro() {
  eraInfo.textContent = `${state.era.name} \u2014 ${state.era.year} AD \u00b7 ${state.location.name}`;

  let h = `<p>${esc(state.era.description)}</p>`;
  h += `<p>You are <strong>${esc(state.player.name)}</strong>, ${esc(
    state.player.role.toLowerCase()
  )}. ${esc(state.player.description)}</p>`;

  h += "<p>Nearby:</p><ul>";
  for (const npc of state.npcs) {
    h += `<li><strong>${esc(npc.name)}</strong> \u2014 ${esc(npc.role)}</li>`;
  }
  h += "</ul>";

  h += tensionHtml(state.location.political_tension);

  introEl.innerHTML = h;
  input.disabled = false;
  btn.disabled = false;
  input.focus();
}

async function submitTurn() {
  const text = input.value.trim();
  if (!text) return;

  input.disabled = true;
  btn.disabled = true;
  input.value = "";

  const block = document.createElement("div");
  block.className = "turn-block";
  block.innerHTML = `
    <div class="turn-label">Turn ${(state?.turn || 0) + 1}</div>
    <div class="player-line">\u00bb ${esc(text)}</div>
    <div class="loading-text">The world turns\u2026</div>
  `;
  turnsEl.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch("/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: text }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    state = data.world_state;
    renderTurn(block, text, data);
  } catch (e) {
    block.querySelector(".loading-text").innerHTML =
      `<span class="error-text">Error: ${esc(e.message)}</span>`;
  } finally {
    input.disabled = false;
    btn.disabled = false;
    input.focus();
  }
}

function renderTurn(el, playerText, data) {
  const { parsed_action: pa, npc_responses, world_state: ws } = data;

  let h = `<div class="turn-label">Turn ${ws.turn}</div>`;
  h += `<div class="player-line">\u00bb ${esc(playerText)}</div>`;

  if (pa.era_description) {
    h += `<div class="action-narration">${esc(pa.era_description)}</div>`;
  }

  h += `<span class="parsed-badge">${esc(pa.action_type)}${
    pa.target ? " \u2192 " + esc(pa.target) : ""
  }</span>`;

  for (const r of npc_responses) {
    h += `<div class="npc-block">`;
    h += `<div class="npc-label">${esc(r.npc_name)}</div>`;
    h += `<div class="npc-voice">${esc(r.pov)}</div>`;
    h += `</div>`;
  }

  h += tensionHtml(ws.location.political_tension);

  const sid = `state-${ws.turn}`;
  h += `<div class="state-toggle" onclick="toggleState('${sid}')">\u25b8 world state</div>`;
  h += `<div class="state-dump" id="${sid}">${esc(
    JSON.stringify(ws, null, 2)
  )}</div>`;

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });
}

function tensionHtml(level) {
  const cls =
    level === "critical"
      ? "tension-critical"
      : level === "high"
        ? "tension-high"
        : "";
  return `<div class="tension-line">Political tension: <span class="${cls}">${esc(
    level
  )}</span></div>`;
}

/* exported for inline onclick */
window.toggleState = function (id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.display = el.style.display === "block" ? "none" : "block";
};

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !input.disabled) submitTurn();
});
btn.addEventListener("click", () => {
  if (!btn.disabled) submitTurn();
});

loadState();
