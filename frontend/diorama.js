/**
 * Phase 3b — Diorama renderer.
 *
 * Stylized 3D vignettes inset in the manuscript when a major turn fires
 * (significance >= 0.85). Silhouette characters, low-poly setting, slow
 * camera orbit, amber-on-black palette. Reads like a memory.
 *
 * Composition with rest of CHRONOS
 * ---------------------------------
 *  - Triggered by app.js after renderTurnStaggered when the turn's
 *    significance crosses the threshold. app.js POSTs
 *    /api/run/{id}/diorama/{turn_id}, gets the spec, and calls
 *    ChronosDiorama.mount(specEl, diorama).
 *  - Each diorama gets its own Three.js scene + WebGLRenderer + canvas.
 *    They are independent and can be GC'd when the turn-block scrolls
 *    far off-screen (Phase 6 polish; not in 3b).
 *  - Three.js is already loaded (CDN UMD) for globe.js + wartable.js.
 *    We do not re-import; we just consume window.THREE.
 *
 * What the renderer does
 * ----------------------
 *  - Builds a small ground plane.
 *  - Places a "setting kit" (architectural primitives) for the
 *    location_kind from the spec.
 *  - Places 1..6 silhouette character figures from the spec's
 *    `characters` array.
 *  - Configures lighting + tone per the spec's `mood`.
 *  - Configures the camera per the spec's `camera`.
 *  - Animates: auto-orbits the camera slowly. On drag, switches to
 *    user-controlled orbit; resumes auto-orbit after 2s of idle.
 *
 * Public API
 * ----------
 *    ChronosDiorama.mount(container, diorama)  -> sceneId
 *    ChronosDiorama.unmount(sceneId)
 *    ChronosDiorama.unmountAll()
 */

