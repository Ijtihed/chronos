/**
 * CHRONOS War-table — Phase 2.6 (Spatial Substrate).
 *
 * Tilted regional 3D view of the era's region. Terrain rises from a
 * DEM heightmap served by GET /api/geo/terrain/{era_key}. NPC and
 * event markers cast shadows. Borders extrude vertically. The era
 * label appears massive and faint behind the table — a compositional
 * callback to the manuscript's ground name.
 *
 * Toggleable from the globe with `T`. Esc returns to the globe.
 *
 * Activation: same flag as the globe (`?flat=1` disables both). When
 * three.js is missing or the flag is off, this module is a no-op.
 *
 * The war-table is a SECOND view, not a replacement for the globe.
 * The globe stays mounted and resumes when the table is dismissed.
 */

(function () {
  // Same opt-out as globe.js: ?flat=1 in URL disables.
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("flat") === "1") return;
  } catch (e) {
    return;
  }
  if (typeof THREE === "undefined") {
    console.warn(
      "[wartable] THREE.js not loaded; war-table disabled.",
    );
    return;
  }

  // ── State ────────────────────────────────────────────────────────────
  let scene, camera, renderer, raycaster, mouse;
  let terrainMesh, sunLight;
  let borderGroup, markerGroup, eventGroup;
  let initialized = false;
  let isVisible = false;
  let currentEraKey = null;
  let currentRunId = null;
  let bbox = null; // {south, west, north, east}
  let _bordersData = null;
  let _heightmap = null; // Float32Array of normalized [0,1] heights
  let _heightmapW = 0;
  let _heightmapH = 0;

  // Camera orbit around the table center. Pitch ~45° default.
  const camOrbit = { theta: 0, phi: 0.85, dist: 2.4 };
  let _dragging = false;
  let _dragLast = { x: 0, y: 0 };
  let _panMode = false;
  const camPan = { x: 0, y: 0 };

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

  // Visual scale: the terrain plane is 2 units on its longer axis;
  // height is up to TERRAIN_HEIGHT units. Tweak to taste — too much
  // and the table looks cartoonish; too little and the relief
  // disappears under the markers.
  const TERRAIN_PLANE_SIZE = 2.0;
  const TERRAIN_HEIGHT = 0.18;
  const MARKER_SHADOW_LIFT = 0.012; // raise markers slightly above terrain
  const BORDER_LIFT = 0.006;

  function _resolveViewKey() {
    return currentRunId ? "chronos_wartable_view_" + currentRunId : null;
  }
  function _saveViewState() {
    const key = _resolveViewKey();
    if (!key) return;
    try {
      localStorage.setItem(
        key,
        JSON.stringify({ ...camOrbit, panX: camPan.x, panY: camPan.y }),
      );
    } catch (e) {}
  }
  function _loadViewState() {
    const key = _resolveViewKey();
    if (!key) return null;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const v = JSON.parse(raw);
      if (
        v && typeof v.theta === "number" && typeof v.phi === "number" &&
        typeof v.dist === "number" && v.dist >= 0.18 && v.dist <= 8.0
      ) return v;
    } catch (e) {}
    return null;
  }

  // ── lat/lon → table-local (x, z) projection ─────────────────────────
  // The terrain plane is centered at origin, lying in the XZ plane,
  // with +X = east, +Z = south (so -Z is north, like a paper map).
  // Returns null if the coord is outside the bbox.
  function _latLonToPlane(lat, lon) {
    if (!bbox) return null;
    const { south, west, north, east } = bbox;
    const w = east - west;
    const h = north - south;
    if (w <= 0 || h <= 0) return null;
    const u = (lon - west) / w; // 0..1, east
    const v = (lat - south) / h; // 0..1, north
    if (u < 0 || u > 1 || v < 0 || v > 1) return null;
    // Aspect-correct: the plane's longer axis stays TERRAIN_PLANE_SIZE.
    const aspect = w / h;
    let planeW = TERRAIN_PLANE_SIZE;
    let planeH = TERRAIN_PLANE_SIZE;
    if (aspect > 1) planeH = TERRAIN_PLANE_SIZE / aspect;
    else planeW = TERRAIN_PLANE_SIZE * aspect;
    const x = (u - 0.5) * planeW;
    const z = (0.5 - v) * planeH; // flip so north is -Z
    return { x, z };
  }

  function _heightAt(u, v) {
    if (!_heightmap || !_heightmapW || !_heightmapH) return 0;
    const ix = Math.max(0, Math.min(_heightmapW - 1, Math.floor(u * _heightmapW)));
    const iy = Math.max(0, Math.min(_heightmapH - 1, Math.floor((1 - v) * _heightmapH)));
    return _heightmap[iy * _heightmapW + ix] * TERRAIN_HEIGHT;
  }

  function _heightAtLatLon(lat, lon) {
    if (!bbox) return 0;
    const { south, west, north, east } = bbox;
    const u = (lon - west) / (east - west);
    const v = (lat - south) / (north - south);
    if (u < 0 || u > 1 || v < 0 || v > 1) return 0;
    return _heightAt(u, v);
  }

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    if (initialized) return;
    const container = document.getElementById("wartable-container");
    if (!container) return;
    let canvas = document.getElementById("wartable-canvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.id = "wartable-canvas";
      canvas.style.cssText =
        "position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;outline:none;";
      container.appendChild(canvas);
    }

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.Fog(0x000000, 3.5, 8.0);

    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    camera = new THREE.PerspectiveCamera(40, w / h, 0.01, 100);

    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 1);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    // Soft ambient + a directional sun so terrain reads as relief.
    const ambient = new THREE.AmbientLight(0xffffff, 0.32);
    scene.add(ambient);
    sunLight = new THREE.DirectionalLight(0xfff1d3, 1.05);
    sunLight.position.set(2.4, 3.2, 1.6);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.set(1024, 1024);
    sunLight.shadow.camera.near = 0.1;
    sunLight.shadow.camera.far = 8;
    sunLight.shadow.camera.left = -2;
    sunLight.shadow.camera.right = 2;
    sunLight.shadow.camera.top = 2;
    sunLight.shadow.camera.bottom = -2;
    sunLight.shadow.bias = -0.0005;
    scene.add(sunLight);
    // A subtle blue fill from below so the unlit slopes don't go pitch black.
    const fill = new THREE.HemisphereLight(0x4a6c8b, 0x06080c, 0.25);
    scene.add(fill);

    borderGroup = new THREE.Group();
    markerGroup = new THREE.Group();
    eventGroup = new THREE.Group();
    scene.add(borderGroup, markerGroup, eventGroup);

    _wireInteraction(canvas);
    _wireToolbar();
    _wireResize(container);
    _applyOrbit();

    initialized = true;
    _animate();
  }

  // ── Interaction ──────────────────────────────────────────────────────
  function _wireInteraction(canvas) {
    canvas.addEventListener("pointerdown", (e) => {
      _dragging = true;
      _panMode = e.shiftKey || e.button === 2;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      canvas.style.cursor = _panMode ? "move" : "grabbing";
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!_dragging) return;
      const dx = e.clientX - _dragLast.x;
      const dy = e.clientY - _dragLast.y;
      _dragLast.x = e.clientX;
      _dragLast.y = e.clientY;
      // Drag and pan sensitivity scale with camera distance: tight
      // close-in control, sweeping moves when far out. Same idea as
      // the globe.
      const minDist = 0.18;
      const altitude = Math.max(0.04, camOrbit.dist - minDist);
      if (_panMode) {
        const k = 0.0018 * altitude;
        camPan.x -= dx * k;
        camPan.y += dy * k;
      } else {
        const k = 0.0022 * Math.max(0.012, altitude);
        camOrbit.theta -= dx * k;
        camOrbit.phi = Math.max(0.18, Math.min(Math.PI * 0.49, camOrbit.phi - dy * k));
      }
      _applyOrbit();
    });
    const release = (e) => {
      if (!_dragging) return;
      _dragging = false;
      _panMode = false;
      canvas.style.cursor = "grab";
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      _saveViewState();
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("pointerleave", release);
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      // Altitude-proportional zoom (matches the globe's curve). Min
      // distance 0.18 lets you push the camera right into the terrain
      // for a "city-block" view; max 8 backs you off to "looking at
      // the whole region from a distance" framing.
      const minDist = 0.18;
      const altitude = Math.max(0.04, camOrbit.dist - minDist);
      const step = 0.10 * altitude;
      const sign = e.deltaY > 0 ? 1 : -1;
      camOrbit.dist = Math.max(minDist, Math.min(8.0, camOrbit.dist + sign * step));
      _applyOrbit();
      _saveViewState();
    }, { passive: false });

    let _downAt = null;
    canvas.addEventListener("pointerdown", (e) => {
      _downAt = { x: e.clientX, y: e.clientY, t: Date.now() };
    });
    canvas.addEventListener("pointerup", (e) => {
      if (!_downAt) return;
      const drift = Math.hypot(e.clientX - _downAt.x, e.clientY - _downAt.y);
      const dur = Date.now() - _downAt.t;
      _downAt = null;
      if (drift > 6 || dur > 350) return;
      _handleClick(e);
    });

    // T toggles back to globe; Esc returns to globe.
    document.addEventListener("keydown", (e) => {
      if (!isVisible) return;
      const a = document.activeElement;
      if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA")) return;
      if (e.key === "t" || e.key === "T") {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        hide();
      } else if (e.key === "Escape") {
        hide();
      }
    });
  }

  function _wireToolbar() {
    const reset = document.getElementById("wartable-reset");
    if (reset) reset.addEventListener("click", resetView);
    const close = document.getElementById("wartable-close");
    if (close) close.addEventListener("click", hide);
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

  function _applyOrbit() {
    if (!camera) return;
    const { theta, phi, dist } = camOrbit;
    camera.position.x = camPan.x + dist * Math.sin(phi) * Math.sin(theta);
    camera.position.y = dist * Math.cos(phi);
    camera.position.z = camPan.y + dist * Math.sin(phi) * Math.cos(theta);
    camera.lookAt(camPan.x, 0, camPan.y);
  }

  function resetView() {
    camOrbit.theta = 0;
    camOrbit.phi = 0.85;
    camOrbit.dist = 2.4;
    camPan.x = 0;
    camPan.y = 0;
    _applyOrbit();
    _saveViewState();
  }

  // ── Render loop ──────────────────────────────────────────────────────
  function _animate() {
    if (!renderer) return;
    requestAnimationFrame(_animate);
    if (!isVisible) return;
    renderer.render(scene, camera);
  }

  // ── Terrain ──────────────────────────────────────────────────────────
  // Build a plane mesh whose vertices are displaced by the heightmap.
  // We sample the heightmap into a Float32Array so marker placement
  // can read terrain height analytically (without re-reading the image).
  async function _loadTerrain(eraKey) {
    const url = "/api/geo/terrain/" + eraKey;
    let resp;
    try {
      resp = await fetch(url);
    } catch (e) {
      console.warn("[wartable] terrain fetch failed:", e);
      return false;
    }
    if (!resp.ok) {
      console.warn("[wartable] terrain endpoint returned", resp.status);
      return false;
    }
    // Pull bbox from response headers (the endpoint sets these).
    bbox = {
      south: parseFloat(resp.headers.get("X-Terrain-Bbox-South")),
      west: parseFloat(resp.headers.get("X-Terrain-Bbox-West")),
      north: parseFloat(resp.headers.get("X-Terrain-Bbox-North")),
      east: parseFloat(resp.headers.get("X-Terrain-Bbox-East")),
    };
    if ([bbox.south, bbox.west, bbox.north, bbox.east].some((v) => !isFinite(v))) {
      console.warn("[wartable] terrain endpoint missing bbox headers");
      return false;
    }

    const blob = await resp.blob();
    const bitmap = await createImageBitmap(blob);
    const cvs = document.createElement("canvas");
    cvs.width = bitmap.width;
    cvs.height = bitmap.height;
    const ctx = cvs.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);
    const imgData = ctx.getImageData(0, 0, cvs.width, cvs.height).data;
    _heightmapW = cvs.width;
    _heightmapH = cvs.height;
    _heightmap = new Float32Array(_heightmapW * _heightmapH);
    for (let i = 0; i < _heightmap.length; i++) {
      _heightmap[i] = imgData[i * 4] / 255; // R channel of grayscale PNG
    }

    // Build the plane.
    const aspect = (bbox.east - bbox.west) / (bbox.north - bbox.south);
    let planeW = TERRAIN_PLANE_SIZE;
    let planeH = TERRAIN_PLANE_SIZE;
    if (aspect > 1) planeH = TERRAIN_PLANE_SIZE / aspect;
    else planeW = TERRAIN_PLANE_SIZE * aspect;

    // Mesh resolution: 256x256 is plenty for the visual register at
    // typical camera distances. Vertex displacement happens once;
    // markers do their height lookup on the source heightmap.
    const segX = 192;
    const segZ = 192;
    const geo = new THREE.PlaneGeometry(planeW, planeH, segX, segZ);
    geo.rotateX(-Math.PI / 2); // lie flat in XZ
    const positions = geo.attributes.position;
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i);
      const z = positions.getZ(i);
      // Map plane (x, z) back to (u, v) in heightmap. North is -Z.
      const u = (x / planeW) + 0.5;
      const v = 0.5 - (z / planeH);
      const h = _heightAt(u, v);
      positions.setY(i, h);
    }
    positions.needsUpdate = true;
    geo.computeVertexNormals();

    if (terrainMesh) {
      scene.remove(terrainMesh);
      if (terrainMesh.geometry) terrainMesh.geometry.dispose();
      if (terrainMesh.material) terrainMesh.material.dispose();
    }
    const mat = new THREE.MeshStandardMaterial({
      color: 0x1a1a1f,
      roughness: 1.0,
      metalness: 0.0,
      flatShading: false,
    });
    terrainMesh = new THREE.Mesh(geo, mat);
    terrainMesh.receiveShadow = true;
    terrainMesh.userData.kind = "terrain";
    scene.add(terrainMesh);

    return true;
  }

  // ── Borders ──────────────────────────────────────────────────────────
  async function _loadBorders(eraKey) {
    while (borderGroup.children.length) {
      const c = borderGroup.children.pop();
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
    }
    try {
      const resp = await fetch("/api/geo/" + eraKey);
      if (!resp.ok) return;
      const data = await resp.json();
      _bordersData = data;
      _addBorders(data);
    } catch (e) {
      console.warn("[wartable] borders failed:", e);
    }
  }

  function _addBorders(geojson) {
    if (!geojson || !geojson.features || !bbox) return;
    const mat = new THREE.LineBasicMaterial({
      color: 0x9aa3b3,
      transparent: true,
      opacity: 0.85,
      depthTest: true,
    });
    geojson.features.forEach((feature) => {
      const geom = feature.geometry;
      if (!geom) return;
      const polys = [];
      if (geom.type === "Polygon") polys.push(...geom.coordinates);
      else if (geom.type === "MultiPolygon") geom.coordinates.forEach((p) => polys.push(...p));
      else if (geom.type === "LineString") polys.push(geom.coordinates);
      else if (geom.type === "MultiLineString") polys.push(...geom.coordinates);
      else return;
      polys.forEach((ring) => {
        const points = [];
        for (let i = 0; i < ring.length; i++) {
          const [lon, lat] = ring[i];
          const p = _latLonToPlane(lat, lon);
          if (!p) continue;
          const h = _heightAtLatLon(lat, lon) + BORDER_LIFT;
          points.push(new THREE.Vector3(p.x, h, p.z));
        }
        if (points.length < 2) return;
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(geo, mat);
        if (feature.properties) line.userData.feature = feature;
        borderGroup.add(line);
      });
    });
  }

  // ── Markers ──────────────────────────────────────────────────────────
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

  // Build a small marker that reads like a war-table token: a flat
  // disc lying on the terrain with a thin upright rim, slightly
  // emissive so it pops against shadow but doesn't glow.
  //
  // Why this geometry, not a cone: cones from a 45-degree top-down
  // camera read as triangular hoods (literally KKK-shaped). A disc
  // reads like a placed game piece, which is what the war-table
  // metaphor wants. Smaller radius_factor in updateMarkers callers
  // also helps -- pins were sized for a flat plane, not for a
  // closer tilt camera, so the same numbers looked enormous.
  //
  // Geometry: cylinder, radius=size, height=size*0.18 (very flat),
  // sitting on its bottom face with the top facing the sky.
  function _makePin(colorHex, sizeUnits, opacity) {
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: colorHex,
      transparent: opacity < 1,
      opacity: opacity,
      roughness: 0.45,
      metalness: 0.10,
      emissive: colorHex,
      emissiveIntensity: 0.22,
    });
    const disc = new THREE.Mesh(
      new THREE.CylinderGeometry(sizeUnits, sizeUnits, sizeUnits * 0.18, 18),
      mat,
    );
    disc.position.y = sizeUnits * 0.09; // sit on its bottom face
    disc.castShadow = true;
    disc.receiveShadow = false;
    group.add(disc);
    // Thin dark ring around the rim so the token reads as a piece,
    // not a colored blob. Made with a torus laid flat.
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(sizeUnits * 0.98, sizeUnits * 0.06, 6, 24),
      new THREE.MeshStandardMaterial({
        color: 0x000000,
        roughness: 0.9,
        metalness: 0.0,
        transparent: opacity < 1,
        opacity: opacity * 0.9,
      }),
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = sizeUnits * 0.18 + 0.001;
    ring.castShadow = false;
    group.add(ring);
    return group;
  }

  function updateMarkers(pv) {
    if (!initialized) return;
    _disposeGroup(markerGroup);
    if (!pv) return;

    const playerLoc = pv.current_location;
    const locById = {};
    if (playerLoc) locById[playerLoc.id] = playerLoc;
    (pv.known_locations || []).forEach((l) => { locById[l.id] = l; });

    // Marker sizes (table-local units, where the plane is ~2.0 wide).
    // Halved from the previous values that looked like hoods. Also
    // tuned so a player + 4 stacked NPCs doesn't blot out a region.
    const SIZE_PLAYER = 0.022;
    const SIZE_NPC_HERE = 0.016;
    const SIZE_NPC_KNOWN = 0.014;
    const SIZE_UNVISITED = 0.010;
    const SIZE_EVENT = 0.014;
    const SIZE_EVENT_WITNESSED = 0.018;

    if (playerLoc && playerLoc.lat != null && playerLoc.lon != null) {
      const isActive = pv.run_status === "active";
      const pin = _makePin(isActive ? 0x10b981 : 0x71717a, SIZE_PLAYER, isActive ? 1.0 : 0.55);
      const p = _latLonToPlane(playerLoc.lat, playerLoc.lon);
      if (p) {
        pin.position.set(p.x, _heightAtLatLon(playerLoc.lat, playerLoc.lon) + MARKER_SHADOW_LIFT, p.z);
        pin.userData = { kind: "player", name: pv.player_name, role: pv.player_role };
        markerGroup.add(pin);
      }
    }
    if (pv.run_status === "ended") return;

    // NPCs at the player's location: deterministic ring layout instead
    // of random jitter so the same NPC ends up in the same spot each
    // turn. Radius scales with how many there are.
    const here = pv.npcs_here || [];
    here.forEach((npc, i) => {
      if (!playerLoc || playerLoc.lat == null) return;
      const pin = _makePin(0xa1a1aa, SIZE_NPC_HERE, 1.0);
      const p = _latLonToPlane(playerLoc.lat, playerLoc.lon);
      if (!p) return;
      const angle = (i / Math.max(1, here.length)) * Math.PI * 2;
      const radius = 0.012;
      pin.position.set(
        p.x + Math.cos(angle) * radius,
        _heightAtLatLon(playerLoc.lat, playerLoc.lon) + MARKER_SHADOW_LIFT,
        p.z + Math.sin(angle) * radius,
      );
      pin.userData = { kind: "npc_here", npc };
      markerGroup.add(pin);
    });

    (pv.npcs_known || []).forEach((knownNpc) => {
      let knownLoc = null;
      for (const lid in locById) {
        if (locById[lid].name === knownNpc.last_known_location) {
          knownLoc = locById[lid];
          break;
        }
      }
      if (!knownLoc || knownLoc.lat == null) return;
      const fadedColor = pv.run_status === "dead_observing" ? 0x3f3f46 : 0x71717a;
      const pin = _makePin(fadedColor, SIZE_NPC_KNOWN, 0.85);
      const p = _latLonToPlane(knownLoc.lat, knownLoc.lon);
      if (!p) return;
      pin.position.set(p.x, _heightAtLatLon(knownLoc.lat, knownLoc.lon) + MARKER_SHADOW_LIFT, p.z);
      pin.userData = { kind: "npc_known", npc: knownNpc };
      markerGroup.add(pin);
    });

    (pv.unvisited_npc_counts || []).forEach((uv) => {
      if (uv.lat == null || uv.lon == null) return;
      const pin = _makePin(0x27272a, SIZE_UNVISITED, 0.55);
      const p = _latLonToPlane(uv.lat, uv.lon);
      if (!p) return;
      pin.position.set(p.x, _heightAtLatLon(uv.lat, uv.lon) + MARKER_SHADOW_LIFT, p.z);
      pin.userData = { kind: "anon" };
      markerGroup.add(pin);
    });

    // Stash sizes for the event marker pass (kept on a module constant).
    _markerSizes.event = SIZE_EVENT;
    _markerSizes.eventWitnessed = SIZE_EVENT_WITNESSED;
  }

  // Sizes for event markers — populated by updateMarkers so the values
  // live in one place. Keeps event/NPC markers visually proportional
  // even when one is updated independently of the other.
  const _markerSizes = { event: 0.014, eventWitnessed: 0.018 };

  function updateEventMarkers(events) {
    if (!initialized) return;
    _disposeGroup(eventGroup);
    if (!events || !events.length) return;
    events.forEach((ev) => {
      if (typeof ev.lat !== "number" || typeof ev.lon !== "number") return;
      const colorHex = EVENT_TYPE_COLORS[ev.type] || EVENT_TYPE_COLORS.cultural;
      const isWitnessed = ev.tier === "witnessed";
      const opacity =
        ev.tier === "witnessed" || ev.tier === "known" ? 1.0
          : ev.tier === "rumor_reliable" ? 0.7
            : ev.tier === "rumor_unreliable" ? 0.4
              : 0.3;
      const p = _latLonToPlane(ev.lat, ev.lon);
      if (!p) return;
      const size = isWitnessed ? _markerSizes.eventWitnessed : _markerSizes.event;
      const pin = _makePin(colorHex, size, opacity);
      pin.position.set(p.x, _heightAtLatLon(ev.lat, ev.lon) + MARKER_SHADOW_LIFT, p.z);
      pin.userData = { kind: "event", event: ev };
      eventGroup.add(pin);
    });
  }

  // ── Click handling ──────────────────────────────────────────────────
  function _handleClick(e) {
    if (!renderer || !camera) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    // Markers (events first, then NPCs).
    const targets = [
      ...eventGroup.children.flatMap((g) => g.children),
      ...markerGroup.children.flatMap((g) => g.children),
    ];
    const hits = raycaster.intersectObjects(targets, false);
    if (hits.length > 0) {
      const obj = hits[0].object;
      // Walk up to the userData-bearing group.
      const g = obj.parent && obj.parent.userData && obj.parent.userData.kind ? obj.parent : null;
      const ud = (g && g.userData) || obj.userData || {};
      if (ud.kind === "event") return _showEventPanel(ud.event);
      if (ud.kind === "npc_here" || ud.kind === "npc_known") return _showPerception(ud.npc);
      // player pin: no panel.
    }

    // Terrain click → region.
    if (!terrainMesh) return;
    const tHit = raycaster.intersectObject(terrainMesh, false);
    if (tHit.length === 0) return;
    const p = tHit[0].point;
    // Inverse of _latLonToPlane.
    if (!bbox) return;
    const aspect = (bbox.east - bbox.west) / (bbox.north - bbox.south);
    let planeW = TERRAIN_PLANE_SIZE;
    let planeH = TERRAIN_PLANE_SIZE;
    if (aspect > 1) planeH = TERRAIN_PLANE_SIZE / aspect;
    else planeW = TERRAIN_PLANE_SIZE * aspect;
    const u = p.x / planeW + 0.5;
    const v = 0.5 - p.z / planeH;
    const lon = bbox.west + u * (bbox.east - bbox.west);
    const lat = bbox.south + v * (bbox.north - bbox.south);
    const polity = _polityAt(lat, lon);
    if (polity) _showRegionKnowledge(polity);
  }

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
        geom.type === "Polygon" ? [geom.coordinates] :
          geom.type === "MultiPolygon" ? geom.coordinates : [];
      for (let j = 0; j < polys.length; j++) {
        if (_pointInPolygon([lon, lat], polys[j][0])) return name;
      }
    }
    return null;
  }
  function _pointInPolygon(point, vs) {
    const x = point[0], y = point[1];
    let inside = false;
    for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
      const xi = vs[i][0], yi = vs[i][1];
      const xj = vs[j][0], yj = vs[j][1];
      const intersect = ((yi > y) !== (yj > y)) &&
        (x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-9) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  // ── Panels — share the region-panel DOM with map.js / globe.js ──────
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
      data.known_facts.forEach((f) => { h += '<p class="region-fact">' + _esc(f) + "</p>"; });
    }
    if (data.rumors && data.rumors.length) {
      h += '<div class="region-section-label">Rumors</div>';
      data.rumors.forEach((r) => { h += '<p class="region-rumor">' + _esc(r) + "</p>"; });
    }
    if ((!data.known_facts || !data.known_facts.length) && (!data.rumors || !data.rumors.length)) {
      h += '<p class="region-fact" style="color:rgba(255,255,255,0.2);font-style:italic;">You know nothing of this place.</p>';
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
    _showRegionPanel({ polity_name: polityName, known_facts: [], rumors: [], character_note: "" });
    const body = document.getElementById("region-panel-body");
    if (body) body.innerHTML = '<span class="region-loading">Recalling what you know\u2026</span>';
    try {
      const res = await fetch("/api/run/" + currentRunId + "/region/" + encodeURIComponent(polityName));
      if (!res.ok) throw new Error();
      const data = await res.json();
      _showRegionPanel(data);
    } catch (e) {
      _showRegionPanel({
        polity_name: polityName, known_facts: [], rumors: [],
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
    if (ev.tier === "rumor_reliable" || ev.tier === "rumor_unreliable") metaParts.push("RUMORED");
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
    try {
      const res = await fetch("/api/run/" + currentRunId + "/npc/" + npc.id + "/perception");
      if (!res.ok) throw new Error();
      const data = await res.json();
      body.innerHTML = '<p class="region-fact">' + _esc(data.perception) + "</p>";
    } catch (e) {
      body.innerHTML = '<p class="region-fact" style="color:rgba(255,255,255,0.4);font-style:italic;">You can\u2019t place them right now.</p>';
    }
  }

  // ── Lifecycle ────────────────────────────────────────────────────────
  async function show(playerView, eraKey, runIdArg) {
    init();
    const container = document.getElementById("wartable-container");
    if (!container) return;
    container.classList.remove("hidden");
    isVisible = true;
    if (runIdArg) currentRunId = runIdArg;
    if (eraKey && eraKey !== currentEraKey) {
      currentEraKey = eraKey;
      const ok = await _loadTerrain(eraKey);
      if (ok) await _loadBorders(eraKey);
    }
    const saved = _loadViewState();
    if (saved) {
      camOrbit.theta = saved.theta;
      camOrbit.phi = saved.phi;
      camOrbit.dist = saved.dist;
      if (typeof saved.panX === "number") camPan.x = saved.panX;
      if (typeof saved.panY === "number") camPan.y = saved.panY;
      _applyOrbit();
    } else {
      resetView();
    }

    if (playerView) updateMarkers(playerView);
    _loadEventsForRun(currentRunId);

    if (renderer && camera) {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }

    // Update the era label that hangs faintly behind the table.
    const label = document.getElementById("wartable-era-label");
    if (label) {
      const friendly = (currentEraKey || "").replace(/_/g, " ").toUpperCase();
      label.textContent = friendly;
    }
  }

  function hide() {
    const container = document.getElementById("wartable-container");
    if (container) container.classList.add("hidden");
    isVisible = false;
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
      updateEventMarkers(data.events || []);
    } catch (e) { /* swallow */ }
  }

  // Public API. T-key wiring lives in app.js so it can pass current
  // run state into show() rather than the war-table needing to dig
  // for it.
  window.ChronosWarTable = {
    show: show,
    hide: hide,
    refresh: refresh,
    isVisible: function () { return isVisible; },
  };
})();
