/**
 * CHRONOS Globe — Phase 2.6 (Spatial Substrate).
 *
 * Three.js sphere replacing the flat Leaflet map. Same data sources,
 * same panels, same click handlers — just a different surface.
 *
 * Activation: when body has class `chronos-globe-default` (set in
 * app.js initSpatialFlags()), this module overwrites `window.ChronosMap`
 * with the same API surface. `?flat=1` URL parameter keeps the
 * legacy Leaflet ChronosMap from map.js.
 *
 * API contract (must match map.js):
 *   init() / show(playerView, eraKey, runId) / hide() / toggle(state, eraKey)
 *   updateMarkers(playerView) / updateEventMarkers(events) / refresh(playerView, runId)
 *   isVisible()
 *
 * Why globally-named (not module-scoped): the existing app.js consumes
 * ChronosMap as a global. Keeping the API surface identical means
 * app.js doesn't need to learn about which renderer is active.
 *
 * Design rules (see context/game logic context/simulation-and-world.md):
 *   - Earth is dark grey-black per the project palette, not photoreal.
 *   - Atmosphere is a subtle blue limb glow.
 *   - All Knowledge Matrix filtering is preserved at the data layer.
 *   - Click-to-region, click-to-event, click-to-NPC behavior is identical
 *     to the flat map. The same panels are reused.
 */

