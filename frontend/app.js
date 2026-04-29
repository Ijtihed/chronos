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
let defaultSkipTicks = 7;
// Set to true when the backend returns 402 cost_cap_hard. Prevents further
// turn submissions in this session without a page reload / new run.
let hardCapReached = false;

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

// Per-run localStorage keys that this app owns. Listed so we can
// nuke everything for a given run_id consistently when the run is
// abandoned or reset, instead of leaking garbage forever.
const _PER_RUN_KEY_PREFIXES = [
  "chronos_narrative_",
  "chronos_notes_",
  "chronos_map_view_",
  "chronos_graph_pins_",
  "chronos_graph_view_",
];

function clearRunStateFor(runId) {
  if (!runId) return;
  _PER_RUN_KEY_PREFIXES.forEach((p) => {
    try { localStorage.removeItem(p + runId); } catch {}
  });
}

function clearRunFromStorage() {
  const oldId = localStorage.getItem("chronos_run_id");
  clearRunStateFor(oldId);
  localStorage.removeItem("chronos_run_id");
  localStorage.removeItem("chronos_era_key");
  localStorage.removeItem(_OVERLAY_KEY);
  // Clean up any orphaned per-run keys for runs other than the
  // current one. Walk a snapshot of keys (length-stable) since
  // removeItem mutates the index.
  const allKeys = [];
  for (let i = 0; i < localStorage.length; i++) {
    allKeys.push(localStorage.key(i));
  }
  allKeys.forEach((k) => {
    if (!k) return;
    if (_PER_RUN_KEY_PREFIXES.some((p) => k.startsWith(p))) {
      try { localStorage.removeItem(k); } catch {}
    }
  });
}

function getSavedRun() {
  const id = localStorage.getItem("chronos_run_id");
  const era = localStorage.getItem("chronos_era_key");
  return id ? { runId: id, eraKey: era } : null;
}

// ── Overlay state — manuscript | map | connections ────────────────────
//
// Persisted per-key (not per-run) so reload lands the player back on
// whatever they were viewing. Overlay-specific state (map zoom/center,
// graph pinned positions and pan/zoom transform) is persisted per-run
// inside the overlay modules themselves; this only tracks the page.

const _OVERLAY_KEY = "chronos_last_overlay";
const _OVERLAY_VALUES = new Set(["manuscript", "map", "connections"]);

function setLastOverlay(name) {
  if (!_OVERLAY_VALUES.has(name)) return;
  try { localStorage.setItem(_OVERLAY_KEY, name); } catch {}
}

function getLastOverlay() {
  try {
    const v = localStorage.getItem(_OVERLAY_KEY);
    if (_OVERLAY_VALUES.has(v)) return v;
    if (v != null) localStorage.removeItem(_OVERLAY_KEY);
    return "manuscript";
  } catch { return "manuscript"; }
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
  hardCapReached = false;
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
        h += `<cite class="block mt-2 text-[10px] text-white/55 not-italic uppercase tracking-wider">\u2014 ${esc(v.source)}</cite>`;
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
          `${esc(state.player_description)} ` +
          `<span class="text-white/40">Your name is ${esc(state.player_name)}.</span>`;
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
    h += `<div class="text-[11px] uppercase tracking-[0.15em] text-white/55 mb-4 font-semibold">${esc(state.era_name)} \u2014 ${year} AD</div>`;
    h += `<p class="text-sm leading-loose text-white/60 mb-4">${esc(state.era_description)}</p>`;
    h += `<p class="text-sm leading-loose text-white/60 mb-3">${esc(state.player_description)}</p>`;
    h += `<p class="text-xs leading-loose text-white/65 mb-4">Your name is <span class="text-white/85 font-semibold">${esc(state.player_name)}</span>.</p>`;
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

  // Restore the overlay the player was last viewing. Defer one frame
  // so screen-game has been laid out and Leaflet/d3 measure correctly.
  const last = getLastOverlay();
  if (last === "map") {
    requestAnimationFrame(() => showMapOverlay());
  } else if (last === "connections") {
    requestAnimationFrame(() => showGraphOverlay());
  }
  // "manuscript" is the default; nothing to do.
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

  updateClock();
  updateCostIndicator();
}

// ── LLM provider cost indicator ───────────────────────────────────────

