/**
 * CHRONOS Connections — player-centric NPC interaction graph.
 *
 * d3-force visualization of npc.player_interactions + state.events.
 * Read-only snapshot fetched from /api/run/{run_id}/interaction_graph
 * each time the page is opened; no live updates while open.
 *
 * Player node: large amber-gold, fixed at center.
 * NPC nodes: smaller, colored by disposition bucket.
 *   warming/engaged          -> emerald-500   (#10b981)
 *   commanding/fervent/...   -> zinc-300      (#d4d4d8)  cool/distant
 *   neutral/cautious         -> zinc-400      (#a1a1aa)
 *   wary/guarded/grim/...    -> amber-500     (#f59e0b)
 *   fearful                  -> blue-400      (#60a5fa)
 *   hostile                  -> red-500       (#ef4444)
 *
 * Edges:
 *   color  - sentiment of most recent interaction
 *   width  - 1 + count*1.5, capped at 8
 *
 * Drag: pin where dropped (fx/fy retained). Reset Layout button
 * clears all pins and re-runs the simulation.
 */

const ChronosGraph = (function () {
  // ---- Constants ---------------------------------------------------

  const DISPOSITION_COLORS = {
    warming: "#10b981", engaged: "#10b981",
    commanding: "#d4d4d8", fervent: "#d4d4d8",
    formal: "#d4d4d8", reserved: "#d4d4d8",
    neutral: "#a1a1aa", cautious: "#a1a1aa",
    wary: "#f59e0b", guarded: "#f59e0b",
    grim: "#f59e0b", suspicious: "#f59e0b",
    fearful: "#60a5fa",
    hostile: "#ef4444",
  };
  const DISPOSITION_FALLBACK = "#52525b";
  const PLAYER_COLOR = "#fbbf24";

  const SENTIMENT_EDGE = {
    positive: { stroke: "#10b981", opacity: 0.5 },
    negative: { stroke: "#ef4444", opacity: 0.6 },
    neutral:  { stroke: "#71717a", opacity: 0.4 },
  };

  const PLAYER_RADIUS = 22;
  const NPC_RADIUS_MIN = 10;
  const NPC_RADIUS_MAX = 16;

  const EDGE_BASE = 1.0;
  const EDGE_PER_INTERACTION = 1.5;
  const EDGE_MAX = 8;

  // NPC<->NPC "witnessed-together" edges. Visually distinct from
  // player edges: dashed, thinner, slate hue (different from the zinc
  // used for neutral disposition so they don't blend at endpoints).
  // Legibility tuning notes (apr 2026): bumped width floor 0.8 -> 2.0
  // so a single shared turn still reads from 30+ inches; bumped
  // opacity 0.35 -> 0.55 to compensate for dashed-line ink loss; dash
  // pattern shifted to longer dashes & shorter gaps for the same
  // reason. Color shifted slightly bluer (slate-300) to peel away
  // from the neutral-zinc node fill.
  // Width tuning: floor 2 px (legible), cap 4 px (noticeably thinner
  // than even a 2-interaction player edge at 4 px so the player edge
  // hierarchy is preserved). Dashed pattern + slate hue carry the
  // semantic "this is a different kind of edge" load.
  const NPC_LINK_COLOR = "#cbd5e1";        // slate-300
  const NPC_LINK_OPACITY = 0.55;
  const NPC_LINK_BASE_WIDTH = 2.0;
  const NPC_LINK_PER_WEIGHT = 0.5;
  const NPC_LINK_MAX_WIDTH = 4.0;
  const NPC_LINK_DASH = "5 3";

  // ---- State -------------------------------------------------------

  let visible = false;
  let svg = null;
  let svgEl = null;
  let simulation = null;
  let lastData = null;
  let nodesGroup = null;
  let edgesGroup = null;
  let npcLinksGroup = null;
  // Wrapper <g> that receives the d3-zoom transform. Everything else
  // (nodes, edges, npc-links) is appended inside it so pan/zoom moves
  // the whole graph as a unit.
  let zoomLayer = null;
  let zoomBehavior = null;
  // Active run id for namespaced localStorage; set by show().
  let currentRunId = null;
  let resizeObserver = null;
  let initialized = false;

  // ---- Helpers -----------------------------------------------------

  function _esc(s) {
    if (s === null || s === undefined) return "";
    var d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }

  function _dispositionColor(disp) {
    var d = (disp || "").toLowerCase();
    return DISPOSITION_COLORS[d] || DISPOSITION_FALLBACK;
  }

  function _npcRadius(memoryOfPlayer) {
    var m = Math.max(0, Math.min(1, Number(memoryOfPlayer) || 0));
    return NPC_RADIUS_MIN + (NPC_RADIUS_MAX - NPC_RADIUS_MIN) * m;
  }

  function _edgeWidth(count) {
    var n = Math.max(0, Number(count) || 0);
    return Math.min(EDGE_MAX, EDGE_BASE + n * EDGE_PER_INTERACTION);
  }

  function _npcLinkWidth(weight) {
    var n = Math.max(0, Number(weight) || 0);
    return Math.min(NPC_LINK_MAX_WIDTH, NPC_LINK_BASE_WIDTH + n * NPC_LINK_PER_WEIGHT);
  }

  function _mostRecentSentiment(interactions) {
    if (!interactions || !interactions.length) return "neutral";
    return interactions[interactions.length - 1].sentiment || "neutral";
  }

  function _formatActionType(at) {
    if (!at) return "";
    return String(at).toUpperCase().replace(/_/g, " ");
  }

  // ---- DOM init ----------------------------------------------------

  function init() {
    if (initialized) return;
    svgEl = document.getElementById("graph-canvas");
    if (!svgEl) return;

    // Validate the d3 surface we depend on. If any of these is missing
    // the page renders nothing meaningful, so fail loudly rather than
    // silently produce a top-left node cluster.
    var d3Missing = [];
    if (typeof d3 === "undefined") {
      d3Missing.push("d3 global");
    } else {
      ["select", "drag", "forceSimulation", "forceLink", "forceManyBody",
       "forceCenter", "forceCollide"].forEach(function (sym) {
        if (typeof d3[sym] !== "function") d3Missing.push("d3." + sym);
      });
    }
    if (d3Missing.length) {
      console.error("ChronosGraph: missing d3 symbols:", d3Missing.join(", "));
      return;
    }

    svg = d3.select(svgEl);
    // Render order matters: NPC<->NPC links sit underneath, then
    // player<->NPC edges, then nodes on top. All inside zoomLayer so
    // pan/zoom transforms the whole graph as one.
    zoomLayer = svg.append("g").attr("class", "graph-zoom-layer");
    npcLinksGroup = zoomLayer.append("g").attr("class", "graph-npc-links");
    edgesGroup = zoomLayer.append("g").attr("class", "graph-edges");
    nodesGroup = zoomLayer.append("g").attr("class", "graph-nodes");

    // d3-zoom: scroll-wheel zoom + drag-pan. Skips when the gesture
    // started on a node (so node-drag still works).
    if (typeof d3.zoom === "function") {
      zoomBehavior = d3.zoom()
        .scaleExtent([0.4, 4])
        .filter(function (event) {
          // Allow wheel anywhere; pan only from background, not nodes.
          if (event.type === "wheel") return true;
          var t = event.target;
          // Walk up to see if the gesture started on a node.
          while (t && t !== svgEl) {
            if (t.classList && t.classList.contains("graph-node")) {
              return false;
            }
            t = t.parentNode;
          }
          return true;
        })
        .on("zoom", function (event) {
          zoomLayer.attr("transform", event.transform);
          _saveViewState(event.transform);
        });
      svg.call(zoomBehavior);
      // Disable d3-zoom's default double-click handler — we use it
      // for "focus on this node" instead.
      svg.on("dblclick.zoom", null);
    }

    // Click on background closes the side panel.
    svg.on("click", function (event) {
      if (event.target === svgEl || event.target.tagName === "g") {
        _hideSidePanel();
        _hideTooltip();
      }
    });

    var resetBtn = document.getElementById("btn-graph-reset");
    if (resetBtn) resetBtn.addEventListener("click", resetView);

    var sideClose = document.getElementById("graph-side-close");
    if (sideClose) sideClose.addEventListener("click", _hideSidePanel);

    // NPC list sidebar — per-row click handlers are wired in
    // _renderNpcList() because rows depend on the current data.
    var listToggle = document.getElementById("btn-graph-list-toggle");
    if (listToggle) listToggle.addEventListener("click", _toggleNpcList);

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(function () {
        if (visible && simulation) _onResize();
      });
      resizeObserver.observe(svgEl);
    } else {
      window.addEventListener("resize", function () {
        if (visible && simulation) _onResize();
      });
    }

    initialized = true;
  }

  // ---- Simulation lifecycle ----------------------------------------

  function _viewportCenter() {
    var rect = svgEl.getBoundingClientRect();
    var w = rect.width, h = rect.height;
    // First-frame fallback: the parent container was just un-hidden and
    // hasn't laid out yet. Use the viewport minus the top bar (40px) and
    // the graph header (36px) as a defensible fallback so nodes don't
    // pile up at (0, 0).
    if (w < 50 || h < 50) {
      w = window.innerWidth || 1024;
      h = (window.innerHeight || 768) - 40 - 36;
    }
    return { cx: w / 2, cy: h / 2 };
  }

  function _onResize() {
    var c = _viewportCenter();
    var nodes = simulation.nodes();
    if (nodes.length && nodes[0].id === "__player__") {
      nodes[0].fx = c.cx;
      nodes[0].fy = c.cy;
    }
    simulation.force("center", d3.forceCenter(c.cx, c.cy));
    simulation.alpha(0.3).restart();
  }

  function _buildModel(data) {
    var c = _viewportCenter();
    var savedPins = _loadPinsState() || {};
    var nodes = [{
      id: "__player__",
      kind: "player",
      label: data.player.name,
      role: data.player.role,
      archetype: data.player.archetype,
      fx: c.cx,
      fy: c.cy,
      r: PLAYER_RADIUS,
      color: PLAYER_COLOR,
    }];
    var links = [];

    (data.nodes || []).forEach(function (n) {
      var sentiment = _mostRecentSentiment(n.interactions);
      var pin = savedPins[n.id];
      var node = {
        id: n.id,
        kind: "npc",
        label: n.name,
        archetype: n.archetype,
        role: n.role,
        disposition: n.disposition,
        memory_of_player: n.memory_of_player,
        memory_label: n.memory_label,
        last_interaction_turn: n.last_interaction_turn,
        interactions: n.interactions,
        interaction_count: n.interaction_count,
        r: _npcRadius(n.memory_of_player),
        color: _dispositionColor(n.disposition),
      };
      if (pin && typeof pin.fx === "number" && typeof pin.fy === "number") {
        node.fx = pin.fx;
        node.fy = pin.fy;
        node.x = pin.fx;
        node.y = pin.fy;
      }
      nodes.push(node);
      links.push({
        source: "__player__",
        target: n.id,
        count: n.interaction_count,
        sentiment: sentiment,
        width: _edgeWidth(n.interaction_count),
      });
    });

    var npcLinks = (data.npc_links || []).map(function (l) {
      return {
        source: l.source,
        target: l.target,
        weight: l.weight,
        shared_turns: l.shared_turns || [],
        width: _npcLinkWidth(l.weight),
      };
    });

    return { nodes: nodes, links: links, npcLinks: npcLinks };
  }

  function updateGraph(data) {
    if (!initialized) init();
    if (!initialized) return;
    lastData = data;

    var hasNpcs = (data.nodes || []).length > 0;

    // Empty state: show ONLY the centered "no connections" message.
    // Hide the canvas, legend, NPC list panel, side panel, and the
    // header's right-side buttons. Title shows just the year + name.
    _setEmptyMode(!hasNpcs);

    edgesGroup.selectAll("*").remove();
    nodesGroup.selectAll("*").remove();
    if (npcLinksGroup) npcLinksGroup.selectAll("*").remove();
    _hideSidePanel();
    _hideTooltip();

    var titleYear = document.getElementById("graph-title-year");
    var titleName = document.getElementById("graph-title-name");
    if (titleYear) titleYear.textContent = (data.year || "") + " AD";
    if (titleName) titleName.textContent = (data.player && data.player.name) || "";

    if (simulation) {
      simulation.stop();
      simulation = null;
    }

    if (!hasNpcs) {
      // Empty: skip all simulation/list rendering. The empty-state
      // overlay is the only thing visible.
      return;
    }

    var model = _buildModel(data);

    var c = _viewportCenter();

    var linkSel = edgesGroup.selectAll("line")
      .data(model.links, function (d) { return d.target; })
      .enter()
      .append("line")
      .attr("class", "graph-edge")
      .attr("stroke", function (d) { return SENTIMENT_EDGE[d.sentiment].stroke; })
      .attr("stroke-opacity", function (d) { return SENTIMENT_EDGE[d.sentiment].opacity; })
      .attr("stroke-width", function (d) { return d.width; })
      .attr("stroke-linecap", "round")
      .style("cursor", "pointer")
      .on("mouseenter", function (event, d) { _showEdgeTooltip(event, d); })
      .on("mousemove", function (event, d) { _showEdgeTooltip(event, d); })
      .on("mouseleave", _hideTooltip)
      .on("click", function (event, d) {
        event.stopPropagation();
        _hideTooltip();
        _showSidePanelForNpc(_findNpcByLink(d, model));
      });

    var npcLinkSel = npcLinksGroup.selectAll("line")
      .data(model.npcLinks, function (d) { return d.source + "::" + d.target; })
      .enter()
      .append("line")
      .attr("class", "graph-npc-link")
      .attr("stroke", NPC_LINK_COLOR)
      .attr("stroke-opacity", NPC_LINK_OPACITY)
      .attr("stroke-width", function (d) { return d.width; })
      .attr("stroke-dasharray", NPC_LINK_DASH)
      .attr("stroke-linecap", "round")
      .style("cursor", "default")
      .on("mouseenter", function (event, d) { _showNpcLinkTooltip(event, d); })
      .on("mousemove", function (event, d) { _showNpcLinkTooltip(event, d); })
      .on("mouseleave", _hideTooltip);

    var nodeSel = nodesGroup.selectAll("g")
      .data(model.nodes, function (d) { return d.id; })
      .enter()
      .append("g")
      .attr("class", function (d) {
        var cls = "graph-node graph-node-" + (d.kind || "npc");
        // Soft glow on vivid-memory NPCs — visually obvious "they
        // remember you well" cue for new players.
        if (d.kind === "npc" && (d.memory_label === "vivid")) {
          cls += " graph-node-vivid";
        }
        return cls;
      })
      .style("cursor", function (d) {
        return d.kind === "player" ? "default" : "pointer";
      });

    nodeSel.append("circle")
      .attr("r", function (d) { return d.r; })
      .attr("fill", function (d) { return d.color; })
      .attr("stroke", "rgba(0,0,0,0.55)")
      .attr("stroke-width", function (d) { return d.kind === "player" ? 2 : 1.2; });

    nodeSel.append("text")
      .text(function (d) { return d.label; })
      .attr("class", "graph-node-label")
      .attr("text-anchor", "middle")
      .attr("dy", function (d) { return d.r + 12; });

    nodeSel.filter(function (d) { return d.kind === "npc"; })
      .on("click", function (event, d) {
        event.stopPropagation();
        _showSidePanelForNpc(d);
      })
      .call(d3.drag()
        .on("start", _dragStart)
        .on("drag", _dragged)
        .on("end", _dragEnd));

    // Combine player edges + NPC<->NPC edges into a single forceLink
    // so d3 maintains both as constraints. We tag each link by kind so
    // distance/strength can differ.
    var allLinks = model.links.concat(model.npcLinks.map(function (l) {
      return Object.assign({ kind: "npc" }, l);
    }));
    model.links.forEach(function (l) { l.kind = "player"; });

    simulation = d3.forceSimulation(model.nodes)
      .force("link", d3.forceLink(allLinks)
        .id(function (d) { return d.id; })
        .distance(function (d) {
          if (d.kind === "npc") {
            // NPCs sharing turns sit closer to each other.
            return Math.max(50, 140 - 20 * Math.min(5, d.weight || 1));
          }
          var pull = 30 * Math.min(5, d.count || 1);
          return Math.max(60, 180 - pull);
        })
        .strength(function (d) {
          return d.kind === "npc" ? 0.25 : 0.6;
        }))
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(c.cx, c.cy))
      .force("collide", d3.forceCollide().radius(function (d) { return d.r + 6; }))
      .alpha(1.0)
      .alphaDecay(0.03)
      .on("tick", function () {
        linkSel
          .attr("x1", function (d) { return d.source.x; })
          .attr("y1", function (d) { return d.source.y; })
          .attr("x2", function (d) { return d.target.x; })
          .attr("y2", function (d) { return d.target.y; });
        npcLinkSel
          .attr("x1", function (d) { return d.source.x; })
          .attr("y1", function (d) { return d.source.y; })
          .attr("x2", function (d) { return d.target.x; })
          .attr("y2", function (d) { return d.target.y; });
        nodeSel.attr("transform", function (d) {
          return "translate(" + d.x + "," + d.y + ")";
        });
      });

    // Auto-select the most-interacted NPC so the side panel populates
    // immediately as a worked example.
    var npcsByCount = model.nodes
      .filter(function (n) { return n.kind === "npc"; })
      .slice()
      .sort(function (a, b) {
        return (b.interaction_count || 0) - (a.interaction_count || 0);
      });
    if (npcsByCount.length) {
      _showSidePanelForNpc(npcsByCount[0]);
    }

    // Render the per-run NPC list sidebar.
    _renderNpcList(npcsByCount);

    // Restore the persisted zoom transform if any. Done after the
    // simulation is up so the layout has nodes to anchor to.
    var savedView = _loadViewState();
    if (savedView && zoomBehavior && svg) {
      svg.call(
        zoomBehavior.transform,
        d3.zoomIdentity.translate(savedView.x, savedView.y).scale(savedView.k),
      );
    }
  }

  function _findNpcByLink(link, model) {
    var targetId = (link.target && link.target.id) || link.target;
    for (var i = 0; i < model.nodes.length; i++) {
      if (model.nodes[i].id === targetId) return model.nodes[i];
    }
    return null;
  }

  // Toggle the entire graph UI between "empty" and "populated" mode.
  // In empty mode only the centered #graph-empty message is visible —
  // canvas, legend, NPC list panel, header buttons, and side panel
  // are all hidden so there is nothing else on screen for a player
  // who has not yet engaged with anyone.
  function _setEmptyMode(empty) {
    var emptyEl = document.getElementById("graph-empty");
    var canvas = document.getElementById("graph-canvas");
    var legend = document.getElementById("graph-legend");
    var listPanel = document.getElementById("graph-npc-list-panel");
    var listToggle = document.getElementById("btn-graph-list-toggle");
    var resetBtn = document.getElementById("btn-graph-reset");
    var sidePanel = document.getElementById("graph-side-panel");

    if (emptyEl) {
      if (empty) emptyEl.classList.remove("hidden");
      else emptyEl.classList.add("hidden");
    }
    if (canvas) {
      // Hide the SVG entirely in empty mode so there is no visible
      // canvas / lone player node behind the message.
      canvas.style.visibility = empty ? "hidden" : "";
    }
    if (legend) legend.classList.toggle("hidden", !!empty);
    if (listPanel) listPanel.classList.toggle("hidden", !!empty);
    if (listToggle) listToggle.classList.toggle("hidden", !!empty);
    if (resetBtn) resetBtn.classList.toggle("hidden", !!empty);
    if (sidePanel && empty) sidePanel.classList.add("hidden");
  }

  // ---- Drag handlers ----------------------------------------------

  function _dragStart(event, d) {
    if (!simulation) return;
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function _dragged(event, d) {
    if (!simulation) return;
    d.fx = event.x;
    d.fy = event.y;
  }

  function _dragEnd(event, d) {
    if (!simulation) return;
    if (!event.active) simulation.alphaTarget(0);
    // Pin where dropped — keep fx/fy set. Player remains pinned at center.
    _savePinsState();
  }

  // ---- Persistence (per-run) --------------------------------------
  //
  // Two pieces of state are saved per run:
  //   - chronos_graph_pins_<runId>      { id -> { fx, fy } }
  //   - chronos_graph_view_<runId>      { x, y, k }   (zoom transform)
  // Restored in updateGraph() before the simulation starts so the
  // graph appears as the player left it.

  function _pinsKey() {
    return currentRunId ? ("chronos_graph_pins_" + currentRunId) : null;
  }

  function _viewKey() {
    return currentRunId ? ("chronos_graph_view_" + currentRunId) : null;
  }

  function _savePinsState() {
    var key = _pinsKey();
    if (!key || !simulation) return;
    var out = {};
    simulation.nodes().forEach(function (d) {
      if (d.kind === "npc" && d.fx != null && d.fy != null) {
        out[d.id] = { fx: d.fx, fy: d.fy };
      }
    });
    try { localStorage.setItem(key, JSON.stringify(out)); } catch (e) {}
  }

  function _loadPinsState() {
    var key = _pinsKey();
    if (!key) return null;
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") {
        localStorage.removeItem(key);
        return null;
      }
      // Only keep entries with finite numeric fx/fy.
      var clean = {};
      Object.keys(parsed).forEach(function (k) {
        var p = parsed[k];
        if (
          p && typeof p.fx === "number" && isFinite(p.fx) &&
          typeof p.fy === "number" && isFinite(p.fy)
        ) {
          clean[k] = { fx: p.fx, fy: p.fy };
        }
      });
      return Object.keys(clean).length ? clean : null;
    } catch (e) {
      try { localStorage.removeItem(key); } catch (e2) {}
      return null;
    }
  }

  function _saveViewState(transform) {
    var key = _viewKey();
    if (!key || !transform) return;
    try {
      localStorage.setItem(
        key,
        JSON.stringify({ x: transform.x, y: transform.y, k: transform.k }),
      );
    } catch (e) {}
  }

  function _loadViewState() {
    var key = _viewKey();
    if (!key) return null;
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return null;
      var v = JSON.parse(raw);
      if (
        v &&
        typeof v.x === "number" && isFinite(v.x) &&
        typeof v.y === "number" && isFinite(v.y) &&
        typeof v.k === "number" && isFinite(v.k) &&
        v.k > 0.1 && v.k < 10
      ) {
        return v;
      }
      localStorage.removeItem(key);
    } catch (e) {
      try { localStorage.removeItem(key); } catch (e2) {}
    }
    return null;
  }

  function _clearPersistedState() {
    var pk = _pinsKey();
    var vk = _viewKey();
    try {
      if (pk) localStorage.removeItem(pk);
      if (vk) localStorage.removeItem(vk);
    } catch (e) {}
  }

  // ---- Reset / focus ----------------------------------------------

  function resetView() {
    if (!simulation) return;
    var c = _viewportCenter();
    simulation.nodes().forEach(function (d) {
      if (d.kind === "player") {
        d.fx = c.cx;
        d.fy = c.cy;
      } else {
        d.fx = null;
        d.fy = null;
      }
    });
    // Reset zoom transform to identity.
    if (zoomBehavior && svg) {
      svg.transition().duration(300).call(zoomBehavior.transform, d3.zoomIdentity);
    }
    _clearPersistedState();
    // Clear focus ring + active row in the NPC list.
    if (nodesGroup) {
      nodesGroup.selectAll(".graph-node").classed("graph-node-focused", false);
    }
    var listEl = document.getElementById("graph-npc-list");
    if (listEl) {
      Array.prototype.forEach.call(
        listEl.querySelectorAll(".graph-list-row-active"),
        function (r) { r.classList.remove("graph-list-row-active"); },
      );
    }
    simulation.alpha(1.0).restart();
  }

  function focusOnNpc(npcId) {
    if (!simulation || !zoomBehavior || !svg) return;
    var node = simulation.nodes().find(function (n) { return n.id === npcId; });
    if (!node) return;
    var c = _viewportCenter();
    // Compute a zoom transform that puts the node at the viewport
    // center at scale 1.6 (mild zoom, keeps neighborhood visible).
    var k = 1.6;
    var tx = c.cx - node.x * k;
    var ty = c.cy - node.y * k;
    svg.transition()
      .duration(450)
      .call(
        zoomBehavior.transform,
        d3.zoomIdentity.translate(tx, ty).scale(k),
      );
    _showSidePanelForNpc(node);
    _highlightNpc(npcId);
  }

  function _highlightNpc(npcId) {
    if (!nodesGroup) return;
    nodesGroup.selectAll(".graph-node")
      .classed("graph-node-focused", function (d) { return d && d.id === npcId; });
  }

  // ---- NPC list sidebar ------------------------------------------

  function _renderNpcList(npcsByCount) {
    var listEl = document.getElementById("graph-npc-list");
    var countEl = document.getElementById("graph-npc-count");
    if (!listEl) return;
    if (countEl) countEl.textContent = String(npcsByCount.length);

    if (!npcsByCount.length) {
      listEl.innerHTML =
        '<div class="graph-list-empty">No connections yet. Speak or do something to someone.</div>';
      return;
    }

    var html = "";
    for (var i = 0; i < npcsByCount.length; i++) {
      var n = npcsByCount[i];
      var sentiment = _mostRecentSentiment(n.interactions);
      var sentClass = "graph-list-sent-" + sentiment;
      var disp = (n.disposition || "").toLowerCase();
      var color = _dispositionColor(disp);
      html +=
        '<button class="graph-list-row ' + sentClass + '" data-npc-id="' +
          _esc(n.id) + '">' +
          '<span class="graph-list-dot" style="background:' + color + '"></span>' +
          '<span class="graph-list-name">' + _esc(n.label) + '</span>' +
          '<span class="graph-list-meta">' + _esc(n.interaction_count) +
          (n.memory_label === "vivid" ? '<span class="graph-list-vivid" title="Remembers you vividly">\u25CF</span>' : '') +
          '</span>' +
        '</button>';
    }
    listEl.innerHTML = html;

    // Wire row clicks.
    Array.prototype.forEach.call(
      listEl.querySelectorAll(".graph-list-row"),
      function (el) {
        el.addEventListener("click", function () {
          var id = el.getAttribute("data-npc-id");
          if (id) focusOnNpc(id);
          // Also set the active state on the row.
          Array.prototype.forEach.call(
            listEl.querySelectorAll(".graph-list-row"),
            function (r) { r.classList.remove("graph-list-row-active"); },
          );
          el.classList.add("graph-list-row-active");
        });
      },
    );
  }

  function _toggleNpcList() {
    var aside = document.getElementById("graph-npc-list-panel");
    if (!aside) return;
    aside.classList.toggle("collapsed");
    var btn = document.getElementById("btn-graph-list-toggle");
    if (btn) {
      btn.textContent = aside.classList.contains("collapsed")
        ? "Show list" : "Hide list";
    }
  }

  // ---- Tooltip + side panel ---------------------------------------

  function _showEdgeTooltip(event, link) {
    var npc = _findNpcByLink(link, { nodes: simulation ? simulation.nodes() : [] });
    if (!npc) return;
    var tip = document.getElementById("graph-tooltip");
    if (!tip) return;

    var last = (npc.interactions && npc.interactions.length)
      ? npc.interactions[npc.interactions.length - 1]
      : null;
    var html =
      '<div class="gtt-name">' + _esc(npc.label) + '</div>' +
      '<div class="gtt-meta">' +
        _esc(npc.interaction_count) +
        ' interaction' + (npc.interaction_count === 1 ? '' : 's') +
      '</div>';
    if (last) {
      html += '<div class="gtt-last">' +
        'Last: turn ' + _esc(last.turn) +
        ' &middot; ' + _esc(_formatActionType(last.action_type)) +
        (last.intent ? ' &mdash; ' + _esc(last.intent) : '') +
        '</div>';
    }
    tip.innerHTML = html;
    tip.classList.remove("hidden");
    tip.style.left = (event.clientX + 14) + "px";
    tip.style.top = (event.clientY + 14) + "px";
  }

  function _showNpcLinkTooltip(event, link) {
    var nodes = simulation ? simulation.nodes() : [];
    var src = null, tgt = null;
    for (var i = 0; i < nodes.length; i++) {
      var nid = nodes[i].id;
      var lsrc = (link.source && link.source.id) || link.source;
      var ltgt = (link.target && link.target.id) || link.target;
      if (nid === lsrc) src = nodes[i];
      if (nid === ltgt) tgt = nodes[i];
    }
    if (!src || !tgt) return;
    var tip = document.getElementById("graph-tooltip");
    if (!tip) return;
    var turns = (link.shared_turns || []).join(", ");
    var html =
      '<div class="gtt-name">' + _esc(src.label) + ' &nbsp;\u00b7\u00b7\u00b7\u00b7\u00b7&nbsp; ' + _esc(tgt.label) + '</div>' +
      '<div class="gtt-meta">Witnessed together</div>' +
      '<div class="gtt-last">' +
        (link.shared_turns.length === 1 ? 'Turn ' : 'Turns ') + _esc(turns) +
      '</div>';
    tip.innerHTML = html;
    tip.classList.remove("hidden");
    tip.style.left = (event.clientX + 14) + "px";
    tip.style.top = (event.clientY + 14) + "px";
  }

  function _hideTooltip() {
    var tip = document.getElementById("graph-tooltip");
    if (tip) tip.classList.add("hidden");
  }

  function _showSidePanelForNpc(npc) {
    if (!npc) return;
    var panel = document.getElementById("graph-side-panel");
    var nameEl = document.getElementById("graph-side-name");
    var metaEl = document.getElementById("graph-side-meta");
    var bodyEl = document.getElementById("graph-side-body");
    if (!panel || !nameEl || !metaEl || !bodyEl) return;

    nameEl.textContent = npc.label;
    var metaParts = [];
    if (npc.archetype) metaParts.push(npc.archetype);
    if (npc.disposition) metaParts.push(npc.disposition);
    if (npc.memory_label) metaParts.push("memory: " + npc.memory_label);
    metaEl.textContent = metaParts.join(" \u00b7 ");

    var html = "";
    if (npc.role) {
      html += '<div class="graph-side-role">' + _esc(npc.role) + '</div>';
    }
    if (!npc.interactions || !npc.interactions.length) {
      html += '<div class="graph-side-empty">No recorded interactions yet.</div>';
    } else {
      html += '<div class="graph-side-section-label">Interactions</div>';
      html += '<ol class="graph-side-list">';
      // Most recent first.
      var ordered = npc.interactions.slice().reverse();
      for (var i = 0; i < ordered.length; i++) {
        var it = ordered[i];
        var sentClass = "graph-sent-" + (it.sentiment || "neutral");
        html += '<li class="graph-side-item ' + sentClass + '">' +
          '<div class="graph-side-item-head">' +
            'Turn ' + _esc(it.turn) +
            ' &middot; ' + _esc(it.year) + ' AD' +
            ' &middot; <span class="graph-action-type">' +
              _esc(_formatActionType(it.action_type)) + '</span>' +
          '</div>' +
          (it.intent ? '<div class="graph-side-item-body">' + _esc(it.intent) + '</div>' : '') +
        '</li>';
      }
      html += '</ol>';
    }
    bodyEl.innerHTML = html;
    panel.classList.remove("hidden");
  }

  function _hideSidePanel() {
    var panel = document.getElementById("graph-side-panel");
    if (panel) panel.classList.add("hidden");
  }

  // ---- Public API --------------------------------------------------

  async function show(runId) {
    var container = document.getElementById("graph-container");
    if (!container) return;
    if (!initialized) init();
    if (!initialized) return;

    container.classList.remove("hidden");
    visible = true;
    currentRunId = runId || null;

    var titleYear = document.getElementById("graph-title-year");
    var titleName = document.getElementById("graph-title-name");
    if (titleYear) titleYear.textContent = "Loading...";
    if (titleName) titleName.textContent = "";

    if (!runId) {
      console.warn("ChronosGraph.show() called without runId");
      return;
    }

    try {
      var res = await fetch("/api/run/" + encodeURIComponent(runId) + "/interaction_graph");
      if (!res.ok) throw new Error("HTTP " + res.status);
      var data = await res.json();
      // Force a paint frame before measuring so the freshly-unhidden SVG
      // has real dimensions when the simulation initializes.
      await new Promise(function (r) { requestAnimationFrame(function () { r(); }); });
      updateGraph(data);
    } catch (e) {
      console.warn("interaction_graph fetch failed:", e);
      if (titleYear) titleYear.textContent = "Error";
    }
  }

  function hide() {
    var container = document.getElementById("graph-container");
    if (container) container.classList.add("hidden");
    visible = false;
    if (simulation) {
      simulation.stop();
    }
    _hideTooltip();
    _hideSidePanel();
  }

  function isVisible() { return visible; }

  return {
    init: init,
    show: show,
    hide: hide,
    isVisible: isVisible,
    updateGraph: updateGraph,
    resetView: resetView,
    focusOnNpc: focusOnNpc,
  };
})();
