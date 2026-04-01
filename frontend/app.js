const $ = (sel) => document.querySelector(sel);

// ── Screens ──────────────────────────────────────────────────
const screens = {
  start:   $("#screen-start"),
  loading: $("#screen-loading"),
  game:    $("#screen-game"),
  erasure: $("#screen-erasure"),
};

// ── Loading ──────────────────────────────────────────────────
const loadingEraLabel    = $("#loading-era-label");
const loadingEraDesc     = $("#loading-era-desc");
const loadingEvents      = $("#loading-events");
const loadingVoices      = $("#loading-voices");
const loadingCharSection = $("#loading-char-section");
const loadingCharLabel   = $("#loading-char-label");
const loadingCharDesc    = $("#loading-char-desc");
const loadingRingFill    = $("#loading-ring-fill");
const RING_CIRCUMFERENCE = 125.66;

// ── Game chrome ──────────────────────────────────────────────
const topBarInfo         = $("#top-bar-info");
const deathIndicator     = $("#death-indicator");
const deathIndicatorName = $("#death-indicator-name");
const manuscript         = $("#manuscript");
const turnsContainer     = $("#turns-container");
const deathMarker        = $("#death-marker");
const deathMarkerTitle   = $("#death-marker-title");
const deathMarkerQuote   = $("#death-marker-quote");
const obsInputSection    = $("#obs-input-section");
const obsInput           = $("#obs-input");
const bottomBar          = $("#bottom-bar");
const playerInput        = $("#player-input");

// ── Hamburger ────────────────────────────────────────────────
const hamburgerPanel     = $("#hamburger-panel");
const hamburgerOverlay   = $("#hamburger-overlay");
const hamburgerIcon      = $("#hamburger-icon");
const hamburgerCloseIcon = $("#hamburger-close-icon");
const newRunConfirm      = $("#new-run-confirm");
const mapBtnText         = $("#map-btn-text");

// ── Erasure ──────────────────────────────────────────────────
const erasureText  = $("#erasure-text");
const erasureCycle = $("#erasure-cycle");

// ── Map ──────────────────────────────────────────────────────
const mapContainer = $("#map-container");

// ── State ────────────────────────────────────────────────────
let state   = null;
let runId   = null;
let eraKey  = null;
let busy    = false;
let mapOpen = false;

// ═════════════════════════════════════════════════════════════
//  ERA LOADING CONTENT — real historical events & voices
// ═════════════════════════════════════════════════════════════

const ERA_KEYS = [
  "roman_late_empire",
  "viking_age",
  "crusader_states",
  "black_death",
  "fall_of_constantinople",
];