function updateCostIndicator() {
  if (!state) return;
  const el = document.getElementById("cost-indicator");
  const cur = document.getElementById("cost-current");
  const goal = document.getElementById("cost-goal");
  if (!el || !cur || !goal) return;

  const costEur = Number(state.cost_eur || 0);
  const softCap = Number(state.cost_cap_soft_eur || 1.0);
  const hardCap = Number(state.cost_cap_hard_eur || 2.0);
  const capState = state.cost_cap_state || "none";

  el.classList.remove("hidden");
  el.classList.add("flex");

  cur.textContent = `\u20ac${costEur.toFixed(2)}`;
  goal.textContent = `\u20ac${softCap.toFixed(2)}`;

  el.classList.remove(
    "cost-warning", "cost-soft-exceeded", "cost-hard-exceeded",
  );
  if (capState === "hard" || costEur >= hardCap) {
    el.classList.add("cost-hard-exceeded");
  } else if (capState === "soft_crossed" || costEur >= softCap) {
    el.classList.add("cost-soft-exceeded");
  } else if (costEur >= softCap * 0.8) {
    el.classList.add("cost-warning");
  }

  // Soft-cap banner (show once per run, dismissible via localStorage).
  const banner = document.getElementById("cost-soft-banner");
  if (banner && state.run_id) {
    const dismissKey = `cost_soft_dismissed_${state.run_id}`;
    const dismissed = localStorage.getItem(dismissKey) === "1";
    const shouldShow =
      capState === "soft_crossed" && !dismissed && capState !== "hard";
    banner.classList.toggle("hidden", !shouldShow);
    banner.classList.toggle("flex", shouldShow);
  }

  // Hard-cap overlay.
  const overlay = document.getElementById("cost-hard-overlay");
  const overlayText = document.getElementById("cost-hard-overlay-text");
  if (overlay) {
    const showHard = capState === "hard";
    overlay.classList.toggle("hidden", !showHard);
    overlay.classList.toggle("flex", showHard);
    if (showHard && overlayText) {
      overlayText.textContent =
        `This run has reached \u20ac${costEur.toFixed(2)} (cap \u20ac${hardCap.toFixed(2)}). ` +
        `Further turns are blocked. You can still read the world and end the run.`;
    }
  }
}

(function initCostBannerHandlers() {
  document.addEventListener("DOMContentLoaded", () => {
    const dismiss = document.getElementById("cost-soft-banner-dismiss");
    if (dismiss) {
      dismiss.addEventListener("click", () => {
        const banner = document.getElementById("cost-soft-banner");
        if (banner) {
          banner.classList.add("hidden");
          banner.classList.remove("flex");
        }
        if (state && state.run_id) {
          localStorage.setItem(`cost_soft_dismissed_${state.run_id}`, "1");
        }
      });
    }
    const hardClose = document.getElementById("cost-hard-overlay-close");
    if (hardClose) {
      hardClose.addEventListener("click", () => {
        const overlay = document.getElementById("cost-hard-overlay");
        if (overlay) {
          overlay.classList.add("hidden");
          overlay.classList.remove("flex");
        }
      });
    }
    const hardEnd = document.getElementById("cost-hard-overlay-end");
    if (hardEnd) {
      hardEnd.addEventListener("click", async () => {
        if (!runId) { showScreen("screen-start"); return; }
        try {
          await fetch(`/api/run/${runId}`, { method: "DELETE" });
        } catch (_) {}
        clearRunFromStorage();
        runId = null;
        state = null;
        hardCapReached = false;
        const overlay = document.getElementById("cost-hard-overlay");
        if (overlay) { overlay.classList.add("hidden"); overlay.classList.remove("flex"); }
        showScreen("screen-start");
        const continueBtn = document.getElementById("btn-continue");
        if (continueBtn) continueBtn.classList.add("hidden");
      });
    }
  });
})();

function updateClock() {
  const clockEl = $("#clock-element");
  const seasonEl = $("#clock-season");
  if (!clockEl || !seasonEl || !state) return;

  clockEl.classList.remove("hidden");
  clockEl.classList.add("flex");

  const year = state.current_year;
  const turn = state.turn || 0;
  const weekInYear = (turn % 52) + 1;
  const seasons = ["winter", "spring", "summer", "autumn"];
  const season = seasons[Math.floor(((weekInYear - 1) % 52) / 13)];

  seasonEl.textContent = `wk ${weekInYear} \u00b7 ${season}`;
}

