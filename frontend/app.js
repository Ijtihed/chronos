/**
 * CHRONOS — Simulation-first game loop.
 *
 * Turn flow: world simulates (NPCs act) → player optionally acts →
 * narrative shows ambient activity first, player action as one thread.
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let state = null;
let runId = null;
let eraKey = null;
let turnInProgress = false;
let inputSetup = false;

// ── Screen management ─────────────────────────────────────────────────

function showScreen(id) {
  $$(".screen").forEach((s) => s.classList.remove("active"));
  const s = $(`#${id}`);
  if (s) s.classList.add("active");
}

// ── localStorage — session persistence, not game state ────────────────

function saveRunToStorage() {
  if (runId && eraKey) {
    localStorage.setItem("chronos_run_id", runId);
    localStorage.setItem("chronos_era_key", eraKey);
  }
  const tc = document.getElementById("turns-container");
  if (tc && runId) {
    localStorage.setItem("chronos_narrative_" + runId, tc.innerHTML);
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

// ── Check for existing run on load ────────────────────────────────────

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

// ── Start screen ──────────────────────────────────────────────────────

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

const beginYes = $("#btn-begin-yes");
if (beginYes) {
  beginYes.addEventListener("click", () => {
    const confirmEl = $("#begin-confirm");
    if (confirmEl) {
      confirmEl.classList.add("hidden");
      confirmEl.classList.add("was-confirmed");
    }
    clearRunFromStorage();
    startNewRun();
  });
}

const beginNo = $("#btn-begin-no");
if (beginNo) {
  beginNo.addEventListener("click", () => {
    const confirmEl = $("#begin-confirm");
    if (confirmEl) confirmEl.classList.add("hidden");
  });
}

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

const beginAgain = $("#btn-begin-again");
if (beginAgain) {
  beginAgain.addEventListener("click", () => {
    clearRunFromStorage();
    showScreen("screen-start");
    $("#btn-continue").classList.add("hidden");
    const confirmEl = $("#begin-confirm");
    if (confirmEl) {
      confirmEl.classList.add("hidden");
      confirmEl.classList.remove("was-confirmed");
    }
  });
}

// ── Run lifecycle ─────────────────────────────────────────────────────

async function startNewRun() {
  showScreen("screen-loading");

  $("#loading-era-label").textContent = "";
  $("#loading-era-desc").textContent = "";
  const eventsEl = $("#loading-events");
  const voicesEl = $("#loading-voices");
  const charSection = $("#loading-char-section");
  if (eventsEl) eventsEl.innerHTML = "";
  if (voicesEl) voicesEl.innerHTML = "";
  if (charSection) {
    charSection.classList.add("hidden");
    charSection.classList.remove("fade-in-up");
  }

  startProgressBar();

  try {
    const previewRes = await fetch("/api/run/preview", { method: "POST" });
    const preview = await previewRes.json();
    eraKey = preview.era_key;

    $("#loading-era-label").textContent =
      `${preview.era_name} \u2014 ${preview.year_start} AD`;
    $("#loading-era-desc").textContent = preview.description;

    if (eventsEl && preview.loading_events) {
      let h = "";
      preview.loading_events.forEach((ev, i) => {
        h += `<div class="border border-white/5 rounded-lg p-4 bg-white/[0.015] stagger-item" style="--i:${i + 2};">`;
        h += `<p class="text-sm leading-relaxed text-white/45">${esc(ev)}</p></div>`;
      });
      eventsEl.innerHTML = h;
    }

    if (voicesEl && preview.loading_voices) {
      let h = "";
      const base = (preview.loading_events ? preview.loading_events.length : 0) + 3;
      preview.loading_voices.forEach((v, i) => {
        h += `<blockquote class="pl-4 border-l-2 border-white/8 stagger-item" style="--i:${base + i};">`;
        h += `<p class="text-sm italic leading-relaxed text-white/50">\u201c${esc(v.quote)}\u201d</p>`;
        h += `<cite class="block mt-2 text-[10px] text-white/20 not-italic uppercase tracking-wider">\u2014 ${esc(v.source)}</cite>`;
        h += `</blockquote>`;
      });
      voicesEl.innerHTML = h;
    }

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

    if (charSection) {
      const charLabel = $("#loading-char-label");
      const charDesc = $("#loading-char-desc");
      if (charLabel) charLabel.textContent = "Your life begins";
      if (charDesc) {
        charDesc.innerHTML =
          `You are <span class="text-white/80 font-medium">${esc(state.player_name)}</span>, ` +
          `${esc(state.player_role.toLowerCase())}. ${esc(state.player_description)}`;
      }
      charSection.classList.add("fade-in-up");
      charSection.classList.remove("hidden");
    }

    completeProgressBar();

    setTimeout(() => {
      showScreen("screen-transition");
      setTimeout(() => enterGame(), 3000);
    }, 1200);
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

  const savedNarrative = runId
    ? localStorage.getItem("chronos_narrative_" + runId)
    : null;
  const isOldFormat = savedNarrative && savedNarrative.includes("font-body");

  if (savedNarrative && !isOldFormat && turnsContainer) {
    turnsContainer.innerHTML = savedNarrative;
    const manuscript = $("#manuscript");
    if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
  } else {
    if (turnsContainer) turnsContainer.innerHTML = "";
    if (isOldFormat) localStorage.removeItem("chronos_narrative_" + runId);

    const loc = state.current_location;
    const year = state.current_year;

    let h = `<div class="mb-10">`;
    h += `<div class="text-[10px] uppercase tracking-[0.15em] text-white/15 mb-4 font-medium">${esc(state.era_name)} \u2014 ${year} AD</div>`;
    h += `<p class="text-sm leading-loose text-white/60 mb-4">${esc(state.era_description)}</p>`;
    h += `<p class="text-sm leading-loose text-white/60 mb-4">You are <span class="text-white/80 font-medium">${esc(state.player_name)}</span>, ${esc(state.player_role.toLowerCase())}. ${esc(state.player_description)}</p>`;
    if (loc) {
      h += `<p class="text-sm leading-loose text-white/60">${esc(loc.description)}</p>`;
    }
    h += `</div>`;
    turnsContainer.innerHTML = h;
    saveRunToStorage();
  }

  if (state.run_status === "dead_observing") {
    const deathEvent = (state.confirmed_events || []).find(
      (e) =>
        e.knowledge_type === "witnessed" &&
        e.description &&
        e.description.includes("succumbs")
    );
    if (deathEvent) showDeathMarker(deathEvent.description);
    enterObservationMode();
  }
}

function updateTopBar() {
  const info = $("#top-bar-info");
  if (!info || !state) return;
  const locName = state.current_location ? state.current_location.name : "";
  info.textContent = `${state.current_year} AD \u00b7 ${locName}`;

  const deathInd = $("#death-indicator");
  const deathName = $("#death-indicator-name");
  if (state.run_status === "dead_observing" && deathInd) {
    deathInd.classList.remove("hidden");
    deathInd.classList.add("flex");
    if (deathName) deathName.textContent = `\u2020 ${state.player_name}`;
  }
}

// ── Input handling ────────────────────────────────────────────────────

function setupInput() {
  if (inputSetup) return;
  inputSetup = true;

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

async function submitTurn(text) {
  if (!text || !runId || turnInProgress) return;
  turnInProgress = true;

  const input = $("#player-input");
  const obsInput = $("#obs-input");
  const bottomBar = $("#bottom-bar");

  [input, obsInput].forEach((el) => {
    if (!el) return;
    el.value = "";
    el.disabled = true;
    el.placeholder = "\u00b7 \u00b7 \u00b7";
    el.style.pointerEvents = "none";
    el.style.opacity = "0.3";
  });
  if (bottomBar) bottomBar.style.pointerEvents = "none";

  const turnsContainer = $("#turns-container");
  const block = document.createElement("div");
  block.className = "turn-block mb-8";
  block.innerHTML =
    `<p class="text-sm italic text-white/20 mb-3 pl-3 border-l border-white/5">${esc(text)}</p>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">\u00b7 \u00b7 \u00b7</span></div>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });
  saveRunToStorage();

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
    updateTurnDimming();
    saveRunToStorage();

    if (data.death) {
      showDeathMarker(data.death.cause);
      enterObservationMode();
    }

    if (
      typeof ChronosMap !== "undefined" &&
      !$("#map-container").classList.contains("hidden")
    ) {
      ChronosMap.updateMarkers(state);
    }
  } catch (e) {
    block.innerHTML =
      `<p class="text-sm italic text-white/20 pl-3 border-l border-white/5">${esc(text)}</p>` +
      `<p class="text-[10px] text-red-400/60 mt-3 uppercase tracking-wider">Something went wrong. ${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    if (bottomBar) bottomBar.style.pointerEvents = "";
    [input, obsInput].forEach((el) => {
      if (!el) return;
      el.disabled = false;
      el.style.pointerEvents = "";
      el.style.opacity = "";
    });
    if (input) input.placeholder = "...";
    if (obsInput) obsInput.placeholder = "Travel only...";
    if (state && state.run_status === "active" && input) input.focus();
    if (state && state.run_status === "dead_observing" && obsInput)
      obsInput.focus();
  }
}

// ── Word-by-word streaming ────────────────────────────────────────────

function streamWords(container, text, msPerWord) {
  return new Promise((resolve) => {
    const words = text.split(/\s+/).filter(Boolean);
    if (!words.length) {
      resolve();
      return;
    }
    container.classList.add("word-stream");
    const spans = words.map((w) => {
      const s = document.createElement("span");
      s.textContent = w + " ";
      container.appendChild(s);
      return s;
    });
    let i = 0;
    function tick() {
      if (i >= spans.length) {
        resolve();
        return;
      }
      spans[i].classList.add("visible");
      i++;
      const manuscript = $("#manuscript");
      if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
      setTimeout(tick, msPerWord);
    }
    tick();
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Staggered turn rendering ──────────────────────────────────────────

async function renderTurnStaggered(el, playerText, data) {
  const pa = data.parsed_action || {};
  const { npc_responses, player_view: pv } = data;
  const ambient = data.ambient_activity || [];

  let h = `<div class="text-[10px] uppercase tracking-[0.15em] text-white/15 mb-4 font-medium">${pv.current_year} AD</div>`;

  if (ambient.length) {
    h += `<div class="space-y-2 mb-4">`;
    for (const a of ambient) {
      h += `<p class="text-sm leading-relaxed text-white/50">`;
      if (a.interacts_with) {
        h += `<span class="text-white/60 font-medium">${esc(a.npc_name)}</span> and <span class="text-white/60 font-medium">${esc(a.interacts_with)}</span> \u2014 `;
      } else {
        h += `<span class="text-white/60 font-medium">${esc(a.npc_name)}</span> \u2014 `;
      }
      h += `${esc(a.activity)}</p>`;
    }
    h += `</div>`;
  }

  h += `<p class="text-sm italic text-white/20 mb-4 pl-3 border-l border-white/5">${esc(playerText)}</p>`;

  if (pa.era_description) {
    h += `<p class="text-sm leading-loose text-white/70 mb-3">${esc(pa.era_description)}</p>`;
  }

  if (data.travel) {
    h += `<p class="text-sm leading-relaxed text-white/50 mb-3">${esc(
      `The journey from ${data.travel.from} to ${data.travel.to} takes ${data.travel.turns_spent} turns.`
    )}</p>`;
  }

  const rumors = pv.rumors || [];
  if (rumors.length) {
    for (const r of rumors) {
      h += `<p class="text-sm leading-relaxed italic text-amber-300/40 mb-4">${esc(r.description)}</p>`;
    }
  }

  const npcIds = [];
  for (let i = 0; i < (npc_responses || []).length; i++) {
    const id = `npc-stagger-${Date.now()}-${i}`;
    npcIds.push(id);
    h += `<div id="${id}" class="npc-block-stagger pl-4 border-l-2 border-white/10 my-4">`;
    h += `<div class="text-[9px] uppercase tracking-[0.15em] text-white/25 mb-1.5 font-medium">${esc(npc_responses[i].npc_name)}</div>`;
    h += `<p class="text-sm leading-relaxed text-white/55 npc-pov-text"></p>`;
    h += `</div>`;
  }

  h += `<div class="mt-6 mb-2"><div class="w-full h-px bg-white/[0.03]"></div></div>`;

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });

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

// ── Turn dimming — older turns recede ─────────────────────────────────

function updateTurnDimming() {
  const blocks = document.querySelectorAll(".turn-block");
  const total = blocks.length;
  blocks.forEach((block, index) => {
    const age = total - 1 - index;
    const opacity = Math.max(0.35, 1 - age * 0.15);
    block.style.setProperty("--turn-opacity", opacity);
  });
}

// ── Death / observation ───────────────────────────────────────────────

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

// ── Erasure ───────────────────────────────────────────────────────────

function showErasure(text) {
  showScreen("screen-erasure");

  const dimLayer = $("#erasure-dim-layer");
  const content = $("#erasure-content");
  const erasureText = $("#erasure-text");
  const restart = $("#erasure-restart");

  if (content) {
    content.style.transition = "none";
    content.classList.remove("visible");
  }
  if (restart) {
    restart.style.transition = "none";
    restart.classList.remove("visible");
  }

  requestAnimationFrame(() => {
    if (content) content.style.transition = "";
    if (restart) restart.style.transition = "";
    if (dimLayer) dimLayer.classList.add("active");
  });

  setTimeout(() => {
    if (erasureText) erasureText.textContent = text;
    if (content) content.classList.add("visible");
  }, 10000 + 4000);

  setTimeout(() => {
    if (restart) restart.classList.add("visible");
  }, 10000 + 4000 + 4000);
}

// ── Hamburger menu ────────────────────────────────────────────────────

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
  const nrc = $("#new-run-confirm");
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

// Map toggle
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
      if (typeof ChronosMap !== "undefined")
        ChronosMap.show(state, eraKey, runId);
    } else {
      mapContainer.classList.add("hidden");
      if (manuscript) manuscript.style.display = "";
      if (state && state.run_status === "active" && bottomBar)
        bottomBar.classList.remove("hidden");
      if (mapText) mapText.textContent = "Map";
      if (typeof ChronosMap !== "undefined") ChronosMap.hide();
    }
    closePanel();
  });
}

// New run
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

// M key shortcut
document.addEventListener("keydown", (e) => {
  if (e.key === "m" || e.key === "M") {
    if (!state || !runId) return;
    if (document.activeElement === $("#player-input")) return;
    if (document.activeElement === $("#obs-input")) return;
    if (mapBtn) mapBtn.click();
  }
});

// ── Progress bar ──────────────────────────────────────────────────────

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
  if (barRAF) {
    cancelAnimationFrame(barRAF);
    barRAF = null;
  }
  const fill = $("#loading-bar-fill");
  if (fill) {
    fill.style.transition = "width 0.4s ease";
    fill.style.width = "100%";
    setTimeout(() => {
      fill.style.transition = "";
    }, 500);
  }
}

// ── Selection overlays — word definition + historical context ─────────

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
    var ms =
      document.getElementById("manuscript-inner") ||
      document.getElementById("manuscript");
    return ms && ms.contains(el);
  }

  function positionAt(el, rect, maxW) {
    var left = Math.min(
      rect.left + rect.width / 2 - 40,
      window.innerWidth - (maxW || 320)
    );
    if (left < 8) left = 8;
    el.style.left = left + "px";
    el.style.top = rect.top - el.offsetHeight - 8 + "px";
    if (parseInt(el.style.top) < 40) {
      el.style.top = rect.bottom + 8 + "px";
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
        var res = await fetch(
          "https://api.dictionaryapi.dev/api/v2/entries/en/" +
            encodeURIComponent(text.toLowerCase())
        );
        if (!res.ok) return;
        var data = await res.json();
        if (!data || !data[0]) return;
        var entry = data[0];
        var meaning = entry.meanings && entry.meanings[0];
        var def = meaning && meaning.definitions && meaning.definitions[0];
        if (!def) return;

        tooltip.innerHTML =
          '<div class="def-word">' +
          esc(entry.word) +
          "</div>" +
          (meaning.partOfSpeech
            ? '<div class="def-pos">' + esc(meaning.partOfSpeech) + "</div>"
            : "") +
          '<div class="def-meaning">' +
          esc(def.definition) +
          "</div>";
        tooltip.style.display = "block";
        positionAt(tooltip, rect, 320);
      } catch {
        /* dictionary API failure is silent */
      }
    } else if (hasSpaces && text.length >= 10) {
      tooltip.style.display = "none";
      pendingText = text.substring(0, 500);
      ctxBtn.style.display = "block";
      positionAt(ctxBtn, rect, 120);
    }
  }

  ctxBtn.addEventListener("click", async function () {
    if (!pendingText || !runId) return;
    var rect = {
      left: parseInt(ctxBtn.style.left),
      top: parseInt(ctxBtn.style.top),
      width: 80,
      height: 20,
      bottom: parseInt(ctxBtn.style.top) + 28,
    };

    ctxBtn.style.display = "none";
    ctxPanel.innerHTML =
      '<span class="ctx-loading">Searching the archives\u2026</span>';
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
      ctxPanel.textContent =
        "The archives offer no further illumination on this matter.";
    }
    ctxPanel.style.display = "block";
    positionAt(ctxPanel, rect, 380);
    pendingText = "";
  });
})();