const ERA_LOADING = {
  roman_late_empire: {
    label: "THE WESTERN ROMAN EMPIRE \u00B7 410 AD",
    desc: "The legions retreat. The barbarians advance. The eternal city holds its breath.",
    events: [
      { date: "378 AD", text: "The Battle of Adrianople. Emperor Valens dies on the field. The Goths cannot be stopped." },
      { date: "402 AD", text: "The imperial court abandons Milan for the marshes of Ravenna." },
      { date: "408 AD", text: "Stilicho, the last great general, is executed by his own emperor\u2019s order." },
    ],
    voices: [
      { speaker: "ST. JEROME, LETTER 127", text: "The city which had taken the whole world was itself taken. My voice sticks in my throat, and sobs choke my utterance." },
      { speaker: "ST. AUGUSTINE OF HIPPO", text: "All earthly cities are vulnerable. Only the City of God endures." },
    ],
  },
  viking_age: {
    label: "THE NORSE WORLD \u00B7 870 AD",
    desc: "The longships carry more than warriors. They carry the future of the North.",
    events: [
      { date: "793 AD", text: "Lindisfarne burns. The monks scattered. The age of the Northmen begins." },
      { date: "865 AD", text: "The Great Heathen Army lands in East Anglia. England will never be the same." },
      { date: "860 AD", text: "Norse ships appear before the walls of Constantinople. Even the Romans tremble." },
    ],
    voices: [
      { speaker: "H\u00C1VAM\u00C1L, STANZA 77", text: "Cattle die, kinsmen die, you yourself will die. One thing I know that never dies: the reputation of the dead." },
      { speaker: "ADAM OF BREMEN", text: "They worship Thor, who rules the air, the thunder, the winds, and the rain." },
    ],
  },
  crusader_states: {
    label: "THE CRUSADER STATES \u00B7 1190 AD",
    desc: "Jerusalem has fallen. The coast holds. Faith and steel are all that remain.",
    events: [
      { date: "1187 AD", text: "The Horns of Hattin. Saladin shatters the army of Jerusalem. The True Cross is lost." },
      { date: "1189 AD", text: "The kings of Europe take the cross. Frederick drowns in a river. Philip schemes. Richard sails." },
      { date: "1190 AD", text: "The siege of Acre begins. Two years of blood for a single city." },
    ],
    voices: [
      { speaker: "USAMA IBN MUNQIDH", text: "The Franks are void of all zeal and caution. But there is none more stubborn in war." },
      { speaker: "WILLIAM OF TYRE", text: "Our land is lost to us, unless God Himself sends help from above." },
    ],
  },
  black_death: {
    label: "THE BLACK DEATH \u00B7 1348 AD",
    desc: "The pestilence makes no distinction between lord and serf. The world empties.",
    events: [
      { date: "1347", text: "Genoese ships from Caffa bring death to Messina. The sailors are already dying when they dock." },
      { date: "1348", text: "Florence loses half its people in months. The dead are stacked in churches, then in the streets." },
      { date: "1348", text: "The flagellants march from town to town, whipping themselves bloody, begging God for mercy." },
    ],
    voices: [
      { speaker: "GIOVANNI BOCCACCIO", text: "How many brave men, how many fair ladies, breakfasted with their kinfolk and that same night supped with their ancestors in the other world!" },
      { speaker: "PETRARCH", text: "O happy posterity, who will not experience such abysmal woe, and will look upon our testimony as a fable." },
    ],
  },
  fall_of_constantinople: {
    label: "THE FALL OF CONSTANTINOPLE \u00B7 1453 AD",
    desc: "A thousand years of empire. Seven thousand defenders. One final dawn.",
    events: [
      { date: "1422 AD", text: "Murad II besieges Constantinople. The walls hold. This time." },
      { date: "1444 AD", text: "The Crusade of Varna fails. Hungary is broken. No relief will come from the West." },
      { date: "1452 AD", text: "Mehmed builds the fortress of Rumelihisar\u0131 on the Bosporus. The noose tightens." },
    ],
    voices: [
      { speaker: "GEORGE SPHRANTZES", text: "The Emperor said: \u2018The city is fallen and I am still alive.\u2019 Then he cast aside the imperial insignia and charged into the enemy." },
      { speaker: "DOUKAS, HISTORIAN", text: "The last Romans fought with a courage that shamed the centuries of decline. But courage alone cannot stop a cannon." },
    ],
  },
};

// ═════════════════════════════════════════════════════════════
//  SCREEN MANAGEMENT
// ═════════════════════════════════════════════════════════════

function showScreen(name) {
  Object.values(screens).forEach((s) => {
    s.classList.remove("active");
    s.classList.add("screen");
  });
  const target = screens[name];
  if (target) {
    target.classList.add("active", "fade-in");
    target.addEventListener("animationend", () => target.classList.remove("fade-in"), { once: true });
  }
}

// ═════════════════════════════════════════════════════════════
//  START → LOADING → GAME
// ═════════════════════════════════════════════════════════════

// ── Continue button ──────────────────────────────────────────
const btnContinue = $("#btn-continue");

(async function init() {
  const savedId = localStorage.getItem("chronos_run_id");
  if (savedId) {
    try {
      const res = await fetch(`/api/run/${savedId}`);
      if (res.ok) {
        btnContinue.classList.remove("hidden");
      }
    } catch (_) { /* ignore */ }
  }
})();

$("#btn-begin").addEventListener("click", (e) => {
  e.preventDefault();
  beginNewRun();
});

btnContinue.addEventListener("click", async (e) => {
  e.preventDefault();
  await resumeRun();
});

$("#btn-begin-again").addEventListener("click", (e) => {
  e.preventDefault();
  resetGameState();
  beginNewRun();
});

// ── Progress ring helper ─────────────────────────────────────
let ringInterval = null;

function startProgressRing() {
  let progress = 0;
  setRingProgress(0);
  ringInterval = setInterval(() => {
    progress += 0.012 + Math.random() * 0.008;
    if (progress > 0.85) progress = 0.85;
    setRingProgress(progress);
  }, 200);
}

function completeProgressRing() {
  if (ringInterval) { clearInterval(ringInterval); ringInterval = null; }
  setRingProgress(1);
}

function setRingProgress(pct) {
  const offset = RING_CIRCUMFERENCE * (1 - pct);
  loadingRingFill.style.strokeDashoffset = offset;
}

// ── New run ──────────────────────────────────────────────────

