/**
 * CHRONOS — Simulation-first game loop.
 *
 * Turn flow: world simulates (NPCs act) → player optionally acts →
 * narrative shows ambient activity first, player action as one thread.
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Tutorial / how-it-works overlay ──────────────────────────────────
//
// Opt-in only. Two entry points:
//   - "How it works" button on the start screen (#btn-tutorial-start)
//   - "How it works" entry in the hamburger menu (#btn-tutorial)
// No auto-show on first visit -- the previous auto-popup felt
// jarring on the start screen.
//
// Esc closes; clicking the dim backdrop closes; both close buttons
// inside the card close.
function showTutorial() {
  const overlay = document.getElementById("tutorial-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
}
function hideTutorial() {
  const overlay = document.getElementById("tutorial-overlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
}
(function initTutorial() {
  document.addEventListener("DOMContentLoaded", () => {
    const close = document.getElementById("btn-tutorial-close");
    const begin = document.getElementById("btn-tutorial-begin");
    const menuBtn = document.getElementById("btn-tutorial");
    const startBtn = document.getElementById("btn-tutorial-start");
    if (close) close.addEventListener("click", hideTutorial);
    if (begin) begin.addEventListener("click", hideTutorial);
    if (startBtn) startBtn.addEventListener("click", showTutorial);
    if (menuBtn) menuBtn.addEventListener("click", () => {
      // From the menu: open the tutorial AND close the menu.
      showTutorial();
      const panel = document.getElementById("hamburger-panel");
      const ovBg = document.getElementById("hamburger-overlay");
      if (panel) panel.classList.remove("open");
      if (ovBg) ovBg.classList.add("hidden");
    });
    // Esc closes if open.
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const ov = document.getElementById("tutorial-overlay");
      if (ov && !ov.classList.contains("hidden")) hideTutorial();
    });
    // Click outside the card closes it.
    const ov = document.getElementById("tutorial-overlay");
    if (ov) {
      ov.addEventListener("click", (e) => {
        if (e.target === ov) hideTutorial();
      });
    }
  });
})();

// ── Phase 2.6 feature flags ───────────────────────────────────────────
//
// The 3D substrate (manuscript depth-stack + globe) is on by default.
// `?flat=1` URL parameter disables both — falls back to the pre-Pass-6
// flat manuscript and the legacy Leaflet map. Easy back-out if either
// surface breaks for a given user. See manuscript-as-artifact.md.
//
// `body.chronos-no-3d` is reserved for browser fallback (Safari has had
// historic 3D context bugs); not auto-set today, but the CSS reads it.
(function initSpatialFlags() {
  const params = new URLSearchParams(window.location.search);
  const flat = params.get("flat") === "1";
  if (!flat) {
    document.body.classList.add("chronos-stacked-manuscript");
    document.body.classList.add("chronos-globe-default");
    // Phase 2.8: corridor manuscript replaces the depth-stack as the
    // primary view. The depth-stack class above stays set for the
    // ?flat=1 fallback path; with chronos-corridor-manuscript on,
    // CSS hides #manuscript so the depth-stack is never seen.
    document.body.classList.add("chronos-corridor-manuscript");
  }
})();

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

// A "live" narrative is one we generated ourselves: either a real
// turn (id="turn-<timestamp>") or the rehaul intro block (the only
// place the literal phrase "Your name is" gets emitted). Anything else
// — empty string, design-review placeholder, error stub — is junk we
// must never pickle into localStorage and must evict on restore.
function _isLiveNarrative(html) {
  if (!html || typeof html !== "string") return false;
  if (html.indexOf('id="turn-') !== -1) return true;
  if (html.indexOf("Your name is") !== -1) return true;
  return false;
}

function saveRunToStorage() {
  if (runId && eraKey) {
    localStorage.setItem("chronos_run_id", runId);
    localStorage.setItem("chronos_era_key", eraKey);
  }
  const tc = document.getElementById("turns-container");
  if (tc && runId) {
    if (!_isLiveNarrative(tc.innerHTML)) return;
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

  // Reset transient view state from previous sessions: don't leak the
  // zoomed-out class (and the "Press Z to return" hint that hangs off
  // it) into a fresh entry into the game screen.
  const _ms = document.getElementById("manuscript");
  if (_ms) _ms.classList.remove("zoomed-out");

  updateTopBar();
  setupInput();

  const savedNarrative = runId
    ? localStorage.getItem("chronos_narrative_" + runId)
    : null;
  const isOldFormat = savedNarrative && savedNarrative.includes("font-body");
  // Pre-rehaul builds (and one accidental design-review path) pickled
  // the static placeholder turn-blocks from index.html into localStorage.
  // Those don't contain a real turn id or the rehaul intro signature, so
  // _isLiveNarrative rejects them and we render fresh.
  const isPoisoned = savedNarrative && !_isLiveNarrative(savedNarrative);

  if (savedNarrative && !isOldFormat && !isPoisoned && turnsContainer) {
    turnsContainer.innerHTML = savedNarrative;
    const manuscript = $("#manuscript");
    if (manuscript) manuscript.scrollTop = manuscript.scrollHeight;
    // Re-apply memory decay to restored turns and rewire hover-recovery.
    applyMemoryDecay();
    applyDepthLayering();
    _wireDecayHoverAll();
    // Phase 2.8: hand the restored .turn-block elements to the
    // corridor so they get placed along the board. New turns
    // submitted after restore will have full edges. board_state
    // (saved drag positions) and cut_threads (saved severed edges)
    // are applied BEFORE the cards are added so each card lands at
    // its saved override and severed threads render severed on
    // first paint.
    if (typeof ChronosCorridor !== "undefined") {
      if (state && (state.board_state || state.cut_threads)) {
        ChronosCorridor.applyBoardOverrides(
          state.board_state,
          state.cut_threads,
        );
      }
      ChronosCorridor.show(runId);
      ChronosCorridor.restoreFromContainer();
    }
  } else {
    if (turnsContainer) turnsContainer.innerHTML = "";
    if (runId && (isOldFormat || isPoisoned)) {
      localStorage.removeItem("chronos_narrative_" + runId);
    }

    const loc = state.current_location;
    const year = state.current_year;

    // Intro block.
    //
    // Tagged manuscript-intro so the Pass 6 depth CSS treats it as the
    // baseline layer in the stack (sits at z=0 on entry, then recedes
    // when the first real turn-block appears). The .first-stack-reveal
    // class triggers a one-shot CSS keyframe that drops the block in
    // from depth to z=0 over ~1.4s, visibly establishing the 3D
    // metaphor on first paint even though there are no turn-blocks yet.
    let h = `<div class="mb-10 manuscript-intro first-stack-reveal">`;
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
    // Show the depth-discovery hint once per browser. Disappears the
    // moment the player scrolls or hovers a turn-block.
    _maybeShowDepthHint();
    // Phase 2.8: register the freshly-built intro card with the
    // corridor and bring it on-screen. apply board_state overrides
    // and cut_threads first so the intro lands at its saved position
    // and any prior-cut edges render severed if the player had
    // dragged or cut on a previous visit.
    if (typeof ChronosCorridor !== "undefined") {
      if (state && (state.board_state || state.cut_threads)) {
        ChronosCorridor.applyBoardOverrides(
          state.board_state,
          state.cut_threads,
        );
      }
      ChronosCorridor.show(runId);
      const intro = turnsContainer.querySelector(".manuscript-intro");
      if (intro) ChronosCorridor.addIntroCard(intro);
    }
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

  updateGround();
  updateAtmosphere();
  updateClock();
  updateCostIndicator();
}

// ── Atmosphere — vignette + season tint, driven by state ──────────────
//
// Reads state.current_location.political_tension and the current
// season (derived from state.turn) to set CSS variables on :root that
// drive the edge-vignette intensity/tint and the body color tint.
//
// Tension vocabulary is loose ("uneasy", "tense", "calm", "stable"...).
// We bucket into low/medium/high/critical and pick from there.

const _TENSION_TIER = {
  low: 0, calm: 0, stable: 0, peaceful: 0, quiet: 0,
  moderate: 1, uneasy: 1, restless: 1, watchful: 1, tense: 1,
  high: 2, strained: 2, simmering: 2, fearful: 2,
  critical: 3, explosive: 3, broken: 3, collapsing: 3, rising: 2,
};

function _tensionTier(s) {
  if (!s) return 0;
  const k = String(s).trim().toLowerCase();
  return _TENSION_TIER[k] != null ? _TENSION_TIER[k] : 1;
}

function _seasonName(turn) {
  // Mirror updateClock(): seasons winter/spring/summer/autumn,
  // 13 weeks each. Turn 0 = winter wk 1.
  const w = (turn % 52) + 1;
  const seasons = ["winter", "spring", "summer", "autumn"];
  return seasons[Math.floor(((w - 1) % 52) / 13)];
}

// Map (tension, season, dead) → CSS variables.
function updateAtmosphere() {
  const root = document.documentElement;
  if (!state) return;

  const tier = _tensionTier(
    state.current_location ? state.current_location.political_tension : ""
  );
  const season = _seasonName(state.turn || 0);
  const isDead = state.run_status === "dead_observing";

  // Vignette intensity: 0 (low tension) → 0.95 (critical / dead)
  let intensity = 0.55 + tier * 0.10;
  if (isDead) intensity = 0.92;

  // Vignette tint: rgba(r,g,b, a). Default neutral black.
  // High tension → red-tinged. Dead → deep red. Season also nudges hue.
  let tintR = 0, tintG = 0, tintB = 0, tintA = 0.85;
  if (tier >= 2) { tintR = 60; tintG = 0; tintB = 0; tintA = 0.85; }
  if (tier >= 3) { tintR = 90; tintG = 0; tintB = 0; tintA = 0.92; }
  if (isDead)    { tintR = 50; tintG = 6;  tintB = 14; tintA = 0.96; }
  // Season nudge (subtle): winter cold blue tint, summer warm
  let seasonR = 0, seasonG = 0, seasonB = 0, seasonA = 0;
  if (season === "winter") { seasonR = 8;  seasonG = 16; seasonB = 30; seasonA = 0.10; }
  if (season === "summer") { seasonR = 30; seasonG = 18; seasonB = 0;  seasonA = 0.06; }
  if (season === "autumn") { seasonR = 28; seasonG = 12; seasonB = 0;  seasonA = 0.05; }
  // Spring is unchanged (default).

  // Apply CSS vars
  root.style.setProperty("--vignette-intensity", String(intensity));
  root.style.setProperty(
    "--vignette-tint",
    `rgba(${tintR}, ${tintG}, ${tintB}, ${tintA})`
  );
  root.style.setProperty(
    "--season-tint",
    `rgba(${seasonR}, ${seasonG}, ${seasonB}, ${seasonA})`
  );

  // Set a season class on body so prose can be subtly color-graded
  document.body.classList.remove("season-winter", "season-spring", "season-summer", "season-autumn");
  document.body.classList.add(`season-${season}`);

  // Death stain: persistent red shroud
  document.body.classList.toggle("is-dead", isDead);

  // Start motes once.
  _startMotes();
}

// ── Motes — drifting particles, atmospheric layer ─────────────────────

const _motes = [];
let _motesRafStarted = false;

function _startMotes() {
  if (_motesRafStarted) return;
  const layer = document.getElementById("memory-motes");
  if (!layer) return;

  const N = 36;
  for (let i = 0; i < N; i++) {
    const m = document.createElement("div");
    m.className = "memory-mote";
    const x = Math.random() * window.innerWidth;
    const y = Math.random() * window.innerHeight;
    m.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    m.style.opacity = String(0.04 + Math.random() * 0.07);
    layer.appendChild(m);
    _motes.push({
      el: m, x, y,
      vx: (Math.random() - 0.5) * 0.10,
      vy: 0.08 + Math.random() * 0.10,
    });
  }

  function step() {
    const W = window.innerWidth;
    const H = window.innerHeight;
    for (const m of _motes) {
      m.x += m.vx;
      m.y += m.vy;
      if (m.x < -10) m.x = W + 10;
      if (m.x > W + 10) m.x = -10;
      if (m.y < -10) m.y = H + 10;
      if (m.y > H + 10) m.y = -10;
      m.el.style.transform = `translate3d(${m.x}px, ${m.y}px, 0)`;
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
  _motesRafStarted = true;
}

// ── Ground layer — the felt floor of the moment ──────────────────────
//
// The location name renders behind everything as a massive low-contrast
// glyph. On travel, the old name fades out (via .changing class) and the
// new one fades in. Year + season meta sits below the name.
//
// Drives state-reflective styling: tension intensifies the edge vignette,
// season tints background hue. (Pass 4 will activate season/tension.)

let _lastGroundLoc = null;

function updateGround() {
  const nameEl = document.getElementById("ground-name");
  const metaEl = document.getElementById("ground-meta");
  if (!nameEl || !state) return;

  const loc = state.current_location;
  const newName = loc && loc.name ? loc.name : "";

  if (newName !== _lastGroundLoc) {
    // Animate the change
    nameEl.classList.add("changing");
    setTimeout(() => {
      nameEl.textContent = newName;
      _fitGroundName(nameEl);
      _lastGroundLoc = newName;
      // Remove the changing class to fade in
      nameEl.classList.remove("changing");
    }, 600);
  } else {
    _fitGroundName(nameEl);
  }

  if (metaEl) {
    const year = state.current_year;
    const era = state.era_name || "";
    metaEl.textContent = `${year} \u00b7 ${era}`;
  }
}

// Auto-fit the ground name to viewport width: pick a font-size such that
// the word spans ~78% of the viewport width. Recomputed on resize.
function _fitGroundName(nameEl) {
  if (!nameEl || !nameEl.textContent) return;
  const target = window.innerWidth * 0.78;
  // Binary-ish: try a starting size, scale by ratio of measured width
  // to target. Two passes converges for monospace-ish text.
  nameEl.style.fontSize = "200px";
  const w0 = nameEl.getBoundingClientRect().width || 1;
  const scaled = Math.max(48, Math.min(360, 200 * (target / w0)));
  nameEl.style.fontSize = scaled + "px";
}

// Refit on viewport resize.
window.addEventListener("resize", () => {
  const nameEl = document.getElementById("ground-name");
  if (nameEl) _fitGroundName(nameEl);
});

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

// ── Memory rehaul: zoom-out overview ─────────────────────────────────
//
// Press Z (when not focused on an input) to toggle the manuscript
// into "zoom-out" — every turn becomes small, the run's shape becomes
// visible. Click a turn-block to zoom back in centered on it.

(function initZoomToggle() {
  document.addEventListener("keydown", (e) => {
    if (e.key !== "z" && e.key !== "Z") return;
    // Don't hijack when typing
    const a = document.activeElement;
    if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" ||
              a.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    // Phase 2.8: when the corridor is the active manuscript view,
    // Z toggles the constellation overview (camera pulled back above
    // the path) instead of the legacy zoomed-out scroll.
    if (
      typeof ChronosCorridor !== "undefined" &&
      ChronosCorridor.isVisible() &&
      document.body.classList.contains("chronos-corridor-manuscript")
    ) {
      ChronosCorridor.toggleConstellation();
      return;
    }
    const ms = document.getElementById("manuscript");
    if (!ms) return;
    ms.classList.toggle("zoomed-out");
  });

  // Click on a turn-block while zoomed-out → zoom back in, scrolled
  // to that block.
  document.addEventListener("click", (e) => {
    const ms = document.getElementById("manuscript");
    if (!ms || !ms.classList.contains("zoomed-out")) return;
    const block = e.target.closest(".turn-block");
    if (!block) return;
    e.preventDefault();
    e.stopPropagation();
    ms.classList.remove("zoomed-out");
    setTimeout(() => {
      block.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  }, true);  // capture phase so we beat other handlers
})();


// ── Memory rehaul: chrome collapse + bottom bar collapse ─────────────
//
// The top bar hides itself; hovering the top edge of the screen reveals
// it, and clicking the chrome-handle pins it open. The bottom input bar
// collapses to a thin handle when idle (empty + unfocused for 4s),
// expands on hover/click/keypress.

(function initChromeHandle() {
  const handle = document.getElementById("chrome-handle");
  const topbar = document.getElementById("top-bar");
  if (!handle || !topbar) return;

  // Click chrome-handle → toggle pinned state.
  handle.addEventListener("click", (e) => {
    e.preventDefault();
    handle.classList.toggle("pinned");
  });

  // Click outside top-bar / chrome-handle → unpin (so the bar fades again).
  document.addEventListener("click", (e) => {
    if (!handle.classList.contains("pinned")) return;
    if (handle.contains(e.target) || topbar.contains(e.target)) return;
    // Don't unpin on hamburger interactions either
    const ham = document.getElementById("hamburger-panel");
    if (ham && ham.contains(e.target)) return;
    handle.classList.remove("pinned");
  });
})();

(function initBottomBarCollapse() {
  const bar = document.getElementById("bottom-bar");
  const handle = document.getElementById("bottom-bar-handle");
  const input = document.getElementById("player-input");
  if (!bar || !handle || !input) return;

  let collapseTimer = null;

  function expand() {
    bar.classList.add("expanded");
    if (collapseTimer) { clearTimeout(collapseTimer); collapseTimer = null; }
  }

  function scheduleCollapse() {
    if (collapseTimer) clearTimeout(collapseTimer);
    collapseTimer = setTimeout(() => {
      // Don't collapse if input has content or is focused
      if (document.activeElement === input) return;
      if (input.value && input.value.length > 0) return;
      // Or if a turn is in progress
      if (window.turnInProgress) return;
      bar.classList.remove("expanded");
    }, 4000);
  }

  handle.addEventListener("click", () => {
    expand();
    setTimeout(() => input.focus(), 50);
  });

  // Hover-handle: expand on pointer-enter
  handle.addEventListener("pointerenter", expand);

  // Focus expands; blur schedules collapse
  input.addEventListener("focus", expand);
  input.addEventListener("blur", scheduleCollapse);
  input.addEventListener("input", () => {
    expand();
    if (collapseTimer) { clearTimeout(collapseTimer); collapseTimer = null; }
  });

  // Global keypress: if any printable key fires and the bar is collapsed
  // and no other input is focused, expand and pipe the keystroke into the
  // input field so the player can just start typing.
  document.addEventListener("keydown", (e) => {
    if (bar.classList.contains("expanded")) return;
    // Ignore if any input/textarea/contenteditable is currently focused
    const a = document.activeElement;
    if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" ||
              a.isContentEditable)) return;
    // Only printable keys
    if (e.key.length !== 1) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    expand();
    setTimeout(() => {
      input.focus();
      input.value = (input.value || "") + e.key;
    }, 50);
  });

  // Initial state: collapsed
  bar.classList.remove("expanded");
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

// Phase 2.7 — instant inline inner thought.
//
// Hits /api/run/{id}/inner_thought in parallel with the main /turn
// POST. When the response arrives, fills the .inner-thought-slot
// inside the just-created turn-block. The slot starts in .pending
// state showing dots; on success it swaps to the resolved-state with
// the thought text. On failure (empty response, network error) the
// slot is simply removed from layout and the rest of the turn renders
// without it — no error UI.
//
// Renders BEFORE /turn finishes, giving the player something to read
// in the second between input and full simulation completion.
async function _fetchAndRenderInnerThought(rid, text, block) {
  if (!rid || !text || !block) return;
  let thought = "";
  try {
    const res = await fetch(`/api/run/${rid}/inner_thought`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: text }),
    });
    if (res.ok) {
      const data = await res.json();
      thought = (data && data.inner_thought) ? String(data.inner_thought).trim() : "";
    }
  } catch (e) {
    // Silent — the absence of an inner thought is acceptable.
  }
  const slot = block.querySelector(".inner-thought-slot");
  if (!slot) return;
  if (thought) {
    slot.classList.remove("pending");
    slot.classList.add("resolved");
    slot.innerHTML = `<p class="inner-thought-text">${esc(thought)}</p>`;
  } else {
    // Collapse out of layout cleanly so the turn render below docks
    // up against the player's typed action.
    slot.remove();
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
  block.id = `turn-${Date.now()}`;
  block.className = "turn-block mb-8";
  // The block has three slots:
  //   - the player's typed action (italic, immediate)
  //   - the inner thought placeholder (Phase 2.7) — fills in <1.5s
  //   - the spinner (replaced by the full turn render when /turn returns)
  block.innerHTML =
    `<p class="text-sm italic text-white/55 mb-3 pl-3 border-l border-white/15">${esc(text)}</p>` +
    `<div class="inner-thought-slot pending"><div class="inner-thought-dots">\u00b7 \u00b7 \u00b7</div></div>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">\u00b7 \u00b7 \u00b7</span></div>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });
  saveRunToStorage();

  // Phase 2.6: depth-layer the in-flight block immediately so the
  // intro recedes and the new block sits at z=0 from the moment of
  // submission, not just after /turn returns. Otherwise users see a
  // flat intro for 5-30s while the spinner runs and conclude the 3D
  // isn't working at all.
  applyDepthLayering();

  // Phase 2.8: route the in-flight block into the corridor. The block
  // is now in #turns-container; addTurn moves it to #corridor-cards
  // and registers it in the 3D scene at the next path position.
  // turnData is null at this point (we don't have parsed_action yet);
  // notifyTurnComplete will fill it in after /turn returns.
  if (typeof ChronosCorridor !== "undefined") {
    if (!ChronosCorridor.isVisible()) ChronosCorridor.show();
    ChronosCorridor.addTurn(block, null);
  }

  // Phase 2.7: race the inner thought against /turn. Kick off
  // immediately, render in the slot as soon as it arrives. Failure is
  // silent — the slot just collapses out of layout when empty.
  _fetchAndRenderInnerThought(runId, text, block);

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
    applyMemoryDecay();
    applyDepthLayering();
    _wireDecayHoverAll();
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

// ── Memory rehaul: data-act dispatch ──────────────────────────────────
//
// The 2026-05-01 rehaul makes named entities click-to-act. Each
// interactive element carries data-act="<verb>" plus payload data-*
// attributes. A single delegated click handler routes to the right
// behavior. Keeps render code declarative + concentrates dispatch.
//
// Verbs:
//   speak    — data-name="Lucius"          → prefill "Speak to Lucius — "
//   verify   — data-rumor="..."            → prefill "I try to verify the rumor that ..."
//   skip     — (no data)                   → open skip popup
//   travel   — data-loc-id="..."           → submit a travel turn

document.addEventListener("click", function (e) {
  const target = e.target.closest("[data-act]");
  if (!target) return;
  const act = target.getAttribute("data-act");
  if (!act) return;
  e.preventDefault();
  e.stopPropagation();

  const input = document.getElementById("player-input");
  const obsInput = document.getElementById("obs-input");
  const expand = (txt) => {
    // Expand the bottom bar and prefill the input. The
    // initBottomBarCollapse IIFE listens for input events; setting
    // value + focus + dispatching expand is enough.
    const bar = document.getElementById("bottom-bar");
    if (bar) bar.classList.add("expanded");
    const useInput = (state && state.run_status === "dead_observing")
      ? obsInput
      : input;
    if (!useInput) return;
    useInput.value = txt;
    useInput.focus();
    useInput.setSelectionRange(useInput.value.length, useInput.value.length);
  };

  if (act === "speak") {
    const name = target.getAttribute("data-name") || "";
    if (name) expand(`Speak to ${name} \u2014 `);
  } else if (act === "verify") {
    const rumor = target.getAttribute("data-rumor") || "";
    if (rumor) expand(`I try to verify the rumor that ${rumor}`);
  } else if (act === "skip") {
    // Defer to the existing skip popup / control.
    const skipBtn = document.getElementById("btn-skip");
    if (skipBtn) skipBtn.click();
  } else if (act === "travel") {
    const locName = target.getAttribute("data-loc-name") || "";
    if (locName) expand(`I travel to ${locName}.`);
    _hideTravelPopup();
  } else if (act === "travel-menu") {
    _toggleTravelPopup(target);
  }
});

// Travel popup — neighbors of the player's current location.
function _toggleTravelPopup(anchor) {
  const popup = document.getElementById("travel-popup");
  const list = document.getElementById("travel-popup-list");
  if (!popup || !list || !state) return;

  // If already open, close.
  if (!popup.classList.contains("hidden")) {
    _hideTravelPopup();
    return;
  }

  const loc = state.current_location;
  const neighbors = loc && loc.neighbors ? loc.neighbors : {};
  const known = state.known_locations || [];
  const knownById = {};
  for (const k of known) knownById[k.id] = k;

  let h = "";
  const ids = Object.keys(neighbors);
  if (ids.length === 0) {
    h = `<div class="travel-popup-empty">There is nowhere from here you have heard of yet.</div>`;
  } else {
    for (const id of ids) {
      const turns = neighbors[id];
      const k = knownById[id];
      const name = k ? k.name : id;
      const visited = (state.visited_locations || []).includes(id);
      h += `<button type="button" class="travel-popup-row${visited ? " visited" : ""}"`
        + ` data-act="travel" data-loc-id="${esc(id)}" data-loc-name="${esc(name)}">`
        + `<span class="travel-popup-name">${esc(name)}</span>`
        + `<span class="travel-popup-dist">${esc(String(turns))} turns</span>`
        + `</button>`;
    }
  }
  list.innerHTML = h;
  popup.classList.remove("hidden");

  // Position the popup centered horizontally near the bottom of the ground.
  // Anchor is the ground-name button. We position absolutely below it.
  const r = anchor.getBoundingClientRect();
  popup.style.left = `${Math.max(20, Math.min(window.innerWidth - 320, r.left + r.width / 2 - 160))}px`;
  popup.style.top  = `${Math.min(window.innerHeight - 220, r.bottom + 16)}px`;

  // Click outside closes
  setTimeout(() => {
    document.addEventListener("click", _onTravelOutside, { once: true, capture: true });
  }, 0);
}

function _onTravelOutside(e) {
  const popup = document.getElementById("travel-popup");
  if (!popup) return;
  if (popup.contains(e.target)) {
    // Re-arm for next outside click
    setTimeout(() => {
      document.addEventListener("click", _onTravelOutside, { once: true, capture: true });
    }, 0);
    return;
  }
  _hideTravelPopup();
}

function _hideTravelPopup() {
  const popup = document.getElementById("travel-popup");
  if (popup) popup.classList.add("hidden");
}

// Helper: render an NPC name as a click-to-act target.
function _npcLink(name) {
  return `<button type="button" class="act-name" data-act="speak" data-name="${esc(name)}">${esc(name)}</button>`;
}

// Helper: render a rumor body as a click-to-act target.
function _rumorLink(text) {
  return `<button type="button" class="act-rumor" data-act="verify" data-rumor="${esc(text)}">${esc(text)}</button>`;
}

// Helper: render the year stamp as a click-to-act target.
function _yearLink(year) {
  return `<button type="button" class="act-year" data-act="skip">${esc(String(year))} AD</button>`;
}

async function renderTurnStaggered(el, playerText, data) {
  const pa = data.parsed_action || {};
  const { npc_responses, player_view: pv } = data;
  const ambient = data.ambient_activity || [];

  let h = `<div class="text-[11px] uppercase tracking-[0.15em] text-white/55 mb-4 font-semibold">${_yearLink(pv.current_year)}</div>`;

  // ── Ambient activity (what people nearby are doing) ───────────────────
  if (ambient.length) {
    h += `<div class="text-[9px] uppercase tracking-[0.18em] text-white/45 mb-2 font-semibold">Scene</div>`;
    h += `<div class="space-y-2 mb-5">`;
    for (const a of ambient) {
      h += `<p class="text-sm leading-relaxed text-white/35">`;
      if (a.interacts_with) {
        h += `${_npcLink(a.npc_name)} and ${_npcLink(a.interacts_with)} \u2014 `;
      } else {
        h += `${_npcLink(a.npc_name)} \u2014 `;
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
      h += `<p class="text-sm leading-relaxed italic text-amber-300/40 mb-4">${_rumorLink(r.description)}</p>`;
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
    h += `<div class="text-[10px] uppercase tracking-[0.15em] text-white/75 mb-1.5 font-semibold">${_npcLink(r.npc_name)}</div>`;
    h += `<p class="text-sm leading-relaxed text-white/70 npc-pov-text"></p>`;
    if (r.internal) {
      h += `<p class="text-xs leading-relaxed text-white/55 italic npc-internal-text mt-1.5"></p>`;
    }
    h += `</div>`;
  }

  h += `<div class="mt-6 mb-2"><div class="w-full h-px bg-white/[0.03]"></div></div>`;

  // Phase 2.7: preserve a resolved inner-thought slot across the
  // re-render so the player can keep reading it as part of the
  // permanent turn record. The slot is rendered between the player's
  // typed action and the year stamp.
  const existingThought = el.querySelector(".inner-thought-slot.resolved");
  let thoughtHtml = "";
  if (existingThought) {
    thoughtHtml = existingThought.outerHTML;
  }
  // Preserve the player's typed action header that was set when the
  // block was created. _wrapWordsForDecay later rewires its words.
  const existingPlayerLine = el.querySelector("p.text-sm.italic");
  let playerLineHtml = "";
  if (existingPlayerLine) {
    playerLineHtml = existingPlayerLine.outerHTML;
  }

  el.innerHTML = playerLineHtml + thoughtHtml + h;
  el.scrollIntoView({ behavior: "smooth" });

  // Phase 2.8: hand full turn data to the corridor so it can compute
  // significance, register connection edges (action -> NPC reaction,
  // action -> divergence, NPC <-> NPC), and update the card's tier
  // styling. Idempotent if already added by submitTurn.
  if (typeof ChronosCorridor !== "undefined") {
    ChronosCorridor.notifyTurnComplete(el, data);
  }

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

// ── Memory decay — words drop out of older turns ──────────────────────
//
// After every turn render, walk all .turn-block elements and apply
// progressive word-loss. The newest turn keeps every word; turns 1, 2,
// 3+ ago lose proportionally more. Lost words are hidden and replaced
// with a "…" sibling. Hovering a turn-block recovers the lost words.

// Wrap every word inside body-text paragraphs into <span class="m-word">
// so we can selectively hide them. Idempotent via dataset flag.
//
// Walks text nodes only; preserves nested elements like .act-name and
// .act-rumor buttons that are part of the content. Each text run between
// elements is independently word-wrapped. The button content itself is
// NOT decayed (so NPC names always read; you can always click them).
function _wrapWordsForDecay(blockEl) {
  if (!blockEl || blockEl.dataset.wordsWrapped === "1") return;
  // Body-text paragraph types we want decay on.
  const targets = blockEl.querySelectorAll(
    "p.npc-pov-text, p.npc-internal-text, " +
    "p.text-sm.leading-loose, p.text-sm.leading-relaxed"
  );
  targets.forEach((el) => {
    if (!el.textContent || !el.textContent.trim()) return;
    // Drop word-stream class so the post-rewrap spans aren't held at
    // opacity:0 by the streaming CSS.
    el.classList.remove("word-stream");
    // Walk child nodes; for each text-node, replace with word-wrapped HTML.
    // For element children (e.g. buttons), leave them untouched.
    const newChildren = [];
    el.childNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent;
        if (!text || !text.trim()) {
          newChildren.push(text); // preserve whitespace
          return;
        }
        // Build wrapped HTML for this text segment.
        const words = text.split(/(\s+)/);
        const wrapped = words.map((w) => {
          if (/^\s+$/.test(w)) return w;
          return `<span class="m-word">${esc(w)}</span>`;
        }).join("");
        newChildren.push(wrapped);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        // Push the element's outerHTML untouched — buttons stay clickable.
        newChildren.push(node.outerHTML);
      }
    });
    el.innerHTML = newChildren.join("");
  });
  // Also wrap the rumor button bodies — rumor lines are entirely <button>
  // elements with text inside. We wrap the words inside the button so they
  // can decay, but keep the button element so the click still works.
  const rumorButtons = blockEl.querySelectorAll(".act-rumor");
  rumorButtons.forEach((btn) => {
    if (btn.dataset.wordsWrapped === "1") return;
    const text = btn.textContent;
    if (!text || !text.trim()) return;
    const words = text.split(/(\s+)/);
    btn.innerHTML = words.map((w) => {
      if (/^\s+$/.test(w)) return w;
      return `<span class="m-word">${esc(w)}</span>`;
    }).join("");
    btn.dataset.wordsWrapped = "1";
  });
  blockEl.dataset.wordsWrapped = "1";
}

// Deterministic per-word "decay" — same word in the same turn-position
// always gets the same age-loss order so re-renders are stable.
function _wordSeedHash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return h >>> 0;
}

// Apply decay to a single block at age N (0 = newest, no loss).
// drop_fraction grows with age. Lost words have display:none + a sibling
// "…" placeholder appended (one per consecutive run of lost words).
function _applyDecayToBlock(blockEl, age) {
  if (!blockEl) return;
  _wrapWordsForDecay(blockEl);
  const words = blockEl.querySelectorAll(".m-word");
  if (words.length === 0) return;

  // Drop fraction by age: 0=0, 1=0.05, 2=0.18, 4=0.40, 8=0.65, 15+=0.80
  let drop;
  if (age <= 0) drop = 0;
  else if (age === 1) drop = 0.05;
  else if (age === 2) drop = 0.18;
  else drop = Math.min(0.80, 0.18 + (age - 2) * 0.07);

  // Pick which words to drop. Use a deterministic hash on (block id, index)
  // so the same word always goes first as the block ages.
  const blockId = blockEl.id || blockEl.getAttribute("data-block-id") || "";
  if (!blockId) return;

  // First, restore all words (in case we're re-applying with a different age)
  words.forEach((w) => {
    w.classList.remove("m-word--lost");
    w.style.display = "";
  });
  // Remove old ellipses
  blockEl.querySelectorAll(".m-word--ellipsis").forEach((e) => e.remove());

  if (drop <= 0) return;

  // Compute drop priority: each word gets a deterministic pseudo-random
  // score in [0, 1) seeded by (blockId, position). We drop words below
  // a threshold computed from the desired drop fraction. The same word
  // in the same block always lands at the same score, so sequential
  // decay from age 2 → age 3 simply expands the set of dropped words.
  //
  // We also protect short words and capitalized words (likely names) —
  // they're load-bearing for "the spine of the sentence" and shouldn't
  // be the first to go.
  const totalWords = words.length;
  const scored = Array.from(words).map((w, i) => {
    const text = w.textContent;
    const cap = /^[A-Z]/.test(text);
    const short = text.length <= 3;
    // Base score: deterministic [0..1)
    const base = (_wordSeedHash(blockId + ":" + i) % 1000) / 1000;
    // Protect: capitalized + short words get +0.4 (less likely to drop)
    const protectBonus = (cap ? 0.30 : 0) + (short ? 0.15 : 0);
    return { w, i, score: base + protectBonus };
  });
  scored.sort((a, b) => a.score - b.score);

  const nDrop = Math.floor(drop * totalWords);
  for (let k = 0; k < nDrop; k++) {
    const w = scored[k].w;
    w.classList.add("m-word--lost");
    w.style.display = "none";
  }

  // Walk the words in DOM order, insert "…" placeholders for runs of lost words.
  let inLostRun = false;
  Array.from(words).forEach((w) => {
    if (w.classList.contains("m-word--lost")) {
      if (!inLostRun) {
        const dots = document.createElement("span");
        dots.className = "m-word--ellipsis";
        dots.textContent = "\u2026";
        w.parentNode.insertBefore(dots, w);
        inLostRun = true;
      }
    } else {
      inLostRun = false;
    }
  });
}

// Apply decay across all turns. Newest = age 0.
function applyMemoryDecay() {
  const blocks = document.querySelectorAll(".turn-block");
  const total = blocks.length;
  blocks.forEach((block, index) => {
    const age = total - 1 - index;
    _applyDecayToBlock(block, age);
  });
}

// Wire hover-to-recover on turn blocks. Idempotent via dataset flag.
function _wireDecayHover(blockEl) {
  if (!blockEl || blockEl.dataset.recoverWired === "1") return;
  blockEl.addEventListener("pointerenter", () => {
    blockEl.classList.add("recovering");
  });
  blockEl.addEventListener("pointerleave", () => {
    blockEl.classList.remove("recovering");
  });
  blockEl.dataset.recoverWired = "1";
}

function _wireDecayHoverAll() {
  document.querySelectorAll(".turn-block").forEach(_wireDecayHover);
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


// ── Pass 6: manuscript depth-stack ────────────────────────────────────
//
// Phase 2.6 (Spatial Substrate). Each turn-block sits at a per-block
// z-depth; older turns recede into the page and pick up atmospheric
// haze (filter:blur via --turn-blur). Hover lifts a deep block forward,
// composing with the existing .recovering class from Pass 3 so memory
// recovery and depth recovery happen as one gesture.
//
// No DOM mutation. Sets per-block CSS custom properties only:
//   --turn-z       e.g. "-200px"
//   --turn-blur    e.g. "1.2px"
// And a data attribute used by CSS to skip rendering very-deep blocks:
//   data-deep="1"  on blocks beyond age 20
//
// Math (mirrors the applyMemoryDecay age curve so depth and decay
// progress in lockstep):
//   age 0 (newest) → z=0,    blur 0
//   each step back → z -= 40px, blur += 0.3px
//   floors:          z >= -800px, blur <= 3px
//
// Skipped entirely when the chronos-stacked-manuscript body class is
// off (e.g. ?flat=1) — the existing Pass 1 dimming alone applies.
// Show a one-shot hint that the manuscript has depth -- only ever
// shown the first time per browser, dismissed on first scroll, hover,
// or after 8 seconds. Without this nobody discovers the stack metaphor
// because empty manuscripts have nothing to recede against.
function _maybeShowDepthHint() {
  if (!document.body.classList.contains("chronos-stacked-manuscript")) return;
  try {
    if (localStorage.getItem("chronos_depth_hint_seen") === "1") return;
  } catch (_) { /* private browsing -- show anyway */ }
  if (document.getElementById("depth-hint")) return;
  const hint = document.createElement("div");
  hint.id = "depth-hint";
  hint.textContent = "Scroll to step back through time \u2014 turns recede into depth";
  document.body.appendChild(hint);
  const dismiss = () => {
    if (!hint.parentNode) return;
    hint.classList.add("dismiss");
    try { localStorage.setItem("chronos_depth_hint_seen", "1"); } catch (_) {}
    setTimeout(() => { if (hint.parentNode) hint.parentNode.removeChild(hint); }, 700);
  };
  setTimeout(dismiss, 8000);
  const ms = document.getElementById("manuscript");
  if (ms) ms.addEventListener("scroll", dismiss, { once: true, passive: true });
  document.addEventListener("pointerdown", dismiss, { once: true });
}