// ── Scroll-to-bottom button ───────────────────────────────────────────

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

// ── Time-skip control ─────────────────────────────────────────────────

(function initSkipControl() {
  const btn = $("#btn-skip");
  const popup = $("#skip-popup");
  if (!btn || !popup) return;

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    popup.classList.toggle("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!popup.classList.contains("hidden") && !popup.contains(e.target) && e.target !== btn) {
      popup.classList.add("hidden");
    }
  });

  popup.querySelectorAll(".skip-option").forEach((opt) => {
    opt.addEventListener("click", () => {
      const ticks = parseInt(opt.dataset.ticks, 10);
      popup.classList.add("hidden");
      executeSkip(ticks);
    });
  });
})();

async function executeSkip(ticks) {
  if (!runId || turnInProgress) return;
  turnInProgress = true;

  const input = $("#player-input");
  const bottomBar = $("#bottom-bar");
  const skipBtn = $("#btn-skip");

  if (input) {
    input.disabled = true;
    input.placeholder = "\u00b7 \u00b7 \u00b7";
    input.style.pointerEvents = "none";
    input.style.opacity = "0.3";
  }
  if (skipBtn) skipBtn.style.pointerEvents = "none";
  if (bottomBar) bottomBar.style.pointerEvents = "none";

  const turnsContainer = $("#turns-container");
  const block = document.createElement("div");
  block.className = "turn-block mb-8";
  const label = ticks === 30 ? "1 month" : `${ticks} turn${ticks > 1 ? "s" : ""}`;
  block.innerHTML =
    `<p class="text-sm italic text-white/20 mb-3 pl-3 border-l border-white/5">Time passes\u2026 (${esc(label)})</p>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">\u00b7 \u00b7 \u00b7</span></div>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch(`/api/run/${runId}/skip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticks }),
    });
    if (!res.ok)
      throw new Error(
        (await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`
      );
    const data = await res.json();
    state = data.player_view;

    let h = `<div class="text-[10px] uppercase tracking-[0.15em] text-white/15 mb-4 font-medium">${state.current_year} AD</div>`;
    h += `<p class="text-sm italic text-white/20 mb-4 pl-3 border-l border-white/5">Time passes\u2026 (${esc(label)})</p>`;
    h += `<p class="text-sm leading-loose text-white/55 mb-3">${esc(data.regrounding)}</p>`;
    h += `<div class="mt-6 mb-2"><div class="w-full h-px bg-white/[0.03]"></div></div>`;
    block.innerHTML = h;

    updateTopBar();
    updateTurnDimming();
    saveRunToStorage();

    if (
      typeof ChronosMap !== "undefined" &&
      !$("#map-container").classList.contains("hidden")
    ) {
      ChronosMap.updateMarkers(state);
    }
  } catch (e) {
    block.innerHTML =
      `<p class="text-sm italic text-white/20 pl-3 border-l border-white/5">Time passes\u2026 (${esc(label)})</p>` +
      `<p class="text-[10px] text-red-400/60 mt-3 uppercase tracking-wider">Something went wrong. ${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    if (bottomBar) bottomBar.style.pointerEvents = "";
    if (skipBtn) skipBtn.style.pointerEvents = "";
    if (input) {
      input.disabled = false;
      input.style.pointerEvents = "";
      input.style.opacity = "";
      input.placeholder = "...";
      input.focus();
    }
  }
}

// ── Utility ───────────────────────────────────────────────────────────

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
