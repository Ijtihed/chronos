import {
  initGlobe,
  loadCoastlines,
  loadBorders,
  updateMarkers,
  focusOnLocation,
  startRendering,
  stopRendering,
  isInitialized,
} from "./map.js";

const $ = (sel) => document.querySelector(sel);
const introEl = $("#intro");
const turnsEl = $("#turns");
const input = $("#player-input");
const actBtn = $("#act-btn");
const startScreen = $("#start-screen");
const startBtn = $("#start-btn");
const startLoading = $("#start-loading");
const narrativeEl = $("#narrative");
const inputBar = $("#input-bar");
const mapContainer = $("#map-container");
const mapHint = $("#map-hint");

let state = null;
let runId = null;
let eraKey = null;
let mapShowing = false;
let globeReady = false;

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

// ------------------------------------------------------------------
// Run start
// ------------------------------------------------------------------

async function startNewRun() {
  startBtn.disabled = true;
  show(startLoading);

  try {
    const res = await fetch("/api/run", { method: "POST" });
    const data = await res.json();
    runId = data.run_id;
    eraKey = data.era;
    state = data.world_state;
    hide(startScreen);
    show(narrativeEl);
    show(inputBar);
    renderIntro();
    prepareGlobe();
  } catch (e) {
    startLoading.innerHTML = `<span class="error-text">Error: ${esc(e.message)}</span>`;
  } finally {
    startBtn.disabled = false;
  }
}

async function prepareGlobe() {
  initGlobe();
  await loadCoastlines();
  if (eraKey) await loadBorders(eraKey);
  globeReady = true;
}

// ------------------------------------------------------------------
// Map toggle (M key)
// ------------------------------------------------------------------

function toggleMap() {
  if (!state || !globeReady) return;

  if (mapShowing) {
    hide(mapContainer);
    hide(mapHint);
    show(narrativeEl);
    show(inputBar);
    stopRendering();
    mapShowing = false;
  } else {
    hide(narrativeEl);
    hide(inputBar);
    show(mapContainer);
    show(mapHint);
    syncMapState();
    startRendering();
    mapShowing = true;
  }
}

async function syncMapState() {
  if (!runId) return;
  try {
    const resp = await fetch(`/api/run/${runId}`);
    if (resp.ok) {
      state = await resp.json();
    }
  } catch { /* use cached state */ }

  updateMarkers(state);

  const playerLoc = state.locations.find(
    (l) => l.id === state.player.location
  );
  if (playerLoc) {
    focusOnLocation(playerLoc.lat, playerLoc.lon, false);
  }
}

// ------------------------------------------------------------------
// Narrative rendering
// ------------------------------------------------------------------

function renderIntro() {
  const loc = state.locations.find((l) => l.id === state.player.location);
  const year = state.current_year || state.era.year_start;

  let h = `<div class="year-mark">${esc(state.era.name)} \u2014 ${year} AD</div>`;
  h += `<p>${esc(state.era.description)}</p>`;
  h += `<p>You are <strong>${esc(state.player.name)}</strong>, ${esc(
    state.player.role.toLowerCase()
  )}. ${esc(state.player.description)}</p>`;

  if (loc) {
    h += `<p>${esc(loc.description)}</p>`;
  }

  introEl.innerHTML = h;
  setInputState("active");
  input.focus();
}

function setInputState(mode) {
  if (mode === "active") {
    input.disabled = false;
    actBtn.disabled = false;
    show(inputBar);
  } else if (mode === "observing") {
    input.disabled = true;
    actBtn.disabled = true;
    show(inputBar);
  } else if (mode === "ended") {
    hide(inputBar);
  } else if (mode === "loading") {
    input.disabled = true;
    actBtn.disabled = true;
  }
}

// ------------------------------------------------------------------
// Turn submission
// ------------------------------------------------------------------

async function submitTurn() {
  const text = input.value.trim();
  if (!text) return;

  setInputState("loading");
  input.value = "";

  const block = appendBlock(
    `<div class="player-line">${esc(text)}</div>` +
      `<div class="loading-text">...</div>`
  );

  try {
    const res = await fetch(`/api/run/${runId}/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: text }),
    });
    if (!res.ok)
      throw new Error(
        (await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`
      );
    const data = await res.json();
    state = data.world_state;

    if (data.erasure) {
      block.innerHTML = "";
      appendErasureBlock(data.erasure);
      setInputState("ended");
      if (globeReady) updateMarkers(state);
      return;
    }

    renderTurnResult(block, text, data);

    if (data.death) {
      appendDeathBlock(data.death.cause);
      setInputState("observing");
    } else {
      setInputState("active");
    }

    if (globeReady) {
      updateMarkers(state);
      if (data.travel) {
        const dest = state.locations.find(
          (l) => l.id === state.player.location
        );
        if (dest) focusOnLocation(dest.lat, dest.lon, true);
      }
    }
  } catch (e) {
    block.querySelector(".loading-text").innerHTML = `<span class="error-text">${esc(
      e.message
    )}</span>`;
    setInputState("active");
  }
}

// ------------------------------------------------------------------
// Render helpers
// ------------------------------------------------------------------

function renderTurnResult(el, playerText, data) {
  const { parsed_action: pa, npc_responses, world_state: ws } = data;

  let h = `<div class="year-mark">${ws.current_year} AD</div>`;
  h += `<div class="player-line">${esc(playerText)}</div>`;

  if (pa.era_description) {
    h += `<div class="narration">${esc(pa.era_description)}</div>`;
  }

  if (data.travel) {
    h += `<div class="narration">${esc(
      `The journey from ${data.travel.from} to ${data.travel.to} takes ${data.travel.turns_spent} turns. The world moves on while you travel.`
    )}</div>`;
  }

  for (const r of npc_responses || []) {
    h += `<div class="npc-block">`;
    h += `<div class="npc-label">${esc(r.npc_name)}</div>`;
    h += `<div class="npc-voice">${esc(r.pov)}</div>`;
    h += `</div>`;
  }

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });
}

function appendDeathBlock(cause) {
  const div = document.createElement("div");
  div.className = "death-block";
  div.innerHTML = `<p>${esc(cause)}</p>`;
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

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ------------------------------------------------------------------
// Event listeners
// ------------------------------------------------------------------

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !input.disabled) submitTurn();
});

actBtn.addEventListener("click", () => {
  if (!actBtn.disabled) submitTurn();
});

startBtn.addEventListener("click", startNewRun);

document.addEventListener("keydown", (e) => {
  if (e.key === "m" || e.key === "M") {
    if (document.activeElement === input) return;
    toggleMap();
  }
});