function applyDepthLayering() {
  const enabled = document.body.classList.contains("chronos-stacked-manuscript");
  // Phase 2.8: when the corridor manuscript is the active view, the
  // depth-stack inline transforms would FIGHT the corridor's per-frame
  // projection writes. Skip applyDepthLayering's transform writes when
  // corridor is on. The function still runs (so data-has-turn etc.
  // gets toggled), but the transform-setting branch is muted.
  const corridorActive =
    document.body.classList.contains("chronos-corridor-manuscript") &&
    typeof ChronosCorridor !== "undefined";

  // Force the 3D context onto the inner element directly via inline
  // style. Three previous attempts via stylesheet rules failed for
  // reasons I don't fully understand (cascade conflict? specificity?
  // browser render-engine quirk?). Inline style cannot lose to any
  // stylesheet rule short of !important, and nothing in the cascade
  // sets these with !important. This is the belt-and-suspenders fix.
  const inner = document.getElementById("manuscript-inner");
  if (inner && enabled && !corridorActive) {
    inner.style.perspective = "1400px";
    inner.style.perspectiveOrigin = "50% 30%";
    inner.style.transformStyle = "preserve-3d";
  }
  const tc = document.getElementById("turns-container");
  if (tc && enabled && !corridorActive) {
    tc.style.transformStyle = "preserve-3d";
  }

  const blocks = document.querySelectorAll(".turn-block");
  const total = blocks.length;
  // Mark the container the first time any real turn-block exists so
  // the intro block recedes. We also force the intro recede via
  // INLINE style here -- belt-and-suspenders for the same reason
  // applyDepthLayering is now setting transforms directly on blocks.
  if (tc) {
    // The intro might have been moved into #corridor-cards by the
    // corridor; scope our query so we don't set styles on the corridor's
    // copy.
    const intro = corridorActive ? null : tc.querySelector(".manuscript-intro");
    if (total > 0) {
      tc.setAttribute("data-has-turn", "1");
      if (intro) {
        intro.classList.remove("first-stack-reveal");
        if (enabled) {
          intro.style.transform = "translateZ(-500px)";
          intro.style.filter = "blur(2.2px)";
          intro.style.opacity = "0.5";
          intro.style.transition =
            "transform 0.9s cubic-bezier(0.4,0,0.2,1), filter 0.9s ease, opacity 0.9s ease";
          intro.style.transformStyle = "preserve-3d";
        }
      }
    } else {
      tc.removeAttribute("data-has-turn");
      if (intro) {
        intro.style.transform = "";
        intro.style.filter = "";
        intro.style.opacity = "";
      }
    }
  }
  blocks.forEach((block, index) => {
    const age = total - 1 - index;
    if (!enabled) {
      block.style.transform = "";
      block.style.filter = "";
      block.removeAttribute("data-deep");
      return;
    }
    // Phase 2.8: corridor owns the transform on its cards. Skip per-
    // block transform writes when corridor is active. The block still
    // gets the --turn-z / --turn-blur CSS variables for any code that
    // reads them, but the inline transform/filter is left alone.
    if (corridorActive) {
      return;
    }
    // Aggressive recession curve. Bumped from -300 to -360 because
    // even at -300 a 2-turn run still felt subtle to the user.
    //
    //   age 0  -> z=0,     blur 0
    //   age 1  -> z=-360,  blur 1.0
    //   age 2  -> z=-660,  blur 1.6
    //   age 3  -> z=-960,  blur 2.2
    //   age 5  -> z=-1500 (clamped at -1800)
    //   age 12+ -> z=-1800, content-visibility:auto
    const z = Math.max(-1800, -360 * age - 30 * age * age);
    const blur = Math.min(3, age * 0.9);
    // INLINE transform -- bypasses any cascade conflict.
    block.style.transform = "translateZ(" + z + "px)";
    block.style.filter = "blur(" + blur.toFixed(2) + "px)";
    block.style.transformStyle = "preserve-3d";
    block.style.transition =
      "transform 0.6s cubic-bezier(0.4,0,0.2,1), filter 0.6s ease, opacity 0.8s ease";
    // Keep the CSS variables too in case anything reads them.
    block.style.setProperty("--turn-z", z + "px");
    block.style.setProperty("--turn-blur", blur.toFixed(2) + "px");
    if (age > 12) {
      block.setAttribute("data-deep", "1");
    } else {
      block.removeAttribute("data-deep");
    }
  });
}