(function () {
  // Only install if the 3D substrate is on. The flag set by app.js
  // initSpatialFlags() arrives AFTER this script's IIFE runs, so we
  // re-read the URL directly here. Same rule: ?flat=1 disables.
  // Mirrors the logic in app.js initSpatialFlags() — keep them in
  // sync if the flag semantics change.
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("flat") === "1") return;
  } catch (e) {
    // If URLSearchParams is somehow unavailable, default to the safer
    // path (legacy Leaflet) and skip the globe.
    return;
  }

  // Three.js is loaded as a global via the script tag in index.html.
  // If for any reason it's missing, fall back silently to the existing
  // ChronosMap (Leaflet) so the player still has a map.
  if (typeof THREE === "undefined") {
    console.warn(
      "[globe] THREE.js not loaded; falling back to legacy Leaflet map.",
    );
    return;
  }

  // ── State ────────────────────────────────────────────────────────────
  let scene, camera, renderer, raycaster, mouse;
  let earthMesh, atmosphereMesh, borderGroup, coastlineGroup;
  let markerGroup, eventGroup, placeGroup;
  // DOM-overlay marker layer. We project lat/lon to a 3D point on the
  // sphere, then to screen coords each frame, and place small DOM
  // elements at those positions. This lets us reuse the EXACT marker
  // styling from styles.css (.marker-player, .marker-visited,
  // .marker-event, etc.) — single source of truth shared with map.js.
  // No invented sprite styling, no scale drift, pixel-perfect hits.
  let markerOverlay = null;
  // Each entry: { el, vec3, kind, payload }
  let domMarkers = [];
  let initialized = false;
  let isVisible = false;
  let currentEraKey = null;
  let currentRunId = null;
  let lastPlayerLatLng = null;
  let perceptionCache = {};
  let regionCache = {};
  let _firstMarkerPlacement = true;
  let _bordersData = null; // raw GeoJSON, kept for raycast lookups

  // Auto-rotate when idle so the world reads as alive.
  let _autoRotate = true;
  let _idleSince = Date.now();

  // Pointer-drag orbit state.
  let _dragging = false;
  let _dragLast = { x: 0, y: 0 };
  // Camera in spherical coords around (0,0,0). Distance is in scene
  // units (sphere is radius=1). Defaults updated by loadBorders for
  // per-era framing.
  const camOrbit = { theta: 0, phi: 1.0, dist: 3.2 };
  let _defaultOrbit = { theta: 0, phi: 1.0, dist: 3.2 };

  const EVENT_TYPE_COLORS = {
    war: 0xdc2626,
    epidemic: 0x16a34a,
    famine: 0xea580c,
    political: 0x2563eb,
    religious: 0x9333ea,
    economic: 0xca8a04,
    natural_disaster: 0x78350f,
    cultural: 0x71717a,
  };

  // Per-era default camera framing — same intent as defaultCenter in
  // map.js, just expressed as orbit angles around the sphere. Values
  // approximate the era's region centroid; loadBorders refines the
  // distance based on the bounding box of the loaded borders.
  const ERA_FRAMING = {
    roman_late_empire: { lat: 42, lon: 15, dist: 2.4 },
    viking_age: { lat: 62, lon: 8, dist: 2.4 },
    crusader_states: { lat: 33, lon: 36, dist: 2.4 },
    black_death: { lat: 45, lon: 10, dist: 2.4 },
    fall_of_constantinople: { lat: 41, lon: 28, dist: 2.4 },
  };

  function _resolveViewKey() {
    return currentRunId ? "chronos_globe_view_" + currentRunId : null;
  }

  function _saveViewState() {
    const key = _resolveViewKey();
    if (!key) return;
    try {
      localStorage.setItem(
        key,
        JSON.stringify({
          theta: camOrbit.theta,
          phi: camOrbit.phi,
          dist: camOrbit.dist,
        }),
      );
    } catch (e) { /* swallow */ }
  }

  function _loadViewState() {
    const key = _resolveViewKey();
    if (!key) return null;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const v = JSON.parse(raw);
      if (
        v &&
        typeof v.theta === "number" && isFinite(v.theta) &&
        typeof v.phi === "number" && isFinite(v.phi) &&
        typeof v.dist === "number" && isFinite(v.dist) &&
        v.dist >= 1.015 && v.dist <= 15.0
      ) {
        return v;
      }
      localStorage.removeItem(key);
    } catch (e) {
      try { localStorage.removeItem(key); } catch (e2) {}
    }
    return null;
  }

  // ── Geometry helpers ─────────────────────────────────────────────────
  // lat/lon → 3D point on a unit sphere (radius=1, slight elevation
  // for markers/borders so they sit just above the surface and don't
  // z-fight with the earth mesh).
  function latLonToVec3(lat, lon, radius) {
    const r = radius == null ? 1.001 : radius;
    const phi = (90 - lat) * Math.PI / 180;
    const theta = (lon + 180) * Math.PI / 180;
    return new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi),
      r * Math.sin(phi) * Math.sin(theta),
    );
  }

  // Convert orbit (theta, phi, dist) → camera position. theta rotates
  // around Y, phi is polar angle from +Y down. Camera always looks at
  // the origin (sphere center).
  function _applyOrbitToCamera() {
    if (!camera) return;
    const { theta, phi, dist } = camOrbit;
    camera.position.x = dist * Math.sin(phi) * Math.sin(theta);
    camera.position.y = dist * Math.cos(phi);
    camera.position.z = dist * Math.sin(phi) * Math.cos(theta);
    camera.lookAt(0, 0, 0);
  }

  function _eraOrbit(eraKey) {
    const f = ERA_FRAMING[eraKey] || { lat: 30, lon: 0, dist: 2.6 };
    // theta from longitude (rotate east), phi from latitude (down from pole).
    const theta = (f.lon + 180) * Math.PI / 180;
    const phi = (90 - f.lat) * Math.PI / 180;
    return { theta, phi, dist: f.dist };
  }

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    if (initialized) return;
    const container = document.getElementById("map-container");
    if (!container) return;

    // Replace the leaflet #map div (if present) with a canvas the
    // first time the globe initializes. Index.html keeps the legacy
    // <div id="map"> for the Leaflet path.
    let canvas = document.getElementById("globe-canvas");
    if (!canvas) {
      const oldMap = document.getElementById("map");
      canvas = document.createElement("canvas");
      canvas.id = "globe-canvas";
      canvas.style.cssText =
        "position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;outline:none;";
      if (oldMap && oldMap.parentNode) {
        oldMap.style.display = "none";
        oldMap.parentNode.insertBefore(canvas, oldMap);
      } else {
        container.appendChild(canvas);
      }
    }

    // DOM marker overlay. Sits above the canvas, transparent, with
    // pointer-events:none on the container so dragging the canvas still
    // works. Individual markers re-enable pointer-events for hits.
    if (!markerOverlay) {
      markerOverlay = document.createElement("div");
      markerOverlay.id = "globe-marker-overlay";
      markerOverlay.style.cssText =
        "position:absolute;inset:0;pointer-events:none;z-index:5;";
      container.appendChild(markerOverlay);
    }

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);

    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 100);

    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 1);

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    // Earth — dark sphere. Matte, slightly inset from the marker shell
    // so markers cleanly sit on top.
    const earthGeo = new THREE.SphereGeometry(1.0, 64, 48);
    const earthMat = new THREE.MeshBasicMaterial({ color: 0x0a0a0c });
    earthMesh = new THREE.Mesh(earthGeo, earthMat);
    scene.add(earthMesh);

    // Atmosphere — slightly larger sphere, additive blue glow on the
    // limb. BackSide so we only see it where the earth doesn't cover it.
    const atmoGeo = new THREE.SphereGeometry(1.04, 48, 32);
    const atmoMat = new THREE.ShaderMaterial({
      uniforms: {},
      vertexShader: [
        "varying vec3 vNormal;",
        "void main() {",
        "  vNormal = normalize(normalMatrix * normal);",
        "  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);",
        "}",
      ].join("\n"),
      fragmentShader: [
        "varying vec3 vNormal;",
        "void main() {",
        "  float intensity = pow(0.7 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.5);",
        "  gl_FragColor = vec4(0.30, 0.55, 0.95, 1.0) * intensity * 0.55;",
        "}",
      ].join("\n"),
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
    });
    atmosphereMesh = new THREE.Mesh(atmoGeo, atmoMat);
    scene.add(atmosphereMesh);

    // Marker / border / event groups — every redraw clears + repopulates.
    borderGroup = new THREE.Group();
    coastlineGroup = new THREE.Group();
    markerGroup = new THREE.Group();
    eventGroup = new THREE.Group();
    placeGroup = new THREE.Group();
    scene.add(borderGroup, coastlineGroup, markerGroup, eventGroup, placeGroup);

    _wireInteraction(canvas);
    _wireToolbar();
    _wireResize(container);

    // Coastlines load once; reused across eras.
    _loadCoastlines();

    initialized = true;
    _animate();
  }

  // ── Interaction: drag to orbit, wheel to zoom, click to query ────────
  function _wireInteraction(canvas) {
    canvas.addEventListener("pointerdown", (e) => {
      _dragging = true;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      _autoRotate = false;
      canvas.style.cursor = "grabbing";
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!_dragging) return;
      const dx = e.clientX - _dragLast.x;
      const dy = e.clientY - _dragLast.y;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      // Drag east -> rotate camera east. Sensitivity scales with the
      // square of altitude-above-surface, so close-in drags barely move
      // the view and far-out drags sweep continents.
      //
      // Tuning history:
      //   v1 (linear):     k = 0.005 * (dist/2.5)              — felt
      //                                                          slingy at
      //                                                          all zooms
      //   v2 (sq, base 0.004 / floor 0.04): far better, but still
      //     overshoots when ultra-close.
      //   v3 (this):       base 0.0022, floor 0.012 — roughly half v2's
      //                    sensitivity at every zoom level. At dist=1.06
      //                    (deepest possible zoom) you barely budge per
      //                    pixel of drag; at default dist=2.4 the world
      //                    still rotates comfortably.
      const altitude = Math.max(0.05, camOrbit.dist - 1);
      const k = 0.0022 * Math.max(0.012, altitude * altitude);
      camOrbit.theta -= dx * k;
      camOrbit.phi = Math.max(0.05, Math.min(Math.PI - 0.05, camOrbit.phi - dy * k));
      _applyOrbitToCamera();
      _idleSince = Date.now();
    });
    const _release = (e) => {
      if (!_dragging) return;
      _dragging = false;
      canvas.style.cursor = "grab";
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      _saveViewState();
    };
    canvas.addEventListener("pointerup", _release);
    canvas.addEventListener("pointercancel", _release);
    canvas.addEventListener("pointerleave", _release);

    canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        // Zoom proportional to altitude above the sphere surface so
        // steps stay predictable near the surface and grow naturally
        // when wide. Range: dist=1.015 (almost-touching close-up,
        // useful for picking out a single city) up to 15.0 (earth as
        // a small object in deep space).
        //
        // Step coefficient is intentionally small (0.10) so each
        // wheel notch only nudges the view; this matches the lower
        // drag sensitivity so neither input is jumpy.
        const altitude = Math.max(0.015, camOrbit.dist - 1);
        const step = 0.10 * altitude;
        const sign = e.deltaY > 0 ? 1 : -1;
        camOrbit.dist = Math.max(1.015, Math.min(15.0, camOrbit.dist + sign * step));
        _applyOrbitToCamera();
        _idleSince = Date.now();
        _autoRotate = false;
        _saveViewState();
      },
      { passive: false },
    );

    // Click-to-query: short pointerdown with no significant drag opens
    // the appropriate panel for whatever's under the pointer.
    let _downAt = null;
    canvas.addEventListener("pointerdown", (e) => {
      _downAt = { x: e.clientX, y: e.clientY, t: Date.now() };
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!_downAt) return;
      const drift = Math.hypot(e.clientX - _downAt.x, e.clientY - _downAt.y);
      const dur = Date.now() - _downAt.t;
      _downAt = null;
      if (drift > 6 || dur > 350) return; // a drag, not a click
      _handleClick(e);
    });

    // Esc resets view (matches Leaflet behavior).
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!isVisible) return;
      const a = document.activeElement;
      if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA")) return;
      resetView();
    });
  }

  function _wireToolbar() {
    const zi = document.getElementById("map-zoom-in");
    const zo = document.getElementById("map-zoom-out");
    const rb = document.getElementById("map-reset");
    const cp = document.getElementById("map-center-player");
    if (zi) zi.addEventListener("click", () => {
      // Toolbar zoom uses the same altitude-proportional curve as the
      // wheel handler, just with a larger step (0.20 vs 0.10) for the
      // "deliberate jump" feel of clicking a button.
      const altitude = Math.max(0.015, camOrbit.dist - 1);
      camOrbit.dist = Math.max(1.015, camOrbit.dist - 0.20 * altitude);
      _applyOrbitToCamera();
      _saveViewState();
    });
    if (zo) zo.addEventListener("click", () => {
      const altitude = Math.max(0.015, camOrbit.dist - 1);
      camOrbit.dist = Math.min(15.0, camOrbit.dist + 0.20 * altitude);
      _applyOrbitToCamera();
      _saveViewState();
    });
    if (rb) rb.addEventListener("click", resetView);
    if (cp) cp.addEventListener("click", centerOnPlayer);

    // Reuse the existing legend toggle wiring from map.js — it just
    // flips a body class. Already initialized by map.js on load; we
    // don't need to touch it here.
  }

  function _wireResize(container) {
    let _resizeRAF = null;
    const onResize = () => {
      if (_resizeRAF) return;
      _resizeRAF = requestAnimationFrame(() => {
        _resizeRAF = null;
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

  function resetView() {
    camOrbit.theta = _defaultOrbit.theta;
    camOrbit.phi = _defaultOrbit.phi;
    camOrbit.dist = _defaultOrbit.dist;
    _applyOrbitToCamera();
    _saveViewState();
  }

  // Center on the player and zoom CLOSE. The previous version only
  // moved the camera in if it was already wide-enough -- if the user
  // had panned somewhere and clicked "You", camera might rotate to the
  // player but stay zoomed out, defeating the purpose. New behavior:
  // always rotate to player AND always zoom to a close "city level"
  // distance (1.18 = 18% above the surface, ~150 km eye height).
  function centerOnPlayer() {
    if (!lastPlayerLatLng) return;
    const phi = (90 - lastPlayerLatLng.lat) * Math.PI / 180;
    const theta = (lastPlayerLatLng.lon + 180) * Math.PI / 180;
    camOrbit.theta = theta;
    camOrbit.phi = phi;
    camOrbit.dist = 1.18;
    _autoRotate = false;
    _applyOrbitToCamera();
    _saveViewState();
  }

  // ── Render loop ──────────────────────────────────────────────────────
  function _animate() {
    if (!renderer) return;
    requestAnimationFrame(_animate);
    if (!isVisible) return;
    // Idle rotation: only if user hasn't interacted in a while AND
    // allowed it. Subtle — 0.05 rad/s, easy to ignore, easy to feel.
    if (_autoRotate && Date.now() - _idleSince > 4000) {
      camOrbit.theta += 0.0007;
      _applyOrbitToCamera();
    }
    renderer.render(scene, camera);
    // Project DOM markers AFTER the render so we have the latest
    // matrix world. Done every frame so markers track during orbit
    // and idle rotation.
    _projectDomMarkers();
  }

  // ── Coastlines ───────────────────────────────────────────────────────
  async function _loadCoastlines() {
    if (coastlineGroup.children.length > 0) return;
    try {
      const resp = await fetch("/geo/coastlines.geojson");
      const data = await resp.json();
      _addGeoJsonLines(coastlineGroup, data, 0x3f3f46, 0.55, 1.0015);
    } catch (e) {
      console.warn("[globe] coastlines failed:", e);
    }
  }

  // ── Borders ──────────────────────────────────────────────────────────
  async function loadBorders(eraKey) {
    // Clear existing borders.
    while (borderGroup.children.length) {
      const c = borderGroup.children.pop();
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
    }
    currentEraKey = eraKey;

    try {
      const resp = await fetch("/api/geo/" + eraKey);
      if (!resp.ok) return;
      const data = await resp.json();
      _bordersData = data;
      _addGeoJsonLines(borderGroup, data, 0x52525b, 0.7, 1.002);
    } catch (e) {
      console.warn("[globe] borders failed:", e);
    }
  }

  // Project a GeoJSON FeatureCollection into the given group as line
  // segments along great-circle arcs. Handles Polygon and MultiPolygon
  // (rings) and LineString and MultiLineString.
  //
  // Antimeridian handling: we densify each segment by interpolating
  // in lat/lon space, then snap to the sphere. For segments crossing
  // ±180, we split when the |dLon| > 180 and treat it as wrapping
  // the short way around. Crude but visually correct for the existing
  // simplified era borders.
  function _addGeoJsonLines(group, geojson, colorHex, opacity, radius) {
    if (!geojson || !geojson.features) return;
    const mat = new THREE.LineBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: opacity,
      depthTest: true,
    });
    geojson.features.forEach((feature) => {
      const geom = feature.geometry;
      if (!geom) return;
      const polys = [];
      if (geom.type === "Polygon") {
        polys.push(...geom.coordinates);
      } else if (geom.type === "MultiPolygon") {
        geom.coordinates.forEach((p) => polys.push(...p));
      } else if (geom.type === "LineString") {
        polys.push(geom.coordinates);
      } else if (geom.type === "MultiLineString") {
        polys.push(...geom.coordinates);
      } else {
        return;
      }
      polys.forEach((ring) => {
        const segs = _splitOnAntimeridian(ring);
        segs.forEach((seg) => {
          const points = [];
          for (let i = 0; i < seg.length - 1; i++) {
            const [lon1, lat1] = seg[i];
            const [lon2, lat2] = seg[i + 1];
            const steps = Math.max(2, Math.ceil(_haversineDeg(lat1, lon1, lat2, lon2) / 3));
            for (let s = 0; s <= steps; s++) {
              const t = s / steps;
              const lat = lat1 + (lat2 - lat1) * t;
              const lon = lon1 + (lon2 - lon1) * t;
              points.push(latLonToVec3(lat, lon, radius));
            }
          }
          if (points.length < 2) return;
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          const line = new THREE.Line(geo, mat);
          // Stash feature properties on the line so click can identify
          // the polity it belongs to.
          if (feature.properties) {
            line.userData.feature = feature;
          }
          group.add(line);
        });
      });
    });
  }

  // Split a coordinate ring into sub-rings each contained within one
  // hemisphere relative to the antimeridian.
  function _splitOnAntimeridian(ring) {
    const segs = [];
    let cur = [ring[0]];
    for (let i = 1; i < ring.length; i++) {
      const [lon1] = ring[i - 1];
      const [lon2] = ring[i];
      if (Math.abs(lon2 - lon1) > 180) {
        segs.push(cur);
        cur = [ring[i]];
      } else {
        cur.push(ring[i]);
      }
    }
    segs.push(cur);
    return segs;
  }

  function _haversineDeg(lat1, lon1, lat2, lon2) {
    const dLat = Math.abs(lat2 - lat1);
    const dLon = Math.abs(lon2 - lon1);
    return Math.sqrt(dLat * dLat + dLon * dLon);
  }

  // ── Markers (player / NPC / event) ──────────────────────────────────
  //
  // DOM overlay strategy: each marker is a small absolutely-positioned
  // div using the EXACT CSS classes already defined for the flat map
  // (.marker-player, .marker-visited, .marker-unvisited, .marker-event,
  // .marker-event-<type>, .marker-event-witnessed, .marker-faded).
  // styles.css is the single source of truth for marker design — globe
  // and Leaflet stay visually identical.
  //
  // Per render-frame (in _animate), each marker's 3D position is
  // projected to screen coords. Markers on the back of the sphere
  // are hidden (back-face cull via dot product). This gives accurate
  // pixel-perfect placement without any sprite-scale guessing.

  function _disposeGroup(group) {
    while (group.children.length) {
      const c = group.children.pop();
      if (c.geometry) c.geometry.dispose();
      if (c.material) {
        if (c.material.map) c.material.map.dispose();
        c.material.dispose();
      }
    }
  }

  // Wipe all DOM markers. Called at the top of every updateMarkers /
  // updateEventMarkers run — full repaint each turn, same model the
  // Leaflet path uses.
  function _clearDomMarkersByKind(kindPredicate) {
    const keep = [];
    domMarkers.forEach((m) => {
      if (kindPredicate(m.kind)) {
        if (m.el && m.el.parentNode) m.el.parentNode.removeChild(m.el);
      } else {
        keep.push(m);
      }
    });
    domMarkers = keep;
  }

  // size is the CSS pixel size for the dot/square. The marker sits at
  // the projected screen point, anchored at its visual center.
  function _addDomMarker(opts) {
    if (!markerOverlay) return null;
    const el = document.createElement("div");
    el.className = opts.className;
    const size = opts.size;
    el.style.cssText =
      "position:absolute;width:" + size + "px;height:" + size + "px;" +
      "left:0;top:0;transform:translate(-9999px,-9999px);" +
      "pointer-events:auto;cursor:pointer;" +
      "transition:opacity 0.15s ease;" +
      (opts.opacity != null ? "opacity:" + opts.opacity + ";" : "") +
      (opts.zIndex != null ? "z-index:" + opts.zIndex + ";" : "");
    if (opts.title) el.title = opts.title;
    if (opts.onClick) {
      el.addEventListener("click", function (e) {
        e.stopPropagation();
        opts.onClick(e);
      });
    }
    markerOverlay.appendChild(el);
    const entry = {
      el: el,
      vec3: latLonToVec3(opts.lat, opts.lon, 1.001),
      kind: opts.kind,
      payload: opts.payload,
      hideOnBack: opts.hideOnBack !== false,
    };
    domMarkers.push(entry);
    return entry;
  }

  // Project all DOM markers each frame. Hide ones on the far hemisphere.
  function _projectDomMarkers() {
    if (!camera || !markerOverlay) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const camPos = camera.position;
    const camLen = camPos.length() || 1;
    const tmp = new THREE.Vector3();
    for (let i = 0; i < domMarkers.length; i++) {
      const m = domMarkers[i];
      // Back-face cull: marker is on the far side of the sphere if its
      // outward normal (== position vector) points away from the camera.
      // dot(camPos / |camPos|, vec3) < threshold means it's tipping
      // around the limb — fade out cleanly rather than pop.
      const dot =
        (camPos.x * m.vec3.x + camPos.y * m.vec3.y + camPos.z * m.vec3.z) / camLen;
      if (m.hideOnBack && dot < 0.05) {
        m.el.style.opacity = "0";
        m.el.style.pointerEvents = "none";
        continue;
      }
      // Project to NDC then to screen.
      tmp.copy(m.vec3).project(camera);
      const sx = (tmp.x * 0.5 + 0.5) * w;
      const sy = (1 - (tmp.y * 0.5 + 0.5)) * h;
      // -size/2 to center the element on the projected point.
      const size = m.el.offsetWidth || 10;
      m.el.style.transform =
        "translate(" + (sx - size / 2) + "px," + (sy - size / 2) + "px)";
      // Smooth fade-in near the limb so markers don't pop.
      const limbFade = Math.min(1, Math.max(0.15, (dot - 0.05) / 0.20));
      m.el.style.opacity = String(limbFade);
      m.el.style.pointerEvents = limbFade > 0.5 ? "auto" : "none";
    }
  }

  function updateMarkers(pv) {
    if (!initialized) return;
    // Wipe any non-event markers from a previous turn.
    _clearDomMarkersByKind((k) => k !== "event");

    if (!pv) return;
    const runStatus = pv.run_status;
    const playerLoc = pv.current_location;

    const locById = {};
    if (playerLoc) locById[playerLoc.id] = playerLoc;
    (pv.known_locations || []).forEach((l) => { locById[l.id] = l; });

    // Player marker (matches Leaflet: 14px when active, 10px when dead).
    if (playerLoc && playerLoc.lat != null && playerLoc.lon != null) {
      lastPlayerLatLng = { lat: playerLoc.lat, lon: playerLoc.lon };
      const isActive = runStatus === "active";
      const cls = isActive ? "marker-player" : "marker-faded";
      const size = isActive ? 14 : 10;
      _addDomMarker({
        kind: "player",
        lat: playerLoc.lat,
        lon: playerLoc.lon,
        className: cls,
        size: size,
        title: pv.player_name
          ? pv.player_name + (pv.player_role ? " — " + pv.player_role : "")
          : "",
        zIndex: 1000,
        // Click the player marker to center + zoom in close. Always
        // re-center, even if the user has panned away — that's the
        // whole point of clicking it.
        onClick: function () { centerOnPlayer(); },
      });
    }

    if (runStatus === "ended") {
      _maybeAutoFitToPlayer();
      return;
    }

    // NPCs at current location (10px visited dot, with tiny lat/lon
    // offset so they don't fully stack — same trick as Leaflet path).
    (pv.npcs_here || []).forEach((npc, n) => {
      if (!playerLoc || playerLoc.lat == null) return;
      const offset = (n * 0.003) % 0.01;
      _addDomMarker({
        kind: "npc_here",
        lat: playerLoc.lat + offset,
        lon: playerLoc.lon + offset,
        className: "marker-visited",
        size: 10,
        title: npc.name + (npc.role ? " — " + npc.role : npc.archetype ? " — " + npc.archetype : ""),
        zIndex: 500,
        payload: npc,
        onClick: function () { _showPerception(npc); },
      });
    });

    // NPCs at known visited locations (8px, faded if observing).
    (pv.npcs_known || []).forEach((knownNpc, kn) => {
      let knownLoc = null;
      for (const lid in locById) {
        if (locById[lid].name === knownNpc.last_known_location) {
          knownLoc = locById[lid];
          break;
        }
      }
      if (!knownLoc || knownLoc.lat == null) return;
      const cls = runStatus === "dead_observing" ? "marker-faded" : "marker-visited";
      const offset = (kn * 0.003) % 0.01;
      _addDomMarker({
        kind: "npc_known",
        lat: knownLoc.lat + offset,
        lon: knownLoc.lon + offset,
        className: cls,
        size: 8,
        title: knownNpc.name + (knownNpc.archetype ? " — " + knownNpc.archetype : ""),
        zIndex: 300,
        payload: knownNpc,
        onClick: function () { _showPerception(knownNpc); },
      });
    });

    // Anonymous dots for unvisited locations with NPCs (5px, dim).
    (pv.unvisited_npc_counts || []).forEach((uv) => {
      if (uv.lat == null || uv.lon == null) return;
      _addDomMarker({
        kind: "anon",
        lat: uv.lat,
        lon: uv.lon,
        className: "marker-unvisited",
        size: 5,
        zIndex: 100,
      });
    });

    _maybeAutoFitToPlayer();
  }

  // True when the user has zoomed in past the era-default — used to
  // skip auto-zoom side effects when they're already inspecting
  // something. Mirrors the same heuristic in the legacy map.js.
  function _isUserNavigating() {
    return camOrbit.dist < (_defaultOrbit.dist - 0.4);
  }

  function _maybeAutoFitToPlayer() {
    if (!_firstMarkerPlacement || !lastPlayerLatLng) return;
    // Defer to any saved view from this run; only auto-frame on a
    // truly fresh visit.
    const saved = _loadViewState();
    if (saved) {
      _firstMarkerPlacement = false;
      return;
    }
    centerOnPlayer();
    _firstMarkerPlacement = false;
  }

  // ── Event markers ────────────────────────────────────────────────────
  // Match the Leaflet design exactly: 12×12 rounded square, color by
  // event type via marker-event marker-event-<type>; witnessed adds
  // marker-event-witnessed which paints the small white indicator dot.
  // Tier modulates opacity (witnessed/known full, rumor_reliable 0.7,
  // rumor_unreliable 0.4) — same as map.js _tierOpacity().

  function _tierOpacity(tier) {
    if (tier === "witnessed" || tier === "known") return 1.0;
    if (tier === "rumor_reliable") return 0.7;
    if (tier === "rumor_unreliable") return 0.4;
    return 0.3;
  }

  function updateEventMarkers(events) {
    if (!initialized) return;
    _clearDomMarkersByKind((k) => k === "event");
    if (!events || !events.length) return;
    events.forEach(_addEventMarker);
  }

  function _addEventMarker(ev) {
    if (typeof ev.lat !== "number" || typeof ev.lon !== "number") return;
    const isWitnessed = ev.tier === "witnessed";
    let className = "marker-event marker-event-" + (ev.type || "cultural");
    if (isWitnessed) className += " marker-event-witnessed";
    _addDomMarker({
      kind: "event",
      lat: ev.lat,
      lon: ev.lon,
      className: className,
      size: 12,
      opacity: _tierOpacity(ev.tier),
      title:
        ev.year + " AD — " + (ev.type || "").toUpperCase() +
        (ev.summary ? " — " + ev.summary.substring(0, 80) : ""),
      zIndex: 200,
      payload: ev,
      onClick: function () { _showEventPanel(ev); },
    });
  }

  // ── Click handling ───────────────────────────────────────────────────
  // Marker clicks are handled by the DOM overlay directly (each marker
  // div has its own listener via _addDomMarker onClick). What's left
  // here is region selection: when the user clicks somewhere on the
  // earth that isn't a marker, raycast against the sphere and look up
  // the polity at that lat/lon.
  function _handleClick(e) {
    if (!renderer || !camera) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    const earthHit = raycaster.intersectObject(earthMesh, false);
    if (earthHit.length > 0) {
      const p = earthHit[0].point;
      const lat = 90 - Math.acos(p.y) * 180 / Math.PI;
      const lonRaw = Math.atan2(p.z, -p.x) * 180 / Math.PI - 180;
      const lon = ((lonRaw + 540) % 360) - 180; // wrap to -180..180
      const polity = _polityAt(lat, lon);
      if (polity) _showRegionKnowledge(polity);
    }
  }

  // Point-in-polygon test against the loaded borders. Walks the
  // GeoJSON FeatureCollection (kept in _bordersData) and returns the
  // feature.properties.NAME of the first polygon containing the point.
  function _polityAt(lat, lon) {
    if (!_bordersData) return null;
    const features = _bordersData.features || [];
    for (let i = 0; i < features.length; i++) {
      const f = features[i];
      const name = f.properties && f.properties.NAME;
      if (!name) continue;
      const geom = f.geometry;
      if (!geom) continue;
      const polys =
        geom.type === "Polygon"
          ? [geom.coordinates]
          : geom.type === "MultiPolygon"
            ? geom.coordinates
            : [];
      for (let j = 0; j < polys.length; j++) {
        if (_pointInPolygon([lon, lat], polys[j][0])) {
          return name;
        }
      }
    }
    return null;
  }

  function _pointInPolygon(point, vs) {
    const x = point[0];
    const y = point[1];
    let inside = false;
    for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
      const xi = vs[i][0], yi = vs[i][1];
      const xj = vs[j][0], yj = vs[j][1];
      const intersect =
        ((yi > y) !== (yj > y)) &&
        (x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-9) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  // ── Panels — reuse the DOM panels already built for the flat map ────
  function _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function _showRegionPanel(data) {
    const panel = document.getElementById("region-panel");
    const overlay = document.getElementById("region-overlay");
    const title = document.getElementById("region-panel-title");
    const body = document.getElementById("region-panel-body");
    if (!panel || !body) return;
    if (title) title.textContent = data.polity_name;
    let h = "";
    if (data.known_facts && data.known_facts.length) {
      h += '<div class="region-section-label">Known</div>';
      data.known_facts.forEach((f) => {
        h += '<p class="region-fact">' + _esc(f) + "</p>";
      });
    }
    if (data.rumors && data.rumors.length) {
      h += '<div class="region-section-label">Rumors</div>';
      data.rumors.forEach((r) => {
        h += '<p class="region-rumor">' + _esc(r) + "</p>";
      });
    }
    if ((!data.known_facts || !data.known_facts.length) && (!data.rumors || !data.rumors.length)) {
      h +=
        '<p class="region-fact" style="color:rgba(255,255,255,0.2);font-style:italic;">You know nothing of this place.</p>';
    }
    if (data.character_note) {
      h += '<div class="region-note">' + _esc(data.character_note) + "</div>";
    }
    body.innerHTML = h;
    panel.classList.remove("hidden");
    if (overlay) overlay.classList.remove("hidden");
  }

  async function _showRegionKnowledge(polityName) {
    if (!currentRunId) return;
    const cacheKey = polityName + "_" + ((Date.now() / 60000) | 0);
    if (regionCache[cacheKey]) {
      _showRegionPanel(regionCache[cacheKey]);
      return;
    }
    _showRegionPanel({
      polity_name: polityName,
      known_facts: [],
      rumors: [],
      character_note: "",
    });
    const body = document.getElementById("region-panel-body");
    if (body) body.innerHTML = '<span class="region-loading">Recalling what you know\u2026</span>';
    try {
      const res = await fetch(
        "/api/run/" + currentRunId + "/region/" + encodeURIComponent(polityName),
      );
      if (!res.ok) throw new Error();
      const data = await res.json();
      regionCache[cacheKey] = data;
      _showRegionPanel(data);
    } catch (e) {
      _showRegionPanel({
        polity_name: polityName,
        known_facts: [],
        rumors: [],
        character_note: "You search your memory but recall nothing of this place.",
      });
    }
  }

  function _showEventPanel(ev) {
    const panel = document.getElementById("region-panel");
    const overlay = document.getElementById("region-overlay");
    const title = document.getElementById("region-panel-title");
    const body = document.getElementById("region-panel-body");
    if (!panel || !body) return;
    if (title) title.textContent = ev.year + " AD — " + (ev.region || "unknown region");
    const metaParts = [];
    if (ev.type) metaParts.push(ev.type.toUpperCase().replace(/_/g, " "));
    if (ev.significance) metaParts.push(ev.significance.toUpperCase());
    if (ev.tier === "rumor_reliable" || ev.tier === "rumor_unreliable") {
      metaParts.push("RUMORED");
    }
    let h = '<div class="region-section-label event-meta">' + _esc(metaParts.join(" \u2022 ")) + "</div>";
    h += '<p class="region-fact">' + _esc(ev.summary) + "</p>";
    body.innerHTML = h;
    panel.classList.remove("hidden");
    if (overlay) overlay.classList.remove("hidden");
  }

  async function _showPerception(npc) {
    if (!currentRunId || !npc || !npc.id) return;
    const panel = document.getElementById("region-panel");
    const title = document.getElementById("region-panel-title");
    const body = document.getElementById("region-panel-body");
    if (!panel || !body) return;
    if (title) title.textContent = npc.name + (npc.role ? " — " + npc.role : "");
    body.innerHTML = '<span class="region-loading">Thinking\u2026</span>';
    panel.classList.remove("hidden");
    const overlay = document.getElementById("region-overlay");
    if (overlay) overlay.classList.remove("hidden");
    const cacheKey = npc.id + "_" + ((Date.now() / 60000) | 0);
    if (perceptionCache[cacheKey]) {
      body.innerHTML = '<p class="region-fact">' + _esc(perceptionCache[cacheKey]) + "</p>";
      return;
    }
    try {
      const res = await fetch("/api/run/" + currentRunId + "/npc/" + npc.id + "/perception");
      if (!res.ok) throw new Error();
      const data = await res.json();
      perceptionCache[cacheKey] = data.perception;
      body.innerHTML = '<p class="region-fact">' + _esc(data.perception) + "</p>";
    } catch (e) {
      body.innerHTML =
        '<p class="region-fact" style="color:rgba(255,255,255,0.4);font-style:italic;">You can\u2019t place them right now.</p>';
    }
  }

  // ── Lifecycle ────────────────────────────────────────────────────────
  function show(playerView, eraKeyArg, runIdArg) {
    init();
    const container = document.getElementById("map-container");
    if (!container) return;
    container.classList.remove("hidden");
    isVisible = true;

    // Loading overlay: same pattern as the war-table. Cover the canvas
    // until borders are loaded so the user doesn't see a black sphere
    // for the second or two it takes the GeoJSON to fetch + project.
    // For era changes we reset to the loading state; for re-opens
    // with the same era and existing borders we leave .ready alone
    // and the overlay stays faded.
    const stageEl = document.getElementById("map-loading-stage");
    const setStage = (s) => { if (stageEl) stageEl.textContent = s; };
    const eraChanged = eraKeyArg && eraKeyArg !== currentEraKey;
    if (eraChanged || borderGroup.children.length === 0) {
      container.classList.remove("ready");
      setStage("Loading borders\u2026");
    }

    if (runIdArg && runIdArg !== currentRunId) {
      _firstMarkerPlacement = true;
      perceptionCache = {};
      regionCache = {};
    }
    if (runIdArg) currentRunId = runIdArg;

    if (eraChanged) {
      _defaultOrbit = _eraOrbit(eraKeyArg);
      camOrbit.theta = _defaultOrbit.theta;
      camOrbit.phi = _defaultOrbit.phi;
      camOrbit.dist = _defaultOrbit.dist;
      _applyOrbitToCamera();
      // Fire-and-forget border load; mark ready in its callback path.
      loadBorders(eraKeyArg).then(() => {
        setStage("Placing markers\u2026");
        _markGlobeReady(container);
      }).catch(() => {
        setStage("Borders failed");
      });
    } else {
      // Same era; if borders already loaded from a prior show, mark
      // ready immediately. If they haven't (very rare race), fall
      // back to a quick deferred check.
      if (borderGroup.children.length > 0) {
        _markGlobeReady(container);
      } else {
        // Borders are still loading from the previous show()'s
        // fire-and-forget. Poll briefly.
        let _polls = 0;
        const _check = () => {
          if (borderGroup.children.length > 0) {
            _markGlobeReady(container);
          } else if (_polls++ < 40) {
            setTimeout(_check, 100);
          }
        };
        _check();
      }
    }

    // Restore prior view if we have one.
    const saved = _loadViewState();
    if (saved) {
      camOrbit.theta = saved.theta;
      camOrbit.phi = saved.phi;
      camOrbit.dist = saved.dist;
      _applyOrbitToCamera();
      _firstMarkerPlacement = false;
    }

    if (playerView) updateMarkers(playerView);
    _loadEventsForRun(currentRunId);

    // Renderer canvas pulls from the container dimensions; if the
    // overlay was opened first time the container had 0×0, kick a
    // resize so the perspective is correct now.
    if (renderer && camera) {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
  }

  function _markGlobeReady(container) {
    // Defer two animation frames so we get at least one painted
    // frame at full size before the overlay fades; prevents catching
    // a flash of empty canvas during the transition.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        container.classList.add("ready");
      });
    });
  }

  function hide() {
    const container = document.getElementById("map-container");
    if (container) container.classList.add("hidden");
    isVisible = false;
  }

  function toggle(playerView, eraKeyArg) {
    if (isVisible) hide();
    else show(playerView, eraKeyArg);
  }

  function refresh(playerView, runIdArg) {
    if (runIdArg) currentRunId = runIdArg;
    if (playerView) updateMarkers(playerView);
    _loadEventsForRun(currentRunId);
  }

  async function _loadEventsForRun(runId) {
    if (!runId) return;
    try {
      const res = await fetch("/api/run/" + runId + "/events/visible");
      if (!res.ok) return;
      const data = await res.json();
      if (data.era_key && currentEraKey && data.era_key !== currentEraKey) {
        return;
      }
      updateEventMarkers(data.events || []);
    } catch (e) {
      console.warn("[globe] events failed:", e);
    }
  }

  // ── Public API — overwrite ChronosMap so app.js doesn't change ──────
  //
  // map.js declares `const ChronosMap = ...` at module scope. A `const`
  // binding cannot be reassigned, AND it does not live on `window` — it
  // lives in the script's lexical environment. So `window.ChronosMap = X`
  // here would only create a *separate* binding on window, while
  // unqualified `ChronosMap` references in app.js still resolve to the
  // lexical const from map.js (Leaflet). Net effect: the globe would
  // install but app.js would never call it.
  //
  // The fix: copy each method onto the existing ChronosMap object, in
  // place. Both files's references stay valid; the methods now route to
  // globe code instead of Leaflet code. We also keep `window.ChronosMap`
  // pointing at the same object so anyone reading via `window` sees the
  // same shape.
  const _globeApi = {
    init: init,
    show: show,
    hide: hide,
    toggle: toggle,
    updateMarkers: updateMarkers,
    updateEventMarkers: updateEventMarkers,
    refresh: refresh,
    isVisible: function () { return isVisible; },
  };
  if (typeof ChronosMap !== "undefined" && ChronosMap) {
    Object.keys(_globeApi).forEach(function (k) {
      ChronosMap[k] = _globeApi[k];
    });
    // Mirror onto window for any code that reads via window.ChronosMap.
    window.ChronosMap = ChronosMap;
  } else {
    // Defensive: if map.js failed to load, still expose ourselves so
    // the rest of the app at least has *something* on window.ChronosMap.
    window.ChronosMap = _globeApi;
  }

  // Expose the latLonToVec3 helper so the war-table module (also
  // Three.js) can reuse the same projection convention.
  window.ChronosGlobe = {
    latLonToVec3: latLonToVec3,
    EVENT_TYPE_COLORS: EVENT_TYPE_COLORS,
  };
})();
