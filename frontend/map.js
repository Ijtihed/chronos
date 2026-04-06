/**
 * CHRONOS Map — 2D Leaflet map with historical borders, player/NPC markers.
 * Toggled with the narrative view via 'M' key.
 *
 * Marker design requirement: visited NPCs are visually distinct from unvisited.
 * State comes from the world state API, not hardcoded.
 */

const ChronosMap = (function () {
  let map = null;
  let coastlineLayer = null;
  let borderLayer = null;
  let playerMarker = null;
  let npcMarkers = [];
  let isVisible = false;
  let initialized = false;
  let currentEraKey = null;
  let currentRunId = null;
  let perceptionCache = {};

  function init() {
    if (initialized) return;

    map = L.map("map", {
      center: [42, 15],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
      maxBoundsViscosity: 1.0,
    });

    map.getContainer().style.background = "#0e0e0e";
    initialized = true;

    var zoomIn = document.getElementById("map-zoom-in");
    var zoomOut = document.getElementById("map-zoom-out");
    if (zoomIn) zoomIn.addEventListener("click", function () { map.zoomIn(); });
    if (zoomOut) zoomOut.addEventListener("click", function () { map.zoomOut(); });
  }

  async function loadCoastlines() {
    if (coastlineLayer) return;
    try {
      const resp = await fetch("/geo/coastlines.geojson");
      const data = await resp.json();
      coastlineLayer = L.geoJSON(data, {
        style: {
          color: "#2a2620",
          weight: 1,
          opacity: 0.6,
          fill: false,
        },
      }).addTo(map);
    } catch (e) {
      console.warn("Failed to load coastlines:", e);
    }
  }

  async function loadBorders(eraKey) {
    if (borderLayer) {
      map.removeLayer(borderLayer);
      borderLayer = null;
    }
    currentEraKey = eraKey;
    try {
      const resp = await fetch(`/api/geo/${eraKey}`);
      if (!resp.ok) return;
      const data = await resp.json();
      borderLayer = L.geoJSON(data, {
        style: function (feature) {
          const name = feature.properties && feature.properties.NAME;
          return {
            color: name ? "#504838" : "#1e1c18",
            weight: name ? 1.2 : 0.5,
            opacity: name ? 0.7 : 0.3,
            fillColor: name ? "#1a1816" : "#0e0e0e",
            fillOpacity: name ? 0.15 : 0.05,
          };
        },
        onEachFeature: function (feature, layer) {
          const name = feature.properties && feature.properties.NAME;
          if (name) {
            layer.bindTooltip(name, {
              className: "polity-tooltip",
              direction: "center",
              permanent: false,
              opacity: 0.8,
            });
          }
        },
      }).addTo(map);
    } catch (e) {
      console.warn("Failed to load borders:", e);
    }
  }

  function makeIcon(cssClass, size) {
    return L.divIcon({
      className: cssClass,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function updateMarkers(pv) {
    if (!map) return;

    if (playerMarker) {
      map.removeLayer(playerMarker);
      playerMarker = null;
    }
    npcMarkers.forEach(function (m) {
      map.removeLayer(m);
    });
    npcMarkers = [];

    var runStatus = pv.run_status;
    var playerLoc = pv.current_location;

    // Build location lookup from PlayerView
    var locById = {};
    if (playerLoc) locById[playerLoc.id] = playerLoc;
    var knownLocs = pv.known_locations || [];
    for (var k = 0; k < knownLocs.length; k++) {
      locById[knownLocs[k].id] = knownLocs[k];
    }

    if (playerLoc && playerLoc.lat && playerLoc.lon) {
      var playerClass =
        runStatus === "dead_observing"
          ? "marker-faded"
          : runStatus === "ended"
            ? "marker-faded"
            : "marker-player";
      var playerSize =
        runStatus === "active" ? 14 : 10;
      playerMarker = L.marker([playerLoc.lat, playerLoc.lon], {
        icon: makeIcon(playerClass, playerSize),
        zIndexOffset: 1000,
      }).addTo(map);

      if (runStatus === "active") {
        playerMarker.bindTooltip(
          '<span style="font-family:IM Fell English,serif;font-size:13px;color:#c8b89a;">' +
          (pv.player_name || '') + '</span><br>' +
          '<span style="font-family:Special Elite,monospace;font-size:9px;color:#8a7040;text-transform:uppercase;letter-spacing:0.08em;">' +
          (pv.player_role || '') + '</span>',
          {
            direction: "top",
            offset: [0, -10],
            opacity: 1,
            className: "npc-tooltip",
          }
        );
      }
    }

    if (runStatus === "ended") {
      if (playerLoc && playerLoc.lat) {
        map.setView([playerLoc.lat, playerLoc.lon], map.getZoom(), { animate: true, duration: 0.8 });
      }
      return;
    }

    // NPCs at current location (full detail)
    var npcsHere = pv.npcs_here || [];
    for (var n = 0; n < npcsHere.length; n++) {
      var npc = npcsHere[n];
      if (!playerLoc || !playerLoc.lat) continue;

      var offset = (n * 0.003) % 0.01;
      var m = L.marker([playerLoc.lat + offset, playerLoc.lon + offset], {
        icon: makeIcon("marker-visited", 10),
        zIndexOffset: 500,
      }).addTo(map);

      m.bindTooltip(
        '<span style="font-family:IM Fell English,serif;font-size:13px;color:#c8b89a;letter-spacing:0.02em;">' +
        npc.name + '</span><br>' +
        '<span style="font-family:Special Elite,monospace;font-size:9px;color:#5a4e3a;text-transform:uppercase;letter-spacing:0.08em;">' +
        (npc.role || npc.archetype || '') + '</span>',
        { direction: "top", offset: [0, -8], opacity: 1, className: "npc-tooltip" }
      );
      (function (npcRef, marker) {
        marker.on("click", function () { _showPerception(npcRef, marker); });
      })(npc, m);

      npcMarkers.push(m);
    }

    // NPCs at known (visited) locations — name + archetype only
    var npcsKnown = pv.npcs_known || [];
    for (var kn = 0; kn < npcsKnown.length; kn++) {
      var knownNpc = npcsKnown[kn];
      var knownLoc = null;
      for (var lid in locById) {
        if (locById[lid].name === knownNpc.last_known_location) {
          knownLoc = locById[lid];
          break;
        }
      }
      if (!knownLoc || !knownLoc.lat) continue;

      var markerClass = runStatus === "dead_observing" ? "marker-faded" : "marker-visited";
      var kOffset = (kn * 0.003) % 0.01;
      var km = L.marker([knownLoc.lat + kOffset, knownLoc.lon + kOffset], {
        icon: makeIcon(markerClass, 8),
        zIndexOffset: 300,
      }).addTo(map);

      km.bindTooltip(
        '<span style="font-family:IM Fell English,serif;font-size:13px;color:#c8b89a;">' +
        knownNpc.name + '</span><br>' +
        '<span style="font-family:Special Elite,monospace;font-size:9px;color:#5a4e3a;text-transform:uppercase;letter-spacing:0.08em;">' +
        (knownNpc.archetype || '') + '</span>',
        { direction: "top", offset: [0, -8], opacity: 1, className: "npc-tooltip" }
      );

      npcMarkers.push(km);
    }

    if (playerLoc && playerLoc.lat) {
      map.setView([playerLoc.lat, playerLoc.lon], map.getZoom(), {
        animate: true,
        duration: 0.8,
      });
    }
  }

  async function _showPerception(npc, marker) {
    if (!currentRunId) return;
    var cacheKey = npc.id + "_" + (Date.now() / 60000 | 0);
    if (perceptionCache[cacheKey]) {
      marker.unbindPopup();
      marker.bindPopup(
        '<div style="font-family:IM Fell English,serif;font-size:14px;color:#c8b89a;max-width:280px;line-height:1.6;padding:4px;">' +
        perceptionCache[cacheKey] + '</div>',
        { className: "perception-popup", closeButton: false, maxWidth: 300 }
      ).openPopup();
      return;
    }
    marker.unbindPopup();
    marker.bindPopup(
      '<div style="font-family:Special Elite,monospace;font-size:10px;color:#5a4e3a;padding:4px;">thinking...</div>',
      { className: "perception-popup", closeButton: false }
    ).openPopup();
    try {
      var res = await fetch("/api/run/" + currentRunId + "/npc/" + npc.id + "/perception");
      if (!res.ok) return;
      var data = await res.json();
      perceptionCache[cacheKey] = data.perception;
      marker.unbindPopup();
      marker.bindPopup(
        '<div style="font-family:IM Fell English,serif;font-size:14px;color:#c8b89a;max-width:280px;line-height:1.6;padding:4px;">' +
        data.perception + '</div>',
        { className: "perception-popup", closeButton: false, maxWidth: 300 }
      ).openPopup();
    } catch (e) {}
  }

  function show(playerView, eraKey, runId) {
    var container = document.getElementById("map-container");
    if (!container) return;

    init();
    container.classList.remove("hidden");
    isVisible = true;
    if (runId) currentRunId = runId;
    perceptionCache = {};
    map.invalidateSize();

    loadCoastlines();
    if (eraKey && eraKey !== currentEraKey) {
      loadBorders(eraKey);
    }

    if (playerView) {
      updateMarkers(playerView);
    }
  }

  function hide() {
    var container = document.getElementById("map-container");
    if (container) container.classList.add("hidden");
    isVisible = false;
  }

  function toggle(worldState, eraKey) {
    if (isVisible) {
      hide();
    } else {
      show(worldState, eraKey);
    }
  }

  return {
    init: init,
    show: show,
    hide: hide,
    toggle: toggle,
    updateMarkers: updateMarkers,
    isVisible: function () {
      return isVisible;
    },
  };
})();