// Phase 2.7 — diagnostic helper. Returns a structured snapshot of
// every Phase-2.6/2.7-relevant runtime check so the user can paste
// the result back when something looks broken.
//
// Run from DevTools console:  chronosDiag()
//
// The intent is "show me the state of each gate at a glance" rather
// than "fix it for me" — keep this read-only and side-effect-free.
window.chronosDiag = function chronosDiag() {
  const has = (cls) => document.body.classList.contains(cls);
  const tc = document.getElementById("turns-container");
  const blocks = document.querySelectorAll(".turn-block");
  const intro = document.querySelector(".manuscript-intro");
  const introCS = intro ? getComputedStyle(intro) : null;
  const blockCS = blocks.length ? getComputedStyle(blocks[0]) : null;
  const innerCS = (() => {
    const e = document.getElementById("manuscript-inner");
    return e ? getComputedStyle(e) : null;
  })();
  const out = {
    flags: {
      stacked: has("chronos-stacked-manuscript"),
      globeDefault: has("chronos-globe-default"),
      no3d: has("chronos-no-3d"),
    },
    runtime: {
      THREE_loaded: typeof THREE !== "undefined",
      ChronosMap_kind: typeof ChronosMap === "undefined"
        ? "undefined"
        : (ChronosMap.show ? "object" : typeof ChronosMap),
      ChronosWarTable_kind: typeof ChronosWarTable === "undefined"
        ? "undefined"
        : (ChronosWarTable.show ? "object" : typeof ChronosWarTable),
      ChronosCorridor_kind: typeof ChronosCorridor === "undefined"
        ? "undefined"
        : (ChronosCorridor.show ? "object" : typeof ChronosCorridor),
      // state, runId, eraKey are module-scope `let`s, not on window.
      // We poke the closure references directly here.
      state_loaded: !!state,
      runId_loaded: !!runId,
      eraKey_loaded: !!eraKey,
    },
    corridor: typeof ChronosCorridor === "undefined" || !ChronosCorridor.getDiag
      ? "(unavailable)"
      : ChronosCorridor.getDiag(),
    manuscript_inner_perspective: innerCS ? innerCS.perspective : "(no element)",
    manuscript_inner_transform_style: innerCS ? innerCS.transformStyle : "(no element)",
    turns_container_has_data: tc ? tc.getAttribute("data-has-turn") : "(no element)",
    turn_block_count: blocks.length,
    first_block_z_var: blockCS ? blockCS.getPropertyValue("--turn-z").trim() : "(no blocks)",
    first_block_transform: blockCS ? blockCS.transform : "(no blocks)",
    intro_present: !!intro,
    intro_transform: introCS ? introCS.transform : "(no intro)",
  };
  console.log("[chronosDiag]", out);
  return out;
};

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

