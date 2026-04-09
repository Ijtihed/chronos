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
  let regionCache = {};

  function init() {
    if (initialized) return;

    map = L.map("map", {
      center: [42, 15],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
      maxBoundsViscosity: 1.0,
    });

    map.getContainer().style.background = "#000000";
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
          color: "#27272a",
          weight: 1,
          opacity: 0.5,
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
            color: name ? "#3f3f46" : "#18181b",
            weight: name ? 1.2 : 0.5,
            opacity: name ? 0.6 : 0.25,
            fillColor: name ? "#18181b" : "#000000",
            fillOpacity: name ? 0.12 : 0.04,
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
            layer.on("click", function () {
              _showRegionKnowledge(name);
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
          '<span style="font-size:11px;color:#d4d4d8;">' +
          (pv.player_name || '') + '</span><br>' +
          '<span style="font-size:9px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.1em;">' +
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
        '<span style="font-size:11px;color:#d4d4d8;">' +
        npc.name + '</span><br>' +
        '<span style="font-size:9px;color:#71717a;text-transform:uppercase;letter-spacing:0.1em;">' +
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
        '<span style="font-size:11px;color:#d4d4d8;">' +
        knownNpc.name + '</span><br>' +
        '<span style="font-size:9px;color:#71717a;text-transform:uppercase;letter-spacing:0.1em;">' +
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
        '<div style="font-size:12px;color:#d4d4d8;max-width:280px;line-height:1.7;padding:4px;">' +
        perceptionCache[cacheKey] + '</div>',
        { className: "perception-popup", closeButton: false, maxWidth: 300 }
      ).openPopup();
      return;
    }
    marker.unbindPopup();
    marker.bindPopup(
      '<div style="font-size:10px;color:rgba(255,255,255,0.25);text-transform:uppercase;letter-spacing:0.1em;padding:4px;">thinking\u2026</div>',
      { className: "perception-popup", closeButton: false }
    ).openPopup();
    try {
      var res = await fetch("/api/run/" + currentRunId + "/npc/" + npc.id + "/perception");
      if (!res.ok) return;
      var data = await res.json();
      perceptionCache[cacheKey] = data.perception;
      marker.unbindPopup();
      marker.bindPopup(
        '<div style="font-size:12px;color:#d4d4d8;max-width:280px;line-height:1.7;padding:4px;">' +
        data.perception + '</div>',
        { className: "perception-popup", closeButton: false, maxWidth: 300 }
      ).openPopup();
    } catch (e) {}
  }

  function _esc(s) {
    if (!s) return "";
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function _showRegionPanel(data) {
    var panel = document.getElementById("region-panel");
    var overlay = document.getElementById("region-overlay");
    var title = document.getElementById("region-panel-title");
    var body = document.getElementById("region-panel-body");
    if (!panel || !body) return;

    title.textContent = data.polity_name;

    var h = "";

    if (data.known_facts && data.known_facts.length) {
      h += '<div class="region-section-label">Known</div>';
      for (var i = 0; i < data.known_facts.length; i++) {
        h += '<p class="region-fact">' + _esc(data.known_facts[i]) + '</p>';
      }
    }

    if (data.rumors && data.rumors.length) {
      h += '<div class="region-section-label">Rumors</div>';
      for (var j = 0; j < data.rumors.length; j++) {
        h += '<p class="region-rumor">' + _esc(data.rumors[j]) + '</p>';
      }
    }

    if (!data.known_facts.length && !data.rumors.length) {
      h += '<p class="region-fact" style="color:rgba(255,255,255,0.2);font-style:italic;">You know nothing of this place.</p>';
    }

    if (data.character_note) {
      h += '<div class="region-note">' + _esc(data.character_note) + '</div>';
    }

    body.innerHTML = h;
    panel.classList.remove("hidden");
    if (overlay) overlay.classList.remove("hidden");
  }

  function _closeRegionPanel() {
    var panel = document.getElementById("region-panel");
    var overlay = document.getElementById("region-overlay");
    if (panel) panel.classList.add("hidden");
    if (overlay) overlay.classList.add("hidden");
  }

  (function _initRegionPanelClose() {
    var panel = document.getElementById("region-panel");
    var overlay = document.getElementById("region-overlay");
    if (panel) {
      var closeBtn = panel.querySelector(".region-close");
      if (closeBtn) closeBtn.addEventListener("click", _closeRegionPanel);
    }
    if (overlay) overlay.addEventListener("click", _closeRegionPanel);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") _closeRegionPanel();
    });
  })();

  async function _showRegionKnowledge(polityName) {
    if (!currentRunId) return;

    var cacheKey = polityName + "_" + (Date.now() / 60000 | 0);
    if (regionCache[cacheKey]) {
      _showRegionPanel(regionCache[cacheKey]);
      return;
    }

    _showRegionPanel({
      polity_name: polityName,
      known_facts: [],
      rumors: [],
      character_note: "",
      _loading: true,
    });

    var body = document.getElementById("region-panel-body");
    if (body) body.innerHTML = '<span class="region-loading">Recalling what you know\u2026</span>';

    try {
      var res = await fetch("/api/run/" + currentRunId + "/region/" + encodeURIComponent(polityName));
      if (!res.ok) throw new Error();
      var data = await res.json();
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

  function show(playerView, eraKey, runId) {
    var container = document.getElementById("map-container");
    if (!container) return;

    init();
    container.classList.remove("hidden");
    isVisible = true;
    if (runId) currentRunId = runId;
    perceptionCache = {};
    regionCache = {};
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
