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
    state = runData.player_view;
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

  const savedNarrative = runId ? localStorage.getItem("chronos_narrative_" + runId) : null;
  if (savedNarrative && turnsContainer) {
    turnsContainer.innerHTML = savedNarrative;
    const manuscript = $("#manuscript");
    if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
  } else {
    if (turnsContainer) turnsContainer.innerHTML = "";
    const loc = state.current_location;
    const year = state.current_year;

    let introHtml = `<div class="mb-12">`;
    introHtml += `<div class="font-system text-[10px] tracking-[0.15em] text-tertiary-container mb-4">${esc(state.era_name)} — ${year} AD</div>`;
    introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface known mb-4">${esc(state.era_description)}</p>`;
    introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface known mb-4">You are <strong class="text-primary-fixed">${esc(state.player_name)}</strong>, ${esc(state.player_role.toLowerCase())}. ${esc(state.player_description)}</p>`;
    if (loc) {
      introHtml += `<p class="font-body text-[18px] leading-relaxed text-on-surface known">${esc(loc.description)}</p>`;
    }
    introHtml += `</div>`;
    turnsContainer.innerHTML = introHtml;
    saveRunToStorage();
  }

  if (state.run_status === "dead_observing") {
    const deathEvent = (state.confirmed_events || []).find(e => e.knowledge_type === "witnessed" && e.description && e.description.includes("succumbs"));
    if (deathEvent) showDeathMarker(deathEvent.description);
    enterObservationMode();
  }
}

function updateTopBar() {
  const info = $("#top-bar-info");
  if (!info || !state) return;
  const locName = state.current_location ? state.current_location.name : "";
  const year = state.current_year;
  info.textContent = `${year} AD · ${locName}`;

  const deathInd = $("#death-indicator");
  const deathName = $("#death-indicator-name");
  if (state.run_status === "dead_observing" && deathInd) {
    deathInd.classList.remove("hidden");
    deathInd.classList.add("flex");
    if (deathName) deathName.textContent = `† ${state.player_name}`;
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
      if (e.key === "Enter" && !turnInProgress && !input.disabled) {
        e.preventDefault();
        submitTurn(input.value.trim());
      }
    });
  }
  if (obsInput) {
    obsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !turnInProgress && !obsInput.disabled) {
        e.preventDefault();
        submitTurn(obsInput.value.trim());
      }
    });
  }
}

let turnInProgress = false;

