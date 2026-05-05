/**
 * CHRONOS Manuscript Detective Board -- Phase 2.8 Phase A v3 (read-only).
 *
 * The manuscript is a 3D detective board. Each turn is a full readable
 * PAGE pinned at deterministic 3D coordinates derived from its turn
 * index plus its NPC + location associations. Causal threads connect
 * related pages. The player can DRAG any page to a new position; the
 * threads stretch to follow. Drag positions persist in the run's
 * session state via POST /api/run/{run_id}/board so reopening the run
 * restores the layout.
 *
 * Time is locked to the Z axis (newer turns close to camera at z=0,
 * older turns recede). X/Y is determined by:
 *   1. A deterministic column formula based on which NPC or location
 *      a turn primarily involves -- same NPC = same column every time.
 *   2. A row offset (rows wrap as the run grows).
 *   3. Plus any override the player has saved by dragging.
 *
 * No force simulator. No wandering layout. Same run = same initial
 * arrangement. The player's drags are the only thing that moves a
 * page off its deterministic spot.
 *
 * Cut-the-thread interaction is explicitly NOT in this commit -- it
 * lands in the next commit once the page-board itself is verified.
 *
 * Module shape: same IIFE / window.ChronosCorridor public API as v2
 * so existing app.js hooks (submitTurn / renderTurnStaggered /
 * enterGame / Z-key / skip endpoint) work unchanged. The TWO new
 * additions are applyBoardOverrides(boardState) and getBoardState();
 * everything else (init / show / hide / isVisible / addTurn /
 * notifyTurnComplete / addIntroCard / restoreFromContainer /
 * toggleConstellation / getDiag) keeps the same signatures.
 *
 * Renderer: DOM-overlay strategy unchanged from v2 -- Three.js draws
 * connection lines on a transparent canvas; turn-block DOM elements
 * live in #corridor-cards and are projected to screen coords each
 * frame. No CSS3DRenderer. No ES module switch.
 */

