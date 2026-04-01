let mapModule = null;

async function loadMapModule() {
  try {
    mapModule = await import("./map.js");
    console.log("Map module loaded successfully");
  } catch (e) {
    console.warn("Map module failed to load (Three.js CDN may be blocked):", e);
    mapModule = null;
  }
}

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

const menuBtn = $("#menu-btn");
const menuPanel = $("#menu-panel");
const menuMap = $("#menu-map");
const menuNew = $("#menu-new");
const menuStatus = $("#menu-status");

let state = null;
let runId = null;
let eraKey = null;
let mapShowing = false;
let globeReady = false;
let menuOpen = false;

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

// ------------------------------------------------------------------
// Persistence — survive page reload
// ------------------------------------------------------------------

function saveRunLocally() {
  if (runId) {
    localStorage.setItem("chronos_run_id", runId);
  }
  if (eraKey) {
    localStorage.setItem("chronos_era_key", eraKey);
  }
}

function clearLocalRun() {
  localStorage.removeItem("chronos_run_id");
  localStorage.removeItem("chronos_era_key");
}

async function tryResumeRun() {
  const savedRunId = localStorage.getItem("chronos_run_id");
  if (!savedRunId) return false;

  try {
    const resp = await fetch(`/api/run/${savedRunId}?_t=${Date.now()}`);
    if (!resp.ok) {
      clearLocalRun();
      return false;
    }
    state = await resp.json();
    runId = savedRunId;
    eraKey = localStorage.getItem("chronos_era_key") || "";

    hide(startScreen);
    show(narrativeEl);
    show(inputBar);
    show(menuBtn);
    renderResumedRun();
    prepareGlobe();
    return true;
  } catch {
    clearLocalRun();
    return false;
  }
}

function renderResumedRun() {
  const loc = state.locations.find((l) => l.id === state.player.location);
  const year = state.current_year || state.era.year_start;

  let h = `<div class="year-mark">${esc(state.era.name)} \u2014 ${state.era.year_start} AD</div>`;
  h += `<p>${esc(state.era.description)}</p>`;
  h += `<p>You are <strong>${esc(state.player.name)}</strong>, ${esc(
    state.player.role.toLowerCase()
  )}. ${esc(state.player.description)}</p>`;

  if (loc) {
    h += `<p>${esc(loc.description)}</p>`;
  }

  introEl.innerHTML = h;

  turnsEl.innerHTML = "";
  for (const ev of state.events) {
    const block = document.createElement("div");
    block.className = "turn-block";

    let bh = `<div class="year-mark">${esc(String(
      Math.round(state.era.year_start + ev.turn * (state.era.years_per_turn || 0.25))
    ))} AD</div>`;
    bh += `<div class="narration">${esc(ev.description)}</div>`;
    block.innerHTML = bh;
    turnsEl.appendChild(block);
  }

  if (state.run_status === "active") {
    setInputState("active");
  } else if (state.run_status === "dead_observing") {
    setInputState("observing");
  } else if (state.run_status === "ended") {
    setInputState("ended");
  }

  if (turnsEl.lastChild) {
    turnsEl.lastChild.scrollIntoView({ behavior: "smooth" });
  }

  input.focus();
}

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
    saveRunLocally();
    hide(startScreen);
    hide(startLoading);
    show(narrativeEl);
    show(inputBar);
    show(menuBtn);
    renderIntro();
    prepareGlobe();
  } catch (e) {
    startLoading.innerHTML = `<span class="error-text">Error: ${esc(e.message)}</span>`;
  } finally {
    startBtn.disabled = false;
  }
}

async function prepareGlobe() {
  if (!mapModule) return;
  try {
    mapModule.initGlobe();
    await mapModule.loadCoastlines();
    if (eraKey) await mapModule.loadBorders(eraKey);
    globeReady = true;
  } catch (e) {
    console.warn("Globe init failed:", e);
  }
}