// T key — Phase 2.6 war-table toggle. Opens the regional 3D terrain
// view from the globe (or anywhere). Esc and the in-overlay close
// button dismiss; wartable.js handles those itself.
document.addEventListener("keydown", (e) => {
  if (e.key !== "t" && e.key !== "T") return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (!state || !runId || !eraKey) return;
  const a = document.activeElement;
  if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable)) return;
  if (typeof ChronosWarTable === "undefined") return;
  if (ChronosWarTable.isVisible()) {
    ChronosWarTable.hide();
  } else {
    ChronosWarTable.show(state, eraKey, runId);
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
  block.id = `turn-${Date.now()}`;
  block.className = "turn-block mb-8";
  const label = ticks === 30 ? "1 month" : `${ticks} turn${ticks > 1 ? "s" : ""}`;
  block.innerHTML =
    `<p class="text-sm italic text-white/55 mb-3 pl-3 border-l border-white/15">Time passes\u2026 (${esc(label)})</p>` +
    `<div class="turn-spinner"><div class="turn-spinner-ring"></div><span class="streaming-dots">\u00b7 \u00b7 \u00b7</span></div>`;
  turnsContainer.appendChild(block);
  block.scrollIntoView({ behavior: "smooth" });

  // Phase 2.8: a time-skip block also lands as a card in the corridor.
  // No connection edges (skip has no parsed_action / npc_responses);
  // it just shows up as a "time passes" marker along the path.
  if (typeof ChronosCorridor !== "undefined") {
    if (!ChronosCorridor.isVisible()) ChronosCorridor.show();
    ChronosCorridor.addTurn(block, null);
  }

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
    applyMemoryDecay();
    applyDepthLayering();
    _wireDecayHoverAll();
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
