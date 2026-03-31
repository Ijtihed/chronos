const $ = (sel) => document.querySelector(sel);
const eraInfo = $("#era-info");
const introEl = $("#intro");
const turnsEl = $("#turns");
const input = $("#player-input");
const actBtn = $("#act-btn");
const startScreen = $("#start-screen");
const startBtn = $("#start-btn");
const startLoading = $("#start-loading");
const newRunBtn = $("#new-run-btn");
const narrativeEl = $("#narrative");
const inputBar = $("#input-bar");
const locationBar = $("#location-bar");

let state = null;
let runId = null;

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

async function startNewRun() {
  startBtn.disabled = true;
  show(startLoading);

  try {
    const res = await fetch("/api/run", { method: "POST" });
    const data = await res.json();
    runId = data.run_id;
    state = data.world_state;
    hide(startScreen);
    show(narrativeEl);
    show(inputBar);
    show(locationBar);
    renderIntro();
  } catch (e) {
    startLoading.innerHTML = `<span class="error-text">Error: ${esc(e.message)}</span>`;
  } finally {
    startBtn.disabled = false;
  }
}

function renderIntro() {
  eraInfo.textContent = `${state.era.name} \u2014 ${state.current_year} AD`;
  updateLocationBar();

  let h = `<p>${esc(state.era.description)}</p>`;
  h += `<p>You are <strong>${esc(state.player.name)}</strong>, ${esc(
    state.player.role.toLowerCase()
  )}. ${esc(state.player.description)}</p>`;

  const nearby = state.npcs.filter((n) => n.location === state.player.location);
  if (nearby.length) {
    h += "<p>Nearby:</p><ul style='margin:6px 0 12px 22px;list-style:disc'>";
    for (const npc of nearby) {
      h += `<li><strong>${esc(npc.name)}</strong> \u2014 ${esc(npc.role)}</li>`;
    }
    h += "</ul>";
  }

  introEl.innerHTML = h;
  setInputState("active");
}

function updateLocationBar() {
  if (!state) return;
  const loc = state.locations.find((l) => l.id === state.player.location);
  if (!loc) return;

  const nearby = state.npcs.filter((n) => n.location === state.player.location);
  const npcList = nearby.map((n) => esc(n.name)).join(", ") || "none";

  let travelHtml = "";
  const neighbors = Object.keys(loc.neighbors || {});
  if (neighbors.length && state.run_status !== "ended") {
    const links = neighbors
      .map((nid) => {
        const dest = state.locations.find((l) => l.id === nid);
        const name = dest ? dest.name : nid;
        const turns = loc.neighbors[nid];
        return `<span class="travel-link" onclick="doTravel('${nid}')">${esc(
          name
        )} (${turns}t)</span>`;
      })
      .join(" \u00b7 ");
    travelHtml = `<span>Travel: ${links}</span>`;
  }

  locationBar.innerHTML =
    `<span class="loc-name">${esc(loc.name)}</span>` +
    `<span class="nearby-label">People here: ${npcList}</span>` +
    travelHtml;
}

function setInputState(mode) {
  if (mode === "active") {
    input.disabled = false;
    actBtn.disabled = false;
    input.placeholder = "";
    show(inputBar);
  } else if (mode === "observing") {
    input.disabled = true;
    actBtn.disabled = true;
    input.placeholder = "";
    show(inputBar);
  } else if (mode === "ended") {
    hide(inputBar);
  } else if (mode === "loading") {
    input.disabled = true;
    actBtn.disabled = true;
  }
}