(function () {
  "use strict";

  if (typeof window === "undefined") return;

  // ── Config / palettes ───────────────────────────────────────────────
  // Each mood is a tuple of [bgColor, lightColor, lightIntensity,
  // accentColor (player figure)]. amber_low_light is the default; see
  // backend/world_state.DIORAMA_MOODS for the canonical list.
  const MOOD_PALETTES = {
    amber_low_light: {
      bg: 0x0a0805,
      key: 0xffb37a,        // warm amber key light
      key_intensity: 1.05,
      ambient: 0x2a1a0c,
      ambient_intensity: 0.6,
      figure: 0x000000,     // silhouette characters: solid black
      figure_player: 0xff9a4a, // player slightly warmer
      ground: 0x1a0f06,
    },
    silver_cold: {
      bg: 0x07080a,
      key: 0xb6cee0,
      key_intensity: 0.95,
      ambient: 0x18202a,
      ambient_intensity: 0.55,
      figure: 0x000000,
      figure_player: 0xc6dbe8,
      ground: 0x121519,
    },
    twilight_blue: {
      bg: 0x06060c,
      key: 0x6a82c8,
      key_intensity: 0.85,
      ambient: 0x111425,
      ambient_intensity: 0.55,
      figure: 0x000000,
      figure_player: 0x8aa4e0,
      ground: 0x0e1020,
    },
    harsh_noon: {
      bg: 0x1a1614,
      key: 0xfff1c2,
      key_intensity: 1.4,
      ambient: 0x40342a,
      ambient_intensity: 0.85,
      figure: 0x000000,
      figure_player: 0xffd58a,
      ground: 0x2a2018,
    },
    darkness: {
      bg: 0x010102,
      key: 0xff8a30,
      key_intensity: 0.6,
      ambient: 0x080606,
      ambient_intensity: 0.20,
      figure: 0x000000,
      figure_player: 0xff8a30,
      ground: 0x060404,
    },
  };

  // ── State ───────────────────────────────────────────────────────────
  const _scenes = new Map();   // sceneId -> { renderer, scene, camera, ... }
  let _nextId = 1;

  // ── Public API ──────────────────────────────────────────────────────
  const api = {
    mount,
    unmount,
    unmountAll,
    getDiag,
  };
  window.ChronosDiorama = api;

  function getDiag() {
    return {
      scene_count: _scenes.size,
      scene_ids: Array.from(_scenes.keys()),
    };
  }

  function mount(container, diorama) {
    if (typeof THREE === "undefined") {
      console.warn("[diorama] THREE not loaded; cannot mount.");
      return null;
    }
    if (!container || !diorama) return null;

    const sceneId = "scene_" + (_nextId++);
    const palette = MOOD_PALETTES[diorama.mood && diorama.mood.mood]
      || MOOD_PALETTES.amber_low_light;

    // ── Renderer ──
    // Container should already have a defined size (CSS); we read
    // clientWidth/Height once and resize on visibility-change.
    const canvas = document.createElement("canvas");
    canvas.style.cssText =
      "display:block;width:100%;height:100%;cursor:grab;outline:none;touch-action:none;";
    container.appendChild(canvas);

    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: false,        // silhouette aesthetic; AA would soften
      alpha: false,
      preserveDrawingBuffer: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const width = container.clientWidth || 600;
    const height = container.clientHeight || 250;
    renderer.setSize(width, height, false);

    // ── Scene + background ──
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(palette.bg);

    // ── Camera ──
    const cameraSpec = diorama.camera || { type: "low_orbit_slow", initial_phi: 70, distance: 5.0 };
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    const camOrbit = {
      theta: 0,
      phi: _phiFromSpec(cameraSpec.initial_phi),
      distance: cameraSpec.distance || 5.0,
      autoSpeed: _autoSpeedForCamera(cameraSpec.type),
      type: cameraSpec.type || "low_orbit_slow",
      idleResumeAt: 0,         // ms when auto-orbit resumes
    };
    _applyOrbit(camera, camOrbit);

    // ── Lights ──
    const ambient = new THREE.AmbientLight(
      palette.ambient,
      palette.ambient_intensity * (diorama.mood ? (diorama.mood.intensity || 0.7) : 0.7),
    );
    scene.add(ambient);
    const key = new THREE.DirectionalLight(
      palette.key,
      palette.key_intensity * (diorama.mood ? (diorama.mood.intensity || 0.7) : 0.7),
    );
    key.position.set(3, 5, 4);
    scene.add(key);

    // ── Ground ──
    const groundGeo = new THREE.PlaneGeometry(12, 12);
    const groundMat = new THREE.MeshStandardMaterial({
      color: palette.ground,
      roughness: 1.0,
      metalness: 0.0,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);

    // ── Setting kit ──
    const settingGroup = _buildSettingKit(diorama.location_kind || "chamber", palette);
    scene.add(settingGroup);

    // ── Characters ──
    const figures = (diorama.characters || []).slice(0, 6);
    figures.forEach((fig) => {
      const figGroup = _buildFigure(fig, palette);
      if (figGroup) scene.add(figGroup);
    });

    // ── Interaction (drag to orbit) ──
    let _dragging = false;
    let _lastPointer = { x: 0, y: 0 };
    canvas.addEventListener("pointerdown", (e) => {
      _dragging = true;
      _lastPointer.x = e.clientX;
      _lastPointer.y = e.clientY;
      canvas.style.cursor = "grabbing";
      camOrbit.idleResumeAt = Date.now() + 2000;
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!_dragging) return;
      const dx = e.clientX - _lastPointer.x;
      const dy = e.clientY - _lastPointer.y;
      _lastPointer.x = e.clientX;
      _lastPointer.y = e.clientY;
      camOrbit.theta -= dx * 0.006;
      camOrbit.phi = Math.max(0.25, Math.min(Math.PI / 2 - 0.05, camOrbit.phi - dy * 0.006));
      _applyOrbit(camera, camOrbit);
      camOrbit.idleResumeAt = Date.now() + 2000;
    });
    const _release = (e) => {
      if (!_dragging) return;
      _dragging = false;
      canvas.style.cursor = "grab";
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      camOrbit.idleResumeAt = Date.now() + 2000;
    };
    canvas.addEventListener("pointerup", _release);
    canvas.addEventListener("pointercancel", _release);
    canvas.addEventListener("pointerleave", _release);

    // ── Resize observer ──
    const ro = new ResizeObserver(() => {
      const w = container.clientWidth || 600;
      const h = container.clientHeight || 250;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    ro.observe(container);

    // ── Animation loop ──
    let _running = true;
    let _lastT = performance.now();
    const tick = () => {
      if (!_running) return;
      const now = performance.now();
      const dt = Math.min((now - _lastT) / 1000, 0.1);  // clamp big tab-switch gaps
      _lastT = now;

      // Auto-orbit if not in user-drag and idle period has passed.
      if (!_dragging && now > camOrbit.idleResumeAt) {
        if (camOrbit.type === "high_static") {
          // No motion.
        } else if (camOrbit.type === "dolly_in") {
          // Slowly approach the focus, but don't crash through it.
          camOrbit.distance = Math.max(2.5, camOrbit.distance - dt * 0.06);
          _applyOrbit(camera, camOrbit);
        } else if (camOrbit.type === "wide_pan") {
          camOrbit.theta += dt * 0.08;
          _applyOrbit(camera, camOrbit);
        } else {
          // low_orbit_slow (default)
          camOrbit.theta += dt * camOrbit.autoSpeed;
          _applyOrbit(camera, camOrbit);
        }
      }

      renderer.render(scene, camera);
      _scenes.get(sceneId)._raf = requestAnimationFrame(tick);
    };

    const sceneRecord = {
      renderer,
      scene,
      camera,
      camOrbit,
      canvas,
      container,
      ro,
      _raf: requestAnimationFrame(tick),
      stop: () => { _running = false; },
    };
    _scenes.set(sceneId, sceneRecord);
    return sceneId;
  }

  function unmount(sceneId) {
    const s = _scenes.get(sceneId);
    if (!s) return;
    s.stop();
    if (s._raf) cancelAnimationFrame(s._raf);
    if (s.ro) {
      try { s.ro.disconnect(); } catch (_) {}
    }
    if (s.canvas && s.canvas.parentNode) {
      s.canvas.parentNode.removeChild(s.canvas);
    }
    if (s.renderer) {
      try { s.renderer.dispose(); } catch (_) {}
    }
    if (s.scene) {
      // Walk and dispose all geometries / materials. Several setting
      // kits share a single CylinderGeometry across multiple column
      // meshes (see _addColumns), and a single MeshStandardMaterial
      // across every architectural piece in a scene. dispose() is
      // idempotent at the WebGL layer but each call dispatches a
      // `dispose` event; deduping keeps the event noise down and
      // makes long-run telemetry readable.
      const seenGeo = new Set();
      const seenMat = new Set();
      s.scene.traverse((obj) => {
        if (obj.geometry && !seenGeo.has(obj.geometry)) {
          seenGeo.add(obj.geometry);
          try { obj.geometry.dispose(); } catch (_) {}
        }
        if (obj.material) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((m) => {
            if (m && !seenMat.has(m)) {
              seenMat.add(m);
              try { m.dispose && m.dispose(); } catch (_) {}
            }
          });
        }
      });
    }
    _scenes.delete(sceneId);
  }

  function unmountAll() {
    Array.from(_scenes.keys()).forEach(unmount);
  }

  // ── Camera helpers ──────────────────────────────────────────────────
  function _phiFromSpec(degrees) {
    // initial_phi in the spec is degrees from horizontal (30..85);
    // Three.js spherical phi is from positive Y axis (0 = top down).
    // Convert: phi = (90 - degrees) -> radians.
    const d = (typeof degrees === "number" && isFinite(degrees)) ? degrees : 70;
    return ((90 - Math.max(20, Math.min(85, d))) * Math.PI) / 180;
  }
  function _autoSpeedForCamera(type) {
    // Radians per second for auto-orbit.
    if (type === "wide_pan") return 0.10;
    return 0.085;  // low_orbit_slow default
  }
  function _applyOrbit(camera, orbit) {
    // Convert spherical -> cartesian. Center the orbit at origin
    // (the diorama is sized to fit a [-3, 3] x [-3, 3] ground tile).
    const r = Math.max(1.5, Math.min(12, orbit.distance));
    const sinPhi = Math.sin(orbit.phi);
    const cosPhi = Math.cos(orbit.phi);
    camera.position.x = r * sinPhi * Math.cos(orbit.theta);
    camera.position.y = r * cosPhi;
    camera.position.z = r * sinPhi * Math.sin(orbit.theta);
    camera.lookAt(0, 0.7, 0);  // slightly above ground for natural framing
  }

  // ── Setting kits ────────────────────────────────────────────────────
  // Each kit is a small THREE.Group of low-poly architectural
  // primitives. NO external assets; everything built from
  // BoxGeometry / CylinderGeometry / PlaneGeometry. The aesthetic is
  // deliberately abstract -- the player's mind fills in detail.
  function _buildSettingKit(kind, palette) {
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: 0x080604,
      roughness: 1.0,
      metalness: 0.0,
    });
    if (kind === "interior_columns") {
      _addColumns(group, mat, 4);
    } else if (kind === "exterior_wall") {
      _addWall(group, mat);
    } else if (kind === "throne_room") {
      _addColumns(group, mat, 2);
      _addThrone(group, mat);
    } else if (kind === "market") {
      _addMarketStalls(group, mat);
    } else if (kind === "road") {
      _addRoadEdges(group, mat);
    } else if (kind === "ship") {
      _addShipDeck(group, mat);
    } else if (kind === "cloister") {
      _addColumns(group, mat, 6);
    } else if (kind === "field") {
      _addFieldElements(group, mat);
    } else if (kind === "ruin") {
      _addRuinedColumns(group, mat);
    } else {
      // chamber (default)
      _addChamberWalls(group, mat);
    }
    return group;
  }

  function _addColumns(group, mat, count) {
    const colGeo = new THREE.CylinderGeometry(0.18, 0.20, 3.0, 10);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const r = 3.2;
      const c = new THREE.Mesh(colGeo, mat);
      c.position.set(Math.cos(angle) * r, 1.5, Math.sin(angle) * r);
      group.add(c);
    }
  }
  function _addWall(group, mat) {
    const geo = new THREE.BoxGeometry(7, 3.5, 0.4);
    const wall = new THREE.Mesh(geo, mat);
    wall.position.set(0, 1.75, -3.5);
    group.add(wall);
    // small flanking turrets
    const tGeo = new THREE.BoxGeometry(0.8, 4.5, 0.8);
    const tL = new THREE.Mesh(tGeo, mat);
    tL.position.set(-3.6, 2.25, -3.5);
    const tR = new THREE.Mesh(tGeo, mat);
    tR.position.set(3.6, 2.25, -3.5);
    group.add(tL);
    group.add(tR);
  }
  function _addThrone(group, mat) {
    const baseGeo = new THREE.BoxGeometry(1.4, 0.4, 1.2);
    const base = new THREE.Mesh(baseGeo, mat);
    base.position.set(0, 0.2, -2.2);
    group.add(base);
    const seatGeo = new THREE.BoxGeometry(1.0, 0.2, 0.9);
    const seat = new THREE.Mesh(seatGeo, mat);
    seat.position.set(0, 0.5, -2.2);
    group.add(seat);
    const backGeo = new THREE.BoxGeometry(1.1, 1.6, 0.2);
    const back = new THREE.Mesh(backGeo, mat);
    back.position.set(0, 1.2, -2.55);
    group.add(back);
  }
  function _addMarketStalls(group, mat) {
    const stallGeo = new THREE.BoxGeometry(1.0, 1.4, 1.0);
    const positions = [[-2.5, 0.7, -2.5], [2.5, 0.7, -2.5], [-2.5, 0.7, 2.5], [2.5, 0.7, 2.5]];
    positions.forEach((p) => {
      const s = new THREE.Mesh(stallGeo, mat);
      s.position.set(p[0], p[1], p[2]);
      group.add(s);
    });
  }
  function _addRoadEdges(group, mat) {
    // Two thin strips of "vegetation" along the road edge.
    const stripGeo = new THREE.BoxGeometry(0.4, 0.15, 8);
    const left = new THREE.Mesh(stripGeo, mat);
    left.position.set(-2.5, 0.075, 0);
    const right = new THREE.Mesh(stripGeo, mat);
    right.position.set(2.5, 0.075, 0);
    group.add(left);
    group.add(right);
    // Two trees / posts in the distance.
    const treeGeo = new THREE.CylinderGeometry(0.05, 0.05, 2.5, 6);
    const tL = new THREE.Mesh(treeGeo, mat);
    tL.position.set(-3, 1.25, -3);
    const tR = new THREE.Mesh(treeGeo, mat);
    tR.position.set(3, 1.25, -3);
    group.add(tL);
    group.add(tR);
  }
  function _addShipDeck(group, mat) {
    // Mast + rail.
    const mastGeo = new THREE.CylinderGeometry(0.10, 0.10, 5, 6);
    const mast = new THREE.Mesh(mastGeo, mat);
    mast.position.set(0, 2.5, 0);
    group.add(mast);
    const railGeo = new THREE.BoxGeometry(7, 0.2, 0.15);
    const railF = new THREE.Mesh(railGeo, mat);
    railF.position.set(0, 0.5, 3);
    const railB = new THREE.Mesh(railGeo, mat);
    railB.position.set(0, 0.5, -3);
    group.add(railF);
    group.add(railB);
  }
  function _addFieldElements(group, mat) {
    // A single tree, low to the ground.
    const trunkGeo = new THREE.CylinderGeometry(0.12, 0.16, 1.6, 6);
    const trunk = new THREE.Mesh(trunkGeo, mat);
    trunk.position.set(2.5, 0.8, -2);
    group.add(trunk);
    const canopyGeo = new THREE.SphereGeometry(0.9, 8, 6);
    const canopy = new THREE.Mesh(canopyGeo, mat);
    canopy.position.set(2.5, 2.0, -2);
    group.add(canopy);
  }
  function _addRuinedColumns(group, mat) {
    // Two broken columns + one fallen.
    const standingGeo = new THREE.CylinderGeometry(0.18, 0.20, 2.2, 8);
    const c1 = new THREE.Mesh(standingGeo, mat);
    c1.position.set(-2.5, 1.1, -2.5);
    const c2 = new THREE.Mesh(standingGeo, mat);
    c2.position.set(2.0, 1.1, -2.5);
    group.add(c1);
    group.add(c2);
    const fallenGeo = new THREE.CylinderGeometry(0.18, 0.20, 2.5, 8);
    const fallen = new THREE.Mesh(fallenGeo, mat);
    fallen.rotation.z = Math.PI / 2;
    fallen.position.set(0.5, 0.18, 1.0);
    group.add(fallen);
  }
  function _addChamberWalls(group, mat) {
    // Two short walls suggesting an interior corner.
    const wallGeo = new THREE.BoxGeometry(7, 2.5, 0.2);
    const wall = new THREE.Mesh(wallGeo, mat);
    wall.position.set(0, 1.25, -3.4);
    group.add(wall);
    const sideGeo = new THREE.BoxGeometry(0.2, 2.5, 7);
    const sideL = new THREE.Mesh(sideGeo, mat);
    sideL.position.set(-3.4, 1.25, 0);
    group.add(sideL);
  }

  // ── Character figures ───────────────────────────────────────────────
  // Each is a small THREE.Group of primitives suggesting a human form.
  // No anatomical detail. Heads are spheres; bodies are boxes; legs
  // and arms are small cylinders. Player figures use the palette's
  // accent color; everyone else is solid black.
  function _buildFigure(spec, palette) {
    if (!spec) return null;
    const kind = spec.kind || "standing";
    const isPlayer = !!spec.is_player;
    const color = isPlayer ? palette.figure_player : palette.figure;
    const mat = new THREE.MeshStandardMaterial({
      color: color,
      roughness: 1.0,
      metalness: 0.0,
      emissive: isPlayer ? new THREE.Color(palette.figure_player).multiplyScalar(0.10) : 0x000000,
    });

    let group = null;
    if (kind === "standing") group = _figureStanding(mat);
    else if (kind === "robed") group = _figureRobed(mat);
    else if (kind === "kneeling") group = _figureKneeling(mat);
    else if (kind === "horseback") group = _figureHorseback(mat);
    else if (kind === "seated") group = _figureSeated(mat);
    else if (kind === "fallen") group = _figureFallen(mat);
    else group = _figureStanding(mat);

    if (!group) return null;
    // Place by spec.x / spec.z (-3..3 range from backend).
    group.position.set(spec.x || 0, 0, spec.z || 0);
    // Rotate per `facing`: spec is degrees, 0 = facing center. Three.js
    // rotation.y is radians around vertical.
    const facingDeg = (typeof spec.facing === "number") ? spec.facing : 0;
    group.rotation.y = (facingDeg * Math.PI) / 180;
    return group;
  }

  function _figureStanding(mat) {
    const g = new THREE.Group();
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 10, 8), mat);
    head.position.y = 1.65;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.8, 0.22), mat);
    body.position.y = 1.10;
    const legL = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.7, 6), mat);
    legL.position.set(-0.10, 0.35, 0);
    const legR = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.7, 6), mat);
    legR.position.set(0.10, 0.35, 0);
    const armL = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.6, 6), mat);
    armL.position.set(-0.22, 1.10, 0);
    const armR = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.6, 6), mat);
    armR.position.set(0.22, 1.10, 0);
    g.add(head, body, legL, legR, armL, armR);
    return g;
  }
  function _figureRobed(mat) {
    const g = new THREE.Group();
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 10, 8), mat);
    head.position.y = 1.62;
    // The robe is one cone-ish primitive replacing the body+legs.
    const robe = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.5, 1.5, 10), mat);
    robe.position.y = 0.75;
    g.add(head, robe);
    // Slight hood overlap with head.
    const hood = new THREE.Mesh(new THREE.SphereGeometry(0.20, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2), mat);
    hood.position.y = 1.62;
    g.add(hood);
    return g;
  }
  function _figureKneeling(mat) {
    const g = new THREE.Group();
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 10, 8), mat);
    head.position.y = 0.95;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.55, 0.22), mat);
    body.position.y = 0.62;
    const thighs = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.20, 0.45), mat);
    thighs.position.set(0, 0.18, 0.18);
    g.add(head, body, thighs);
    return g;
  }
  function _figureHorseback(mat) {
    const g = new THREE.Group();
    // Horse body
    const horseBody = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.55, 0.45), mat);
    horseBody.position.y = 0.85;
    // Legs
    const legGeo = new THREE.CylinderGeometry(0.07, 0.07, 0.85, 6);
    const offsets = [[-0.45, -0.18], [0.45, -0.18], [-0.45, 0.18], [0.45, 0.18]];
    offsets.forEach(([x, z]) => {
      const l = new THREE.Mesh(legGeo, mat);
      l.position.set(x, 0.42, z);
      g.add(l);
    });
    // Horse head + neck
    const neck = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.45, 0.25), mat);
    neck.position.set(0.65, 1.20, 0);
    neck.rotation.z = -0.5;
    const horseHead = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.22, 0.20), mat);
    horseHead.position.set(0.92, 1.42, 0);
    horseHead.rotation.z = -0.3;
    g.add(horseBody, neck, horseHead);
    // Rider
    const riderHead = new THREE.Mesh(new THREE.SphereGeometry(0.15, 10, 8), mat);
    riderHead.position.set(-0.10, 1.95, 0);
    const riderBody = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.65, 0.20), mat);
    riderBody.position.set(-0.10, 1.50, 0);
    g.add(riderHead, riderBody);
    return g;
  }
  function _figureSeated(mat) {
    const g = new THREE.Group();
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 10, 8), mat);
    head.position.y = 1.20;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.55, 0.22), mat);
    body.position.y = 0.85;
    const thighs = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.20, 0.50), mat);
    thighs.position.set(0, 0.50, 0.20);
    const shins = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.50, 0.18), mat);
    shins.position.set(-0.08, 0.25, 0.42);
    const shins2 = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.50, 0.18), mat);
    shins2.position.set(0.08, 0.25, 0.42);
    g.add(head, body, thighs, shins, shins2);
    return g;
  }
  function _figureFallen(mat) {
    const g = new THREE.Group();
    // Body horizontal on the ground.
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.20, 0.30), mat);
    body.position.y = 0.10;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 10, 8), mat);
    head.position.set(0.50, 0.15, 0);
    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.15, 0.25), mat);
    legs.position.set(-0.45, 0.075, 0);
    g.add(body, head, legs);
    return g;
  }
})();
