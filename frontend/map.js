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
    L.control.zoom({ position: "bottomright" }).addTo(map);
    initialized = true;
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

  function updateMarkers(worldState) {
    if (!map) return;

    if (playerMarker) {
      map.removeLayer(playerMarker);
      playerMarker = null;
    }
    npcMarkers.forEach(function (m) {
      map.removeLayer(m);
    });
    npcMarkers = [];

    var visitedLocs = worldState.visited_locations || [];
    var locations = worldState.locations || [];
    var runStatus = worldState.run_status;

    var playerLoc = null;
    for (var i = 0; i < locations.length; i++) {
      if (locations[i].id === worldState.player.location) {
        playerLoc = locations[i];
        break;
      }
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
        playerMarker.bindTooltip(worldState.player.name, {
          direction: "top",
          offset: [0, -10],
          opacity: 0.9,
        });
      }
    }

    var npcs = worldState.npcs || [];
    for (var n = 0; n < npcs.length; n++) {
      var npc = npcs[n];
      var npcLoc = null;
      for (var j = 0; j < locations.length; j++) {
        if (locations[j].id === npc.location) {
          npcLoc = locations[j];
          break;
        }
      }
      if (!npcLoc || !npcLoc.lat || !npcLoc.lon) continue;

      var visited = visitedLocs.indexOf(npc.location) !== -1;

      if (runStatus === "ended") continue;

      if (runStatus === "dead_observing" && npc.memory_of_player <= 0) {
        continue;
      }

      var markerClass = visited ? "marker-visited" : "marker-unvisited";
      var markerSize = visited ? 10 : 7;

      if (runStatus === "dead_observing") {
        var mem = npc.memory_of_player || 0;
        if (mem < 0.2) markerClass = "marker-faded";
      }

      var offset = (n * 0.003) % 0.01;
      var m = L.marker([npcLoc.lat + offset, npcLoc.lon + offset], {
        icon: makeIcon(markerClass, markerSize),
        zIndexOffset: visited ? 500 : 100,
      }).addTo(map);

      if (visited) {
        m.bindTooltip(npc.name + " \u2014 " + npc.role, {
          direction: "top",
          offset: [0, -8],
          opacity: 0.8,
        });
      }

      npcMarkers.push(m);
    }

    if (playerLoc && playerLoc.lat) {
      map.setView([playerLoc.lat, playerLoc.lon], map.getZoom(), {
        animate: true,
        duration: 0.8,
      });
    }
  }

  function show(worldState, eraKey) {
    var container = document.getElementById("map-container");
    if (!container) return;

    init();
    container.classList.remove("hidden");
    isVisible = true;
    map.invalidateSize();

    loadCoastlines();
    if (eraKey && eraKey !== currentEraKey) {
      loadBorders(eraKey);
    }

    if (worldState) {
      updateMarkers(worldState);
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