async function submitTurn() {
  const text = input.value.trim();
  if (!text) return;

  setInputState("loading");
  input.value = "";

  const block = appendBlock(
    `<div class="turn-label">Turn ${(state?.turn || 0) + 1}</div>` +
      `<div class="player-line">\u00bb ${esc(text)}</div>` +
      `<div class="loading-text">The world turns\u2026</div>`
  );

  try {
    const res = await fetch(`/api/run/${runId}/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    const data = await res.json();
    state = data.world_state;
    renderTurnResult(block, text, data);

    if (data.death) {
      appendDeathBlock(data.death.cause);
      setInputState("observing");
    } else {
      setInputState("active");
    }
  } catch (e) {
    block.querySelector(".loading-text").innerHTML = `<span class="error-text">${esc(e.message)}</span>`;
    setInputState("active");
  }
}

window.doTravel = async function (destId) {
  setInputState("loading");

  const block = appendBlock(
    `<div class="turn-label">Traveling\u2026</div>` +
      `<div class="loading-text">The world moves while you travel\u2026</div>`
  );

  try {
    const res = await fetch(`/api/run/${runId}/travel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ destination: destId }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    const data = await res.json();
    state = data.world_state;

    if (data.erasure) {
      block.innerHTML = "";
      appendErasureBlock(data.erasure);
      setInputState("ended");
      return;
    }

    let h = `<div class="turn-label">Arrived</div>`;
    if (data.travel) {
      h += `<div class="action-narration">Traveled from ${esc(data.travel.from)} to ${esc(
        data.travel.to
      )} (${data.travel.turns_spent} turns passed).</div>`;
    }

    if (data.stored_povs && Object.keys(data.stored_povs).length) {
      h += `<div style="margin-top:10px;font-size:0.82em;color:#706850">While you were away:</div>`;
      for (const [, info] of Object.entries(data.stored_povs)) {
        for (const pov of info.povs) {
          h += `<div class="npc-block"><div class="npc-label">${esc(info.npc_name)}</div>`;
          h += `<div class="npc-voice">${esc(pov)}</div></div>`;
        }
      }
    }

    if (data.arrival_reactions && data.arrival_reactions.length) {
      for (const r of data.arrival_reactions) {
        h += `<div class="npc-block">`;
        h += `<div class="npc-label">${esc(r.npc_name)}</div>`;
        h += `<div class="npc-voice">${esc(r.pov)}</div>`;
        h += `</div>`;
      }
    }

    const loc = state.locations.find((l) => l.id === state.player.location);
    if (loc) {
      h += tensionHtml(loc.political_tension);
    }

    block.innerHTML = h;
    updateLocationBar();
    eraInfo.textContent = `${state.era.name} \u2014 ${state.current_year} AD`;
    block.scrollIntoView({ behavior: "smooth" });

    if (state.run_status === "active") setInputState("active");
    else if (state.run_status === "dead_observing") setInputState("observing");
    else setInputState("ended");
  } catch (e) {
    block.querySelector(".loading-text").innerHTML = `<span class="error-text">${esc(e.message)}</span>`;
    setInputState(state?.run_status === "active" ? "active" : "observing");
  }
};

function renderTurnResult(el, playerText, data) {
  const { parsed_action: pa, npc_responses, world_state: ws } = data;

  let h = `<div class="turn-label">Turn ${ws.turn} \u2014 ${ws.current_year} AD</div>`;
  h += `<div class="player-line">\u00bb ${esc(playerText)}</div>`;

  if (pa.era_description) {
    h += `<div class="action-narration">${esc(pa.era_description)}</div>`;
  }

  h += `<span class="parsed-badge">${esc(pa.action_type)}${
    pa.target ? " \u2192 " + esc(pa.target) : ""
  }</span>`;

  for (const r of npc_responses || []) {
    h += `<div class="npc-block">`;
    h += `<div class="npc-label">${esc(r.npc_name)}</div>`;
    h += `<div class="npc-voice">${esc(r.pov)}</div>`;
    h += `</div>`;
  }

  const loc = ws.locations.find((l) => l.id === ws.player.location);
  if (loc) {
    h += tensionHtml(loc.political_tension);
  }

  el.innerHTML = h;
  updateLocationBar();
  eraInfo.textContent = `${ws.era.name} \u2014 ${ws.current_year} AD`;
  el.scrollIntoView({ behavior: "smooth" });
}

function appendDeathBlock(cause) {
  const div = document.createElement("div");
  div.className = "death-block";
  div.innerHTML = `<p>${esc(cause)}</p><p style="margin-top:12px;font-size:0.82em;color:#706050">You have died. You may still travel and observe as memories fade.</p>`;
  turnsEl.appendChild(div);
  div.scrollIntoView({ behavior: "smooth" });
}

function appendErasureBlock(text) {
  const div = document.createElement("div");
  div.className = "erasure-block";
  div.innerHTML = `<p>${esc(text)}</p>`;
  turnsEl.appendChild(div);
  div.scrollIntoView({ behavior: "smooth" });
}

function appendBlock(html) {
  const block = document.createElement("div");
  block.className = "turn-block";
  block.innerHTML = html;
  turnsEl.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });
  return block;
}

function tensionHtml(level) {
  const cls = level === "critical" ? "tension-critical" : level === "high" ? "tension-high" : "";
  return `<div class="tension-line">Political tension: <span class="${cls}">${esc(level)}</span></div>`;
}

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !input.disabled) submitTurn();
});
actBtn.addEventListener("click", () => { if (!actBtn.disabled) submitTurn(); });
startBtn.addEventListener("click", startNewRun);
newRunBtn.addEventListener("click", () => {
  turnsEl.innerHTML = "";
  introEl.innerHTML = "";
  hide(narrativeEl);
  hide(inputBar);
  hide(locationBar);
  show(startScreen);
  startLoading.classList.add("hidden");
  startLoading.innerHTML = "Generating your world...";
});
