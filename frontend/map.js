/**
 * CHRONOS — 3D Globe Map
 *
 * Three.js globe with:
 * - Natural Earth coastlines projected onto sphere
 * - Era-specific historical borders from GeoJSON
 * - Player marker (glowing)
 * - NPC markers with visited/unvisited distinction
 * - Camera follows player region, smooth rotation on travel
 * - Click-drag to rotate, scroll to zoom
 */

import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/controls/OrbitControls.js";
import { GeoJsonGeometry } from "https://cdn.jsdelivr.net/npm/three-geojson-geometry@1.3.2/dist/three-geojson-geometry.mjs";

const GLOBE_RADIUS = 100;
const DEG2RAD = Math.PI / 180;
const MARKER_ALTITUDE = 1.005;

let scene, camera, renderer, controls, globeGroup;
let playerMarker, npcMarkers = [];
let currentState = null;
let currentEraKey = null;
let animationId = null;
let isVisible = false;

const container = document.getElementById("map-container");

function latLonToVec3(lat, lon, radius) {
  const phi = (90 - lat) * DEG2RAD;
  const theta = (lon + 180) * DEG2RAD;
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  );
}

export function initGlobe() {
  if (scene) return;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0a);

  camera = new THREE.PerspectiveCamera(45, 1, 1, 1000);
  camera.position.set(0, 0, 300);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 130;
  controls.maxDistance = 500;
  controls.enablePan = false;

  globeGroup = new THREE.Group();
  scene.add(globeGroup);

  const sphereGeo = new THREE.SphereGeometry(GLOBE_RADIUS, 64, 64);
  const sphereMat = new THREE.MeshBasicMaterial({
    color: 0x111110,
    transparent: true,
    opacity: 0.95,
  });
  globeGroup.add(new THREE.Mesh(sphereGeo, sphereMat));

  const ambLight = new THREE.AmbientLight(0x404040);
  scene.add(ambLight);

  resize();
  window.addEventListener("resize", resize);
}

function resize() {
  if (!container || !renderer) return;
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

export async function loadCoastlines() {
  try {
    const resp = await fetch("/geo/coastlines.geojson");
    const geo = await resp.json();
    const lineGeo = new GeoJsonGeometry(geo, GLOBE_RADIUS);
    const lineMat = new THREE.LineBasicMaterial({
      color: 0x2a2820,
      linewidth: 1,
    });
    const coastlines = new THREE.LineSegments(lineGeo, lineMat);
    coastlines.name = "coastlines";
    globeGroup.add(coastlines);
  } catch (e) {
    console.warn("Failed to load coastlines:", e);
  }
}

export async function loadBorders(eraKey) {
  const existing = globeGroup.getObjectByName("borders");
  if (existing) globeGroup.remove(existing);

  try {
    const resp = await fetch(`/api/geo/${eraKey}`);
    if (!resp.ok) return;
    const geo = await resp.json();
    currentEraKey = eraKey;

    const borderGroup = new THREE.Group();
    borderGroup.name = "borders";

    for (const feature of geo.features) {
      if (!feature.geometry) continue;
      try {
        const featureGeo = new GeoJsonGeometry(feature.geometry, GLOBE_RADIUS * 1.001);
        const mat = new THREE.LineBasicMaterial({
          color: 0x3a3428,
          linewidth: 1,
          transparent: true,
          opacity: 0.6,
        });
        borderGroup.add(new THREE.LineSegments(featureGeo, mat));
      } catch {
        // skip malformed features
      }
    }

    globeGroup.add(borderGroup);
  } catch (e) {
    console.warn("Failed to load borders for", eraKey, e);
  }
}

export function updateMarkers(state) {
  currentState = state;

  if (playerMarker) {
    globeGroup.remove(playerMarker);
    playerMarker = null;
  }
  for (const m of npcMarkers) {
    globeGroup.remove(m);
  }
  npcMarkers = [];

  if (!state) return;

  const playerLoc = state.locations.find(
    (l) => l.id === state.player.location
  );
  if (playerLoc && playerLoc.lat && playerLoc.lon) {
    playerMarker = createPlayerMarker(playerLoc.lat, playerLoc.lon, state.run_status);
    globeGroup.add(playerMarker);
  }

  const visitedSet = new Set(state.visited_locations || []);

  for (const npc of state.npcs) {
    const loc = state.locations.find((l) => l.id === npc.location);
    if (!loc || !loc.lat || !loc.lon) continue;

    const visited = visitedSet.has(npc.location);
    const marker = createNpcMarker(
      loc.lat,
      loc.lon,
      npc,
      visited,
      state.run_status
    );
    npcMarkers.push(marker);
    globeGroup.add(marker);
  }
}

function createPlayerMarker(lat, lon, runStatus) {
  const pos = latLonToVec3(lat, lon, GLOBE_RADIUS * MARKER_ALTITUDE);
  const geo = new THREE.SphereGeometry(1.2, 16, 16);

  let color = 0xc8b88a;
  let opacity = 1.0;
  if (runStatus === "dead_observing") {
    color = 0x706050;
    opacity = 0.4;
  } else if (runStatus === "ended") {
    opacity = 0.0;
  }

  const mat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.copy(pos);

  const glowGeo = new THREE.SphereGeometry(2.0, 16, 16);
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0xc8b88a,
    transparent: true,
    opacity: opacity * 0.15,
  });
  const glow = new THREE.Mesh(glowGeo, glowMat);
  glow.position.copy(pos);

  const group = new THREE.Group();
  group.add(mesh);
  group.add(glow);
  group.name = "playerMarker";
  return group;
}

function createNpcMarker(lat, lon, npc, visited, runStatus) {
  const pos = latLonToVec3(lat, lon, GLOBE_RADIUS * MARKER_ALTITUDE);

  const jitter = (npc.id.charCodeAt(0) % 10 - 5) * 0.3;
  pos.x += jitter;
  pos.z += jitter * 0.7;

  let size, color, opacity;

  if (runStatus === "ended") {
    opacity = 0.0;
  } else if (visited) {
    size = 0.7;
    color = 0xa09070;
    opacity = 0.9;
  } else {
    size = 0.4;
    color = 0x484030;
    opacity = 0.5;
  }

  if (runStatus === "dead_observing" && npc.memory_of_player <= 0) {
    opacity = 0.0;
  } else if (runStatus === "dead_observing") {
    opacity *= npc.memory_of_player;
  }

  const geo = visited
    ? new THREE.SphereGeometry(size, 12, 12)
    : new THREE.SphereGeometry(size, 6, 6);
  const mat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: opacity || 0,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.copy(pos);
  mesh.name = `npc_${npc.id}`;
  return mesh;
}

export function focusOnLocation(lat, lon, animate) {
  if (!camera || !controls) return;
  const target = latLonToVec3(lat, lon, 0);
  const camPos = latLonToVec3(lat, lon, 250);

  if (animate) {
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    let t = 0;
    const duration = 60;

    function step() {
      t++;
      const p = Math.min(t / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);

      camera.position.lerpVectors(startPos, camPos, ease);
      controls.target.lerpVectors(startTarget, target, ease);
      controls.update();

      if (p < 1) requestAnimationFrame(step);
    }
    step();
  } else {
    camera.position.copy(camPos);
    controls.target.copy(target);
    controls.update();
  }
}

export function startRendering() {
  isVisible = true;
  function animate() {
    if (!isVisible) return;
    animationId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

export function stopRendering() {
  isVisible = false;
  if (animationId) {
    cancelAnimationFrame(animationId);
    animationId = null;
  }
}

export function isInitialized() {
  return !!scene;
}
