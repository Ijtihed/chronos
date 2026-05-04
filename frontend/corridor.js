/**
 * CHRONOS Constellation Manuscript -- Phase 2.8 Phase A v2 (read-only).
 *
 * The manuscript is a 3D constellation of memories. Each past turn
 * is a node hanging in space. TIME is locked to the Z axis -- newer
 * turns near the camera at z=0, older turns recede into +z. The
 * X/Y position of each turn is determined by a force-directed
 * simulation: turns repel each other; causal connections (action ->
 * NPC reaction, action -> divergence, NPC <-> NPC) act as springs
 * pulling related turns together; high-significance DECISIONS are
 * pinned at deliberate angular anchors so they always stand out as
 * structural nodes around which the run organizes.
 *
 * The result: clusters where causality concentrates, voids where it
 * doesn't. The shape of the constellation IS the shape of the run.
 *
 * Camera: free orbit around the constellation centroid. Drag to
 * orbit, wheel to zoom, WASD to pan, Z toggles a wide overview.
 *
 * Design source of truth: context/game logic context/manuscript-as-artifact.md
 * (Phase 2.8 section). Roadmap entry: roadmap.md "PHASE 2.8 -- The
 * corridor manuscript" -- this v2 keeps the same intent but swaps the
 * positioning algorithm from a fixed corridor path to a real spatial
 * graph. Docs will be updated to reflect the new naming after browser
 * verification.
 *
 * Module shape: same IIFE / window.ChronosCorridor public API as v1
 * so existing app.js hooks (submitTurn / renderTurnStaggered /
 * enterGame / Z-key) work unchanged.
 *
 * Renderer: DOM-overlay strategy -- Three.js draws ONLY the connection
 * line geometry on a transparent canvas. Turn-block DOM elements live
 * in #corridor-cards and are projected to screen coords each frame.
 * Same proven pattern as globe.js DOM markers and wartable.js DOM
 * labels. No CSS3DRenderer, no ES module switch.
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
  let scene, camera, renderer;
  let lineGroup;        // Three.js group for all connection-line geometry
  let cardsLayer;       // DOM div that holds the moved .turn-block elements
  let initialized = false;
  let isVisible = false;

  // Each card node:
  //   { id, el, kind, tier,
  //     pos: Vector3,         // CURRENT world position (mutated each frame)
  //     vel: Vector3,         // velocity (force-sim integrates)
  //     anchor: Vector3|null, // pinned target (decisions) or null
  //     z: number,            // locked time-axis position
  //     mass: number,         // larger for decisions, smaller for filler
  //     idx: number           // age (0 = newest)
  //   }
  const cards = [];
  let nextTurnIndex = 0;
  // Map from turn-block id ("turn-<timestamp>") to its card.
  const cardByTurnId = new Map();
  // NPC nodes -- one per unique NPC across the run, keyed by lowercased name.
  const npcNodes = new Map();
  // Edges: { from: nodeRef, to: nodeRef, kind, restLength, strength, _key }
  // 'from'/'to' are LIVE references; each frame we read .pos fresh.
  const edges = [];

  // Decision anchor allocation. Each new decision gets the next
  // golden-angle slot around the time axis.
  let decisionAnchorCount = 0;
  // Time-axis stride. Each turn back is ~1.4 units further into +z.
  const Z_STEP = 1.4;

  // Force-sim coefficients (tunable via ChronosCorridor.tune).
  const tuning = {
    k_repel: 0.9,   // pairwise repulsion strength
    k_spring: 0.18, // edge spring strength
    k_anchor: 0.55, // pull toward pinned anchor
    k_center: 0.04, // weak pull toward (0, 0, node.z)
    damping: 0.84,  // velocity damping per tick
    max_vel: 0.45,  // velocity cap to prevent jitter
    rest_length: 1.2,
    repel_radius: 3.0, // ignore repulsion past this distance (cheap O(n^2))
  };

  // Simulation control. Runs while there's still energy in the
  // system; stops when settled to save battery + cleanly snap into
  // place. Bumped back into running on every addTurn / new edge.
  let simRunning = true;
  let simIdleFrames = 0;
  const SIM_IDLE_THRESHOLD = 90; // frames of low energy before sleep
  const SIM_KE_EPSILON = 0.0008;

  // Free-orbit camera.
  const camOrbit = {
    theta: 0,            // azimuth (rotation around Y axis)
    phi: Math.PI * 0.45, // polar angle from +Y
    dist: 7.5,           // distance from target
    target: new THREE.Vector3(0, 0, 4), // looking at this point
  };
  const _defaultOrbit = {
    theta: 0,
    phi: Math.PI * 0.45,
    dist: 7.5,
    targetZ: 4,
  };
  let _constellation = false; // overview mode (Z key)

  function _significanceTier(score) {
    if (typeof score !== "number" || isNaN(score)) return "notable";
    if (score < 0.4) return "filler";
    if (score < 0.8) return "notable";
    return "decision";
  }

  // Connection-line styling per type.
  const EDGE_STYLE = {
    action_npc_positive:  { color: 0x10b981, opacity: 0.55, dashed: false, restLength: 1.6, strength: 0.22 },
    action_npc_negative:  { color: 0xef4444, opacity: 0.55, dashed: false, restLength: 1.6, strength: 0.22 },
    action_npc_neutral:   { color: 0x71717a, opacity: 0.45, dashed: false, restLength: 1.8, strength: 0.18 },
    action_divergence:    { color: 0xfcd34d, opacity: 0.7,  dashed: true,  restLength: 1.4, strength: 0.30 },
    npc_npc:              { color: 0x94a3b8, opacity: 0.35, dashed: true,  restLength: 1.3, strength: 0.14 },
  };

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
    scene.fog = new THREE.Fog(0x000000, 16, 60);
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
    const t = camOrbit.target;
    const x = t.x + camOrbit.dist * Math.sin(camOrbit.phi) * Math.sin(camOrbit.theta);
    const y = t.y + camOrbit.dist * Math.cos(camOrbit.phi);
    const z = t.z + camOrbit.dist * Math.sin(camOrbit.phi) * Math.cos(camOrbit.theta);
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
      // Drag east -> orbit east. Sensitivity scales with dist so
      // close-in is precise.
      const k = 0.0035 * Math.min(1.4, camOrbit.dist / 4);
      camOrbit.theta -= dx * k;
      camOrbit.phi = Math.max(0.05, Math.min(Math.PI - 0.05, camOrbit.phi - dy * k));
      _applyCameraOrbit();
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

    // Wheel zooms in/out on the constellation. Altitude-proportional
    // step, same idea as the globe.
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const step = 0.12 * Math.max(0.4, camOrbit.dist - 1.5);
      const sign = e.deltaY > 0 ? 1 : -1;
      camOrbit.dist = Math.max(1.5, Math.min(40, camOrbit.dist + sign * step));
      _applyCameraOrbit();
    }, { passive: false });

    // WASD pans the camera target. W/S walk along the time axis
    // (target.z) -- W = forward in space = back in time. A/D pans X.
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
    if (simRunning) {
      const ke = _tickSimulation();
      if (ke < SIM_KE_EPSILON) {
        simIdleFrames++;
        if (simIdleFrames > SIM_IDLE_THRESHOLD) simRunning = false;
      } else {
        simIdleFrames = 0;
      }
    }
    _drawConnections();
    renderer.render(scene, camera);
    _projectCards();
  }

  // ── Force simulation ────────────────────────────────────────────────
  // Runs each frame while energy is in the system. Updates X/Y of each
  // node's velocity + position; Z (time) is locked.
  //
  // Forces:
  //   1. Repulsion between every pair of cards within REPEL_RADIUS
  //      (charge-like, F = k_repel / dist^2).
  //   2. Springs along edges (Hooke, F = k * (dist - restLength)).
  //   3. Anchor pull on pinned nodes (decisions): F = k * (anchor - pos).
  //   4. Center pull (weak): F = k_center * (-pos.x, -pos.y) -- keeps
  //      isolated nodes from drifting to infinity.
  //   5. Damping: vel *= damping.
  //   6. Velocity cap.
  //
  // Returns total kinetic energy (sum of |vel|^2) so the loop can
  // detect "settled" and stop ticking.
  function _tickSimulation() {
    const allNodes = _allMovableNodes();
    const n = allNodes.length;
    if (n === 0) return 0;

    // Force accumulators per node (reset each tick). Allocating fresh
    // is cheaper than mutating shared Vector3s in tight loop.
    const fx = new Float32Array(n);
    const fy = new Float32Array(n);

    // 1) Pairwise repulsion + 2-D plane only (Z is locked).
    const repelR2 = tuning.repel_radius * tuning.repel_radius;
    for (let i = 0; i < n; i++) {
      const a = allNodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = allNodes[j];
        // Skip pairs across very different Z bands -- they don't
        // visually overlap so the cost isn't worth it.
        if (Math.abs(a.pos.z - b.pos.z) > 4) continue;
        const dx = a.pos.x - b.pos.x;
        const dy = a.pos.y - b.pos.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > repelR2) continue;
        const d = Math.sqrt(d2) + 0.05; // avoid div0
        const f = tuning.k_repel / (d2 + 0.1);
        const ux = dx / d;
        const uy = dy / d;
        // Mass-weighted: heavier nodes (decisions) push back harder.
        const ma = a.mass || 1;
        const mb = b.mass || 1;
        fx[i] += ux * f * mb;
        fy[i] += uy * f * mb;
        fx[j] -= ux * f * ma;
        fy[j] -= uy * f * ma;
      }
    }

    // 2) Spring forces along edges.
    for (let e = 0; e < edges.length; e++) {
      const ed = edges[e];
      if (!ed.from || !ed.to) continue;
      const ai = ed.from._simIndex;
      const bi = ed.to._simIndex;
      if (ai == null || bi == null) continue;
      const a = allNodes[ai];
      const b = allNodes[bi];
      if (!a || !b) continue;
      const dx = b.pos.x - a.pos.x;
      const dy = b.pos.y - a.pos.y;
      const d = Math.sqrt(dx * dx + dy * dy) + 0.001;
      const stretch = d - (ed.restLength || tuning.rest_length);
      const f = (ed.strength || tuning.k_spring) * stretch;
      const ux = dx / d;
      const uy = dy / d;
      fx[ai] += ux * f;
      fy[ai] += uy * f;
      fx[bi] -= ux * f;
      fy[bi] -= uy * f;
    }

    // 3) Anchor pull (decisions, intro, NPC nodes).
    for (let i = 0; i < n; i++) {
      const node = allNodes[i];
      if (!node.anchor) continue;
      const dx = node.anchor.x - node.pos.x;
      const dy = node.anchor.y - node.pos.y;
      fx[i] += dx * tuning.k_anchor;
      fy[i] += dy * tuning.k_anchor;
    }

    // 4) Center pull (weak) -- keeps unconnected nodes from drifting away.
    for (let i = 0; i < n; i++) {
      const node = allNodes[i];
      if (node.anchor) continue; // anchored nodes don't need it
      fx[i] += -node.pos.x * tuning.k_center;
      fy[i] += -node.pos.y * tuning.k_center;
    }

    // Integrate.
    let totalKE = 0;
    for (let i = 0; i < n; i++) {
      const node = allNodes[i];
      const m = node.mass || 1;
      // Apply to velocity, damp, cap, integrate position.
      node.vel.x = (node.vel.x + fx[i] / m) * tuning.damping;
      node.vel.y = (node.vel.y + fy[i] / m) * tuning.damping;
      const speed = Math.sqrt(node.vel.x * node.vel.x + node.vel.y * node.vel.y);
      if (speed > tuning.max_vel) {
        const s = tuning.max_vel / speed;
        node.vel.x *= s;
        node.vel.y *= s;
      }
      node.pos.x += node.vel.x;
      node.pos.y += node.vel.y;
      // Z is locked -- always at node.z (set on creation).
      node.pos.z = node.z;
      totalKE += speed * speed;
    }
    return totalKE;
  }

  function _allMovableNodes() {
    // Collect cards + npcNodes in one array. Index each so edges can
    // reference them in the force loop without a Map lookup per edge
    // per frame.
    const out = [];
    for (let i = 0; i < cards.length; i++) {
      cards[i]._simIndex = out.length;
      out.push(cards[i]);
    }
    npcNodes.forEach((n) => {
      n._simIndex = out.length;
      out.push(n);
    });
    return out;
  }

  function _kickSim() {
    simRunning = true;
    simIdleFrames = 0;
  }

  // ── Pre-settle helper ────────────────────────────────────────────────
  // Run a handful of force ticks immediately after a node is added so
  // the new node "swims into place" quickly rather than visibly popping
  // from (0,0) for a second.
  function _preSettle(iterations) {
    for (let i = 0; i < iterations; i++) {
      _tickSimulation();
    }
  }

  // ── Card lifecycle ───────────────────────────────────────────────────
  function addTurn(blockEl, turnData) {
    if (!cardsLayer) init();
    if (!blockEl || !blockEl.classList || !blockEl.classList.contains("turn-block")) return;
    const tid = blockEl.id || "";
    if (tid && cardByTurnId.has(tid)) {
      if (turnData) _registerEdgesForTurn(tid, turnData);
      return;
    }
    const idx = nextTurnIndex++;
    const score = _extractSignificance(turnData);
    const tier = _significanceTier(score);
    const z = idx * Z_STEP;

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

    // Initial position: small random offset around (0, 0, z) so the
    // simulator has something to push apart.
    const rx = (Math.random() - 0.5) * 0.6;
    const ry = (Math.random() - 0.5) * 0.6;

    const card = {
      id: tid,
      el: blockEl,
      pos: new THREE.Vector3(rx, ry, z),
      vel: new THREE.Vector3(0, 0, 0),
      anchor: null,
      z: z,
      idx: idx,
      tier: tier,
      kind: "turn",
      mass: tier === "decision" ? 1.6 : tier === "filler" ? 0.7 : 1.0,
    };

    // Decisions get a deterministic anchor on the golden-angle wheel.
    if (tier === "decision") {
      card.anchor = _allocateDecisionAnchor(z);
      card.pos.x = card.anchor.x;
      card.pos.y = card.anchor.y;
    }

    cards.push(card);
    if (tid) cardByTurnId.set(tid, card);
    if (turnData) _registerEdgesForTurn(tid, turnData);

    // Pre-settle so the new card swims into place quickly.
    _kickSim();
    _preSettle(20);

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
      card.mass = newTier === "decision" ? 1.6 : newTier === "filler" ? 0.7 : 1.0;
      // Promoting to decision? Allocate an anchor.
      if (newTier === "decision" && !card.anchor) {
        card.anchor = _allocateDecisionAnchor(card.z);
      }
    }
    _registerEdgesForTurn(tid, data);
    _kickSim();
  }

  function _extractSignificance(data) {
    if (!data) return 0.5;
    const pa = data.parsed_action || data.parsed || {};
    const s = pa.significance_score;
    return typeof s === "number" ? s : 0.5;
  }

  // Restored runs (from saved HTML in localStorage). Per-turn data
  // isn't available; cards just get default mass and no edges except
  // those inferable from the markup.
  function restoreFromContainer() {
    if (!cardsLayer) init();
    const tc = document.getElementById("turns-container");
    if (!tc) return;
    const blocks = tc.querySelectorAll(".turn-block");
    blocks.forEach((b) => addTurn(b, null));
    const intro = tc.querySelector(".manuscript-intro");
    if (intro) addIntroCard(intro);
    // After restoring, run a longer pre-settle so the constellation
    // is in a coherent position before the user sees the canvas.
    _preSettle(60);
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
    // Intro sits at the deepest position in the constellation, anchored
    // at the time-axis origin (X=0, Y=0) -- it's the run's beginning.
    const introZ = (nextTurnIndex + 4) * Z_STEP; // always behind the deepest turn
    const introCard = {
      id: "manuscript-intro",
      el: introEl,
      pos: new THREE.Vector3(0, 0, introZ),
      vel: new THREE.Vector3(0, 0, 0),
      anchor: new THREE.Vector3(0, 0, introZ),
      z: introZ,
      idx: -1,
      tier: "intro",
      kind: "intro",
      mass: 1.4,
    };
    cards.push(introCard);
    _kickSim();
  }

  // ── Decision anchors ────────────────────────────────────────────────
  // Golden-angle allocation gives even angular spacing without
  // collisions for any number of decisions. Each anchor sits at radius
  // 1.8 from the time axis at the decision's Z.
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5)); // ~2.39996 rad
  function _allocateDecisionAnchor(z) {
    const theta = decisionAnchorCount * GOLDEN_ANGLE;
    decisionAnchorCount++;
    const r = 1.8;
    return new THREE.Vector3(Math.cos(theta) * r, Math.sin(theta) * r, z);
  }

  // ── NPC nodes ────────────────────────────────────────────────────────
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

    // NPC anchor: deterministic-hash position around the time axis at
    // a wider radius than decisions. Z starts at the present and
    // smoothly drifts back as more turns reference this NPC.
    const h = _hash(key);
    const theta = (h % 360) * Math.PI / 180;
    const r = 2.6;
    const z = nextTurnIndex > 0 ? (nextTurnIndex - 1) * Z_STEP : 0;
    const anchor = new THREE.Vector3(Math.cos(theta) * r, Math.sin(theta) * r - 0.4, z);
    node = {
      name: name,
      role: role,
      el: el,
      pos: new THREE.Vector3(anchor.x, anchor.y, z),
      vel: new THREE.Vector3(0, 0, 0),
      anchor: anchor,
      z: z,
      idx: -2,
      tier: "notable",
      kind: "npc",
      mass: 1.1,
      _refTurnZs: [], // running list of Z's this NPC has been referenced at
    };
    npcNodes.set(key, node);
    return node;
  }

  function _updateNpcNodeZ(node, refZ) {
    node._refTurnZs.push(refZ);
    if (node._refTurnZs.length > 8) node._refTurnZs.shift();
    let sum = 0;
    for (let i = 0; i < node._refTurnZs.length; i++) sum += node._refTurnZs[i];
    const meanZ = sum / node._refTurnZs.length;
    node.z = meanZ;
    node.anchor.z = meanZ;
  }

  function _hash(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  // ── Connection edges ─────────────────────────────────────────────────
  function _registerEdgesForTurn(tid, data) {
    if (!data || !tid) return;
    const card = cardByTurnId.get(tid);
    if (!card) return;

    // 1) action -> NPC reaction edges, one per NPC POV.
    const npcResponses = data.npc_responses || [];
    const impacts = (data.parsed_action || data.parsed || {}).npc_impacts || [];
    npcResponses.forEach((r) => {
      if (!r || !r.npc_name) return;
      const sentiment = _sentimentForNpc(r.npc_name, impacts);
      const npcNode = _ensureNpcNode(r.npc_name, r.npc_role || "");
      if (!npcNode) return;
      _updateNpcNodeZ(npcNode, card.z);
      const kind = sentiment === "positive" ? "action_npc_positive"
                 : sentiment === "negative" ? "action_npc_negative"
                 : "action_npc_neutral";
      _pushEdge(card, npcNode, kind, tid + "->npc:" + r.npc_name);
    });

    // 2) action -> divergence edges.
    const divergences = data.divergences || [];
    divergences.forEach((d, i) => {
      const anchorPos = new THREE.Vector3(
        card.pos.x + (i % 2 === 0 ? 1.4 : -1.4),
        card.pos.y + 0.6,
        card.z,
      );
      const divNode = _ensureDivergenceNode(tid + ":div:" + i, d, anchorPos);
      if (!divNode) return;
      _pushEdge(card, divNode, "action_divergence", tid + "->div:" + i);
    });

    // 3) NPC <-> NPC edges from ambient_activity.
    const ambient = data.ambient_activity || [];
    ambient.forEach((a) => {
      if (!a || !a.npc_name || !a.interacts_with) return;
      const aNode = _ensureNpcNode(a.npc_name, "");
      const bNode = _ensureNpcNode(a.interacts_with, "");
      if (!aNode || !bNode) return;
      _updateNpcNodeZ(aNode, card.z);
      _updateNpcNodeZ(bNode, card.z);
      _pushEdge(aNode, bNode, "npc_npc", tid + ":" + a.npc_name + "<->" + a.interacts_with);
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

  function _pushEdge(fromNode, toNode, kind, key) {
    if (!fromNode || !toNode) return;
    if (key) {
      for (let i = 0; i < edges.length; i++) {
        if (edges[i]._key === key) return;
      }
    }
    const style = EDGE_STYLE[kind] || EDGE_STYLE.npc_npc;
    edges.push({
      from: fromNode,
      to: toNode,
      kind: kind,
      restLength: style.restLength,
      strength: style.strength,
      _key: key,
    });
    _kickSim();
  }

  // ── Divergence anchor markers ────────────────────────────────────────
  function _ensureDivergenceNode(key, divergence, anchorPos) {
    if (cardByTurnId.has("div:" + key)) return null;
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
    const node = {
      id: "div:" + key,
      el: el,
      pos: anchorPos.clone(),
      vel: new THREE.Vector3(0, 0, 0),
      anchor: anchorPos.clone(),
      z: anchorPos.z,
      idx: -3,
      tier: "notable",
      kind: "divergence",
      mass: 0.9,
    };
    cards.push(node);
    cardByTurnId.set("div:" + key, node);
    return node;
  }

  // ── Connection lines (Three.js) ──────────────────────────────────────
  // Read each edge's live from/to positions every frame. Cheap for our
  // edge counts (<300).
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
    const points = [edge.from.pos.clone(), edge.to.pos.clone()];
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
    const tierScale = tier === "decision" ? 1.15 : tier === "filler" ? 0.78 : 1.0;
    const distScale = Math.max(0.45, 1 - Math.min(0.55, dist * 0.04));
    const scale = baseScale * tierScale * distScale;
    const cw = c.el.offsetWidth || 320;
    const ch = c.el.offsetHeight || 100;
    const tx = sx - (cw * scale) / 2;
    const ty = sy - (ch * scale) / 2;
    let opacity = 1;
    if (dist > 6) opacity = Math.max(0.25, 1 - (dist - 6) * 0.04);
    if (tier === "filler") opacity *= 0.78;
    c.el.style.transform = "translate3d(" + tx + "px," + ty + "px,0) scale(" + scale.toFixed(3) + ")";
    c.el.style.opacity = opacity.toFixed(3);
    c.el.style.pointerEvents = opacity > 0.5 ? "auto" : "none";
    c.el.style.zIndex = String(10000 - Math.round(dist * 10));
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
    if (renderer && camera) {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      }
    }
    _kickSim();
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
      // Pull way back to see the whole shape from above.
      camOrbit.theta = 0;
      camOrbit.phi = 0.55;
      camOrbit.dist = Math.max(14, 4 + nextTurnIndex * Z_STEP * 0.7);
      camOrbit.target.set(0, 0, (nextTurnIndex * Z_STEP) / 2);
    } else {
      _resetView();
    }
    _applyCameraOrbit();
    return _constellation;
  }

  function tune(opts) {
    if (!opts) return Object.assign({}, tuning);
    Object.keys(opts).forEach((k) => {
      if (k in tuning) tuning[k] = opts[k];
    });
    _kickSim();
    return Object.assign({}, tuning);
  }

  function getDiag() {
    const cardCounts = { turn: 0, intro: 0, divergence: 0 };
    cards.forEach((c) => { cardCounts[c.kind] = (cardCounts[c.kind] || 0) + 1; });
    return {
      card_count: cards.length,
      card_kinds: cardCounts,
      npc_node_count: npcNodes.size,
      edge_count: edges.length,
      decision_anchor_count: decisionAnchorCount,
      sim_running: simRunning,
      sim_idle_frames: simIdleFrames,
      camera: {
        theta: camOrbit.theta,
        phi: camOrbit.phi,
        dist: camOrbit.dist,
        target_z: camOrbit.target.z,
      },
      constellation_overview: _constellation,
      tuning: Object.assign({}, tuning),
    };
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
    tune: tune,
    getDiag: getDiag,
  };
})();