// ── Time scale presets ────────────────────────────────────────────────

(function initTimePresets() {
  const presets = document.querySelectorAll(".time-preset");
  presets.forEach(function (btn) {
    btn.addEventListener("click", function () {
      presets.forEach(function (b) { b.classList.remove("active-preset"); });
      btn.classList.add("active-preset");
      defaultSkipTicks = parseInt(btn.dataset.ticks, 10);
    });
  });
})();

// ── Input handling ────────────────────────────────────────────────────

function setupInput() {
  if (inputSetup) return;
  inputSetup = true;

  const input = $("#player-input");
  const obsInput = $("#obs-input");

  if (input) {
    input.addEventListener("keydown", (e) => {
      if (hardCapReached) return;
      if (e.key === "Enter" && !turnInProgress && !input.disabled) {
        e.preventDefault();
        submitTurn(input.value.trim());
      }
    });
  }
  if (obsInput) {
    obsInput.addEventListener("keydown", (e) => {
      if (hardCapReached) return;
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
  userScrolledUp = false;
  cancelActiveStreams();

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
    `<p class="text-sm italic text-white/55 mb-3 pl-3 border-l border-white/15">${esc(text)}</p>` +
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
    if (res.status === 402) {
      const body = await res.json().catch(() => ({}));
      const d = body.detail || {};
      if (d && d.code === "cost_cap_hard") {
        hardCapReached = true;
        if (state) state.cost_cap_state = "hard";
        updateCostIndicator();
        block.remove();
        return;
      }
    }
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
      ChronosMap.refresh(state, runId);
    }
  } catch (e) {
    block.innerHTML =
      `<p class="text-sm italic text-white/55 pl-3 border-l border-white/15">${esc(text)}</p>` +
      `<p class="text-[10px] text-red-400/60 mt-3 uppercase tracking-wider">Something went wrong. ${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    if (bottomBar) bottomBar.style.pointerEvents = "";
    if (!hardCapReached) {
      [input, obsInput].forEach((el) => {
        if (!el) return;
        el.disabled = false;
        el.style.pointerEvents = "";
        el.style.opacity = "";
      });
      if (input) input.placeholder = "What do you do, think, or say?";
      if (obsInput) obsInput.placeholder = "Travel only...";
      if (state && state.run_status === "active" && input) input.focus();
      if (state && state.run_status === "dead_observing" && obsInput)
        obsInput.focus();
    }
  }
}

// ── Scroll state ─────────────────────────────────────────────────────

let userScrolledUp = false;

// ── Word-by-word streaming ────────────────────────────────────────────

let streamCancelled = false;

function cancelActiveStreams() {
  streamCancelled = true;
}

function streamWords(container, text, msPerWord) {
  streamCancelled = false;
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
      if (streamCancelled || i >= spans.length) {
        spans.forEach((s) => s.classList.add("visible"));
        resolve();
        return;
      }
      spans[i].classList.add("visible");
      i++;
      if (!userScrolledUp) {
        const manuscript = $("#manuscript");
        if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
      }
      setTimeout(tick, msPerWord);
    }
    tick();
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Staggered turn rendering ──────────────────────────────────────────

// Pattern that identifies the fallback era_description produced when
// action_parser fails — "X attempts something in Y." — so we can suppress it.
const _ERA_FALLBACK_RE = /attempts something in /i;

async function renderTurnStaggered(el, playerText, data) {
  const pa = data.parsed_action || {};
  const { npc_responses, player_view: pv } = data;
  const ambient = data.ambient_activity || [];

  let h = `<div class="text-[11px] uppercase tracking-[0.15em] text-white/55 mb-4 font-semibold">${pv.current_year} AD</div>`;

  // ── Ambient activity (what people nearby are doing) ───────────────────
  if (ambient.length) {
    h += `<div class="text-[9px] uppercase tracking-[0.18em] text-white/45 mb-2 font-semibold">Scene</div>`;
    h += `<div class="space-y-2 mb-5">`;
    for (const a of ambient) {
      h += `<p class="text-sm leading-relaxed text-white/35">`;
      if (a.interacts_with) {
        h += `<span class="text-white/45 font-medium">${esc(a.npc_name)}</span> and <span class="text-white/45 font-medium">${esc(a.interacts_with)}</span> \u2014 `;
      } else {
        h += `<span class="text-white/45 font-medium">${esc(a.npc_name)}</span> \u2014 `;
      }
      h += `${esc(a.activity)}</p>`;
    }
    h += `</div>`;
  }

  // ── Player action ─────────────────────────────────────────────────────
  h += `<p class="text-sm italic text-white/55 mb-3 pl-3 border-l border-white/15">${esc(playerText)}</p>`;

  // Only render era_description when it carries real content — suppress the
  // action_parser fallback placeholder ("X attempts something in Y").
  const eraDesc = pa.era_description || "";
  if (eraDesc && !_ERA_FALLBACK_RE.test(eraDesc)) {
    h += `<p class="text-sm leading-loose text-white/65 mb-4">${esc(eraDesc)}</p>`;
  }

  if (data.travel) {
    h += `<p class="text-sm leading-relaxed text-white/45 mb-3">${esc(
      `The journey from ${data.travel.from} to ${data.travel.to} takes ${data.travel.turns_spent} turns.`
    )}</p>`;
  }

  const rumors = pv.rumors || [];
  if (rumors.length) {
    for (const r of rumors) {
      h += `<p class="text-sm leading-relaxed italic text-amber-300/40 mb-4">${esc(r.description)}</p>`;
    }
  }

  // ── NPC reactions (what people say to / about you) ────────────────────
  const npcIds = [];
  if ((npc_responses || []).length) {
    h += `<div class="text-[9px] uppercase tracking-[0.18em] text-white/45 mt-5 mb-3 font-semibold">Voices</div>`;
  }
  for (let i = 0; i < (npc_responses || []).length; i++) {
    const r = npc_responses[i];
    const isAddressed = r.mode === "addressed";
    const id = `npc-stagger-${Date.now()}-${i}`;
    npcIds.push({ id, internal: r.internal || null, isAddressed });
    // Addressed NPCs get a slightly brighter left-border to signal direct speech
    const borderClass = isAddressed ? "border-white/40" : "border-white/20";
    h += `<div id="${id}" class="npc-block-stagger pl-4 border-l-2 ${borderClass} my-4">`;
    h += `<div class="text-[10px] uppercase tracking-[0.15em] text-white/75 mb-1.5 font-semibold">${esc(r.npc_name)}</div>`;
    h += `<p class="text-sm leading-relaxed text-white/70 npc-pov-text"></p>`;
    if (r.internal) {
      h += `<p class="text-xs leading-relaxed text-white/55 italic npc-internal-text mt-1.5"></p>`;
    }
    h += `</div>`;
  }

  h += `<div class="mt-6 mb-2"><div class="w-full h-px bg-white/[0.03]"></div></div>`;

  el.innerHTML = h;
  el.scrollIntoView({ behavior: "smooth" });

  for (let i = 0; i < npcIds.length; i++) {
    const { id, internal } = npcIds[i];
    const npcEl = document.getElementById(id);
    if (!npcEl) continue;
    if (i > 0) await sleep(600);
    npcEl.classList.add("revealed");
    const povTextEl = npcEl.querySelector(".npc-pov-text");
    if (povTextEl && npc_responses[i].pov) {
      await streamWords(povTextEl, npc_responses[i].pov, 35);
    }
    if (internal) {
      const internalEl = npcEl.querySelector(".npc-internal-text");
      if (internalEl) {
        await sleep(300);
        await streamWords(internalEl, internal, 40);
      }
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
  const obsInput = $("#obs-input");
  const manuscript = $("#manuscript");
  if (bottomBar) bottomBar.classList.add("hidden");
  if (obsSection) obsSection.classList.remove("hidden");
  if (obsInput) {
    obsInput.disabled = false;
    obsInput.placeholder = "YOU ARE DEAD \u00b7 TRAVEL ONLY";
  }
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
  }, 8000);

  setTimeout(() => {
    if (restart) restart.classList.add("visible");
  }, 8000 + 5000);
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

// Overlay routing — single source of truth for which overlay is open.
//
// The hamburger labels flip between the destination and "Manuscript",
// so toggling one always implies you can return. setLastOverlay()
// persists for cross-reload restoration.

function showMapOverlay() {
  const mapContainer = $("#map-container");
  const graphContainer = $("#graph-container");
  const manuscript = $("#manuscript");
  const bottomBar = $("#bottom-bar");
  const mapText = $("#map-btn-text");
  const graphText = $("#graph-btn-text");
  if (!mapContainer) return;
  // Close graph if it happens to be open.
  if (typeof ChronosGraph !== "undefined" && ChronosGraph.isVisible()) {
    ChronosGraph.hide();
    if (graphContainer) graphContainer.classList.add("hidden");
    if (graphText) graphText.textContent = "Connections";
  }
  mapContainer.classList.remove("hidden");
  if (manuscript) manuscript.style.display = "none";
  if (bottomBar) bottomBar.classList.add("hidden");
  if (mapText) mapText.textContent = "Manuscript";
  if (typeof ChronosMap !== "undefined") ChronosMap.show(state, eraKey, runId);
  setLastOverlay("map");
}

function showGraphOverlay() {
  const graphContainer = $("#graph-container");
  const mapContainer = $("#map-container");
  const manuscript = $("#manuscript");
  const bottomBar = $("#bottom-bar");
  const graphText = $("#graph-btn-text");
  const mapText = $("#map-btn-text");
  if (!graphContainer) return;
  if (typeof ChronosMap !== "undefined" && ChronosMap.isVisible()) {
    ChronosMap.hide();
    if (mapContainer) mapContainer.classList.add("hidden");
    if (mapText) mapText.textContent = "Map";
  }
  if (manuscript) manuscript.style.display = "none";
  if (bottomBar) bottomBar.classList.add("hidden");
  if (graphText) graphText.textContent = "Manuscript";
  if (typeof ChronosGraph !== "undefined") ChronosGraph.show(runId);
  setLastOverlay("connections");
}

function showManuscriptOverlay() {
  const mapContainer = $("#map-container");
  const graphContainer = $("#graph-container");
  const manuscript = $("#manuscript");
  const bottomBar = $("#bottom-bar");
  const mapText = $("#map-btn-text");
  const graphText = $("#graph-btn-text");
  if (mapContainer) mapContainer.classList.add("hidden");
  if (graphContainer) graphContainer.classList.add("hidden");
  if (manuscript) manuscript.style.display = "";
  if (state && state.run_status === "active" && bottomBar) {
    bottomBar.classList.remove("hidden");
  }
  if (mapText) mapText.textContent = "Map";
  if (graphText) graphText.textContent = "Connections";
  if (typeof ChronosMap !== "undefined") ChronosMap.hide();
  if (typeof ChronosGraph !== "undefined") ChronosGraph.hide();
  setLastOverlay("manuscript");
}

// Map toggle
const mapBtn = $("#btn-map-hamburger");
if (mapBtn) {
  mapBtn.addEventListener("click", () => {
    const mapContainer = $("#map-container");
    if (mapContainer && mapContainer.classList.contains("hidden")) {
      showMapOverlay();
    } else {
      showManuscriptOverlay();
    }
    closePanel();
  });
}

// Connections (interaction graph) toggle
const graphBtn = $("#btn-graph-hamburger");
if (graphBtn) {
  graphBtn.addEventListener("click", () => {
    const graphContainer = $("#graph-container");
    if (graphContainer && graphContainer.classList.contains("hidden")) {
      showGraphOverlay();
    } else {
      showManuscriptOverlay();
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
  // Bug 3 (option b): remember the selection's end position by
  // Node + offset so we can recompute a live viewport rect at
  // click time, even if the manuscript scrolled in between.
  var pendingEndNode = null;
  var pendingEndOffset = 0;

  function hideAll() {
    tooltip.style.display = "none";
    ctxBtn.style.display = "none";
    ctxPanel.style.display = "none";
    pendingText = "";
    pendingEndNode = null;
    pendingEndOffset = 0;
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

  // Bug 2: for multi-line selections, range.getBoundingClientRect()
  // returns one huge bbox spanning all lines. Use the LAST rect from
  // getClientRects() — the end of the selection, which is where the
  // user's cursor finished. Single-line selections return one rect
  // and behave unchanged. Falls back to the bbox if empty.
  function getAnchorRect(range) {
    var rects = range.getClientRects();
    if (rects && rects.length > 0) return rects[rects.length - 1];
    return range.getBoundingClientRect();
  }

  // Bug 3 (option b): reconstruct a live viewport rect from the
  // saved end Node + offset. Returns null if the node is no longer
  // in the document (e.g. manuscript re-rendered).
  function liveRectFromSavedPoint() {
    if (!pendingEndNode || !document.contains(pendingEndNode)) return null;
    try {
      var r = document.createRange();
      r.setStart(pendingEndNode, pendingEndOffset);
      r.setEnd(pendingEndNode, pendingEndOffset);
      var liveRect = r.getBoundingClientRect();
      r.detach && r.detach();
      // A collapsed range at end-of-line can return a zero-size
      // rect; that's fine for anchoring — it has a valid top/left.
      return liveRect;
    } catch (_) {
      return null;
    }
  }

  function rectOnScreen(rect) {
    if (!rect) return false;
    return rect.top < window.innerHeight && rect.bottom > 0;
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
    // Bug 1: clamp to viewport bottom as well as top. Handles the
    // edge case where both above AND below cause overflow — pin to
    // viewport bottom rather than running off.
    var topNum = parseInt(el.style.top);
    if (topNum + el.offsetHeight > window.innerHeight - 8) {
      el.style.top = window.innerHeight - el.offsetHeight - 8 + "px";
    }
  }

  async function handleSelection() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;

    var text = sel.toString().trim();
    if (!text || text.length < 2) return;
    if (!inManuscript(sel.anchorNode)) return;

    var range = sel.getRangeAt(0);
    var rect = getAnchorRect(range);
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
      // Bug 3: remember the selection end point so we can recompute
      // a live rect at click time.
      pendingEndNode = range.endContainer;
      pendingEndOffset = range.endOffset;
      ctxBtn.style.display = "block";
      positionAt(ctxBtn, rect, 120);
    }
  }

  ctxBtn.addEventListener("click", async function () {
    if (!pendingText || !runId) return;

    // Bug 3: prefer a freshly-computed rect from the saved end
    // point. If the content has scrolled out of view or the node
    // has been detached, fall back to the button's current
    // position (the pre-Fix-5 behavior).
    var panelRect = liveRectFromSavedPoint();
    if (!rectOnScreen(panelRect)) {
      panelRect = {
        left: parseInt(ctxBtn.style.left),
        top: parseInt(ctxBtn.style.top),
        width: 80,
        height: 20,
        bottom: parseInt(ctxBtn.style.top) + 28,
      };
    }

    ctxBtn.style.display = "none";
    ctxPanel.innerHTML =
      '<span class="ctx-loading">Searching the archives\u2026</span>';
    ctxPanel.style.display = "block";
    positionAt(ctxPanel, panelRect, 380);

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
    positionAt(ctxPanel, panelRect, 380);
    pendingText = "";
    pendingEndNode = null;
    pendingEndOffset = 0;
  });
})();

// ── Scroll-to-bottom button ───────────────────────────────────────────

(function () {
  var ms = document.getElementById("manuscript");
  var btn = document.getElementById("btn-scroll-bottom");
  if (!ms || !btn) return;

  ms.addEventListener("scroll", function () {
    var gap = ms.scrollHeight - ms.scrollTop - ms.clientHeight;
    if (gap > 200) {
      btn.classList.remove("hidden");
      userScrolledUp = true;
    } else {
      btn.classList.add("hidden");
      userScrolledUp = false;
    }
  });

  btn.addEventListener("click", function () {
    ms.scrollTo({ top: ms.scrollHeight, behavior: "smooth" });
    userScrolledUp = false;
  });
})();

// ── Time-skip control ─────────────────────────────────────────────────

(function initSkipControl() {
  const btn = $("#btn-skip");
  const popup = $("#skip-popup");
  if (!btn || !popup) return;

  let longPressTimer = null;

  btn.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    longPressTimer = setTimeout(() => {
      longPressTimer = null;
      popup.classList.toggle("hidden");
    }, 400);
  });

  btn.addEventListener("mouseup", (e) => {
    if (longPressTimer) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
      popup.classList.add("hidden");
      executeSkip(defaultSkipTicks);
    }
  });

  btn.addEventListener("mouseleave", () => {
    if (longPressTimer) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  });

  document.addEventListener("click", (e) => {
    if (!popup.classList.contains("hidden") && !popup.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
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
    `<p class="text-sm italic text-white/55 mb-3 pl-3 border-l border-white/15">Time passes\u2026 (${esc(label)})</p>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">\u00b7 \u00b7 \u00b7</span></div>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch(`/api/run/${runId}/skip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticks }),
    });
    if (res.status === 402) {
      const body = await res.json().catch(() => ({}));
      const d = body.detail || {};
      if (d && d.code === "cost_cap_hard") {
        hardCapReached = true;
        if (state) state.cost_cap_state = "hard";
        updateCostIndicator();
        block.remove();
        return;
      }
    }
    if (!res.ok)
      throw new Error(
        (await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`
      );
    const data = await res.json();
    state = data.player_view;

    let h = `<div class="text-[11px] uppercase tracking-[0.15em] text-white/55 mb-4 font-semibold">${state.current_year} AD</div>`;
    h += `<p class="text-sm italic text-white/55 mb-4 pl-3 border-l border-white/15">Time passes\u2026 (${esc(label)})</p>`;
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
      ChronosMap.refresh(state, runId);
    }
  } catch (e) {
    block.innerHTML =
      `<p class="text-sm italic text-white/55 pl-3 border-l border-white/15">Time passes\u2026 (${esc(label)})</p>` +
      `<p class="text-[10px] text-red-400/60 mt-3 uppercase tracking-wider">Something went wrong. ${esc(e.message)}</p>`;
  } finally {
    turnInProgress = false;
    if (bottomBar) bottomBar.style.pointerEvents = "";
    if (skipBtn) skipBtn.style.pointerEvents = "";
    if (!hardCapReached && input) {
      input.disabled = false;
      input.style.pointerEvents = "";
      input.style.opacity = "";
      input.placeholder = "What do you do, think, or say?";
      input.focus();
    }
  }
}

// ── Notes panel ───────────────────────────────────────────────────────

(function initNotesPanel() {
  const btn = $("#btn-notes");
  const overlay = $("#notes-overlay");
  const panel = $("#notes-panel");
  const textarea = $("#notes-textarea");
  const header = $("#notes-header");
  const closeBtn = $("#notes-close-btn");
  const timestampBtn = $("#notes-timestamp-btn");
  const pinBtn = $("#notes-pin-btn");
  if (!btn || !panel || !textarea) return;

  let saveDebounce = null;

  function notesKey() {
    if (!runId || !state) return null;
    return `chronos_notes_${runId}_${state.player_name || "unknown"}`;
  }

  function loadNotes() {
    const key = notesKey();
    if (!key) return;
    textarea.value = localStorage.getItem(key) || "";
  }

  function saveNotes() {
    const key = notesKey();
    if (!key) return;
    localStorage.setItem(key, textarea.value);
  }

  function openNotes() {
    if (!state || !runId) return;
    if (header) header.textContent = `Notes \u2014 ${state.player_name || "Unknown"}`;
    loadNotes();
    overlay.classList.remove("hidden");
    panel.classList.remove("hidden");
    setTimeout(() => textarea.focus(), 100);
  }

  function closeNotes() {
    saveNotes();
    overlay.classList.add("hidden");
    panel.classList.add("hidden");
  }

  btn.addEventListener("click", openNotes);
  if (closeBtn) closeBtn.addEventListener("click", closeNotes);
  if (overlay) overlay.addEventListener("click", closeNotes);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.classList.contains("hidden")) {
      closeNotes();
    }
  });

  textarea.addEventListener("input", function () {
    clearTimeout(saveDebounce);
    saveDebounce = setTimeout(saveNotes, 500);
  });

  if (timestampBtn) {
    timestampBtn.addEventListener("click", function () {
      if (!state) return;
      const year = state.current_year || "???";
      const turn = state.turn || 0;
      const seasons = ["Winter", "Spring", "Summer", "Autumn"];
      const weekInYear = (turn % 52) + 1;
      const season = seasons[Math.floor(((weekInYear - 1) % 52) / 13)];
      const stamp = `[${season} ${year} AD] `;
      const pos = textarea.selectionStart;
      const before = textarea.value.substring(0, pos);
      const after = textarea.value.substring(pos);
      textarea.value = before + stamp + after;
      textarea.selectionStart = textarea.selectionEnd = pos + stamp.length;
      textarea.focus();
      saveNotes();
    });
  }

  if (pinBtn) {
    pinBtn.addEventListener("click", function () {
      const pos = textarea.selectionStart;
      const before = textarea.value.substring(0, pos);
      const after = textarea.value.substring(pos);
      const pin = "\u25C6 ";
      textarea.value = before + pin + after;
      textarea.selectionStart = textarea.selectionEnd = pos + pin.length;
      textarea.focus();
      saveNotes();
    });
  }
})();

// ── Utility ───────────────────────────────────────────────────────────

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
