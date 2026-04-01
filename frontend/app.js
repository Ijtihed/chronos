/**
 * CHRONOS — Simulation-first game loop.
 *
 * Turn flow: world simulates (NPCs act) → player optionally acts →
 * narrative shows ambient activity first, player action as one thread.
 *
 * Works with the manuscript UI (index.html screen-based navigation).
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let state = null;
let runId = null;
let eraKey = null;

// Screen management
function showScreen(id) {
  $$(".screen").forEach((s) => s.classList.remove("active"));
  const s = $(`#${id}`);
  if (s) s.classList.add("active");
}

// -------------------------------------------------------------------
// Start screen — save/restore runs via localStorage
// -------------------------------------------------------------------

function saveRunToStorage() {
  if (runId && eraKey) {
    localStorage.setItem("chronos_run_id", runId);
    localStorage.setItem("chronos_era_key", eraKey);
  }
  const turnsContainer = document.getElementById("turns-container");
  if (turnsContainer && runId) {
    localStorage.setItem("chronos_narrative_" + runId, turnsContainer.innerHTML);
  }
}

function clearRunFromStorage() {
  const oldId = localStorage.getItem("chronos_run_id");
  if (oldId) localStorage.removeItem("chronos_narrative_" + oldId);
  localStorage.removeItem("chronos_run_id");
  localStorage.removeItem("chronos_era_key");
}

function getSavedRun() {
  const id = localStorage.getItem("chronos_run_id");
  const era = localStorage.getItem("chronos_era_key");
  return id ? { runId: id, eraKey: era } : null;
}

// On page load: check for existing run
(async function checkForExistingRun() {
  const saved = getSavedRun();
  if (!saved) return;
  try {
    const res = await fetch(`/api/run/${saved.runId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.run_status !== "ended") {
        $("#btn-continue").classList.remove("hidden");
      }
    }
  } catch {}
})();

// Begin button — if active run exists, show confirmation first
$("#btn-begin").addEventListener("click", () => {
  const saved = getSavedRun();
  const confirmEl = $("#begin-confirm");
  if (saved && confirmEl && !confirmEl.classList.contains("was-confirmed")) {
    confirmEl.classList.remove("hidden");
    return;
  }
  confirmEl && confirmEl.classList.add("hidden");
  startNewRun();
});

// Confirm yes — start new run (overwrite)
const beginYes = $("#btn-begin-yes");
if (beginYes) {
  beginYes.addEventListener("click", () => {
    const confirmEl = $("#begin-confirm");
    if (confirmEl) { confirmEl.classList.add("hidden"); confirmEl.classList.add("was-confirmed"); }
    clearRunFromStorage();
    startNewRun();
  });
}

// Confirm no — cancel
const beginNo = $("#btn-begin-no");
if (beginNo) {
  beginNo.addEventListener("click", () => {
    const confirmEl = $("#begin-confirm");
    if (confirmEl) confirmEl.classList.add("hidden");
  });
}

// Continue button — load existing run
const continueBtn = $("#btn-continue");
if (continueBtn) {
  continueBtn.addEventListener("click", async () => {
    const saved = getSavedRun();
    if (!saved) return;
    try {
      const res = await fetch(`/api/run/${saved.runId}`);
      if (!res.ok) { clearRunFromStorage(); return; }
      state = await res.json();
      runId = saved.runId;
      eraKey = saved.eraKey;
      enterGame();
    } catch {
      clearRunFromStorage();
    }
  });
}

// Begin again from erasure screen
$("#btn-begin-again") && $("#btn-begin-again").addEventListener("click", () => {
  clearRunFromStorage();
  showScreen("screen-start");
  $("#btn-continue").classList.add("hidden");
  const confirmEl = $("#begin-confirm");
  if (confirmEl) { confirmEl.classList.add("hidden"); confirmEl.classList.remove("was-confirmed"); }
});

async function startNewRun() {
  showScreen("screen-loading");
  $("#loading-era-label").textContent = "";
  $("#loading-era-desc").textContent = "";
  const eventsEl = $("#loading-events");
  const voicesEl = $("#loading-voices");
  const charSection = $("#loading-char-section");
  if (eventsEl) eventsEl.innerHTML = "";
  if (voicesEl) voicesEl.innerHTML = "";
  if (charSection) charSection.classList.add("hidden");
  startProgressBar();

  try {
    // Step 1: Get era info INSTANTLY (no character generation)
    const previewRes = await fetch("/api/run/preview", { method: "POST" });
    const preview = await previewRes.json();

    eraKey = preview.era_key;
    $("#loading-era-label").textContent = `${preview.era_name} \u2014 ${preview.year_start} AD`;
    $("#loading-era-desc").textContent = preview.description;

    // Populate events immediately
    if (eventsEl && preview.loading_events) {
      let evHtml = "";
      for (const ev of preview.loading_events) {
        evHtml += `<p class="font-body text-[16px] leading-relaxed text-on-secondary-container">${esc(ev)}</p>`;
      }
      eventsEl.innerHTML = evHtml;
    }

    // Populate voices immediately
    if (voicesEl && preview.loading_voices) {
      let voHtml = "";
      for (const v of preview.loading_voices) {
        voHtml += `<blockquote class="pl-4" style="border-left: 1px solid #2a2218;">`;
        voHtml += `<p class="font-body italic text-[17px] leading-relaxed text-on-surface">${esc(v.quote)}</p>`;
        voHtml += `<cite class="block mt-1 font-system text-[10px] text-on-secondary-container not-italic tracking-tight">${esc(v.source)}</cite>`;
        voHtml += `</blockquote>`;
      }
      voicesEl.innerHTML = voHtml;
    }

    // Step 2: Generate characters in background (takes 1-2 min)
    const runRes = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ era: eraKey }),
    });
    const runData = await runRes.json();
    runId = runData.run_id;
    eraKey = runData.era;
    state = runData.world_state;
    saveRunToStorage();

    completeProgressBar();

    setTimeout(() => {
      showScreen("screen-transition");
      setTimeout(() => enterGame(), 3000);
    }, 600);
  } catch (e) {
    completeProgressBar();
    $("#loading-era-desc").textContent = `Error: ${e.message}`;
  }
}

function enterGame() {
  showScreen("screen-game");
  const turnsContainer = $("#turns-container");

  updateTopBar();
  setupInput();

  // Try to restore saved narrative (includes intro + all turn blocks)
  const savedNarrative = runId ? localStorage.getItem("chronos_narrative_" + runId) : null;
  if (savedNarrative && turnsContainer) {
    turnsContainer.innerHTML = savedNarrative;
    // Scroll to bottom
    const manuscript = $("#manuscript");
    if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
  } else {
    // Fresh game — render intro
    if (turnsContainer) turnsContainer.innerHTML = "";
    const loc = state.locations.find((l) => l.id === state.player.location);
    const year = state.current_year || state.era.year_start;

    let introHtml = `<div class="mb-12">`;
    introHtml += `<div class="font-system text-[10px] tracking-[0.15em] text-tertiary-container uppercase mb-4">${esc(state.era.name)} — ${year} AD</div>`;
    introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface mb-4">${esc(state.era.description)}</p>`;
    introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface mb-4">You are <strong class="text-primary-fixed">${esc(state.player.name)}</strong>, ${esc(state.player.role.toLowerCase())}. ${esc(state.player.description)}</p>`;
    if (loc) {
      introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface">${esc(loc.description)}</p>`;
    }
    introHtml += `</div>`;
    turnsContainer.innerHTML = introHtml;
    saveRunToStorage();
  }

  // Restore death/observation state if needed
  if (state.run_status === "dead_observing") {
    const deathEvent = (state.events || []).find(e => e.action_type === "death");
    if (deathEvent) showDeathMarker(deathEvent.description);
    enterObservationMode();
  }
}

function updateTopBar() {
  const info = $("#top-bar-info");
  if (!info || !state) return;
  const loc = state.locations.find((l) => l.id === state.player.location);
  const locName = loc ? loc.name : "";
  const year = state.current_year || state.era.year_start;
  info.textContent = `${year} AD · ${locName}`;

  const deathInd = $("#death-indicator");
  const deathName = $("#death-indicator-name");
  if (state.run_status === "dead_observing" && deathInd) {
    deathInd.classList.remove("hidden");
    deathInd.classList.add("flex");
    if (deathName) deathName.textContent = state.player.name;
  }
}

// -------------------------------------------------------------------
// Input handling
// -------------------------------------------------------------------

function setupInput() {
  const input = $("#player-input");
  const obsInput = $("#obs-input");

  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submitTurn(input.value.trim());
    });
  }
  if (obsInput) {
    obsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submitTurn(obsInput.value.trim());
    });
  }
}

let turnInProgress = false;

async function submitTurn(text) {
  if (!text || !runId || turnInProgress) return;
  turnInProgress = true;

  const input = $("#player-input");
  const obsInput = $("#obs-input");

  // Lock input immediately — show "the world is happening"
  if (input) {
    input.value = "";
    input.disabled = true;
    input.placeholder = "The world is happening...";
  }
  if (obsInput) {
    obsInput.value = "";
    obsInput.disabled = true;
    obsInput.placeholder = "The world is happening...";
  }

  const turnsContainer = $("#turns-container");
  const block = document.createElement("div");
  block.className = "mb-8";
  block.innerHTML = `<p class="font-body italic text-[16px] text-on-secondary-container">${esc(text)}</p><p class="font-system text-[10px] text-[#2a2218] mt-2">...</p>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });

  // Save immediately — the player's input is committed, no take-backs on reload
  saveRunToStorage();

  try {
    const res = await fetch(`/api/run/${runId}/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    const data = await res.json();
    state = data.world_state;

    if (data.erasure) {
      block.remove();
      clearRunFromStorage();
      showErasure(data.erasure);
      return;
    }

    renderTurn(block, text, data);
    updateTopBar();
    saveRunToStorage();

    if (data.death) {
      showDeathMarker(data.death.cause);
      enterObservationMode();
    }

    if (typeof ChronosMap !== "undefined" && !$('#map-container').classList.contains('hidden')) {
      ChronosMap.updateMarkers(state);
    }
  } catch (e) {
    block.innerHTML = `<p class="font-body italic text-[16px] text-on-secondary-container">${esc(text)}</p><p class="font-system text-[10px] text-dead-tint mt-2">${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    if (input) {
      input.disabled = false;
      input.placeholder = "";
    }
    if (obsInput) {
      obsInput.disabled = false;
      obsInput.placeholder = "TRAVEL ONLY...";
    }
    if (state && state.run_status === "active" && input) input.focus();
    if (state && state.run_status === "dead_observing" && obsInput) obsInput.focus();
  }
}

function renderTurn(el, playerText, data) {
  const { parsed_action: pa, npc_responses, world_state: ws } = data;
  const ambient = data.ambient_activity || [];

  let h = `<div class="font-system text-[10px] tracking-[0.12em] text-[#2a2218] uppercase mb-4">${ws.current_year} AD</div>`;

  // Ambient world activity FIRST — what NPCs are doing around you
  if (ambient.length) {
    for (const a of ambient) {
      h += `<p class="font-body text-[17px] leading-relaxed text-on-secondary-container mb-3">`;
      if (a.interacts_with) {
        h += `<span class="text-primary-container">${esc(a.npc_name)}</span> and <span class="text-primary-container">${esc(a.interacts_with)}</span> — `;
      } else {
        h += `<span class="text-primary-container">${esc(a.npc_name)}</span> — `;
      }
      h += `${esc(a.activity)}</p>`;
    }
  }

  // Player's action — one thread among the world
  h += `<p class="font-body italic text-[16px] text-on-secondary-container mb-3 mt-4">${esc(playerText)}</p>`;

  if (pa.era_description) {
    h += `<p class="font-body text-[18px] leading-relaxed text-on-surface mb-3">${esc(pa.era_description)}</p>`;
  }

  if (data.travel) {
    h += `<p class="font-body text-[17px] leading-relaxed text-on-secondary-container mb-3">${esc(
      `The journey from ${data.travel.from} to ${data.travel.to} takes ${data.travel.turns_spent} turns.`
    )}</p>`;
  }

  // NPC reactions to the player (if any)
  for (const r of npc_responses || []) {
    h += `<div class="my-4 pl-4" style="border-left: 2px solid #2a2218;">`;
    h += `<div class="font-system text-[9px] tracking-[0.1em] text-on-secondary-container uppercase mb-1">${esc(r.npc_name)}</div>`;
    h += `<p class="font-body text-[17px] leading-relaxed text-on-surface">${esc(r.pov)}</p>`;
    h += `</div>`;
  }

  // Separator
  h += `<div class="mt-6 mb-2"><svg width="100%" height="1"><line x1="0" y1="0" x2="100%" y2="0" stroke="#1e1b18" stroke-width="1" stroke-dasharray="2 3"/></svg></div>`;

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });
}

function showDeathMarker(cause) {
  const marker = $("#death-marker");
  const title = $("#death-marker-title");
  const quote = $("#death-marker-quote");
  if (marker) {
    marker.classList.remove("hidden");
    if (title) title.textContent = state.player.name;
    if (quote) quote.textContent = cause;
    marker.scrollIntoView({ behavior: "smooth" });
  }
}

function enterObservationMode() {
  const bottomBar = $("#bottom-bar");
  const obsSection = $("#obs-input-section");
  if (bottomBar) bottomBar.classList.add("hidden");
  if (obsSection) obsSection.classList.remove("hidden");
}

function showErasure(text) {
  const erasureText = $("#erasure-text");
  const erasureCycle = $("#erasure-cycle");
  if (erasureText) erasureText.textContent = text;
  if (erasureCycle) erasureCycle.textContent = `Run ${runId}`;
  showScreen("screen-erasure");
}

// -------------------------------------------------------------------
// Hamburger menu
// -------------------------------------------------------------------

const hamburgerBtn = $("#btn-hamburger");
const hamburgerPanel = $("#hamburger-panel");
const hamburgerOverlay = $("#hamburger-overlay");
const hamburgerIcon = $("#hamburger-icon");
const hamburgerCloseIcon = $("#hamburger-close-icon");

if (hamburgerBtn) {
  hamburgerBtn.addEventListener("click", () => {
    const isOpen = hamburgerPanel.classList.contains("open");
    if (isOpen) {
      hamburgerPanel.classList.remove("open");
      hamburgerOverlay.classList.add("hidden");
      hamburgerIcon.classList.remove("hidden");
      hamburgerCloseIcon.classList.add("hidden");
    } else {
      hamburgerPanel.classList.add("open");
      hamburgerOverlay.classList.remove("hidden");
      hamburgerIcon.classList.add("hidden");
      hamburgerCloseIcon.classList.remove("hidden");
    }
  });
}

if (hamburgerOverlay) {
  hamburgerOverlay.addEventListener("click", () => {
    hamburgerPanel.classList.remove("open");
    hamburgerOverlay.classList.add("hidden");
    hamburgerIcon.classList.remove("hidden");
    hamburgerCloseIcon.classList.add("hidden");
  });
}

// Map toggle from hamburger
const mapBtn = $("#btn-map-hamburger");
if (mapBtn) {
  mapBtn.addEventListener("click", () => {
    const mapContainer = $("#map-container");
    const manuscript = $("#manuscript");
    const bottomBar = $("#bottom-bar");
    const mapText = $("#map-btn-text");

    if (mapContainer.classList.contains("hidden")) {
      mapContainer.classList.remove("hidden");
      if (manuscript) manuscript.style.display = "none";
      if (bottomBar) bottomBar.classList.add("hidden");
      if (mapText) mapText.textContent = "MANUSCRIPT";
      if (typeof ChronosMap !== "undefined") ChronosMap.show(state, eraKey, runId);
    } else {
      mapContainer.classList.add("hidden");
      if (manuscript) manuscript.style.display = "";
      if (state && state.run_status === "active" && bottomBar) bottomBar.classList.remove("hidden");
      if (mapText) mapText.textContent = "MAP";
      if (typeof ChronosMap !== "undefined") ChronosMap.hide();
    }

    hamburgerPanel.classList.remove("open");
    hamburgerOverlay.classList.add("hidden");
    hamburgerIcon.classList.remove("hidden");
    hamburgerCloseIcon.classList.add("hidden");
  });
}

// New run from hamburger
const newRunBtn = $("#btn-new-run");
const newRunConfirm = $("#new-run-confirm");
if (newRunBtn) {
  newRunBtn.addEventListener("click", () => {
    if (newRunConfirm) newRunConfirm.classList.toggle("hidden");
  });
}
const newRunYes = $("#btn-new-run-yes");
if (newRunYes) {
  newRunYes.addEventListener("click", () => {
    hamburgerPanel.classList.remove("open");
    hamburgerOverlay.classList.add("hidden");
    hamburgerIcon.classList.remove("hidden");
    hamburgerCloseIcon.classList.add("hidden");
    if (newRunConfirm) newRunConfirm.classList.add("hidden");
    clearRunFromStorage();
    startNewRun();
  });
}
const newRunNo = $("#btn-new-run-no");
if (newRunNo) {
  newRunNo.addEventListener("click", () => {
    if (newRunConfirm) newRunConfirm.classList.add("hidden");
  });
}

// M key toggle
document.addEventListener("keydown", (e) => {
  if (e.key === "m" || e.key === "M") {
    if (!state || !runId) return;
    if (document.activeElement === $("#player-input")) return;
    if (document.activeElement === $("#obs-input")) return;
    if (mapBtn) mapBtn.click();
  }
});

// -------------------------------------------------------------------
// Progress bar — asymptotic curve tied to real elapsed time
// -------------------------------------------------------------------

let barRAF = null;
let barStart = 0;
const BAR_TAU = 60;

function startProgressBar() {
  const fill = $("#loading-bar-fill");
  if (fill) fill.style.width = "0%";
  barStart = performance.now();
  function tick() {
    const elapsed = (performance.now() - barStart) / 1000;
    const pct = (1 - Math.exp(-elapsed / BAR_TAU)) * 100;
    if (fill) fill.style.width = pct + "%";
    barRAF = requestAnimationFrame(tick);
  }
  barRAF = requestAnimationFrame(tick);
}

function completeProgressBar() {
  if (barRAF) { cancelAnimationFrame(barRAF); barRAF = null; }
  const fill = $("#loading-bar-fill");
  if (fill) {
    fill.style.transition = "width 0.4s ease";
    fill.style.width = "100%";
    setTimeout(() => { fill.style.transition = ""; }, 500);
  }
}

// -------------------------------------------------------------------
// Word definition overlay
// -------------------------------------------------------------------

(function initWordDefinitions() {
  const tooltip = document.getElementById("word-tooltip");
  if (!tooltip) return;

  let debounce = null;

  document.addEventListener("selectionchange", () => {
    clearTimeout(debounce);
    debounce = setTimeout(handleSelection, 300);
  });

  document.addEventListener("mousedown", () => {
    tooltip.style.display = "none";
  });

  async function handleSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) { tooltip.style.display = "none"; return; }

    const text = sel.toString().trim();
    if (!text || text.includes(" ") || text.length < 2 || text.length > 30) {
      tooltip.style.display = "none";
      return;
    }

    const container = sel.anchorNode && sel.anchorNode.parentElement;
    if (!container) return;
    const manuscript = document.getElementById("manuscript-inner") || document.getElementById("manuscript");
    if (!manuscript || !manuscript.contains(container)) return;

    try {
      const res = await fetch(`https://api.dictionaryapi.dev/api/v2/entries/en/${encodeURIComponent(text.toLowerCase())}`);
      if (!res.ok) { tooltip.style.display = "none"; return; }
      const data = await res.json();
      if (!data || !data[0]) return;

      const entry = data[0];
      const meaning = entry.meanings && entry.meanings[0];
      const def = meaning && meaning.definitions && meaning.definitions[0];
      if (!def) return;

      tooltip.innerHTML =
        `<div class="def-word">${esc(entry.word)}</div>` +
        (meaning.partOfSpeech ? `<div class="def-pos">${esc(meaning.partOfSpeech)}</div>` : "") +
        `<div class="def-meaning">${esc(def.definition)}</div>`;

      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      tooltip.style.left = Math.min(rect.left, window.innerWidth - 320) + "px";
      tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + "px";
      if (parseInt(tooltip.style.top) < 40) {
        tooltip.style.top = (rect.bottom + 8) + "px";
      }
      tooltip.style.display = "block";
    } catch {
      tooltip.style.display = "none";
    }
  }
})();

// -------------------------------------------------------------------
// Scroll-to-bottom button
// -------------------------------------------------------------------

(function () {
  var ms = document.getElementById("manuscript");
  var btn = document.getElementById("btn-scroll-bottom");
  if (!ms || !btn) return;

  ms.addEventListener("scroll", function () {
    var gap = ms.scrollHeight - ms.scrollTop - ms.clientHeight;
    if (gap > 200) btn.classList.remove("hidden");
    else btn.classList.add("hidden");
  });

  btn.addEventListener("click", function () {
    ms.scrollTo({ top: ms.scrollHeight, behavior: "smooth" });
  });
})();

// -------------------------------------------------------------------
// Utility
// -------------------------------------------------------------------

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
