/**
 * Phase 2.9 — Pinboard.
 *
 * The right-side panel where the player curates their reading of the
 * run. The 3D corridor was deleted; this replaces it. Vanilla DOM +
 * SVG, no Three.js.
 *
 * Player flow
 * -----------
 *
 *  1. Highlight a passage in #manuscript.
 *  2. After 150ms of stable selection, a "Pin this" floater appears
 *     near the selection rectangle.
 *  3. Click the floater → POST /api/run/{id}/pin → server classifies
 *     source_confidence (observed/told_by/rumor/inferred) by reading
 *     the turn-log row for source_turn_id → returns Pin → we render
 *     the card with the appropriate border style.
 *  4. Drag pins to reposition (debounced POST /pinboard).
 *  5. Click pin A then pin B → connection (POST /pinboard).
 *  6. Click any connection → cut (POST /pinboard).
 *
 * State
 * -----
 *
 *  - `pins`        : Array<Pin>           pulled from server, mutated locally
 *  - `connections` : Array<PinConnection> same
 *  - `connectFrom` : currently-selected first endpoint, or null
 *
 * No LLM calls. Phase 2.10 will add propose/edit/reject flow on top of
 * this same data model and the same /pinboard endpoint.
 */

(function () {
  "use strict";

  // ── State ───────────────────────────────────────────────────────────
  let panelEl = null;
  let surfaceEl = null;
  let pinsLayer = null;
  let edgesSvg = null;
  let countEl = null;
  let floaterEl = null;
  let runId = null;
  let pins = [];
  let connections = [];
  let connectFrom = null;
  let _persistTimer = null;
  let _selectionTimer = null;
  let _initialized = false;
  let _droppedThisCommit = 0;  // diag
  // Phase 2.10 cooldown gate. Hoisted to module scope so `restore()`
  // can seed it from server state on init (was previously declared
  // next to maybePropose() near the bottom of the IIFE; moving it
  // here is the smallest change that lets reload survive correctly).
  let _lastProposeTurn = -1;

  // ── Public API ──────────────────────────────────────────────────────
  const api = {
    show,
    restore,
    getDiag,
  };
  window.ChronosPinboard = api;

  function show(rid) {
    runId = rid || runId;
    _ensureInit();
  }

  function restore(serverPins, serverConnections, lastProposeTurn) {
    pins = Array.isArray(serverPins) ? serverPins.slice() : [];
    connections = Array.isArray(serverConnections) ? serverConnections.slice() : [];
    // Phase 2.10: seed the cooldown gate from server state so a page
    // reload doesn't reset _lastProposeTurn back to -1 and re-trigger
    // the proposer on the next turn. Treat undefined / non-numeric as
    // "no value provided" and leave the existing client value alone.
    if (typeof lastProposeTurn === "number" && isFinite(lastProposeTurn)) {
      _lastProposeTurn = Math.max(_lastProposeTurn, Math.floor(lastProposeTurn));
    }
    _ensureInit();
    _redraw();
  }

  function getDiag() {
    return {
      run_id: runId,
      pin_count: pins.length,
      connection_count: connections.length,
      cut_count: connections.filter((c) => c.cut).length,
      connect_from: connectFrom ? connectFrom.id : null,
    };
  }

  // ── Init ────────────────────────────────────────────────────────────
  function _ensureInit() {
    if (_initialized) return;
    panelEl = document.getElementById("pinboard-panel");
    surfaceEl = document.getElementById("pinboard-surface");
    pinsLayer = document.getElementById("pinboard-pins");
    edgesSvg = document.getElementById("pinboard-edges");
    countEl = document.getElementById("pinboard-count");
    floaterEl = document.getElementById("pin-this-floater");
    if (!panelEl || !surfaceEl || !pinsLayer || !edgesSvg) {
      return;  // panel not in the DOM (e.g. start screen); bail.
    }
    _initialized = true;
    _wireSelectionToPin();
    _wireFloaterClick();
    _wireSurfaceClick();
    window.addEventListener("resize", _redrawEdgesOnly);
  }

  // ── Render ──────────────────────────────────────────────────────────
  function _redraw() {
    if (!_initialized) return;
    pinsLayer.innerHTML = "";
    pins.forEach(_renderPinCard);
    _redrawEdgesOnly();
    if (countEl) countEl.textContent = String(pins.length);
    if (panelEl) panelEl.classList.toggle("is-empty", pins.length === 0);
  }

  function _renderPinCard(pin) {
    const card = document.createElement("div");
    card.className = "pin-card";
    card.dataset.pinId = pin.id;
    card.dataset.confidence = pin.source_confidence || "inferred";
    card.style.left = (pin.x || 0) + "px";
    card.style.top = (pin.y || 0) + "px";
    card.title = pin.text || "";

    const confLabel = _confidenceLabel(pin);
    card.innerHTML =
      '<button class="pin-delete" type="button" title="Remove pin">\u00d7</button>' +
      '<div class="pin-text"></div>' +
      '<div class="pin-meta">' +
        '<span class="pin-confidence-dot"></span>' +
        '<span class="pin-confidence-label">' + _esc(confLabel) + '</span>' +
      '</div>';
    card.querySelector(".pin-text").textContent = pin.text || "";

    _wirePinDrag(card, pin);
    _wirePinClick(card, pin);
    _wirePinDelete(card, pin);
    pinsLayer.appendChild(card);
  }

  function _confidenceLabel(pin) {
    const c = pin.source_confidence || "inferred";
    if (c === "told_by" && pin.source_attribution) {
      return "Told by " + pin.source_attribution;
    }
    if (c === "told_by") return "Told by an NPC";
    if (c === "observed") return "Observed";
    if (c === "rumor") return "Rumor";
    return "Inferred";
  }

  // Three connection kinds, three visual languages:
  //   "player"        - solid emerald. Player drew it. Click = cut.
  //   "auto"          - solid amber. System proposal the player agreed
  //                     (or edited) into. Click = cut.
  //   "auto_proposed" - faint dashed yellow. Awaiting adjudication.
  //                     Click = open the agree/edit/reject popup; never
  //                     cut directly.
  function _connectionStyle(conn) {
    if (conn.kind === "auto_proposed") {
      return {
        stroke: "rgba(252, 211, 77, 0.55)",
        strokeWidth: 1.5,
        dashArray: "6 4",
        opacity: 0.85,
      };
    }
    if (conn.kind === "auto") {
      return {
        stroke: "rgba(252, 211, 77, 0.7)",
        strokeWidth: 2,
        dashArray: null,
        opacity: 0.9,
      };
    }
    return {
      stroke: "rgba(110, 231, 183, 0.55)",
      strokeWidth: 2,
      dashArray: null,
      opacity: 0.85,
    };
  }

  function _redrawEdgesOnly() {
    if (!_initialized) return;
    while (edgesSvg.firstChild) edgesSvg.removeChild(edgesSvg.firstChild);
    if (connections.length === 0) return;
    const byId = new Map(pins.map((p) => [p.id, p]));
    connections.forEach((conn) => {
      const a = byId.get(conn.from_pin_id);
      const b = byId.get(conn.to_pin_id);
      if (!a || !b) return;
      const ax = (a.x || 0) + 110;  // pin midpoint, half of 220px
      const ay = (a.y || 0) + 30;
      const bx = (b.x || 0) + 110;
      const by = (b.y || 0) + 30;
      const style = _connectionStyle(conn);
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", ax);
      line.setAttribute("y1", ay);
      line.setAttribute("x2", bx);
      line.setAttribute("y2", by);
      line.setAttribute("stroke", style.stroke);
      line.setAttribute("stroke-width", String(style.strokeWidth));
      line.setAttribute("stroke-opacity", String(style.opacity));
      line.setAttribute("stroke-linecap", "round");
      if (style.dashArray) line.setAttribute("stroke-dasharray", style.dashArray);
      line.dataset.connectionId = conn.id;
      if (conn.cut) line.classList.add("is-cut");
      if (conn.kind === "auto_proposed") line.classList.add("is-proposed");
      line.addEventListener("click", (e) => {
        e.stopPropagation();
        if (conn.kind === "auto_proposed") {
          _openAdjudicatePopup(conn, (ax + bx) / 2, (ay + by) / 2);
        } else {
          _cutConnection(conn);
        }
      });
      edgesSvg.appendChild(line);

      // Adjudicate icon at the midpoint of an auto_proposed line.
      // Visually invites the player to interact even before they
      // hover the line itself. Clicking it does the same as clicking
      // the line.
      if (conn.kind === "auto_proposed") {
        const mx = (ax + bx) / 2;
        const my = (ay + by) / 2;
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "g");
        icon.setAttribute("class", "proposal-marker");
        icon.setAttribute("transform", "translate(" + mx + "," + my + ")");
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", "9");
        circle.setAttribute("fill", "rgba(20, 18, 10, 0.95)");
        circle.setAttribute("stroke", "rgba(252, 211, 77, 0.85)");
        circle.setAttribute("stroke-width", "1.4");
        const qm = document.createElementNS("http://www.w3.org/2000/svg", "text");
        qm.setAttribute("text-anchor", "middle");
        qm.setAttribute("dominant-baseline", "central");
        qm.setAttribute("y", "0.5");
        qm.setAttribute("fill", "rgba(252, 211, 77, 0.95)");
        qm.setAttribute("font-size", "11");
        qm.setAttribute("font-family", "JetBrains Mono, monospace");
        qm.setAttribute("font-weight", "600");
        qm.textContent = "?";
        icon.appendChild(circle);
        icon.appendChild(qm);
        icon.addEventListener("click", (e) => {
          e.stopPropagation();
          _openAdjudicatePopup(conn, mx, my);
        });
        edgesSvg.appendChild(icon);
      }
    });
  }

  // ── Selection -> "Pin this" floater ─────────────────────────────────
  function _wireSelectionToPin() {
    document.addEventListener("selectionchange", () => {
      if (_selectionTimer) clearTimeout(_selectionTimer);
      _selectionTimer = setTimeout(_evaluateSelection, 150);
    });
  }

  function _evaluateSelection() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      _hideFloater();
      return;
    }
    const text = (sel.toString() || "").trim();
    if (text.length < 3) {
      _hideFloater();
      return;
    }
    // Selection must be inside #manuscript.
    const range = sel.getRangeAt(0);
    const ms = document.getElementById("manuscript");
    if (!ms || !range || !ms.contains(range.commonAncestorContainer)) {
      _hideFloater();
      return;
    }
    const sourceTurnId = _findSourceTurnId(range.commonAncestorContainer);
    const rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      _hideFloater();
      return;
    }
    _showFloater(rect, text, sourceTurnId, range);
  }

  function _findSourceTurnId(node) {
    while (node && node.nodeType !== Node.ELEMENT_NODE) node = node.parentNode;
    let cur = node;
    while (cur && cur !== document.body) {
      if (cur.classList && cur.classList.contains("turn-block")) {
        // Prefer the post-turn `data-turn-number` stamp set by
        // app.js renderTurnStaggered. That value matches the
        // backend's `turn_logs.turn_number` and the classifier's
        // `turn-<turn_number>` candidate id, so the pin is attached
        // to the right row. The DOM `id` (`turn-<Date.now()>`) is
        // the legacy fallback for older runs whose manuscript was
        // restored from localStorage and pre-dates the dataset stamp.
        const tn = cur.dataset && cur.dataset.turnNumber;
        if (tn != null && tn !== "") return "turn-" + tn;
        if (cur.id) return cur.id;
      }
      if (cur.classList && cur.classList.contains("manuscript-intro")) return "manuscript-intro";
      cur = cur.parentNode;
    }
    return "";
  }

  let _floaterPayload = null;
  function _showFloater(rect, text, sourceTurnId, range) {
    if (!floaterEl) return;
    floaterEl.classList.remove("hidden");
    // Position above the selection, with a small offset.
    const top = Math.max(8, rect.top - 30);
    const left = Math.min(window.innerWidth - 100, rect.right - 80);
    floaterEl.style.top = top + "px";
    floaterEl.style.left = left + "px";
    let offsetStart = 0;
    let offsetEnd = text.length;
    try {
      offsetStart = range.startOffset || 0;
      offsetEnd = (range.startOffset || 0) + text.length;
    } catch (_) { /* best-effort */ }
    _floaterPayload = {
      text,
      source_turn_id: sourceTurnId,
      source_offset_start: offsetStart,
      source_offset_end: offsetEnd,
    };
  }

  function _hideFloater() {
    if (floaterEl) floaterEl.classList.add("hidden");
    _floaterPayload = null;
  }

  function _wireFloaterClick() {
    if (!floaterEl) return;
    floaterEl.addEventListener("mousedown", (e) => {
      // Prevent the mousedown from collapsing the selection before
      // the click handler reads it. The pin payload is already
      // captured by _evaluateSelection.
      e.preventDefault();
    });
    floaterEl.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!_floaterPayload || !runId) {
        _hideFloater();
        return;
      }
      const payload = _floaterPayload;
      _hideFloater();
      // Drop a sensible default position on the panel: cascade down
      // and to the right so successive pins don't pile up at 0,0.
      const surfaceRect = surfaceEl ? surfaceEl.getBoundingClientRect() : { width: 400 };
      const baseX = 24 + (pins.length * 22) % Math.max(80, surfaceRect.width - 250);
      const baseY = 24 + (pins.length * 14) % 360;
      try {
        const res = await fetch("/api/run/" + runId + "/pin", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: payload.text,
            source_turn_id: payload.source_turn_id,
            source_offset_start: payload.source_offset_start,
            source_offset_end: payload.source_offset_end,
            x: baseX,
            y: baseY,
          }),
        });
        if (!res.ok) {
          console.warn("[pinboard] POST /pin failed:", res.status);
          return;
        }
        const body = await res.json();
        if (body && body.pin) {
          pins.push(body.pin);
          _redraw();
        }
      } catch (err) {
        console.warn("[pinboard] /pin error:", err);
      }
    });
  }

  // ── Pin drag ────────────────────────────────────────────────────────
  function _wirePinDrag(card, pin) {
    let dragging = false;
    let startX = 0, startY = 0;
    let originX = 0, originY = 0;
    let moved = false;

    card.addEventListener("pointerdown", (e) => {
      // Don't start drag from the delete button.
      if (e.target.closest(".pin-delete")) return;
      dragging = true;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      originX = parseFloat(card.style.left) || 0;
      originY = parseFloat(card.style.top) || 0;
      card.classList.add("is-dragging");
      try { card.setPointerCapture(e.pointerId); } catch (_) {}
    });
    card.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      card.style.left = (originX + dx) + "px";
      card.style.top = (originY + dy) + "px";
      pin.x = originX + dx;
      pin.y = originY + dy;
      _redrawEdgesOnly();
    });
    const release = (e) => {
      if (!dragging) return;
      dragging = false;
      card.classList.remove("is-dragging");
      try { card.releasePointerCapture(e.pointerId); } catch (_) {}
      if (moved) {
        _schedulePersist({
          pin_positions: [{ id: pin.id, x: pin.x, y: pin.y }],
        });
      }
    };
    card.addEventListener("pointerup", release);
    card.addEventListener("pointercancel", release);
    // Mark moved on the card so the click handler can distinguish
    // drag-end from a genuine click.
    card._hasMovedRef = () => moved;
  }

  // ── Pin click (connect first endpoint, then second) ─────────────────
  function _wirePinClick(card, pin) {
    card.addEventListener("click", (e) => {
      // Drag-end calls pointerup which is followed by a click; ignore
      // those clicks so a drag doesn't accidentally start a connection.
      if (card._hasMovedRef && card._hasMovedRef()) return;
      if (e.target.closest(".pin-delete")) return;
      _toggleConnect(pin);
    });
  }

  function _toggleConnect(pin) {
    if (!connectFrom) {
      connectFrom = pin;
      _markConnectFrom(pin);
      return;
    }
    if (connectFrom.id === pin.id) {
      connectFrom = null;
      _markConnectFrom(null);
      return;
    }
    // Form a connection.
    const a = connectFrom;
    const b = pin;
    connectFrom = null;
    _markConnectFrom(null);
    // Optimistic local insert; backend will dedup if it already exists.
    const tempId = "tmp-" + Math.random().toString(36).slice(2, 10);
    connections.push({
      id: tempId,
      from_pin_id: a.id,
      to_pin_id: b.id,
      kind: "player",
      cut: false,
      label: "",
      meta: {},
    });
    _redrawEdgesOnly();
    _persistConnections();
  }

  function _markConnectFrom(pin) {
    pinsLayer.querySelectorAll(".pin-card.is-connect-source").forEach((el) =>
      el.classList.remove("is-connect-source"),
    );
    if (!pin) return;
    const target = pinsLayer.querySelector(
      '.pin-card[data-pin-id="' + pin.id + '"]',
    );
    if (target) target.classList.add("is-connect-source");
  }

  // ── Click on the surface (not a card) cancels in-progress connect ───
  function _wireSurfaceClick() {
    if (!surfaceEl) return;
    surfaceEl.addEventListener("click", (e) => {
      if (e.target.closest(".pin-card")) return;
      if (e.target.closest("line")) return;
      if (connectFrom) {
        connectFrom = null;
        _markConnectFrom(null);
      }
    });
  }

  // ── Cut a connection ────────────────────────────────────────────────
  function _cutConnection(conn) {
    conn.cut = true;
    _redrawEdgesOnly();
    if (!conn.id || conn.id.indexOf("tmp-") === 0) {
      // Unsaved connection (still in flight). Don't send a cut for
      // an id the server doesn't know about. The next persist cycle
      // will write the new connection AS cut via the upsert path.
      _persistConnections();
      return;
    }
    _schedulePersist({ cut_connection_ids: [conn.id] });
  }

  // ── Pin delete ──────────────────────────────────────────────────────
  function _wirePinDelete(card, pin) {
    const btn = card.querySelector(".pin-delete");
    if (!btn) return;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      // Local removal is immediate; server cleanup follows.
      pins = pins.filter((p) => p.id !== pin.id);
      // Drop any connections referencing this pin so the panel doesn't
      // briefly render an orphan line.
      connections = connections.filter(
        (c) => c.from_pin_id !== pin.id && c.to_pin_id !== pin.id,
      );
      _droppedThisCommit++;
      _redraw();
      _schedulePersist({ delete_pin_ids: [pin.id] });
    });
  }

  // ── Persistence ─────────────────────────────────────────────────────
  function _schedulePersist(payload) {
    // Coalesce drag updates within a 350ms window. Connection / cut /
    // delete events are sent immediately because they're rare.
    if (payload.pin_positions) {
      // Stash the latest position for each pin id; flush after delay.
      _coalescedPositions = _coalescedPositions || new Map();
      payload.pin_positions.forEach((p) =>
        _coalescedPositions.set(p.id, { id: p.id, x: p.x, y: p.y }),
      );
      if (_persistTimer) return;
      _persistTimer = setTimeout(() => {
        _persistTimer = null;
        const flat = Array.from(_coalescedPositions.values());
        _coalescedPositions = new Map();
        _post({ pin_positions: flat });
      }, 350);
      return;
    }
    _post(payload);
  }
  let _coalescedPositions = null;

  function _persistConnections() {
    // Push the full connections list as upserts so the backend can
    // dedup and assign permanent ids. Clients with tmp- ids will get
    // those replaced server-side; we rely on the next state load to
    // pick up authoritative ids.
    const toSend = connections
      .filter((c) => c.id.indexOf("tmp-") === 0)  // only new ones
      .map((c) => ({
        from_pin_id: c.from_pin_id,
        to_pin_id: c.to_pin_id,
        kind: c.kind || "player",
        cut: !!c.cut,
        label: c.label || "",
      }));
    if (toSend.length === 0) return;
    _post({ pin_connections: toSend });
  }

  async function _post(payload) {
    if (!runId) return;
    try {
      const res = await fetch("/api/run/" + runId + "/pinboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        console.warn("[pinboard] /pinboard POST failed:", res.status);
        return;
      }
      // For connection upserts, swap any tmp- ids for server-issued
      // ones by re-fetching the run state. Simple, robust, and keeps
      // the pinboard in sync without bespoke merge logic.
      if (payload.pin_connections) {
        try {
          const fresh = await fetch("/api/run/" + runId);
          if (fresh.ok) {
            const body = await fresh.json();
            if (Array.isArray(body.pin_connections)) {
              connections = body.pin_connections.slice();
              _redrawEdgesOnly();
            }
          }
        } catch (_) { /* best-effort */ }
      }
    } catch (err) {
      console.warn("[pinboard] /pinboard error:", err);
    }
  }

  // ── Phase 2.10: adjudicate popup ────────────────────────────────────
  //
  // Anchored at the line midpoint of an auto_proposed connection. The
  // player sees the system's claim, and adjudicates: Agree, Edit, or
  // Reject. Keyboard: Enter agrees, Esc rejects, Tab moves into the
  // editable textarea.
  //
  // Only one popup is open at a time. Opening a new one closes the
  // previous. Clicking outside closes it (Esc-equivalent reject? no:
  // outside-click is a soft cancel, not a reject -- the proposal
  // stays for later adjudication).
  let _adjudicatePopupEl = null;
  let _adjudicateTarget = null;  // the connection currently being adjudicated

  function _ensureAdjudicatePopup() {
    if (_adjudicatePopupEl && _adjudicatePopupEl.isConnected) return _adjudicatePopupEl;
    const el = document.createElement("div");
    el.id = "pinboard-adjudicate";
    el.className = "hidden";
    el.innerHTML =
      '<div class="adj-header">A connection between two pins on this turn</div>' +
      '<div class="adj-claim" id="adj-claim"></div>' +
      '<textarea id="adj-edit" class="hidden" rows="3" maxlength="140" ' +
      '          placeholder="Rewrite the claim..."></textarea>' +
      '<div class="adj-buttons">' +
      '  <button id="adj-reject" type="button" class="adj-btn adj-reject">Reject</button>' +
      '  <button id="adj-edit-toggle" type="button" class="adj-btn adj-edit">Edit</button>' +
      '  <button id="adj-agree" type="button" class="adj-btn adj-agree">Agree</button>' +
      '</div>' +
      '<div class="adj-keyhint">Enter \u2014 agree \u00b7 Esc \u2014 close</div>';
    document.body.appendChild(el);
    _adjudicatePopupEl = el;
    el.querySelector("#adj-agree").addEventListener("click", _onAdjAgree);
    el.querySelector("#adj-reject").addEventListener("click", _onAdjReject);
    el.querySelector("#adj-edit-toggle").addEventListener("click", _onAdjEditToggle);
    document.addEventListener("pointerdown", _onOutsideClick, true);
    document.addEventListener("keydown", _onAdjKeydown);
    return el;
  }

  function _openAdjudicatePopup(conn, midX, midY) {
    const el = _ensureAdjudicatePopup();
    _adjudicateTarget = conn;
    el.querySelector("#adj-claim").textContent = conn.label || "(no claim)";
    const textarea = el.querySelector("#adj-edit");
    textarea.value = conn.label || "";
    textarea.classList.add("hidden");
    el.classList.remove("hidden");
    // Position the popup near the line midpoint, in viewport
    // coordinates. The midX/midY we got are in #pinboard-edges
    // coordinate space (same as the SVG); convert via the surface's
    // bounding rect to viewport coords.
    const rect = surfaceEl.getBoundingClientRect();
    const viewX = rect.left + midX;
    const viewY = rect.top + midY;
    // Clamp so the popup stays on-screen.
    const popupW = 320;
    const popupH = 170;
    let x = viewX - popupW / 2;
    let y = viewY + 14;  // below the marker
    if (x + popupW > window.innerWidth - 8) x = window.innerWidth - popupW - 8;
    if (x < 8) x = 8;
    if (y + popupH > window.innerHeight - 8) y = viewY - popupH - 14;
    el.style.left = x + "px";
    el.style.top = y + "px";
  }

  function _closeAdjudicatePopup() {
    if (_adjudicatePopupEl) _adjudicatePopupEl.classList.add("hidden");
    _adjudicateTarget = null;
  }

  function _onOutsideClick(e) {
    if (!_adjudicatePopupEl || _adjudicatePopupEl.classList.contains("hidden")) return;
    if (_adjudicatePopupEl.contains(e.target)) return;
    // Clicking the proposal marker / line REopens the popup; we don't
    // want a marker click to also close it. SVG event ordering puts
    // the marker click first; if it landed inside <line> or <g> we
    // bail out here.
    if (e.target.closest && e.target.closest("#pinboard-edges")) return;
    _closeAdjudicatePopup();
  }

  function _onAdjKeydown(e) {
    if (!_adjudicatePopupEl || _adjudicatePopupEl.classList.contains("hidden")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      _closeAdjudicatePopup();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      // Don't hijack Enter inside a textarea -- the player is editing.
      const a = document.activeElement;
      if (a && a.id === "adj-edit") return;
      e.preventDefault();
      _onAdjAgree();
    }
  }

  function _onAdjEditToggle() {
    const el = _ensureAdjudicatePopup();
    const textarea = el.querySelector("#adj-edit");
    const claim = el.querySelector("#adj-claim");
    if (textarea.classList.contains("hidden")) {
      textarea.classList.remove("hidden");
      claim.classList.add("hidden");
      textarea.focus();
      textarea.select();
    } else {
      // Toggle back to read-only display.
      textarea.classList.add("hidden");
      claim.classList.remove("hidden");
    }
  }

  async function _onAdjAgree() {
    const conn = _adjudicateTarget;
    if (!conn) return _closeAdjudicatePopup();
    const el = _ensureAdjudicatePopup();
    const textarea = el.querySelector("#adj-edit");
    const wasEdited = !textarea.classList.contains("hidden");
    const finalLabel = wasEdited
      ? (textarea.value || "").trim().slice(0, 140)
      : (conn.label || "");
    if (wasEdited && !finalLabel) {
      // Edit-to-empty isn't a meaningful agree. Treat as cancel.
      _closeAdjudicatePopup();
      return;
    }
    // Optimistic local update.
    conn.kind = "auto";
    conn.label = finalLabel;
    if (wasEdited) {
      conn.meta = Object.assign({}, conn.meta || {}, { was_edited: true });
    }
    _redrawEdgesOnly();
    _closeAdjudicatePopup();
    // Persist via the upsert path.
    _post({
      pin_connections: [{
        id: conn.id,
        from_pin_id: conn.from_pin_id,
        to_pin_id: conn.to_pin_id,
        kind: "auto",
        label: finalLabel,
        meta_was_edited: !!wasEdited,
      }],
    });
  }

  async function _onAdjReject() {
    const conn = _adjudicateTarget;
    if (!conn) return _closeAdjudicatePopup();
    const a_id = conn.from_pin_id;
    const b_id = conn.to_pin_id;
    // Local removal first; the line will disappear immediately.
    connections = connections.filter((c) => c.id !== conn.id);
    _redrawEdgesOnly();
    _closeAdjudicatePopup();
    // Persist: hard-delete + tombstone the pair so the proposer
    // doesn't suggest the same connection on a future turn.
    _post({
      delete_connection_ids: [conn.id],
      tombstone_pin_pairs: [[a_id, b_id]],
    });
  }

  // ── Phase 2.10: trigger the proposer after a turn ───────────────────
  //
  // Called by app.js after a turn completes. Honors the threshold gate
  // ">=3 unconnected pins AND >=2 turns since last proposal." If the
  // gate passes, POST /pinboard/propose_connections; merge any
  // returned proposals into the local connections array and redraw.
  // (`_lastProposeTurn` is declared at module scope above so restore()
  // can seed it from server state.)

  async function maybePropose(currentTurn) {
    if (!runId) return;
    if (typeof currentTurn !== "number") currentTurn = 0;
    // Threshold gate.
    const unconnected = pins.filter((p) => {
      return !connections.some(
        (c) => c.from_pin_id === p.id || c.to_pin_id === p.id,
      );
    }).length;
    if (unconnected < 3) return;
    if (currentTurn - _lastProposeTurn < 2) return;
    // Reserve the cooldown slot OPTIMISTICALLY so a slow LLM call
    // doesn't get re-fired on the next turn boundary, but only ADVANCE
    // the cooldown on a successful response. A failure (network error,
    // backend 5xx, NoOp circuit) restores the previous value so the
    // gate retries on the next turn -- otherwise repeated transient
    // errors silently freeze the proposer for the rest of the run.
    const prevLastProposeTurn = _lastProposeTurn;
    _lastProposeTurn = currentTurn;
    let succeeded = false;
    try {
      const res = await fetch(
        "/api/run/" + runId + "/pinboard/propose_connections",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_turn: currentTurn }),
        },
      );
      if (!res.ok) {
        console.warn("[pinboard] propose_connections failed:", res.status);
        return;
      }
      succeeded = true;
      const body = await res.json();
      const proposed = Array.isArray(body.proposed) ? body.proposed : [];
      if (proposed.length === 0) return;
      // Append the new auto_proposed connections; redraw.
      connections = connections.concat(proposed);
      _redrawEdgesOnly();
    } catch (err) {
      console.warn("[pinboard] propose_connections error:", err);
    } finally {
      if (!succeeded) {
        _lastProposeTurn = prevLastProposeTurn;
      }
    }
  }
  // Expose for the trigger in app.js.
  api.maybePropose = maybePropose;

  // ── Helpers ─────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    }[c]));
  }
})();