// ------------------------------------------------------------------
// Map toggle (M key)
// ------------------------------------------------------------------

function toggleMap() {
  if (!state || !globeReady || !mapModule) return;

  if (mapShowing) {
    hide(mapContainer);
    hide(mapHint);
    show(narrativeEl);
    show(inputBar);
    mapModule.stopRendering();
    mapShowing = false;
  } else {
    hide(narrativeEl);
    hide(inputBar);
    show(mapContainer);
    show(mapHint);
    mapModule.resize();
    syncMapState();
    mapModule.startRendering();
    mapShowing = true;
  }
}

async function syncMapState() {
  if (!runId || !mapModule) return;
  try {
    const resp = await fetch(`/api/run/${runId}?_t=${Date.now()}`);
    if (resp.ok) {
      state = await resp.json();
    }
  } catch { /* use cached state */ }

  mapModule.updateMarkers(state);

  const playerLoc = state.locations.find(
    (l) => l.id === state.player.location
  );
  if (playerLoc) {
    mapModule.focusOnLocation(playerLoc.lat, playerLoc.lon, false);
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
      clearLocalRun();
      if (globeReady && mapModule) mapModule.updateMarkers(state);
      return;
    }

    renderTurnResult(block, text, data);

    if (data.death) {
      appendDeathBlock(data.death.cause);
      setInputState("observing");
    } else {
      setInputState("active");
    }

    if (globeReady && mapModule) {
      mapModule.updateMarkers(state);
      if (data.travel) {
        const dest = state.locations.find(
          (l) => l.id === state.player.location
        );
        if (dest) mapModule.focusOnLocation(dest.lat, dest.lon, true);
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
// Menu
// ------------------------------------------------------------------

function toggleMenu() {
  menuOpen = !menuOpen;
  if (menuOpen) {
    show(menuPanel);
  } else {
    hide(menuPanel);
  }
}

function newRunFromMenu() {
  hide(menuPanel);
  menuOpen = false;
  clearLocalRun();
  turnsEl.innerHTML = "";
  introEl.innerHTML = "";
  hide(narrativeEl);
  hide(inputBar);
  hide(menuBtn);
  show(startScreen);
  hide(startLoading);
  state = null;
  runId = null;
  eraKey = null;
  globeReady = false;
}

function showRunStatus() {
  if (!state) return;
  hide(menuPanel);
  menuOpen = false;

  const loc = state.locations.find((l) => l.id === state.player.location);
  const age = state.current_year - state.player.birth_year;
  const visited = (state.visited_locations || []).length;
  const total = state.locations.length;

  const block = appendBlock(
    `<div class="year-mark">Status</div>` +
    `<div class="narration" style="font-size:0.82em;color:#585040">` +
    `${esc(state.player.name)} \u00b7 ${esc(state.player.role)}<br>` +
    `Age: ~${age} \u00b7 Turn ${state.turn} \u00b7 ${state.current_year} AD<br>` +
    `Location: ${loc ? esc(loc.name) : "unknown"}<br>` +
    `Visited: ${visited}/${total} locations \u00b7 ` +
    `Status: ${esc(state.run_status)}` +
    `</div>`
  );
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

menuBtn.addEventListener("click", toggleMenu);
menuMap.addEventListener("click", () => { hide(menuPanel); menuOpen = false; toggleMap(); });
menuNew.addEventListener("click", newRunFromMenu);
menuStatus.addEventListener("click", showRunStatus);

document.addEventListener("keydown", (e) => {
  if (e.key === "m" || e.key === "M") {
    if (document.activeElement === input) return;
    toggleMap();
  }
  if (e.key === "Escape" && menuOpen) {
    hide(menuPanel);
    menuOpen = false;
  }
});

// ------------------------------------------------------------------
// Init — try to resume existing run, otherwise show start screen
// ------------------------------------------------------------------

async function init() {
  await loadMapModule();
  const resumed = await tryResumeRun();
  if (!resumed) {
    show(startScreen);
  }
}

init();
