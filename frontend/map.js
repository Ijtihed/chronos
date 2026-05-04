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
  let eventLayer = null;
  // Place-label layer (cities + small named regions). Opacity per
  // marker scales with current zoom; entries below their tier
  // threshold render fully transparent so they don't take pointer
  // events.
  let placeLayer = null;
  let placesData = null;
  let isVisible = false;
  let initialized = false;
  let currentEraKey = null;
  let currentRunId = null;
  let perceptionCache = {};
  let regionCache = {};
  // Most recent player coords; powers the "Recenter on player" button.
  let lastPlayerLatLng = null;
  // True only for the first marker placement of a given run, so the
  // implicit "auto-recenter on player" only fires once. After that
  // the user's pan/zoom (and the saved view) wins.
  let _firstMarkerPlacement = true;

  // Event-type colors — must stay in sync with the 8 types in
  // historical_events.type. Keys match DB values exactly.
  const EVENT_TYPE_COLORS = {
    war: "#dc2626",
    epidemic: "#16a34a",
    famine: "#ea580c",
    political: "#2563eb",
    religious: "#9333ea",
    economic: "#ca8a04",
    natural_disaster: "#78350f",
    cultural: "#71717a",
  };

  function _tierOpacity(tier) {
    if (tier === "witnessed" || tier === "known") return 1.0;
    if (tier === "rumor_reliable") return 0.7;
    if (tier === "rumor_unreliable") return 0.4;
    return 0.3;
  }

  // Per-era default view. Set on first loadBorders so resetView()
  // returns to the right starting frame for the current run's era.
  var defaultCenter = [42, 15];
  var defaultZoom = 5;
  var DEEP_ZOOM = 9;       // when zooming in on a single feature
  var REGION_ZOOM = 7;     // when zooming on a polity / region

  function _resolveViewKey() {
    return currentRunId ? ("chronos_map_view_" + currentRunId) : null;
  }

  function _saveViewState() {
    if (!map) return;
    var key = _resolveViewKey();
    if (!key) return;
    try {
      var c = map.getCenter();
      localStorage.setItem(
        key,
        JSON.stringify({ lat: c.lat, lng: c.lng, zoom: map.getZoom() }),
      );
    } catch (e) {}
  }

  function _loadViewState() {
    var key = _resolveViewKey();
    if (!key) return null;
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return null;
      var v = JSON.parse(raw);
      if (
        v &&
        typeof v.lat === "number" && isFinite(v.lat) &&
        typeof v.lng === "number" && isFinite(v.lng) &&
        typeof v.zoom === "number" && isFinite(v.zoom) &&
        v.lat >= -90 && v.lat <= 90 &&
        v.lng >= -360 && v.lng <= 360 &&
        v.zoom >= 0 && v.zoom <= 20
      ) {
        return v;
      }
      // Garbage in storage; remove so we don't keep tripping on it.
      localStorage.removeItem(key);
    } catch (e) {
      try { localStorage.removeItem(key); } catch (e2) {}
    }
    return null;
  }

  function _updateZoomHint() {
    var hint = document.getElementById("map-zoom-hint");
    if (!hint || !map) return;
    if (map.getZoom() > defaultZoom) {
      hint.classList.remove("hidden");
    } else {
      hint.classList.add("hidden");
    }
  }

  function init() {
    if (initialized) return;

    map = L.map("map", {
      center: defaultCenter,
      zoom: defaultZoom,
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

    var resetBtn = document.getElementById("map-reset");
    if (resetBtn) resetBtn.addEventListener("click", resetView);

    var centerBtn = document.getElementById("map-center-player");
    if (centerBtn) centerBtn.addEventListener("click", centerOnPlayer);

    // Legend toggle — flips a body class so CSS handles the visual
    // state. Persisted across sessions so the player's preference
    // survives reload (and run switches).
    var legendToggle = document.getElementById("map-legend-toggle");
    var legendLabel = document.getElementById("map-legend-toggle-label");
    if (legendToggle) {
      // Restore prior preference (default: visible).
      if (localStorage.getItem("chronos_map_legend_hidden") === "1") {
        document.body.classList.add("map-legend-hidden");
        if (legendLabel) legendLabel.textContent = "Show legend";
        legendToggle.setAttribute("aria-expanded", "false");
      }
      legendToggle.addEventListener("click", function () {
        var hidden = document.body.classList.toggle("map-legend-hidden");
        try {
          localStorage.setItem(
            "chronos_map_legend_hidden",
            hidden ? "1" : "0",
          );
        } catch (e) {}
        if (legendLabel) legendLabel.textContent = hidden ? "Show legend" : "Hide legend";
        legendToggle.setAttribute("aria-expanded", hidden ? "false" : "true");
      });
    }

    // Discoverability hint at the top of the map. Auto-fades after
    // the first interaction (any zoom or click) and on a 6-second
    // timer fallback so it doesn't linger forever for someone who
    // just stares at the map.
    var discoverHint = document.getElementById("map-discover-hint");
    var _hintTimer = null;
    var _hideHint = function () {
      if (!discoverHint) return;
      discoverHint.classList.add("is-hidden");
      if (_hintTimer) { clearTimeout(_hintTimer); _hintTimer = null; }
      // Remove from layout once the fade settles, so it doesn't
      // capture pointer events even at opacity 0 (it's
      // pointer-events:none anyway, but keep DOM clean).
      setTimeout(function () {
        if (discoverHint && discoverHint.classList.contains("is-hidden")) {
          discoverHint.style.display = "none";
        }
      }, 800);
    };
    if (discoverHint) {
      _hintTimer = setTimeout(_hideHint, 6000);
      map.once("click", _hideHint);
      map.once("zoomstart", _hideHint);
      map.once("dragstart", _hideHint);
    }

    // Esc resets the view while the map is the active overlay.
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!isVisible) return;
      if (
        document.activeElement &&
        (document.activeElement.tagName === "INPUT" ||
         document.activeElement.tagName === "TEXTAREA")
      ) return;
      resetView();
    });

    map.on("moveend zoomend", function () {
      _saveViewState();
      _updateZoomHint();
      _updatePlaceLabels();
      _restyleBorders();
      _updateZoomClass();
    });
  }

  // Apply a zoom-tier class to the map container so CSS can scale
  // marker sizes without needing to recreate Leaflet markers on each
  // zoom event. Three tiers: zoomed-out (default), zoomed-mid (+1..2),
  // zoomed-in (+3 or more).
  function _updateZoomClass() {
    if (!map) return;
    var c = map.getContainer();
    if (!c) return;
    var z = map.getZoom();
    var tier = "zoom-out";
    if (z >= defaultZoom + 3) tier = "zoom-in";
    else if (z >= defaultZoom + 1) tier = "zoom-mid";
    c.classList.remove("zoom-out", "zoom-mid", "zoom-in");
    c.classList.add(tier);
  }

  function _flyTo(lat, lon, zoom) {
    if (!map) return;
    map.flyTo([lat, lon], zoom != null ? zoom : DEEP_ZOOM, {
      animate: true,
      duration: 0.6,
    });
  }

  // True when the user has already moved past the era-default view —
  // either zoomed in or panned somewhere specific. Used to skip the
  // automatic "click also zooms" behavior so we don't yank them away
  // from a feature they're already inspecting.
  function _isUserNavigating() {
    if (!map) return false;
    return map.getZoom() > defaultZoom + 0.5;
  }

  function resetView() {
    if (!map) return;
    map.flyTo(defaultCenter, defaultZoom, { animate: true, duration: 0.5 });
  }

  function centerOnPlayer() {
    if (!map || !lastPlayerLatLng) return;
    map.flyTo(
      [lastPlayerLatLng.lat, lastPlayerLatLng.lon],
      Math.max(map.getZoom(), DEEP_ZOOM - 1),
      { animate: true, duration: 0.5 },
    );
  }

  async function loadCoastlines() {
    if (coastlineLayer) return;
    try {
      const resp = await fetch("/geo/coastlines.geojson");
      const data = await resp.json();
      coastlineLayer = L.geoJSON(data, {
        style: function () { return _coastlineStyle(); },
      }).addTo(map);
    } catch (e) {
      console.warn("Failed to load coastlines:", e);
    }
  }

  // ── Place labels (cities + small named regions) ────────────────────
  //
  // Opacity per label scales with current map zoom so the map shows
  // more detail as the player zooms in. Labels for tiny features
  // (radius_km <= 80, "city") fade in at zoom 6 and beyond. Mid-size
  // ("town") at zoom 7+, broad ("region") at zoom 5+. The layer is
  // populated once per session; per-zoom updates only restyle.

  function _placeOpacity(tier, zoom) {
    // Linear ramp from invisible -> 1.0 over 2 zoom levels.
    var threshold;
    if (tier === "city") threshold = 6;
    else if (tier === "town") threshold = 7;
    else threshold = 5;  // region
    if (zoom < threshold) return 0;
    if (zoom >= threshold + 2) return 1.0;
    return (zoom - threshold) / 2;
  }

  async function loadPlaceLabels() {
    if (placeLayer) return;
    try {
      var resp = await fetch("/api/geo/places/labels");
      if (!resp.ok) return;
      var data = await resp.json();
      placesData = data.places || [];
      placeLayer = L.layerGroup().addTo(map);
      placesData.forEach(function (p) {
        var icon = L.divIcon({
          className: "place-label place-label-" + p.tier,
          html: '<span>' + _esc(p.name) + '</span>',
          iconSize: [120, 14],
          iconAnchor: [60, 7],
        });
        var m = L.marker([p.lat, p.lon], {
          icon: icon,
          interactive: false,
          keyboard: false,
          zIndexOffset: -300,  // sit beneath polity tooltips/markers
        });
        m._placeTier = p.tier;
        m.addTo(placeLayer);
      });
      _updatePlaceLabels();
    } catch (e) {
      console.warn("Failed to load place labels:", e);
    }
  }

  function _updatePlaceLabels() {
    if (!placeLayer || !map) return;
    var z = map.getZoom();
    placeLayer.eachLayer(function (m) {
      var op = _placeOpacity(m._placeTier, z);
      var el = m.getElement();
      if (el) {
        el.style.opacity = String(op);
        // pointer-events off when invisible so labels never
        // intercept clicks meant for the polity / pin underneath.
        el.style.pointerEvents = op > 0.1 ? "" : "none";
      }
    });
  }

  // Coastlines + borders styling is zoom-dependent. Computed via
  // these helpers so loadCoastlines / loadBorders use the same logic
  // as the live zoomend handler.

  function _zoomScale(zoom) {
    // Normalized 0..1 from default zoom (5) to high zoom (10).
    var t = (zoom - defaultZoom) / 5;
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    return t;
  }

  function _coastlineStyle() {
    var z = map ? map.getZoom() : defaultZoom;
    var t = _zoomScale(z);
    return {
      color: "#3f3f46",
      weight: 0.8 + t * 1.4,           // 0.8 -> 2.2
      opacity: 0.45 + t * 0.4,          // 0.45 -> 0.85
      fill: false,
    };
  }

  function _borderStyle(feature) {
    var z = map ? map.getZoom() : defaultZoom;
    var t = _zoomScale(z);
    var name = feature.properties && feature.properties.NAME;
    return {
      color: name ? "#52525b" : "#27272a",
      weight: name ? (1.0 + t * 1.6) : (0.4 + t * 0.6),
      opacity: name ? (0.55 + t * 0.4) : (0.2 + t * 0.25),
      fillColor: name ? "#1f1f23" : "#000000",
      fillOpacity: name ? (0.10 + t * 0.16) : (0.04 + t * 0.04),
    };
  }

  function _restyleBorders() {
    if (borderLayer) {
      try {
        borderLayer.setStyle(function (feature) { return _borderStyle(feature); });
      } catch (e) {}
    }
    if (coastlineLayer) {
      try {
        coastlineLayer.setStyle(_coastlineStyle());
      } catch (e) {}
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
        style: function (feature) { return _borderStyle(feature); },
        onEachFeature: function (feature, layer) {
          const name = feature.properties && feature.properties.NAME;
          if (name) {
            layer.bindTooltip(name, {
              className: "polity-tooltip",
              direction: "center",
              permanent: false,
              opacity: 0.8,
            });
            layer.on("click", function (e) {
              if (L.DomEvent && e && e.originalEvent) {
                L.DomEvent.stopPropagation(e.originalEvent);
              }
              _showRegionKnowledge(name);
              if (_isUserNavigating()) return;
              try {
                map.flyToBounds(layer.getBounds(), {
                  padding: [40, 40],
                  maxZoom: REGION_ZOOM,
                  animate: true,
                  duration: 0.6,
                });
              } catch (err) {
                var c = layer.getBounds && layer.getBounds().getCenter();
                if (c) _flyTo(c.lat, c.lng, REGION_ZOOM);
              }
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
      lastPlayerLatLng = { lat: playerLoc.lat, lon: playerLoc.lon };
      playerMarker = L.marker([playerLoc.lat, playerLoc.lon], {
        icon: makeIcon(playerClass, playerSize),
        zIndexOffset: 1000,
      }).addTo(map);
      // Click on the player marker zooms in on it (unless the user
      // has already zoomed in — then we let them stay where they are).
      playerMarker.on("click", function (e) {
        if (L.DomEvent && e && e.originalEvent) {
          L.DomEvent.stopPropagation(e.originalEvent);
        }
        if (_isUserNavigating()) return;
        _flyTo(playerLoc.lat, playerLoc.lon, DEEP_ZOOM);
      });

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
      if (playerLoc && playerLoc.lat && _firstMarkerPlacement) {
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
        marker.on("click", function (e) {
          if (L.DomEvent && e && e.originalEvent) {
            L.DomEvent.stopPropagation(e.originalEvent);
          }
          _showPerception(npcRef, marker);
          // Auto-zoom only if we're at the era-default view. Once the
          // user has zoomed in we leave the camera alone.
          if (!_isUserNavigating()) {
            _flyTo(playerLoc.lat, playerLoc.lon, DEEP_ZOOM - 1);
          }
        });
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

    // Anonymous dots for unvisited locations with NPCs
    var unvisited = pv.unvisited_npc_counts || [];
    for (var u = 0; u < unvisited.length; u++) {
      var uv = unvisited[u];
      if (!uv.lat || !uv.lon) continue;
      var uvm = L.marker([uv.lat, uv.lon], {
        icon: makeIcon("marker-unvisited", 5),
        zIndexOffset: 100,
        interactive: false,
      }).addTo(map);
      npcMarkers.push(uvm);
    }

    if (playerLoc && playerLoc.lat && _firstMarkerPlacement) {
      map.setView([playerLoc.lat, playerLoc.lon], map.getZoom(), {
        animate: true,
        duration: 0.8,
      });
    }
    _firstMarkerPlacement = false;
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

  // ── Event markers ─────────────────────────────────────────────────
  //
  // Rendered as a dedicated L.layerGroup so we can clearLayers()
  // between turns without touching player/NPC markers.
  //
  // Design (2026-05-04):
  //   Always a pin at (ev.lat, ev.lon). No translucent area circles —
  //   they ballooned across the map for broad/rumor events and
  //   obscured everything underneath without telling you anything you
  //   couldn't read in the panel by clicking.
  //
  //   Tier is conveyed by:
  //     witnessed       -> full opacity pin + small white dot overlay
  //                        ("you were here", marker-event-witnessed)
  //     known           -> full opacity pin
  //     rumor_reliable  -> 70% opacity pin
  //     rumor_unreliable-> 40% opacity pin
  //
  //   For "broad" events (region-scale, no exact site), the backend
  //   gives us a centroid in (lat, lon). The pin sits there. The
  //   panel text is the place to communicate "this happened somewhere
  //   in this region", not a multi-thousand-km translucent disc.
  //
  // Color by event type from EVENT_TYPE_COLORS.

  function updateEventMarkers(events) {
    if (!map) return;
    if (!eventLayer) {
      eventLayer = L.layerGroup().addTo(map);
    }
    eventLayer.clearLayers();
    if (!events || !events.length) return;
    for (var i = 0; i < events.length; i++) {
      _addEventMarker(events[i]);
    }
  }

  function _addEventMarker(ev) {
    if (typeof ev.lat !== "number" || typeof ev.lon !== "number") return;
    var isWitnessed = ev.tier === "witnessed";

    var iconClass = "marker-event marker-event-" + (ev.type || "cultural");
    if (isWitnessed) iconClass += " marker-event-witnessed";

    var pin = L.marker([ev.lat, ev.lon], {
      icon: makeIcon(iconClass, 12),
      zIndexOffset: 200,
      opacity: _tierOpacity(ev.tier),
    }).addTo(eventLayer);

    pin.bindTooltip(_eventTooltip(ev), {
      direction: "top",
      offset: [0, -8],
      className: "npc-tooltip",
    });

    (function (evRef) {
      pin.on("click", function (e) {
        if (L.DomEvent && e && e.originalEvent) {
          L.DomEvent.stopPropagation(e.originalEvent);
        }
        _showEventPanel(evRef);
        if (_isUserNavigating()) return;
        // Broad events have no precise site, so don't slam the camera
        // all the way to DEEP_ZOOM — that's misleading.
        var z = evRef.broad ? REGION_ZOOM : DEEP_ZOOM;
        _flyTo(evRef.lat, evRef.lon, z);
      });
    })(ev);
  }

  function _eventTooltip(ev) {
    var year = ev.year + " AD";
    var type = (ev.type || "").toUpperCase();
    return (
      '<span style="font-size:11px;color:#d4d4d8;">' + year + " — " + type + "</span>" +
      '<br><span style="font-size:9px;color:#a1a1aa;">' + _esc(ev.summary.substring(0, 80)) + "</span>"
    );
  }

  async function _loadEventsForRun(runId) {
    if (!runId) return;
    try {
      var res = await fetch("/api/run/" + runId + "/events/visible");
      if (!res.ok) return;
      var data = await res.json();
      // Guard against stale fetches across run switches.
      if (data.era_key && currentEraKey && data.era_key !== currentEraKey) {
        return;
      }
      updateEventMarkers(data.events || []);
    } catch (e) {
      console.warn("events/visible fetch failed:", e);
    }
  }

  function _showEventPanel(ev) {
    // Reuse the region panel DOM — same container, different content.
    // Region click handlers bind no state; simply re-rendering the
    // body with event-shaped data is safe.
    var panel = document.getElementById("region-panel");
    var overlay = document.getElementById("region-overlay");
    var title = document.getElementById("region-panel-title");
    var body = document.getElementById("region-panel-body");
    if (!panel || !body) return;

    if (title) title.textContent = ev.year + " AD — " + (ev.region || "unknown region");

    // Tier is implicit from the marker the user just clicked for
    // known/witnessed — we omit it. Show "RUMORED" only for rumor
    // tiers where the uncertainty matters to the reader.
    var metaParts = [];
    if (ev.type) metaParts.push(ev.type.toUpperCase().replace(/_/g, " "));
    if (ev.significance) metaParts.push(ev.significance.toUpperCase());
    if (ev.tier === "rumor_reliable" || ev.tier === "rumor_unreliable") {
      metaParts.push("RUMORED");
    }
    var meta = metaParts.join(" • ");

    var h = '<div class="region-section-label event-meta">' + _esc(meta) + "</div>";
    h += '<p class="region-fact">' + _esc(ev.summary) + "</p>";

    body.innerHTML = h;
    panel.classList.remove("hidden");
    if (overlay) overlay.classList.remove("hidden");
  }

  function show(playerView, eraKey, runId) {
    var container = document.getElementById("map-container");
    if (!container) return;

    init();
    container.classList.remove("hidden");
    isVisible = true;
    if (runId && runId !== currentRunId) {
      _firstMarkerPlacement = true;
    }
    if (runId) currentRunId = runId;
    perceptionCache = {};
    regionCache = {};
    map.invalidateSize();

    loadCoastlines();
    loadPlaceLabels();
    if (eraKey && eraKey !== currentEraKey) {
      loadBorders(eraKey);
    }
    _restyleBorders();
    _updatePlaceLabels();
    _updateZoomClass();

    // Restore prior pan/zoom if this run has been viewed before.
    // Done BEFORE updateMarkers so the marker code can see we have a
    // saved view (via _firstMarkerPlacement) and skip its
    // auto-recenter on the player.
    var saved = _loadViewState();
    if (saved) {
      map.setView([saved.lat, saved.lng], saved.zoom, { animate: false });
      _firstMarkerPlacement = false;
    }

    if (playerView) {
      updateMarkers(playerView);
    }
    _loadEventsForRun(currentRunId);
    _updateZoomHint();
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

  // Combined refresh: player/NPC markers plus event markers.
  // Callers use this from the per-turn hooks in app.js so the map
  // stays consistent without duplicating the fetch call everywhere.
  function refresh(playerView, runIdArg) {
    if (runIdArg) currentRunId = runIdArg;
    if (playerView) updateMarkers(playerView);
    _loadEventsForRun(currentRunId);
  }

  return {
    init: init,
    show: show,
    hide: hide,
    toggle: toggle,
    updateMarkers: updateMarkers,
    updateEventMarkers: updateEventMarkers,
    refresh: refresh,
    isVisible: function () {
      return isVisible;
    },
  };
})();