async function submitTurn(text) {
  if (!text || !runId || turnInProgress) return;
  turnInProgress = true;

  const input = $("#player-input");
  const obsInput = $("#obs-input");

  // Lock ALL input immediately
  if (input) {
    input.value = "";
    input.disabled = true;
    input.placeholder = "· · ·";
    input.style.pointerEvents = "none";
    input.style.opacity = "0.3";
  }
  if (obsInput) {
    obsInput.value = "";
    obsInput.disabled = true;
    obsInput.placeholder = "· · ·";
    obsInput.style.pointerEvents = "none";
    obsInput.style.opacity = "0.3";
  }
  // Also block the bottom bar entirely
  const bottomBar = $("#bottom-bar");
  if (bottomBar) bottomBar.style.pointerEvents = "none";

  const turnsContainer = $("#turns-container");
  const block = document.createElement("div");
  block.className = "mb-8";
  block.innerHTML = `<p class="font-body italic text-[16px] text-on-secondary-container">${esc(text)}</p>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">· · ·</span></div>`;
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
    state = data.player_view;

    if (data.erasure) {
      block.remove();
      clearRunFromStorage();
      turnInProgress = false;
      showErasure(data.erasure);
      return;
    }

    await renderTurnStaggered(block, text, data);
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
    block.innerHTML = `<p class="font-body italic text-[16px] text-on-secondary-container">${esc(text)}</p><p class="font-system text-[10px] text-dead-tint mt-2">Something went wrong. ${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    const bottomBar = $("#bottom-bar");
    if (bottomBar) bottomBar.style.pointerEvents = "";
    if (input) {
      input.disabled = false;
      input.placeholder = "";
      input.style.pointerEvents = "";
      input.style.opacity = "";
    }
    if (obsInput) {
      obsInput.disabled = false;
      obsInput.placeholder = "TRAVEL ONLY...";
      obsInput.style.pointerEvents = "";
      obsInput.style.opacity = "";
    }
    if (state && state.run_status === "active" && input) input.focus();
    if (state && state.run_status === "dead_observing" && obsInput) obsInput.focus();
  }
}

// -------------------------------------------------------------------
// Word-by-word streaming animation
// -------------------------------------------------------------------

function streamWords(container, text, msPerWord) {
  return new Promise((resolve) => {
    const words = text.split(/\s+/).filter(Boolean);
    if (!words.length) { resolve(); return; }
    container.classList.add("word-stream");
    const spans = words.map((w) => {
      const s = document.createElement("span");
      s.textContent = w + " ";
      container.appendChild(s);
      return s;
    });
    let i = 0;
    function tick() {
      if (i >= spans.length) { resolve(); return; }
      spans[i].classList.add("visible");
      i++;
      const manuscript = $("#manuscript");
      if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
      setTimeout(tick, msPerWord);
    }
    tick();
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// -------------------------------------------------------------------
// Staggered turn rendering
// -------------------------------------------------------------------

async function renderTurnStaggered(el, playerText, data) {
  const { parsed_action: pa, npc_responses, player_view: pv } = data;
  const ambient = data.ambient_activity || [];

  let h = `<div class="font-system text-[10px] tracking-[0.12em] text-[#2a2218] mb-4">${pv.current_year} AD</div>`;

  if (ambient.length) {
    for (const a of ambient) {
      h += `<p class="font-body text-[17px] leading-relaxed known mb-3">`;
      if (a.interacts_with) {
        h += `<span class="text-primary-container">${esc(a.npc_name)}</span> and <span class="text-primary-container">${esc(a.interacts_with)}</span> — `;
      } else {
        h += `<span class="text-primary-container">${esc(a.npc_name)}</span> — `;
      }
      h += `${esc(a.activity)}</p>`;
    }
  }

  h += `<p class="font-body italic text-[16px] text-on-secondary-container mb-3 mt-4">${esc(playerText)}</p>`;

  if (pa.era_description) {
    h += `<p class="font-body text-[18px] leading-relaxed known mb-3">${esc(pa.era_description)}</p>`;
  }

  if (data.travel) {
    h += `<p class="font-body text-[17px] leading-relaxed known mb-3">${esc(
      `The journey from ${data.travel.from} to ${data.travel.to} takes ${data.travel.turns_spent} turns.`
    )}</p>`;
  }

  // Render rumors from PlayerView
  const rumors = pv.rumors || [];
  if (rumors.length) {
    for (const r of rumors) {
      h += `<p class="font-body text-[16px] leading-relaxed rumor mb-2">${esc(r.description)}</p>`;
    }
  }

  // NPC placeholders for staggered reveal
  const npcIds = [];
  for (let i = 0; i < (npc_responses || []).length; i++) {
    const id = `npc-stagger-${Date.now()}-${i}`;
    npcIds.push(id);
    h += `<div id="${id}" class="npc-block-stagger my-4 pl-4" style="border-left: 2px solid #2a2218;">`;
    h += `<div class="font-system text-[9px] tracking-[0.1em] text-on-secondary-container mb-1">${esc(npc_responses[i].npc_name)}</div>`;
    h += `<p class="font-body text-[17px] leading-relaxed known npc-pov-text"></p>`;
    h += `</div>`;
  }

  h += `<div class="mt-6 mb-2"><svg width="100%" height="1"><line x1="0" y1="0" x2="100%" y2="0" stroke="#1e1b18" stroke-width="1" stroke-dasharray="2 3"/></svg></div>`;

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });

  // Stagger NPC responses — one at a time with word streaming
  for (let i = 0; i < npcIds.length; i++) {
    const npcEl = document.getElementById(npcIds[i]);
    if (!npcEl) continue;

    if (i > 0) await sleep(600);

    npcEl.classList.add("revealed");
    const povTextEl = npcEl.querySelector(".npc-pov-text");
    if (povTextEl && npc_responses[i].pov) {
      await streamWords(povTextEl, npc_responses[i].pov, 35);
    }
  }
}

// Keep old renderTurn as fallback for saved narrative restoration
function renderTurn(el, playerText, data) {
  renderTurnStaggered(el, playerText, data);
}

function showDeathMarker(cause) {
  const marker = $("#death-marker");
  const title = $("#death-marker-title");
  const quote = $("#death-marker-quote");
  if (marker) {
    marker.classList.remove("hidden");
    if (title) title.textContent = state.player_name;
    if (quote) quote.textContent = cause;
    marker.scrollIntoView({ behavior: "smooth" });
  }
}

function enterObservationMode() {
  const bottomBar = $("#bottom-bar");
  const obsSection = $("#obs-input-section");
  const manuscript = $("#manuscript");
  if (bottomBar) bottomBar.classList.add("hidden");
  if (obsSection) obsSection.classList.remove("hidden");
  if (manuscript) manuscript.classList.add("observation-muted");
}

function showErasure(text) {
  showScreen("screen-erasure");

  const dimLayer = $("#erasure-dim-layer");
  const content = $("#erasure-content");
  const erasureText = $("#erasure-text");
  const restart = $("#erasure-restart");

  if (content) content.classList.remove("visible");
  if (restart) restart.classList.remove("visible");

  // Phase 1: screen dims over 8 seconds
  requestAnimationFrame(() => {
    if (dimLayer) dimLayer.classList.add("active");
  });

  // Phase 2: 4 second pause, then chronicle fades in
  setTimeout(() => {
    if (erasureText) erasureText.textContent = text;
    if (content) content.classList.add("visible");
  }, 8000 + 4000);

  // Phase 3: 4 more seconds, then "begin again?" appears
  setTimeout(() => {
    if (restart) restart.classList.add("visible");
  }, 8000 + 4000 + 4000);
}

// -------------------------------------------------------------------
// Hamburger menu
// -------------------------------------------------------------------

const hamburgerBtn = $("#btn-hamburger");
const hamburgerPanel = $("#hamburger-panel");
const hamburgerOverlay = $("#hamburger-overlay");
const hamburgerIcon = $("#hamburger-icon");
const hamburgerCloseIcon = $("#hamburger-close-icon");
const panelCloseBtn = $("#btn-panel-close");

function openPanel() {
  hamburgerPanel.classList.add("open");
  hamburgerOverlay.classList.remove("hidden");
  if (hamburgerIcon) hamburgerIcon.classList.add("hidden");
  if (hamburgerCloseIcon) hamburgerCloseIcon.classList.remove("hidden");
}

function closePanel() {
  hamburgerPanel.classList.remove("open");
  hamburgerOverlay.classList.add("hidden");
  if (hamburgerIcon) hamburgerIcon.classList.remove("hidden");
  if (hamburgerCloseIcon) hamburgerCloseIcon.classList.add("hidden");
  var nrc = $("#new-run-confirm");
  if (nrc) nrc.classList.add("hidden");
}

if (hamburgerBtn) {
  hamburgerBtn.addEventListener("click", () => {
    if (hamburgerPanel.classList.contains("open")) closePanel();
    else openPanel();
  });
}

if (hamburgerOverlay) hamburgerOverlay.addEventListener("click", closePanel);
if (panelCloseBtn) panelCloseBtn.addEventListener("click", closePanel);

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
      if (mapText) mapText.textContent = "Manuscript";
      if (typeof ChronosMap !== "undefined") ChronosMap.show(state, eraKey, runId, true);
    } else {
      mapContainer.classList.add("hidden");
      if (manuscript) manuscript.style.display = "";
      if (state && state.run_status === "active" && bottomBar) bottomBar.classList.remove("hidden");
      if (mapText) mapText.textContent = "Map";
      if (typeof ChronosMap !== "undefined") ChronosMap.hide();
    }

    closePanel();
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
    closePanel();
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
// Selection overlay: single word → definition, multi-word → context
// -------------------------------------------------------------------

(function initSelectionOverlays() {
  var tooltip = document.getElementById("word-tooltip");
  var ctxBtn = document.getElementById("context-btn");
  var ctxPanel = document.getElementById("context-panel");
  if (!tooltip || !ctxBtn || !ctxPanel) return;

  var debounce = null;
  var pendingText = "";

  function hideAll() {
    tooltip.style.display = "none";
    ctxBtn.style.display = "none";
    ctxPanel.style.display = "none";
    pendingText = "";
  }

  document.addEventListener("mousedown", function (e) {
    if (e.target === ctxBtn || ctxBtn.contains(e.target)) return;
    hideAll();
  });

  document.addEventListener("selectionchange", function () {
    clearTimeout(debounce);
    debounce = setTimeout(handleSelection, 300);
  });

  function inManuscript(node) {
    if (!node) return false;
    var el = node.parentElement || node;
    var ms = document.getElementById("manuscript-inner") || document.getElementById("manuscript");
    return ms && ms.contains(el);
  }

  function positionAt(el, rect, maxW) {
    var left = Math.min(rect.left + rect.width / 2 - 40, window.innerWidth - (maxW || 320));
    if (left < 8) left = 8;
    el.style.left = left + "px";
    el.style.top = (rect.top - el.offsetHeight - 8) + "px";
    if (parseInt(el.style.top) < 40) {
      el.style.top = (rect.bottom + 8) + "px";
    }
  }

  async function handleSelection() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;

    var text = sel.toString().trim();
    if (!text || text.length < 2) return;
    if (!inManuscript(sel.anchorNode)) return;

    var range = sel.getRangeAt(0);
    var rect = range.getBoundingClientRect();
    var hasSpaces = text.includes(" ");

    if (!hasSpaces && text.length <= 30) {
      ctxBtn.style.display = "none";
      try {
        var res = await fetch("https://api.dictionaryapi.dev/api/v2/entries/en/" + encodeURIComponent(text.toLowerCase()));
        if (!res.ok) return;
        var data = await res.json();
        if (!data || !data[0]) return;
        var entry = data[0];
        var meaning = entry.meanings && entry.meanings[0];
        var def = meaning && meaning.definitions && meaning.definitions[0];
        if (!def) return;

        tooltip.innerHTML =
          '<div class="def-word">' + esc(entry.word) + "</div>" +
          (meaning.partOfSpeech ? '<div class="def-pos">' + esc(meaning.partOfSpeech) + "</div>" : "") +
          '<div class="def-meaning">' + esc(def.definition) + "</div>";
        tooltip.style.display = "block";
        positionAt(tooltip, rect, 320);
      } catch { /* ignore */ }
    } else if (hasSpaces && text.length >= 10) {
      tooltip.style.display = "none";
      pendingText = text.substring(0, 500);
      ctxBtn.style.display = "block";
      positionAt(ctxBtn, rect, 120);
    }
  }

  ctxBtn.addEventListener("click", async function () {
    if (!pendingText || !runId) return;
    var rect = { left: parseInt(ctxBtn.style.left), top: parseInt(ctxBtn.style.top), width: 80, height: 20, bottom: parseInt(ctxBtn.style.top) + 28 };

    ctxBtn.style.display = "none";
    ctxPanel.innerHTML = '<span class="ctx-loading">Searching the archives...</span>';
    ctxPanel.style.display = "block";
    positionAt(ctxPanel, rect, 380);

    try {
      var res = await fetch("/api/run/" + runId + "/context", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: pendingText }),
      });
      if (!res.ok) throw new Error();
      var data = await res.json();
      ctxPanel.textContent = data.context;
    } catch {
      ctxPanel.textContent = "The archives offer no further illumination on this matter.";
    }
    ctxPanel.style.display = "block";
    positionAt(ctxPanel, rect, 380);
    pendingText = "";
  });
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