(function () {
  // Same opt-out as the other 3D modules: ?flat=1 disables.
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("flat") === "1") return;
  } catch (e) {
    return;
  }
  if (typeof THREE === "undefined") {
    console.warn("[corridor] THREE.js not loaded; corridor disabled.");
    return;
  }

  // ── State ────────────────────────────────────────────────────────────
  let scene, camera, renderer, raycaster;
  let lineGroup;
  let cardsLayer;
  let initialized = false;
  let isVisible = false;

  // Each card node: { id, el, kind, tier, pos: Vector3, idx: number }
  const cards = [];
  let nextTurnIndex = 0;
  const cardByTurnId = new Map();
  // NPC nodes -- one per unique NPC across the run, keyed by lowercased name.
  const npcNodes = new Map();
  // Edges: { from: nodeRef, to: nodeRef, kind, _key }
  const edges = [];

  // Layout constants. The board is a tall vertical "wall" of pages
  // arranged in columns. Z = age. X = column (deterministic by NPC
  // or location). Y = row (wraps every COLUMNS_PER_ROW turns).
  const Z_STEP = 1.55;
  const COLUMN_SPACING = 2.6;     // horizontal gap between columns
  const ROW_HEIGHT = 1.4;
  const COLUMNS_PER_ROW = 6;      // turns per row before y-wrap
  const COLUMN_HASH_RADIUS = 5;   // max column index either side of center

  // Board overrides: dict keyed by page id ("turn-<ts>" / "manuscript-intro")
  // mapping to {x, y, z}. Populated by applyBoardOverrides() at run load.
  // When set, addTurn uses these instead of deterministic positions.
  // When the player drags, we mutate this map and persist (debounced).
  const overrides = new Map();
  // Debounced persist. Mutating drag fires _schedulePersist on every
  // pointermove; the timer fires 500ms after the last move.
  let _persistTimer = null;
  // The current run id, set by show(); used as the POST target.
  let currentRunId = null;

  // Free-orbit camera.
  const camOrbit = {
    theta: 0,
    phi: Math.PI * 0.45,
    dist: 9.5,
    target: new THREE.Vector3(0, 0, 4),
  };
  const _defaultOrbit = {
    theta: 0,
    phi: Math.PI * 0.45,
    dist: 9.5,
    targetZ: 4,
  };
  let _constellation = false;

  // Column allocation. Each unique NPC name or location id gets a
  // deterministic column index. We use a hash-of-name lookup so the
  // same NPC always lands in the same column across reloads. New
  // names get the next free slot via a small linear-probe to avoid
  // collisions.
  const columnByKey = new Map(); // columnKey -> column index (integer, signed)
  const usedColumns = new Set(); // set of column indices currently in use

  function _significanceTier(score) {
    if (typeof score !== "number" || isNaN(score)) return "notable";
    if (score < 0.4) return "filler";
    if (score < 0.8) return "notable";
    return "decision";
  }

  // Connection-line styling per type. Phase 2.8 strong-threads:
  // colors are punchier, opacity bumped well above the old 0.35-0.7
  // band so threads read as load-bearing structure rather than
  // decorative hairlines, and each kind gets a `radius` for the
  // TubeGeometry that replaces THREE.Line. WebGL caps line width at
  // 1px regardless of linewidth; tubes give us real screen-space
  // thickness AND clean raycaster picking via the standard mesh path.
  const EDGE_STYLE = {
    action_npc_positive:  { color: 0x10b981, opacity: 0.85, radius: 0.045 },
    action_npc_negative:  { color: 0xef4444, opacity: 0.85, radius: 0.045 },
    action_npc_neutral:   { color: 0x71717a, opacity: 0.65, radius: 0.04  },
    action_divergence:    { color: 0xfcd34d, opacity: 0.95, radius: 0.05  },
    npc_npc:              { color: 0x94a3b8, opacity: 0.55, radius: 0.035 },
  };
  // Visual modifier when a thread has been cut (player-severed). The
  // tube renders as a stub from the source out to ~35% of the path,
  // narrower and more transparent so the cut reads as "broken,
  // dangling" rather than just "thinner line."
  const EDGE_CUT_OPACITY = 0.20;
  const EDGE_CUT_RADIUS_FACTOR = 0.7;
  const EDGE_CUT_LENGTH_FRACTION = 0.35;
  // Hover modifier -- briefly bump radius + opacity so the hovered
  // thread reads clearly even against a busy board.
  const EDGE_HOVER_RADIUS_FACTOR = 1.25;
  const EDGE_HOVER_OPACITY = 1.0;
  // Cut state -- which edge keys are currently severed. Populated by
  // applyBoardOverrides at run load and by _handleThreadClick on
  // user cut. Persisted via _persist alongside board_state.
  const cutEdgeKeys = new Set();

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    if (initialized) return;
    const container = document.getElementById("corridor-container");
    if (!container) return;

    let canvas = document.getElementById("corridor-canvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.id = "corridor-canvas";
      canvas.style.cssText =
        "position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;outline:none;";
      container.appendChild(canvas);
    }

    cardsLayer = document.getElementById("corridor-cards");
    if (!cardsLayer) {
      cardsLayer = document.createElement("div");
      cardsLayer.id = "corridor-cards";
      cardsLayer.style.cssText =
        "position:absolute;inset:0;pointer-events:none;perspective:1400px;perspective-origin:50% 35%;";
      container.appendChild(cardsLayer);
    }

    scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x000000, 18, 70);
    scene.background = null;

    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    camera = new THREE.PerspectiveCamera(58, w / h, 0.05, 200);
    _applyCameraOrbit();

    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 0);

    raycaster = new THREE.Raycaster();

    lineGroup = new THREE.Group();
    scene.add(lineGroup);

    _wireInteraction(canvas);
    _wireResize(container);

    initialized = true;
    _animate();
  }

  // ── Camera orbit ─────────────────────────────────────────────────────
  function _applyCameraOrbit() {
    if (!camera) return;
    // Defense-in-depth phi clamp. Same lesson as the war-table fix.
    const phi = Math.max(0.05, Math.min(Math.PI - 0.05, camOrbit.phi));
    camOrbit.phi = phi;
    const t = camOrbit.target;
    const x = t.x + camOrbit.dist * Math.sin(phi) * Math.sin(camOrbit.theta);
    const y = t.y + camOrbit.dist * Math.cos(phi);
    const z = t.z + camOrbit.dist * Math.sin(phi) * Math.cos(camOrbit.theta);
    camera.position.set(x, y, z);
    camera.lookAt(t);
  }

  function _resetView() {
    camOrbit.theta = _defaultOrbit.theta;
    camOrbit.phi = _defaultOrbit.phi;
    camOrbit.dist = _defaultOrbit.dist;
    camOrbit.target.set(0, 0, _defaultOrbit.targetZ);
    _constellation = false;
    _applyCameraOrbit();
  }

  // ── Interaction ──────────────────────────────────────────────────────
  let _camDragging = false;
  let _dragLast = { x: 0, y: 0 };
  const _keys = new Set();

  // Page drag state. When the user pointerdowns on a card, we capture
  // the card and drag it across a horizontal plane in world space.
  let _pageDrag = null; // { card, plane, offset: Vector3 }

  function _wireInteraction(canvas) {
    // Camera orbit drag. Only fires when the click STARTS on the
    // canvas itself, not on a card -- card drag has its own listener
    // via _wirePageDrag added per card in addTurn.
    //
    // Phase 2.8: also picks up start-of-thread-click info so a brief
    // click on a thread cuts it (vs a longer drag = camera orbit).
    canvas.addEventListener("pointerdown", (e) => {
      _camDragging = true;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      // Capture the pointerdown for the thread-click detector. The
      // raycast is done HERE so we know up-front whether the click
      // started over a thread; on pointerup we check movement and
      // fire the cut if it stayed close to its origin.
      _threadClickStart = {
        x: e.clientX,
        y: e.clientY,
        edge: _pickEdgeAt(e.clientX, e.clientY),
      };
      canvas.style.cursor = "grabbing";
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    });
    canvas.addEventListener("pointermove", (e) => {
      // Hover: even when not dragging, raycast each move to update
      // the thread tooltip. Throttled to one raycast per RAF via the
      // _hoverThrottled flag.
      _scheduleHoverRaycast(e.clientX, e.clientY);
      if (!_camDragging) return;
      const dx = e.clientX - _dragLast.x;
      const dy = e.clientY - _dragLast.y;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      const k = 0.0035 * Math.min(1.4, camOrbit.dist / 4);
      camOrbit.theta -= dx * k;
      camOrbit.phi = Math.max(0.05, Math.min(Math.PI - 0.05, camOrbit.phi - dy * k));
      _applyCameraOrbit();
    });
    const _release = (e) => {
      if (_camDragging) {
        _camDragging = false;
        canvas.style.cursor = "grab";
        try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      }
      // Thread-click detection: if the pointerdown landed on a thread
      // AND total movement is small (camera-orbit drags are typically
      // 10s-100s of pixels), treat as a click and cut the thread.
      if (_threadClickStart) {
        const start = _threadClickStart;
        _threadClickStart = null;
        if (start.edge && e.clientX != null) {
          const dx = (e.clientX - start.x);
          const dy = (e.clientY - start.y);
          if (dx * dx + dy * dy < 36) {  // <6px total movement
            _handleThreadClick(start.edge, e.clientX, e.clientY);
          }
        }
      }
    };
    canvas.addEventListener("pointerup", _release);
    canvas.addEventListener("pointercancel", _release);
    canvas.addEventListener("pointerleave", (e) => {
      _release(e);
      _hideThreadTooltip();
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const step = 0.12 * Math.max(0.4, camOrbit.dist - 1.5);
      const sign = e.deltaY > 0 ? 1 : -1;
      camOrbit.dist = Math.max(1.5, Math.min(40, camOrbit.dist + sign * step));
      _applyCameraOrbit();
    }, { passive: false });

    document.addEventListener("keydown", (e) => {
      if (!isVisible) return;
      const a = document.activeElement;
      if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "w" || k === "arrowup")    { _keys.add("forward");  e.preventDefault(); }
      if (k === "s" || k === "arrowdown")  { _keys.add("backward"); e.preventDefault(); }
      if (k === "a" || k === "arrowleft")  { _keys.add("left");     e.preventDefault(); }
      if (k === "d" || k === "arrowright") { _keys.add("right");    e.preventDefault(); }
    });
    document.addEventListener("keyup", (e) => {
      const k = e.key.toLowerCase();
      if (k === "w" || k === "arrowup")    _keys.delete("forward");
      if (k === "s" || k === "arrowdown")  _keys.delete("backward");
      if (k === "a" || k === "arrowleft")  _keys.delete("left");
      if (k === "d" || k === "arrowright") _keys.delete("right");
    });

    // Global pointermove + up for ACTIVE page drag. We want to keep
    // tracking the drag even if the cursor leaves the original card.
    document.addEventListener("pointermove", _onPageDragMove, true);
    document.addEventListener("pointerup", _onPageDragEnd, true);
  }

  // Per-card drag wiring. Called from addTurn for each new card.
  // The card needs pointer-events:auto from CSS for this to fire.
  function _wirePageDrag(card) {
    if (!card.el) return;
    card.el.addEventListener("pointerdown", (e) => {
      // Don't hijack clicks on interactive children (act-name buttons,
      // act-rumor, etc.) -- those are click affordances, not drag handles.
      if (e.target && e.target.closest && e.target.closest("[data-act], button")) {
        return;
      }
      // Compute the world position the cursor is currently over on
      // the card's plane (we use a horizontal X-Z plane at the
      // card's current y). Compute the offset from the cursor to the
      // card center so dragging doesn't snap the card to the cursor.
      const planeY = card.pos.y;
      const world = _screenToPlane(e.clientX, e.clientY, planeY);
      if (!world) return;
      _pageDrag = {
        card: card,
        planeY: planeY,
        offset: new THREE.Vector3(
          card.pos.x - world.x,
          0,
          card.pos.z - world.z,
        ),
      };
      card.el.classList.add("is-dragging");
      e.preventDefault();
      e.stopPropagation();
    });
  }

  function _onPageDragMove(e) {
    if (!_pageDrag) return;
    const world = _screenToPlane(e.clientX, e.clientY, _pageDrag.planeY);
    if (!world) return;
    const card = _pageDrag.card;
    // Apply offset so the card-to-cursor relationship stays constant
    // throughout the drag.
    card.pos.x = Math.max(-50, Math.min(50, world.x + _pageDrag.offset.x));
    // We DELIBERATELY allow Y to be tweaked by dragging by a small
    // amount: when the camera is angled, the user's intent is "move
    // this page across the wall," so we let the X-Z plane intersection
    // drive the position. But we LOCK z (time) -- a page can move
    // horizontally and vertically on the wall, but never travel through
    // time. To approximate this with a single horizontal plane, we
    // keep z fixed and only update x. Y stays at the deterministic
    // row position. This matches "slide a sheet of paper sideways."
    // (Future: support free vertical placement by intersecting a
    // tilted plane that follows the card's vertical row index.)
  }

  function _onPageDragEnd(e) {
    if (!_pageDrag) return;
    const card = _pageDrag.card;
    if (card.el) card.el.classList.remove("is-dragging");
    // Persist the new position.
    overrides.set(card.id, { x: card.pos.x, y: card.pos.y, z: card.pos.z });
    _schedulePersist();
    _pageDrag = null;
  }

  // Project a screen (x, y) to a world (x, _, z) by ray-casting
  // against a horizontal plane at the given Y. Returns null if the
  // ray is parallel to the plane.
  function _screenToPlane(clientX, clientY, planeY) {
    if (!camera || !renderer) return null;
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -(((clientY - rect.top) / rect.height) * 2 - 1),
    );
    raycaster.setFromCamera(ndc, camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -planeY);
    const target = new THREE.Vector3();
    const hit = raycaster.ray.intersectPlane(plane, target);
    return hit ? target : null;
  }

  function _updateCameraFromInput() {
    const panSpeed = 0.08;
    let moved = false;
    if (_keys.has("forward"))  { camOrbit.target.z += panSpeed; moved = true; }
    if (_keys.has("backward")) { camOrbit.target.z -= panSpeed; moved = true; }
    if (_keys.has("left"))     { camOrbit.target.x -= panSpeed; moved = true; }
    if (_keys.has("right"))    { camOrbit.target.x += panSpeed; moved = true; }
    if (moved) _applyCameraOrbit();
  }

  function _wireResize(container) {
    let raf = null;
    const onResize = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        if (!isVisible || !renderer || !camera) return;
        const w = container.clientWidth || window.innerWidth;
        const h = container.clientHeight || window.innerHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      });
    };
    window.addEventListener("resize", onResize);
  }

  // ── Render loop ──────────────────────────────────────────────────────
  function _animate() {
    if (!renderer) return;
    requestAnimationFrame(_animate);
    if (!isVisible) return;
    _updateCameraFromInput();
    _drawConnections();
    renderer.render(scene, camera);
    _projectCards();
  }

  // ── Deterministic position formula ───────────────────────────────────
  //
  // A turn's 3D position is determined by:
  //   z = turnIdx * Z_STEP                       (locked, age = depth)
  //   y = (turnIdx % COLUMNS_PER_ROW == 0)       (rows wrap every N turns)
  //       step + slight oscillation
  //   x = column owned by an attractor (NPC or location)
  //
  // The COLUMN is allocated like this:
  //   1. If the turn names a target NPC -> that NPC's column.
  //   2. Else, the first NPC in npc_responses -> that NPC's column.
  //   3. Else, the location id -> that location's column.
  //   4. Else, "filler" column at index 0.
  //
  // Each unique column key gets a stable integer column index via
  // _allocateColumn (deterministic-hash with linear-probe fallback so
  // the same key always picks the same column for a given run order).
  // This gives the visual property: pages cluster into vertical
  // columns by NPC/location, time runs down/back.
  function _deterministicPosition(turnIdx, columnKey) {
    const colIdx = _allocateColumn(columnKey || "_filler");
    const x = colIdx * COLUMN_SPACING;
    // Y: each turn nudges its row down by a bit so columns don't pile
    // up infinitely deep without break. Plus a small oscillation so
    // adjacent same-column turns visibly stack rather than overlapping.
    const rowSeed = turnIdx % COLUMNS_PER_ROW;
    const y = -rowSeed * 0.18; // gentle vertical stagger within a column
    const z = turnIdx * Z_STEP;
    return { x, y, z };
  }

  // Allocate a stable column index for a given key. Uses a hash to
  // pick a target column, then linear-probes outward if that column
  // is taken. The probe is deterministic given the same insertion
  // order, so reload-from-saved produces the identical layout.
  function _allocateColumn(key) {
    const existing = columnByKey.get(key);
    if (existing != null) return existing;
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
    let target = ((Math.abs(h) % (COLUMN_HASH_RADIUS * 2 + 1)) - COLUMN_HASH_RADIUS);
    // Linear-probe in alternating directions if the column is taken.
    let step = 0;
    while (usedColumns.has(target)) {
      step++;
      target = (step % 2 === 0)
        ? target + Math.ceil(step / 2)
        : target - Math.ceil(step / 2);
      if (Math.abs(target) > COLUMN_HASH_RADIUS * 4) break; // safety
    }
    columnByKey.set(key, target);
    usedColumns.add(target);
    return target;
  }

  // Pick the column key for a turn from its data, in priority order.
  function _columnKeyForTurn(data) {
    if (!data) return "_filler";
    const pa = data.parsed_action || data.parsed || {};
    if (pa.target && typeof pa.target === "string" && pa.target.trim()) {
      return "npc:" + pa.target.trim().toLowerCase();
    }
    const responses = data.npc_responses || [];
    if (responses.length > 0 && responses[0].npc_name) {
      return "npc:" + responses[0].npc_name.toLowerCase();
    }
    const pv = data.player_view || {};
    if (pv.current_location && pv.current_location.id) {
      return "loc:" + pv.current_location.id.toLowerCase();
    }
    return "_filler";
  }

  function _extractSignificance(data) {
    if (!data) return 0.5;
    const pa = data.parsed_action || data.parsed || {};
    const s = pa.significance_score;
    return typeof s === "number" ? s : 0.5;
  }

  // ── Card lifecycle ───────────────────────────────────────────────────
  function addTurn(blockEl, turnData) {
    if (!cardsLayer) init();
    if (!blockEl || !blockEl.classList || !blockEl.classList.contains("turn-block")) return;
    const tid = blockEl.id || "";
    if (tid && cardByTurnId.has(tid)) {
      if (turnData) {
        // notifyTurnComplete path: column might re-evaluate based on
        // full data. But changing a card's column after placement is
        // visually jarring -- keep it pinned. Just register edges.
        _registerEdgesForTurn(tid, turnData);
      }
      return;
    }
    const idx = nextTurnIndex++;
    const score = _extractSignificance(turnData);
    const tier = _significanceTier(score);
    const columnKey = _columnKeyForTurn(turnData);

    blockEl.classList.add("corridor-card");
    blockEl.dataset.significanceTier = tier;
    blockEl.style.position = "absolute";
    blockEl.style.left = "0";
    blockEl.style.top = "0";
    blockEl.style.transformOrigin = "50% 50%";
    blockEl.style.transition =
      "filter 0.4s ease, opacity 0.4s ease, transform 0.05s linear";
    if (blockEl.parentNode !== cardsLayer) {
      cardsLayer.appendChild(blockEl);
    }
    cards.forEach((c) => {
      if (c.el && c.kind === "turn") c.el.classList.remove("is-current");
    });
    blockEl.classList.add("is-current");

    // Compute deterministic position. If the player has a saved
    // override for this card id, use that instead.
    const det = _deterministicPosition(idx, columnKey);
    const ov = tid ? overrides.get(tid) : null;
    const pos = ov
      ? new THREE.Vector3(ov.x, ov.y, ov.z)
      : new THREE.Vector3(det.x, det.y, det.z);

    const card = {
      id: tid,
      el: blockEl,
      pos: pos,
      idx: idx,
      tier: tier,
      kind: "turn",
      columnKey: columnKey,
    };

    cards.push(card);
    if (tid) cardByTurnId.set(tid, card);
    if (turnData) _registerEdgesForTurn(tid, turnData);

    // Wire drag handler now that the card is in the DOM.
    _wirePageDrag(card);

    // Camera target slides to the present so the player's eye is on
    // the new turn.
    camOrbit.target.z = -1.5;
    _applyCameraOrbit();
  }

  function notifyTurnComplete(blockEl, data) {
    if (!blockEl) return;
    const tid = blockEl.id || "";
    const card = cardByTurnId.get(tid);
    if (!card) {
      addTurn(blockEl, data);
      return;
    }
    const score = _extractSignificance(data);
    const newTier = _significanceTier(score);
    if (newTier !== card.tier) {
      card.tier = newTier;
      blockEl.dataset.significanceTier = newTier;
    }
    _registerEdgesForTurn(tid, data);
  }

  function restoreFromContainer() {
    if (!cardsLayer) init();
    const tc = document.getElementById("turns-container");
    if (!tc) return;
    const blocks = tc.querySelectorAll(".turn-block");
    blocks.forEach((b) => addTurn(b, null));
    const intro = tc.querySelector(".manuscript-intro");
    if (intro) addIntroCard(intro);
  }

  function addIntroCard(introEl) {
    if (!introEl) return;
    if (!cardsLayer) init();
    if (introEl.dataset.corridorRegistered === "1") return;
    introEl.dataset.corridorRegistered = "1";
    introEl.classList.add("corridor-card", "corridor-card-intro");
    introEl.style.position = "absolute";
    introEl.style.left = "0";
    introEl.style.top = "0";
    introEl.style.transformOrigin = "50% 50%";
    introEl.style.transition =
      "filter 0.4s ease, opacity 0.4s ease, transform 0.05s linear";
    if (introEl.parentNode !== cardsLayer) {
      cardsLayer.appendChild(introEl);
    }
    // Intro sits at the deepest position at column 0, anchoring the
    // run's beginning at the time-axis origin.
    const introZ = (nextTurnIndex + 4) * Z_STEP;
    const ov = overrides.get("manuscript-intro");
    const pos = ov
      ? new THREE.Vector3(ov.x, ov.y, ov.z)
      : new THREE.Vector3(0, 0.4, introZ);
    const introCard = {
      id: "manuscript-intro",
      el: introEl,
      pos: pos,
      idx: -1,
      tier: "intro",
      kind: "intro",
    };
    cards.push(introCard);
    cardByTurnId.set("manuscript-intro", introCard);
    _wirePageDrag(introCard);
  }

  // ── Persistence ──────────────────────────────────────────────────────
  // Public method: applyBoardOverrides({turnId: {x, y, z}, ...}).
  // Called from app.js enterGame on initial run load. Stores the
  // saved layout so subsequent addTurn calls see overrides via
  // overrides.get(turnId). Existing cards (if any) get repositioned
  // immediately.
  // Phase 2.8 strong-threads: accepts an optional cutThreads array
  // alongside the board_state dict. Backward-compatible -- callers
  // passing only the dict still work (cutThreads defaults to
  // undefined and the cut state is left empty).
  function applyBoardOverrides(boardState, cutThreads) {
    if (boardState && typeof boardState === "object") {
      overrides.clear();
      Object.keys(boardState).forEach((key) => {
        const v = boardState[key];
        if (!v || typeof v !== "object") return;
        const x = Number(v.x);
        const y = Number(v.y);
        const z = Number(v.z);
        if (!isFinite(x) || !isFinite(y) || !isFinite(z)) return;
        overrides.set(key, { x: x, y: y, z: z });
      });
      // Apply to any cards already in the scene.
      cards.forEach((c) => {
        const ov = overrides.get(c.id);
        if (ov) {
          c.pos.x = ov.x;
          c.pos.y = ov.y;
          c.pos.z = ov.z;
        }
      });
    }
    if (Array.isArray(cutThreads)) {
      cutEdgeKeys.clear();
      cutThreads.forEach((k) => {
        if (typeof k === "string" && k.length > 0) cutEdgeKeys.add(k);
      });
      // Mark any already-registered edges as cut so the next render
      // shows them severed without waiting for a fresh add.
      edges.forEach((e) => {
        if (e._key && cutEdgeKeys.has(e._key)) e.cut = true;
      });
    }
  }

  // Set the run id (called from show()). Used as the POST target.
  function _setRunId(rid) {
    if (rid) currentRunId = rid;
  }

  // Debounced persist: schedule a POST 500ms after the last drag-move.
  function _schedulePersist() {
    if (_persistTimer) clearTimeout(_persistTimer);
    _persistTimer = setTimeout(_persist, 500);
  }

  function _persist() {
    _persistTimer = null;
    if (!currentRunId) return;
    const payload = { board_state: {}, cut_threads: Array.from(cutEdgeKeys) };
    overrides.forEach((pos, key) => {
      payload.board_state[key] = { x: pos.x, y: pos.y, z: pos.z };
    });
    fetch("/api/run/" + currentRunId + "/board", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch((e) => {
      // Silent on failure -- the layout is still correct in-memory;
      // a future drag will try again. Don't block the UI.
      console.warn("[corridor] board persist failed:", e);
    });
  }

  function getBoardState() {
    const out = {};
    overrides.forEach((pos, key) => {
      out[key] = { x: pos.x, y: pos.y, z: pos.z };
    });
    return out;
  }

  // ── Connection edges + templated explanations ──────────────────────
  // Phase 2.8 strong-threads/cut: each edge carries a one-sentence
  // explanation (shown on hover) and a structured `meta` payload used
  // to render the post-cut "what would have changed" preview text.
  // Templates are deterministic strings written here -- no LLM call,
  // no Gemini cost. Cut state is restored from cutEdgeKeys at edge
  // creation so reload preserves severed threads.

  function _registerEdgesForTurn(tid, data) {
    if (!data || !tid) return;
    const card = cardByTurnId.get(tid);
    if (!card) return;

    const playerInput = _extractPlayerInput(card);
    const turnLabel = _pageLabel(card);

    // 1) action -> NPC reaction edges, one per NPC POV.
    const npcResponses = data.npc_responses || [];
    const impacts = (data.parsed_action || data.parsed || {}).npc_impacts || [];
    npcResponses.forEach((r) => {
      if (!r || !r.npc_name) return;
      const sentiment = _sentimentForNpc(r.npc_name, impacts);
      const npcNode = _ensureNpcNode(r.npc_name, r.npc_role || "");
      if (!npcNode) return;
      const kind = sentiment === "positive" ? "action_npc_positive"
                 : sentiment === "negative" ? "action_npc_negative"
                 : "action_npc_neutral";
      const reasonNote = _impactReason(r.npc_name, impacts);
      const explanation = _explainActionNpc(turnLabel, r.npc_name, sentiment, reasonNote);
      _pushEdge(card, npcNode, kind, tid + "->npc:" + r.npc_name, {
        explanation: explanation,
        meta: {
          kind: "action_npc",
          npc: r.npc_name,
          sentiment: sentiment,
          turnLabel: turnLabel,
          playerInput: playerInput,
        },
      });
    });

    // 2) action -> divergence edges.
    const divergences = data.divergences || [];
    divergences.forEach((d, i) => {
      const offset = (i % 2 === 0 ? 1.4 : -1.4);
      const anchorPos = new THREE.Vector3(
        card.pos.x + offset,
        card.pos.y + 0.6,
        card.pos.z,
      );
      const divNode = _ensureDivergenceNode(tid + ":div:" + i, d, anchorPos);
      if (!divNode) return;
      const canon = (d && d.canonical_event) ? String(d.canonical_event) : "(canonical event averted)";
      _pushEdge(card, divNode, "action_divergence", tid + "->div:" + i, {
        explanation: "This action superseded the canonical event: " + canon,
        meta: {
          kind: "action_divergence",
          canonical_event: canon,
          turnLabel: turnLabel,
          playerInput: playerInput,
        },
      });
    });

    // 3) NPC <-> NPC ambient interactions.
    const ambient = data.ambient_activity || [];
    ambient.forEach((a) => {
      if (!a || !a.npc_name || !a.interacts_with) return;
      const aNode = _ensureNpcNode(a.npc_name, "");
      const bNode = _ensureNpcNode(a.interacts_with, "");
      if (!aNode || !bNode) return;
      _pushEdge(aNode, bNode, "npc_npc", tid + ":" + a.npc_name + "<->" + a.interacts_with, {
        explanation: a.npc_name + " and " + a.interacts_with + " were seen together this turn.",
        meta: {
          kind: "npc_npc",
          a: a.npc_name,
          b: a.interacts_with,
          turnLabel: turnLabel,
        },
      });
    });
  }

  // Lift the player's typed action snippet from the card's DOM. The
  // first <p class="text-sm italic"> in the card is the player-input
  // header set by submitTurn / renderTurnStaggered. Empty string when
  // the card is restored from saved HTML before this snippet existed.
  function _extractPlayerInput(card) {
    if (!card || !card.el) return "";
    const p = card.el.querySelector("p.text-sm.italic, p.italic.text-sm");
    if (!p) return "";
    const text = (p.textContent || "").trim();
    return text.length > 80 ? text.slice(0, 77) + "\u2026" : text;
  }

  // Human label for a turn card -- used as the subject of an
  // explanation sentence. "Turn 4 -- 'I threaten the abbot'" reads
  // better than "the action at z=5.6".
  function _pageLabel(card) {
    if (!card) return "this turn";
    const idx = (card.idx != null && card.idx >= 0) ? "Turn " + (card.idx + 1) : "this turn";
    const action = _extractPlayerInput(card);
    return action ? (idx + " -- '" + action + "'") : idx;
  }

  // Lookup the impact reason string for a given NPC if the action
  // parser provided one. Falls back to "" so the explanation
  // template stays grammatical without it.
  function _impactReason(name, impacts) {
    for (let i = 0; i < impacts.length; i++) {
      const im = impacts[i];
      if (im && im.name && im.name.toLowerCase() === name.toLowerCase()) {
        return (im.reason || "").trim();
      }
    }
    return "";
  }

  function _explainActionNpc(turnLabel, npcName, sentiment, reason) {
    const verb = sentiment === "positive" ? "warmed toward you"
               : sentiment === "negative" ? "turned against you"
               : "took notice";
    if (reason) {
      return turnLabel + ": " + npcName + " " + verb + " (" + reason + ").";
    }
    return turnLabel + ": " + npcName + " " + verb + ".";
  }

  function _sentimentForNpc(name, impacts) {
    for (let i = 0; i < impacts.length; i++) {
      const im = impacts[i];
      if (!im || !im.name) continue;
      if (im.name.toLowerCase() === name.toLowerCase()) {
        return im.sentiment || "neutral";
      }
    }
    return "neutral";
  }

  function _pushEdge(fromNode, toNode, kind, key, opts) {
    if (!fromNode || !toNode) return;
    if (key) {
      for (let i = 0; i < edges.length; i++) {
        if (edges[i]._key === key) return;
      }
    }
    const o = opts || {};
    edges.push({
      from: fromNode,
      to: toNode,
      kind: kind,
      _key: key,
      // Phase 2.8: cut state restored from cutEdgeKeys at creation so
      // a reload (which re-fires _registerEdgesForTurn for restored
      // turns) brings back the severed-thread visual.
      cut: !!(key && cutEdgeKeys.has(key)),
      explanation: o.explanation || "",
      meta: o.meta || {},
    });
  }

  function _ensureNpcNode(name, role) {
    if (!name) return null;
    const key = name.toLowerCase();
    let node = npcNodes.get(key);
    if (node) return node;
    if (!cardsLayer) return null;

    const el = document.createElement("div");
    el.className = "corridor-npc-node";
    el.innerHTML =
      '<div class="cnn-name">' + _escHtml(name) + "</div>" +
      (role ? '<div class="cnn-role">' + _escHtml(role) + "</div>" : "");
    el.style.cssText =
      "position:absolute;left:0;top:0;transform:translate(-9999px,-9999px);" +
      "pointer-events:auto;cursor:default;transform-origin:50% 50%;";
    cardsLayer.appendChild(el);

    // NPC nodes get the same column as their NPC (so threads from
    // turns to NPCs stay vertical and the "this NPC owns this column"
    // metaphor reads). Z is a running average of the turns referencing
    // this NPC -- updated here on creation, then by addTurn calls.
    const colIdx = _allocateColumn("npc:" + key);
    const x = colIdx * COLUMN_SPACING;
    const y = 0.8; // sits slightly above the row of turn cards
    const z = nextTurnIndex > 0 ? (nextTurnIndex - 1) * Z_STEP : 0;
    const ov = overrides.get("npc:" + key);
    const pos = ov
      ? new THREE.Vector3(ov.x, ov.y, ov.z)
      : new THREE.Vector3(x, y, z);
    node = {
      id: "npc:" + key,
      name: name,
      role: role,
      el: el,
      pos: pos,
      idx: -2,
      tier: "notable",
      kind: "npc",
    };
    npcNodes.set(key, node);
    return node;
  }

  function _ensureDivergenceNode(key, divergence, anchorPos) {
    if (cardByTurnId.has("div:" + key)) return cardByTurnId.get("div:" + key);
    if (!cardsLayer) return null;
    const el = document.createElement("div");
    el.className = "corridor-divergence-marker";
    const canonText = divergence && divergence.canonical_event
      ? String(divergence.canonical_event).slice(0, 90)
      : "(canonical event averted)";
    el.innerHTML =
      '<div class="cdm-label">DIVERGENCE</div>' +
      '<div class="cdm-text">' + _escHtml(canonText) + "</div>";
    el.style.cssText =
      "position:absolute;left:0;top:0;transform:translate(-9999px,-9999px);" +
      "pointer-events:none;transform-origin:50% 50%;";
    cardsLayer.appendChild(el);
    const id = "div:" + key;
    const ov = overrides.get(id);
    const pos = ov
      ? new THREE.Vector3(ov.x, ov.y, ov.z)
      : anchorPos.clone();
    const node = {
      id: id,
      el: el,
      pos: pos,
      idx: -3,
      tier: "notable",
      kind: "divergence",
    };
    cards.push(node);
    cardByTurnId.set(id, node);
    return node;
  }

  // ── Connection lines ─────────────────────────────────────────────────
  function _drawConnections() {
    while (lineGroup.children.length) {
      const c = lineGroup.children.pop();
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
    }
    edges.forEach(_addEdgeGeometry);
  }

  function _addEdgeGeometry(edge) {
    if (!edge.from || !edge.to) return;
    const style = EDGE_STYLE[edge.kind] || EDGE_STYLE.npc_npc;
    const a = edge.from.pos.clone();
    const b = edge.to.pos.clone();
    // Reject degenerate near-zero-length tubes -- a from/to that
    // resolved to the same world position (rare but possible if two
    // nodes share an anchor position) crashes TubeGeometry.
    if (a.distanceTo(b) < 0.001) return;
    const isCut = !!edge.cut;
    const isHover = (edge === _hoveredEdge);
    const endPoint = isCut ? a.clone().lerp(b, EDGE_CUT_LENGTH_FRACTION) : b;
    const path = new THREE.LineCurve3(a, endPoint);
    const baseRadius = style.radius || 0.04;
    const radius = baseRadius
      * (isCut ? EDGE_CUT_RADIUS_FACTOR : 1.0)
      * (isHover ? EDGE_HOVER_RADIUS_FACTOR : 1.0);
    const opacity = isCut
      ? EDGE_CUT_OPACITY
      : (isHover ? EDGE_HOVER_OPACITY : style.opacity);
    // 1 tubular segment is fine for a straight LineCurve3 -- the tube
    // is a constant-radius cylinder. 8 radial segments gives a clean
    // round profile at all reasonable camera distances; bumping to 12
    // is invisible. ~4800 tris for a 60-turn / 240-edge run -- trivial.
    const geo = new THREE.TubeGeometry(path, 1, radius, 8, false);
    const mat = new THREE.MeshBasicMaterial({
      color: style.color,
      transparent: true,
      opacity: opacity,
      depthWrite: false,
    });
    const tube = new THREE.Mesh(geo, mat);
    // Stash the source edge on the mesh so the raycaster can recover
    // the edge object on hover/click.
    tube.userData.edge = edge;
    lineGroup.add(tube);
  }
  // Currently hovered edge (set by the hover handler each frame).
  let _hoveredEdge = null;

  // ── Thread hover + click-to-cut ─────────────────────────────────────
  // The board has up to a few hundred tubes. We raycast on every
  // pointermove (at most once per RAF, throttled). On hit we show
  // a small floating tooltip with the edge's templated explanation
  // and bump the tube's apparent thickness/opacity for the next
  // frame. Click-to-cut: if pointerdown landed on a tube and pointerup
  // is within a 6px box of the start, fire _handleThreadClick.

  // Pointerdown snapshot used to disambiguate a thread-click from a
  // camera-orbit drag on pointerup.
  let _threadClickStart = null;
  // Throttle the per-pointermove raycast to at most once per frame.
  let _hoverThrottled = false;
  let _pendingHoverPos = null;
  // Lazy ref to the floating tooltip DOM node.
  let _threadTooltipEl = null;

  // Run a raycast against the lineGroup tubes for the cursor at
  // (clientX, clientY). Returns the hit edge or null.
  function _pickEdgeAt(clientX, clientY) {
    if (!camera || !renderer || !raycaster || !lineGroup) return null;
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -(((clientY - rect.top) / rect.height) * 2 - 1),
    );
    raycaster.setFromCamera(ndc, camera);
    const hits = raycaster.intersectObjects(lineGroup.children, false);
    if (hits.length === 0) return null;
    return hits[0].object && hits[0].object.userData
      ? hits[0].object.userData.edge || null
      : null;
  }

  // Schedule a hover raycast for the next animation frame. If the
  // cursor moves multiple times before the frame ticks, only the
  // most-recent position is processed -- avoids burning CPU on
  // raycasts the user never sees the result of.
  function _scheduleHoverRaycast(clientX, clientY) {
    _pendingHoverPos = { x: clientX, y: clientY };
    if (_hoverThrottled) return;
    _hoverThrottled = true;
    requestAnimationFrame(() => {
      _hoverThrottled = false;
      const p = _pendingHoverPos;
      _pendingHoverPos = null;
      if (!p) return;
      _processHover(p.x, p.y);
    });
  }

  function _processHover(clientX, clientY) {
    const edge = _pickEdgeAt(clientX, clientY);
    if (edge !== _hoveredEdge) {
      _hoveredEdge = edge;
      // _drawConnections is rebuilt every frame from the edges array,
      // and reads _hoveredEdge for the radius/opacity bump, so the
      // change applies on the next render frame automatically.
    }
    if (edge && edge.explanation) {
      _showThreadTooltip(edge.explanation, clientX, clientY);
    } else {
      _hideThreadTooltip();
    }
  }

  function _ensureThreadTooltip() {
    if (_threadTooltipEl && _threadTooltipEl.isConnected) return _threadTooltipEl;
    let el = document.getElementById("corridor-thread-tooltip");
    if (!el) {
      el = document.createElement("div");
      el.id = "corridor-thread-tooltip";
      document.body.appendChild(el);
    }
    _threadTooltipEl = el;
    return el;
  }

  function _showThreadTooltip(text, clientX, clientY) {
    const el = _ensureThreadTooltip();
    el.textContent = text;
    el.style.display = "block";
    // Anchor near the cursor with a small offset so the tooltip
    // doesn't sit under the pointer (which would intercept the next
    // raycast). Bottom-right by default, flipped if near edges.
    const margin = 14;
    let x = clientX + margin;
    let y = clientY + margin;
    // Flip if the tooltip would overflow the viewport.
    const w = el.offsetWidth || 240;
    const h = el.offsetHeight || 60;
    if (x + w > window.innerWidth - 8) x = clientX - margin - w;
    if (y + h > window.innerHeight - 8) y = clientY - margin - h;
    el.style.transform = "translate(" + x + "px," + y + "px)";
  }

  function _hideThreadTooltip() {
    if (_threadTooltipEl) _threadTooltipEl.style.display = "none";
  }

  // ── Cut a thread + render preview note ──────────────────────────────
  function _handleThreadClick(edge, clientX, clientY) {
    if (!edge || edge.cut) return;  // idempotent
    edge.cut = true;
    if (edge._key) cutEdgeKeys.add(edge._key);
    _schedulePersist();
    _showCutPreview(edge, clientX, clientY);
  }

  // Floating .corridor-cut-preview note. Auto-dismiss after 8s OR
  // on outside-click. Positioned at the cursor for now -- the edge
  // midpoint would track better but cards drift on drag and the
  // note would chase. Cursor anchor is honest about "this is the
  // place you decided to cut."
  function _showCutPreview(edge, clientX, clientY) {
    // Remove any existing preview note first -- one at a time.
    const prior = document.querySelectorAll(".corridor-cut-preview");
    prior.forEach((n) => n.parentNode && n.parentNode.removeChild(n));

    const note = document.createElement("div");
    note.className = "corridor-cut-preview";
    note.textContent = _explainCut(edge);
    document.body.appendChild(note);

    // Position at cursor + offset; flip near edges.
    const margin = 18;
    const w = 260;
    let x = (clientX != null ? clientX : window.innerWidth / 2) + margin;
    let y = (clientY != null ? clientY : window.innerHeight / 2) + margin;
    if (x + w > window.innerWidth - 8) x = clientX - margin - w;
    note.style.left = x + "px";
    note.style.top = y + "px";

    const dismiss = () => {
      if (!note.parentNode) return;
      note.parentNode.removeChild(note);
      document.removeEventListener("pointerdown", outsideHandler, true);
    };
    note.addEventListener("click", dismiss);
    // Outside-click dismiss. Capture-phase so it fires before our
    // canvas pointerdown handler steals it.
    const outsideHandler = (e) => {
      if (note.contains(e.target)) return;
      dismiss();
    };
    setTimeout(() => {
      document.addEventListener("pointerdown", outsideHandler, true);
    }, 0);
    // Auto-dismiss timer.
    setTimeout(dismiss, 8000);
  }

  // Templated read-only "what would have changed" preview. No LLM,
  // no Gemini cost. Phase B (simulation actually rewinding when a
  // thread is cut) is blocked by the 3 open questions; this is the
  // honest read-only version that ships in Phase A.
  function _explainCut(edge) {
    const m = edge.meta || {};
    if (m.kind === "action_npc") {
      const verb = m.sentiment === "positive" ? "warmed toward you"
                 : m.sentiment === "negative" ? "turned against you"
                 : "taken notice of you";
      return "Without this turn, " + (m.npc || "they") + " might never have " + verb + ".";
    }
    if (m.kind === "action_divergence") {
      return "Without this turn, the canonical event would have unfolded: " + (m.canonical_event || "(an event averted)") + ".";
    }
    if (m.kind === "npc_npc") {
      return "Without this turn, " + (m.a || "they") + " and " + (m.b || "they") + " might never have crossed paths.";
    }
    return "If this hadn't happened, what followed wouldn't have either.";
  }

  // ── DOM-card projection ──────────────────────────────────────────────
  function _projectCards() {
    if (!camera || !cardsLayer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const tmp = new THREE.Vector3();
    cards.forEach((c) => _projectOne(c, w, h, tmp));
    npcNodes.forEach((n) => _projectOne(n, w, h, tmp));
  }

  function _projectOne(c, w, h, tmp) {
    if (!c.el || !c.pos) return;
    tmp.copy(c.pos).project(camera);
    if (tmp.z > 1) {
      c.el.style.opacity = "0";
      c.el.style.pointerEvents = "none";
      return;
    }
    const sx = (tmp.x * 0.5 + 0.5) * w;
    const sy = (1 - (tmp.y * 0.5 + 0.5)) * h;
    const dist = camera.position.distanceTo(c.pos);
    const baseScale = c.kind === "intro" ? 1.05
                    : c.kind === "npc"   ? 0.55
                    : c.kind === "divergence" ? 0.75
                    : 1.0;
    const tier = c.tier || "notable";
    const tierScale = tier === "decision" ? 1.1 : tier === "filler" ? 0.85 : 1.0;
    const distScale = Math.max(0.45, 1 - Math.min(0.55, dist * 0.04));
    const scale = baseScale * tierScale * distScale;
    const cw = c.el.offsetWidth || 440;
    const ch = c.el.offsetHeight || 480;
    const tx = sx - (cw * scale) / 2;
    const ty = sy - (ch * scale) / 2;
    let opacity = 1;
    if (dist > 6) opacity = Math.max(0.25, 1 - (dist - 6) * 0.04);
    if (tier === "filler") opacity *= 0.85;
    c.el.style.transform = "translate3d(" + tx + "px," + ty + "px,0) scale(" + scale.toFixed(3) + ")";
    c.el.style.opacity = opacity.toFixed(3);
    c.el.style.pointerEvents = opacity > 0.4 ? "auto" : "none";
    c.el.style.zIndex = String(10000 - Math.round(dist * 10));
  }

  function _escHtml(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Lifecycle ────────────────────────────────────────────────────────
  function show(runId) {
    init();
    if (runId) _setRunId(runId);
    const container = document.getElementById("corridor-container");
    if (!container) return;
    container.classList.remove("hidden");
    isVisible = true;
    if (renderer && camera) {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      }
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        container.classList.add("ready");
      });
    });
  }
  function hide() {
    const container = document.getElementById("corridor-container");
    if (container) container.classList.add("hidden");
    isVisible = false;
  }

  function toggleConstellation() {
    _constellation = !_constellation;
    if (_constellation) {
      camOrbit.theta = 0;
      camOrbit.phi = 0.55;
      camOrbit.dist = Math.max(16, 4 + nextTurnIndex * Z_STEP * 0.7);
      camOrbit.target.set(0, 0, (nextTurnIndex * Z_STEP) / 2);
    } else {
      _resetView();
    }
    _applyCameraOrbit();
    return _constellation;
  }

  function getDiag() {
    const cardCounts = { turn: 0, intro: 0, divergence: 0 };
    cards.forEach((c) => { cardCounts[c.kind] = (cardCounts[c.kind] || 0) + 1; });
    return {
      card_count: cards.length,
      card_kinds: cardCounts,
      npc_node_count: npcNodes.size,
      edge_count: edges.length,
      column_count: columnByKey.size,
      override_count: overrides.size,
      camera: {
        theta: camOrbit.theta,
        phi: camOrbit.phi,
        dist: camOrbit.dist,
        target_z: camOrbit.target.z,
      },
      constellation_overview: _constellation,
      run_id: currentRunId,
    };
  }

  // tune() kept as no-op for backward compat with chronosDiag callers.
  // The force simulator is gone in v3; there's nothing to tune. Returns
  // the (empty) settings object so existing chronosDiag display works.
  function tune(_opts) {
    return { note: "force simulator retired in Phase 2.8 v3 (detective board)" };
  }

  window.ChronosCorridor = {
    init: init,
    show: show,
    hide: hide,
    isVisible: function () { return isVisible; },
    addTurn: addTurn,
    notifyTurnComplete: notifyTurnComplete,
    addIntroCard: addIntroCard,
    restoreFromContainer: restoreFromContainer,
    toggleConstellation: toggleConstellation,
    applyBoardOverrides: applyBoardOverrides,
    getBoardState: getBoardState,
    tune: tune,
    getDiag: getDiag,
  };
})();