async function beginNewRun() {
  eraKey = ERA_KEYS[Math.floor(Math.random() * ERA_KEYS.length)];
  populateEraLoading(eraKey);
  showScreen("loading");
  loadingCharSection.classList.add("hidden");
  startProgressRing();

  try {
    const res  = await fetch("/api/run", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ era: eraKey }),
    });
    const data = await res.json();
    runId  = data.run_id;
    eraKey = data.era;
    state  = data.world_state;

    localStorage.setItem("chronos_run_id", runId);

    completeProgressRing();
    showCharacterOnLoading();

    await delay(3500);
    transitionToGame();
  } catch (e) {
    completeProgressRing();
    loadingEraDesc.textContent = "Error: " + e.message;
  }
}

// ── Resume saved run ─────────────────────────────────────────

async function resumeRun() {
  const savedId = localStorage.getItem("chronos_run_id");
  if (!savedId) return;

  try {
    const res = await fetch(`/api/run/${savedId}`);
    if (!res.ok) throw new Error("Run not found");
    const ws = await res.json();

    runId  = ws.run_id;
    state  = ws;
    eraKey = guessEraKey(ws.era.name);

    showScreen("game");
    updateGameChrome();
    renderInitialTurn();
    playerInput.focus();
  } catch (e) {
    localStorage.removeItem("chronos_run_id");
    btnContinue.classList.add("hidden");
    beginNewRun();
  }
}

function guessEraKey(eraName) {
  for (const k of ERA_KEYS) {
    if (ERA_LOADING[k] && ERA_LOADING[k].label.includes(eraName.split(" ")[0].toUpperCase())) return k;
  }
  return ERA_KEYS[0];
}

// ── Loading screen helpers ───────────────────────────────────

function populateEraLoading(key) {
  const era = ERA_LOADING[key];
  if (!era) return;

  loadingEraLabel.textContent = era.label;
  loadingEraDesc.textContent  = era.desc;

  let evHtml = "";
  for (const ev of era.events) {
    evHtml += `<div class="flex gap-4 items-baseline">`;
    evHtml += `<span class="font-system text-[10px] text-tertiary-container tracking-wider shrink-0 w-[70px]">${esc(ev.date)}</span>`;
    evHtml += `<p class="font-body text-[16px] leading-[1.7] text-on-surface">${esc(ev.text)}</p>`;
    evHtml += `</div>`;
  }
  loadingEvents.innerHTML = evHtml;

  let voHtml = "";
  for (const v of era.voices) {
    voHtml += `<div class="space-y-2">`;
    voHtml += `<p class="font-body italic text-[16px] leading-[1.7] text-on-secondary-container">\u201C${esc(v.text)}\u201D</p>`;
    voHtml += `<span class="font-system text-[10px] text-tertiary-container tracking-wider">\u2014 ${esc(v.speaker)}</span>`;
    voHtml += `</div>`;
  }
  loadingVoices.innerHTML = voHtml;
}

function showCharacterOnLoading() {
  const player = state.player;
  loadingCharLabel.textContent = `${player.name.toUpperCase()} \u00B7 ${player.role.toUpperCase()}`;
  loadingCharDesc.textContent  = player.description;
  loadingCharSection.classList.remove("hidden");
  loadingCharSection.style.opacity = "0";
  requestAnimationFrame(() => {
    loadingCharSection.style.opacity = "1";
  });
}

function transitionToGame() {
  showScreen("game");
  updateGameChrome();
  renderInitialTurn();
  playerInput.focus();
}

// ═════════════════════════════════════════════════════════════
//  GAME STATE HELPERS
// ═════════════════════════════════════════════════════════════

function resetGameState() {
  state  = null;
  runId  = null;
  eraKey = null;
  busy   = false;
  mapOpen = false;
  turnsContainer.innerHTML = "";

  deathMarker.classList.add("hidden");
  obsInputSection.classList.add("hidden");
  deathIndicator.classList.add("hidden");
  deathIndicator.style.display = "";
  bottomBar.classList.remove("hidden");
  newRunConfirm.classList.add("hidden");
  closeHamburger();
  hideMap();
}

function updateGameChrome() {
  if (!state) return;

  const year    = state.current_year || state.era.year_start;
  const locName = locationName(state.player.location);

  topBarInfo.textContent = `${year} AD \u00B7 ${locName.toUpperCase()} \u00B7 ${state.player.name.toUpperCase()}`;

  if (state.run_status === "dead_observing") enterObservationMode();
}

function locationName(locId) {
  if (!state || !state.locations) return locId || "";
  const loc = state.locations.find((l) => l.id === locId);
  return loc ? loc.name : locId;
}

