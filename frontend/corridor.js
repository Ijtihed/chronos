/**
 * CHRONOS Corridor Manuscript -- Phase 2.8 Phase A (read-only).
 *
 * The manuscript is a corridor in 3D space. Each past turn hangs at a
 * 3D position along a meandering path the character actually walked.
 * Causal connections between turns -- a betrayal pointing forward to
 * its consequence, a person you met pointing forward to a rumor about
 * them later -- are drawn as visible lines linking the cards across
 * space. The player navigates by moving the camera through the
 * corridor: forward in physical space goes back in time; backward
 * returns to now. Reading the past is travel.
 *
 * Design source of truth: context/game logic context/manuscript-as-artifact.md
 * (Phase 2.8 section). Roadmap entry: roadmap.md "PHASE 2.8 -- The
 * corridor manuscript".
 *
 * Architecture (DOM-overlay strategy):
 *
 *   Three.js renders ONLY connection lines on a transparent canvas.
 *   Turn cards are real DOM elements (the existing .turn-block markup,
 *   moved out of #turns-container into #corridor-cards). Each frame we
 *   project each card's 3D world position to screen coords and set
 *   inline transform: translate3d(...). This reuses the proven pattern
 *   from globe.js DOM markers and wartable.js DOM labels.
 *
 *   Why DOM-overlay instead of Three.js CSS3DRenderer:
 *   - No ES module switch (existing globe.js / wartable.js stay as
 *     script-tag globals reading window.THREE).
 *   - Existing turn-block CSS classes, click affordances, memory-decay
 *     wiring, and inner-thought slot all work UNCHANGED. Cards stay
 *     fully readable HTML; only their position is computed in 3D.
 *   - Cards billboard to the camera (always face the reader), so a
 *     turn is always reader-friendly regardless of camera angle.
 *
 * Activation: body.chronos-corridor-manuscript (default on).
 * ?flat=1 disables both this and the depth-stack, falls back to the
 * legacy vertical scroll.
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
  let scene, camera, renderer, raycaster, mouse;
  let lineGroup;        // Three.js group for all connection-line geometry
  let cardsLayer;       // DOM div that holds the moved .turn-block elements
  let initialized = false;
  let isVisible = false;

  // Each card: { id, el, pos: Vector3, age: int, significance: float, kind:'turn'|'intro'|'npc' }
  // Indexed by an internal sequence number, which corresponds to age
  // along the path. The intro card sits at index -1 (deepest in the
  // corridor). New turns increment a counter and take the next index.
  const cards = [];
  let nextTurnIndex = 0;
  // Map from turnId (the "turn-<timestamp>" id of the .turn-block) to
  // its card index, so notifyTurnComplete can find the right card.
  const cardByTurnId = new Map();
  // NPC nodes -- one per unique NPC across the run, keyed by name.
  // Each: { name, role, lat, lon, locName, lastTurnIdx, pos, el }
  const npcNodes = new Map();
  // Edges to render every frame: { from: Vector3, to: Vector3, kind, sentiment? }
  const edges = [];

  // Camera state. Position along the path is `cameraT` (unitless, 0 = at
  // the most recent turn). Negative cameraT walks INTO the past.
  // Positive overshoots ahead of the player (rare). Yaw/pitch are
  // mouse-pivot deltas applied to the camera's look direction.
  const camState = {
    t: 0,        // position along path, unit = "one turn back per unit"
    yaw: 0,      // horizontal pivot (radians)
    pitch: -0.05, // tiny down-tilt so cards aren't perfectly head-on
    velocity: 0, // for smooth WASD
  };
  // Constellation mode: pulled-back overview (toggled by Z key).
  let _constellation = false;

  // Path geometry. Each turn advances FORWARD along the camera's
  // initial -Z axis, with a slow horizontal arc. Newest turn at the
  // origin, older turns deeper into +Z (further from camera).
  const PATH_STEP = 1.6;          // units between turns
  const PATH_BEND_PER_TURN = 0.07; // radians of horizontal arc per turn
  const PATH_HEIGHT_OSC = 0.08;    // tiny vertical sine to break flatness

  // Significance tiers (matches the doc).
  // < 0.4: filler -- smaller, dimmer, central
  // < 0.8: notable -- full size
  // >= 0.8: decision -- larger, brighter, slightly off-path
  function _significanceTier(score) {
    if (typeof score !== "number" || isNaN(score)) return "notable";
    if (score < 0.4) return "filler";
    if (score < 0.8) return "notable";
    return "decision";
  }
  function _significanceLateral(score) {
    // Decisions get pushed sideways alternating left/right based on
    // index parity so multiple decisions in a row don't clump.
    if (typeof score !== "number" || score < 0.8) return 0;
    return 0.6;
  }

  // Connection-line styling per type.
  const EDGE_STYLE = {
    action_npc_positive:  { color: 0x10b981, opacity: 0.55, dashed: false },
    action_npc_negative:  { color: 0xef4444, opacity: 0.55, dashed: false },
    action_npc_neutral:   { color: 0x71717a, opacity: 0.45, dashed: false },
    action_divergence:    { color: 0xfcd34d, opacity: 0.7,  dashed: true  },
    npc_npc:              { color: 0x94a3b8, opacity: 0.35, dashed: true  },
  };

  // ── Path geometry ────────────────────────────────────────────────────
  // Index 0 = the most recent turn (camera-at-rest looks at it).
  // Index N (N > 0) = N turns ago, deeper into +Z.
  // Index -1 = the intro card, anchored slightly past the oldest turn.
  function _pathPoint(index) {
    // Negative bend phase so that walking forward (+t) sweeps INTO the
    // past in a leftward-bending arc -- arbitrary but consistent.
    const bend = index * PATH_BEND_PER_TURN;
    const z = index * PATH_STEP;
    const x = Math.sin(bend) * 0.9; // gentle horizontal drift
    const y = Math.sin(index * 0.4) * PATH_HEIGHT_OSC;
    return new THREE.Vector3(x, y, z);
  }

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

    // The cards layer is a sibling of the canvas, sitting above it.
    // Each card we move into here is absolutely positioned and gets
    // its transform updated every frame.
    cardsLayer = document.getElementById("corridor-cards");
    if (!cardsLayer) {
      cardsLayer = document.createElement("div");
      cardsLayer.id = "corridor-cards";
      cardsLayer.style.cssText =
        "position:absolute;inset:0;pointer-events:none;perspective:1400px;perspective-origin:50% 35%;";
      container.appendChild(cardsLayer);
    }

    scene = new THREE.Scene();
    // Subtle dark fog so far cards in the corridor fade to black.
    scene.fog = new THREE.Fog(0x000000, 30, 90);
    scene.background = null; // transparent canvas

    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    // Wider FOV than the globe (which is at distance) so the corridor
    // feels enclosed, hallway-like, instead of telephoto-flat.
    camera = new THREE.PerspectiveCamera(60, w / h, 0.05, 200);
    _placeCameraAtRest();

    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 0);

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    lineGroup = new THREE.Group();
    scene.add(lineGroup);

    _wireInteraction(canvas);
    _wireResize(container);

    initialized = true;
    _animate();
  }

  function _placeCameraAtRest() {
    // Camera sits slightly in front of the most-recent turn, looking
    // back into the past.
    const present = _pathPoint(0);
    camera.position.set(present.x, present.y + 0.2, present.z - 1.8);
    camera.lookAt(present.x, present.y, present.z);
  }

  // ── Interaction (WASD + arrow keys + mouse-drag pivot) ───────────────
  let _dragging = false;
  let _dragLast = { x: 0, y: 0 };
  const _keys = new Set();

  function _wireInteraction(canvas) {
    canvas.addEventListener("pointerdown", (e) => {
      _dragging = true;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      canvas.style.cursor = "grabbing";
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!_dragging) return;
      const dx = e.clientX - _dragLast.x;
      const dy = e.clientY - _dragLast.y;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      camState.yaw -= dx * 0.0035;
      camState.pitch = Math.max(-0.6, Math.min(0.6, camState.pitch - dy * 0.0035));
    });
    const _release = (e) => {
      if (!_dragging) return;
      _dragging = false;
      canvas.style.cursor = "grab";
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    canvas.addEventListener("pointerup", _release);
    canvas.addEventListener("pointercancel", _release);
    canvas.addEventListener("pointerleave", _release);

    canvas.addEventListener("wheel", (e) => {
      // Wheel walks along the path: deltaY > 0 means forward (into
      // the past), < 0 means backward (toward present).
      e.preventDefault();
      camState.t += e.deltaY * 0.003;
      _clampCameraT();
    }, { passive: false });

    // Keyboard navigation: WASD + arrows. Only when corridor is the
    // active overlay AND not focused on a text input.
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
  }

  function _clampCameraT() {
    // Don't let the camera fly past the most recent turn (forward of
    // the present) or further than a few turns past the deepest one.
    const maxBack = Math.max(8, nextTurnIndex + 4);
    if (camState.t < -2) camState.t = -2;
    if (camState.t > maxBack) camState.t = maxBack;
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

  function _updateCameraFromInput() {
    // WASD movement: forward/backward steps t along path; left/right
    // strafes the camera laterally without changing path position.
    const walkSpeed = 0.06;
    if (_keys.has("forward"))  camState.t += walkSpeed;
    if (_keys.has("backward")) camState.t -= walkSpeed;
    _clampCameraT();

    // Smoothly position the camera along the path at camState.t.
    const onPath = _pathPoint(camState.t);
    let strafe = 0;
    if (_keys.has("left"))  strafe -= 0.03;
    if (_keys.has("right")) strafe += 0.03;

    if (_constellation) {
      // Pull-back overview: float far above and behind the present,
      // looking down the corridor.
      camera.position.set(0, 4.5, -6);
      camera.lookAt(0, 0, 8);
      return;
    }

    camera.position.x = onPath.x + strafe;
    camera.position.y = onPath.y + 0.2;
    camera.position.z = onPath.z - 1.8;

    // Look-direction: down the path, modulated by yaw/pitch.
    const lookAt = _pathPoint(camState.t + 1.5);
    const dx = lookAt.x - camera.position.x + Math.sin(camState.yaw) * 0.6;
    const dy = lookAt.y - camera.position.y + Math.tan(camState.pitch) * 0.6;
    const dz = lookAt.z - camera.position.z;
    camera.lookAt(
      camera.position.x + dx,
      camera.position.y + dy,
      camera.position.z + dz,
    );
  }

  // ── Connection lines (Three.js geometry) ─────────────────────────────
  function _drawConnections() {
    // Wipe and redraw each frame -- cheap for our edge counts (<300).
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
    const points = [edge.from.clone(), edge.to.clone()];
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    let mat;
    if (style.dashed) {
      mat = new THREE.LineDashedMaterial({
        color: style.color,
        opacity: style.opacity,
        transparent: true,
        dashSize: 0.18,
        gapSize: 0.12,
      });
    } else {
      mat = new THREE.LineBasicMaterial({
        color: style.color,
        opacity: style.opacity,
        transparent: true,
      });
    }
    const line = new THREE.Line(geo, mat);
    if (style.dashed) line.computeLineDistances();
    lineGroup.add(line);
  }

  // ── DOM-card projection ──────────────────────────────────────────────
  // For each card, project its 3D world position to screen coords and
  // set inline transform. Cards are billboarded -- they always face the
  // camera regardless of orientation. Cards behind the camera are
  // hidden via opacity:0.
  function _projectCards() {
    if (!camera || !cardsLayer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const tmp = new THREE.Vector3();
    // Hover/recovering needs distance-based prioritization too.
    cards.forEach((c) => _projectCard(c, w, h, tmp));
    // Project NPC nodes too.
    npcNodes.forEach((n) => _projectCard(n, w, h, tmp));
  }

  function _projectCard(c, w, h, tmp) {
    if (!c.el || !c.pos) return;
    tmp.copy(c.pos).project(camera);
    // Hide cards behind the camera or extremely off-screen.
    if (tmp.z > 1) {
      c.el.style.opacity = "0";
      c.el.style.pointerEvents = "none";
      return;
    }
    const sx = (tmp.x * 0.5 + 0.5) * w;
    const sy = (1 - (tmp.y * 0.5 + 0.5)) * h;
    // Distance from camera (world units) -- used for size scaling and
    // a light "atmospheric" opacity falloff.
    const dist = camera.position.distanceTo(c.pos);
    const baseScale = c.kind === "intro" ? 1.05 : c.kind === "npc" ? 0.55 : 1.0;
    const tier = c.tier || "notable";
    const tierScale = tier === "decision" ? 1.18 : tier === "filler" ? 0.7 : 1.0;
    // Cards shrink with distance roughly inversely; perspective is
    // already applied to position, so we scale modestly to avoid
    // double-counting.
    const scale = baseScale * tierScale * (1 - Math.min(0.45, dist * 0.012));
    // Card width is its own CSS-set width; we pin its top-left at the
    // projected point minus half its measured width/height for centering.
    // Use offsetWidth/Height because the card has been laid out by CSS.
    const cw = c.el.offsetWidth || 320;
    const ch = c.el.offsetHeight || 100;
    const tx = sx - (cw * scale) / 2;
    const ty = sy - (ch * scale) / 2;
    // Opacity falls off with distance; very-near (current) card stays
    // full. Filler cards dim more aggressively.
    let opacity = 1;
    if (dist > 4)  opacity = Math.max(0.35, 1 - (dist - 4) * 0.05);
    if (tier === "filler") opacity *= 0.78;
    if (tier === "decision") opacity = Math.min(1, opacity * 1.1);
    c.el.style.transform = "translate3d(" + tx + "px," + ty + "px,0) scale(" + scale.toFixed(3) + ")";
    c.el.style.opacity = opacity.toFixed(3);
    c.el.style.pointerEvents = opacity > 0.5 ? "auto" : "none";
    // Z-stack so closer cards visually overlap further ones in DOM
    // order. Higher z-index = closer to camera. Convert distance to
    // an integer and invert.
    c.el.style.zIndex = String(10000 - Math.round(dist * 10));
  }

  // ── Card lifecycle ───────────────────────────────────────────────────
  // Move a turn-block out of #turns-container into #corridor-cards and
  // register it in our scene. Idempotent: calling addTurn twice for
  // the same block is a no-op after the first.
  function addTurn(blockEl, turnData) {
    if (!cardsLayer) init();
    if (!blockEl || !blockEl.classList || !blockEl.classList.contains("turn-block")) return;
    const tid = blockEl.id || "";
    if (tid && cardByTurnId.has(tid)) {
      // Already registered. Update connection edges if turnData arrived.
      if (turnData) _registerEdgesForTurn(tid, turnData);
      return;
    }
    const idx = nextTurnIndex++;
    const score = _extractSignificance(turnData);
    const tier = _significanceTier(score);
    const lateral = _significanceLateral(score);
    const pos = _pathPoint(idx);
    if (lateral) {
      pos.x += (idx % 2 === 0 ? 1 : -1) * lateral;
    }
    blockEl.classList.add("corridor-card");
    blockEl.dataset.significanceTier = tier;
    blockEl.style.position = "absolute";
    blockEl.style.left = "0";
    blockEl.style.top = "0";
    blockEl.style.transformOrigin = "50% 50%";
    blockEl.style.transition =
      "filter 0.4s ease, opacity 0.4s ease, transform 0.05s linear";
    // Move the DOM element into the corridor layer.
    if (blockEl.parentNode !== cardsLayer) {
      cardsLayer.appendChild(blockEl);
    }
    // Mark current = false on the previously-current card.
    cards.forEach((c) => {
      if (c.el && c.kind === "turn") c.el.classList.remove("is-current");
    });
    blockEl.classList.add("is-current");
    const card = {
      id: tid,
      el: blockEl,
      pos: pos,
      idx: idx,
      tier: tier,
      kind: "turn",
    };
    cards.push(card);
    if (tid) cardByTurnId.set(tid, card);
    if (turnData) _registerEdgesForTurn(tid, turnData);
    // Camera glides to the new turn (slightly forward of the just-
    // submitted block).
    camState.t = -0.5;
  }

  // Called from app.js renderTurnStaggered AFTER full turn data is in.
  // Updates significance + edges for an already-added card.
  function notifyTurnComplete(blockEl, data) {
    if (!blockEl) return;
    const tid = blockEl.id || "";
    const card = cardByTurnId.get(tid);
    if (!card) {
      // Card hasn't been added yet -- add it now with full data.
      addTurn(blockEl, data);
      return;
    }
    // Update tier/significance now that we have parsed_action.
    const score = _extractSignificance(data);
    const tier = _significanceTier(score);
    card.tier = tier;
    blockEl.dataset.significanceTier = tier;
    // Re-register edges (idempotent dedup inside).
    _registerEdgesForTurn(tid, data);
  }

  function _extractSignificance(data) {
    if (!data) return 0.5;
    const pa = data.parsed_action || data.parsed || {};
    const s = pa.significance_score;
    return typeof s === "number" ? s : 0.5;
  }

  // Restore: walk #turns-container .turn-block elements (already
  // restored from saved HTML) and add them to the corridor in order.
  // We don't have full turn-data for restored turns; connections will
  // only render for new turns submitted after restore.
  function restoreFromContainer() {
    if (!cardsLayer) init();
    const tc = document.getElementById("turns-container");
    if (!tc) return;
    const blocks = tc.querySelectorAll(".turn-block");
    blocks.forEach((b) => addTurn(b, null));
    // Special-case the manuscript-intro: if it exists in turns-container,
    // place it at the deepest position behind all turns.
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
    // Place the intro DEEP into the corridor -- past all turns. Its
    // index updates as new turns are added: keeps it always at the end.
    const introCard = {
      id: "manuscript-intro",
      el: introEl,
      // Position is recomputed in _animate so the intro stays anchored
      // at the deepest point even as turns are added.
      pos: _pathPoint(Math.max(8, nextTurnIndex + 2)),
      idx: -1,
      tier: "intro",
      kind: "intro",
    };
    // Attach a getter for pos so it tracks the path's current end.
    Object.defineProperty(introCard, "pos", {
      get: function () {
        return _pathPoint(Math.max(8, nextTurnIndex + 2));
      },
    });
    cards.push(introCard);
  }

  // ── Connection edges ─────────────────────────────────────────────────
  // Register edges from a turn's data. Called when a turn completes
  // (notifyTurnComplete) and on submitTurn if data is already known.
  // Edges drawn:
  //   action -> NPC reaction: turn -> npc node (color = sentiment)
  //   action -> divergence:   turn -> off-path "canonical" anchor
  //   NPC <-> NPC:            ambient_activity pairs
  function _registerEdgesForTurn(tid, data) {
    if (!data || !tid) return;
    const card = cardByTurnId.get(tid);
    if (!card) return;
    const turnPos = card.pos;

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
      _pushEdge({ from: turnPos, to: npcNode.pos, kind: kind, _key: tid + "->npc:" + r.npc_name });
    });

    // 2) action -> divergence edges. Each divergence creates a small
    // anchor card off to the side at the turn's z-position; a dashed
    // amber line connects the turn to it.
    const divergences = data.divergences || [];
    divergences.forEach((d, i) => {
      const anchorPos = new THREE.Vector3(
        turnPos.x + (i % 2 === 0 ? 1.4 : -1.4),
        turnPos.y + 0.6,
        turnPos.z,
      );
      _ensureDivergenceMarker(tid + ":div:" + i, d, anchorPos);
      _pushEdge({ from: turnPos, to: anchorPos, kind: "action_divergence", _key: tid + "->div:" + i });
    });

    // 3) NPC <-> NPC edges from ambient_activity.
    const ambient = data.ambient_activity || [];
    ambient.forEach((a) => {
      if (!a || !a.npc_name || !a.interacts_with) return;
      const aNode = _ensureNpcNode(a.npc_name, "");
      const bNode = _ensureNpcNode(a.interacts_with, "");
      if (!aNode || !bNode) return;
      _pushEdge({
        from: aNode.pos,
        to: bNode.pos,
        kind: "npc_npc",
        _key: tid + ":" + a.npc_name + "<->" + a.interacts_with,
      });
    });
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

  function _pushEdge(edge) {
    // Dedup by _key so re-running notifyTurnComplete doesn't pile up
    // duplicate lines.
    if (edge._key) {
      for (let i = 0; i < edges.length; i++) {
        if (edges[i]._key === edge._key) return;
      }
    }
    edges.push(edge);
  }

  // ── NPC nodes ────────────────────────────────────────────────────────
  function _ensureNpcNode(name, role) {
    if (!name) return null;
    const key = name.toLowerCase();
    let node = npcNodes.get(key);
    if (node) {
      // Update position to track wherever the most recent turn referencing
      // this NPC is, so the lines stay near recent activity.
      const referencingTurnIdx = Math.max(0, nextTurnIndex - 1);
      const base = _pathPoint(referencingTurnIdx);
      // Place NPC nodes off to the side of the path, alternating left
      // and right by a deterministic hash of the name so the same NPC
      // always sits on the same side.
      const side = _hashSide(name);
      node.pos.set(base.x + side * 1.8, base.y - 0.3, base.z);
      return node;
    }
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
    const referencingTurnIdx = Math.max(0, nextTurnIndex - 1);
    const base = _pathPoint(referencingTurnIdx);
    const side = _hashSide(name);
    const pos = new THREE.Vector3(base.x + side * 1.8, base.y - 0.3, base.z);
    node = { name: name, role: role, el: el, pos: pos, kind: "npc", tier: "notable" };
    npcNodes.set(key, node);
    return node;
  }

  function _hashSide(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return (h % 2 === 0) ? 1 : -1;
  }

  function _ensureDivergenceMarker(key, divergence, pos) {
    if (!cardsLayer) return null;
    if (cardByTurnId.has("div:" + key)) return;
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
    const card = {
      id: "div:" + key,
      el: el,
      pos: pos,
      idx: -2,
      tier: "notable",
      kind: "divergence",
    };
    cards.push(card);
    cardByTurnId.set("div:" + key, card);
    return card;
  }

  function _escHtml(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Lifecycle ────────────────────────────────────────────────────────
  function show() {
    init();
    const container = document.getElementById("corridor-container");
    if (!container) return;
    container.classList.remove("hidden");
    isVisible = true;
    // Resize at-show time -- container was display:none until now.
    if (renderer && camera) {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      }
    }
    // After two RAFs (so overlay has reflowed), mark ready.
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
    return _constellation;
  }

  function getDiag() {
    return {
      card_count: cards.length,
      npc_node_count: npcNodes.size,
      edge_count: edges.length,
      camera_t: camState.t,
      camera_yaw: camState.yaw,
      camera_pitch: camState.pitch,
      constellation: _constellation,
    };
  }

  // Public API.
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
    getDiag: getDiag,
  };
})();