function enterObservationMode() {
  deathIndicator.classList.remove("hidden");
  deathIndicator.style.display = "flex";
  deathIndicatorName.textContent = `\u2020 ${state.player.name.toUpperCase()}`;

  bottomBar.classList.add("hidden");
  obsInputSection.classList.remove("hidden");
}

// ═════════════════════════════════════════════════════════════
//  TURN RENDERING
// ═════════════════════════════════════════════════════════════

function renderInitialTurn() {
  const era    = state.era;
  const player = state.player;
  const loc    = state.locations.find((l) => l.id === player.location);
  const year   = state.current_year || era.year_start;

  addTurnBlock({
    year:         `${year} AD`,
    narration:    era.description,
    playerIntro:  `You are ${player.name}, ${player.role.toLowerCase()}. ${player.description}`,
    locationDesc: loc ? loc.description : "",
    npcResponses: [],
  });
}

function addTurnBlock(data) {
  const block = document.createElement("div");
  block.className = "turn-block space-y-6 pb-12 transition-opacity duration-700";

  let h = "";

  if (data.year) {
    h += `<div class="font-system text-[11px] text-on-secondary-container tracking-widest text-center">${esc(data.year)}${data.season ? " \u00B7 " + esc(data.season) : ""}</div>`;
  }

  if (data.playerAction) {
    h += `<div class="font-body italic text-[16px] text-on-secondary-container text-center">${esc(data.playerAction)}</div>`;
  }

  if (data.playerIntro) {
    h += `<div class="font-body text-[18px] leading-[1.9] text-on-surface text-center">${esc(data.playerIntro)}</div>`;
  }

  if (data.narration) {
    h += `<div class="font-body text-[18px] leading-[1.9] text-on-surface text-center">${esc(data.narration)}</div>`;
  }

  if (data.locationDesc) {
    h += `<div class="font-body text-[18px] leading-[1.9] text-on-surface text-center">${esc(data.locationDesc)}</div>`;
  }

  if (data.travel) {
    h += `<div class="font-body italic text-[16px] text-on-secondary-container text-center">The journey from ${esc(data.travel.from)} to ${esc(data.travel.to)} takes ${data.travel.turns_spent} turn${data.travel.turns_spent === 1 ? "" : "s"}. The world moves on while you travel.</div>`;
  }

  for (const npc of data.npcResponses || []) {
    h += `<div class="pt-4" style="border-top: 1px solid rgba(42,34,24,0.3);">`;
    h += `<span class="font-system text-[13px] text-on-secondary-container block mb-2 tracking-widest text-center">${esc((npc.npc_name || npc.name || "").toUpperCase())}</span>`;
    h += `<p class="font-body text-[17px] leading-[1.7] text-on-surface pl-6" style="border-left: 1px solid #2a2218;">${esc(npc.pov || npc.text || "")}</p>`;
    h += `</div>`;
  }

  h += `<div class="w-full h-[1px] bg-surface-container mt-6"></div>`;

  block.innerHTML = h;
  turnsContainer.appendChild(block);
  updateTurnOpacities();
  block.scrollIntoView({ behavior: "smooth" });
}

function updateTurnOpacities() {
  const blocks = turnsContainer.querySelectorAll(".turn-block");
  const total  = blocks.length;

  blocks.forEach((block, i) => {
    const dist = total - 1 - i;
    if (dist === 0)      block.style.opacity = "1";
    else if (dist === 1) block.style.opacity = "0.72";
    else if (dist === 2) block.style.opacity = "0.48";
    else if (dist === 3) block.style.opacity = "0.18";
    else                 block.style.opacity = "0.10";
  });
}

// ═════════════════════════════════════════════════════════════
//  TURN SUBMISSION
// ═════════════════════════════════════════════════════════════

async function submitTurn(text) {
  text = text.trim();
  if (!text || !runId || busy) return;
  busy = true;

  const loader = document.createElement("div");
  loader.className = "turn-block space-y-6 pb-12";
  loader.innerHTML = `
    <div class="font-body italic text-[16px] text-on-secondary-container text-center">${esc(text)}</div>
    <div class="flex justify-center dots-pulse">
      <span class="font-body text-2xl text-on-secondary-container mx-2">\u00B7</span>
      <span class="font-body text-2xl text-on-secondary-container mx-2">\u00B7</span>
      <span class="font-body text-2xl text-on-secondary-container mx-2">\u00B7</span>
    </div>`;
  turnsContainer.appendChild(loader);
  loader.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch(`/api/run/${runId}/turn`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ player_input: text }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    state = data.world_state;
    turnsContainer.removeChild(loader);

    if (data.erasure) {
      showErasure(data.erasure);
      busy = false;
      return;
    }

    addTurnBlock({
      year:         `${state.current_year} AD`,
      playerAction: text,
      narration:    data.parsed_action ? data.parsed_action.era_description : "",
      npcResponses: data.npc_responses || [],
      travel:       data.travel || null,
    });

    updateGameChrome();

    if (data.death) {
      showDeathMarker(data.death.cause);
      enterObservationMode();
    }

    if (typeof ChronosMap !== "undefined" && ChronosMap.isVisible()) {
      ChronosMap.updateMarkers(state);
    }
  } catch (e) {
    loader.innerHTML = `
      <div class="font-body italic text-[16px] text-on-secondary-container text-center">${esc(text)}</div>
      <div class="font-system text-[12px] text-[#805040] text-center">${esc(e.message)}</div>`;
    updateTurnOpacities();
  }

  busy = false;
}

function showDeathMarker(cause) {
  deathMarker.classList.remove("hidden");
  deathMarkerTitle.textContent = `The Death of ${state.player.name}`;
  deathMarkerQuote.textContent = `\u201C${cause}\u201D`;
  deathMarker.scrollIntoView({ behavior: "smooth" });
}

function showErasure(text) {
  erasureText.textContent  = text;
  erasureCycle.textContent = `End of Cycle ${state.turn}`;
  localStorage.removeItem("chronos_run_id");
  showScreen("erasure");
}

// ═════════════════════════════════════════════════════════════
//  INPUT HANDLING
// ═════════════════════════════════════════════════════════════

playerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && playerInput.value.trim()) {
    const v = playerInput.value;
    playerInput.value = "";
    submitTurn(v);
  }
});

obsInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && obsInput.value.trim()) {
    const v = obsInput.value;
    obsInput.value = "";
    submitTurn(v);
  }
});

// ═════════════════════════════════════════════════════════════
//  HAMBURGER PANEL
// ═════════════════════════════════════════════════════════════

function openHamburger() {
  hamburgerPanel.classList.add("open");
  hamburgerOverlay.classList.remove("hidden");
  hamburgerIcon.classList.add("hidden");
  hamburgerCloseIcon.classList.remove("hidden");
  syncMapButtonText();
}

function closeHamburger() {
  hamburgerPanel.classList.remove("open");
  hamburgerOverlay.classList.add("hidden");
  hamburgerIcon.classList.remove("hidden");
  hamburgerCloseIcon.classList.add("hidden");
  newRunConfirm.classList.add("hidden");
}

function toggleHamburger() {
  if (hamburgerPanel.classList.contains("open")) closeHamburger();
  else openHamburger();
}

$("#btn-hamburger").addEventListener("click", toggleHamburger);
$("#hamburger-overlay").addEventListener("click", closeHamburger);

$("#btn-new-run").addEventListener("click", () => {
  newRunConfirm.classList.toggle("hidden");
});

$("#btn-new-run-yes").addEventListener("click", () => {
  closeHamburger();
  localStorage.removeItem("chronos_run_id");
  resetGameState();
  beginNewRun();
});

$("#btn-new-run-no").addEventListener("click", () => {
  newRunConfirm.classList.add("hidden");
});

// ═════════════════════════════════════════════════════════════
//  MAP
// ═════════════════════════════════════════════════════════════

function showMap() {
  if (!state || !runId) return;
  mapOpen = true;
  mapContainer.classList.remove("hidden");
  bottomBar.classList.add("hidden");
  if (typeof ChronosMap !== "undefined") ChronosMap.show(state, eraKey);
}

function hideMap() {
  mapOpen = false;
  mapContainer.classList.add("hidden");
  if (typeof ChronosMap !== "undefined") ChronosMap.hide();
  if (state && state.run_status === "active") {
    bottomBar.classList.remove("hidden");
  }
}

function toggleMap() {
  if (mapOpen) hideMap();
  else showMap();
}

function syncMapButtonText() {
  mapBtnText.textContent = mapOpen ? "MANUSCRIPT" : "MAP";
}

$("#btn-map-hamburger").addEventListener("click", () => {
  closeHamburger();
  toggleMap();
});

document.addEventListener("keydown", (e) => {
  if ((e.key === "m" || e.key === "M") && state && runId) {
    if (document.activeElement === playerInput || document.activeElement === obsInput) return;
    toggleMap();
  }
});

// ═════════════════════════════════════════════════════════════
//  UTILITIES
// ═════════════════════════════════════════════════════════════

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
