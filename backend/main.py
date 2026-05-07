"""CHRONOS — FastAPI entry point.

Simulation-first architecture: the world advances every turn,
then the player optionally acts. The player is a perspective,
not a protagonist.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import defaultdict
from pathlib import Path
from string import Template

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.action_parser import parse_action
from backend.character_gen import generate_run
from backend.inner_thought import generate_inner_thought
from backend.death_engine import (
    apply_death,
    check_death,
    decay_memories,
    generate_erasure,
    generate_memory_fade,
)
from backend.eras import ALL_ERAS, random_era
from backend.llm_provider import (
    call_llm,
    gemini_ok,
    load_prompt,
    track_turn_cost,
)
from backend import config
from backend.npc_engine import generate_npc_addressed, generate_npc_pov
from backend.persistence import (
    append_turn_log,
    build_narrative_output,
    compute_state_diff,
    delete_session,
    init_db,
    list_sessions,
    load_session,
    query_historical_events,
    save_session,
)
from backend.llm_schemas import leaks_raw_numbers, scrub_leaked_numbers
from backend.player_knowledge import (
    build_player_view,
    filter_historical_events,
    _knowledge_tier,
)
from backend.scene_triggers import (
    check_illustration_trigger,
    compute_witnessed_events_this_turn,
)
from backend.world_engine import (
    advance_world,
    advance_world_skip,
    generate_arrival_catchup,
    mark_consequence_superseded_mem,
    player_skip_turn,
    simulate_turn,
)
from backend.world_state import (
    PIN_CONNECTION_KINDS,
    PIN_SOURCE_CONFIDENCES,
    Event,
    Pin,
    PinConnection,
    PinSourceOffset,
    ScheduledConsequence,
    WorldState,
    apply_action,
    create_initial_state,
    get_location,
    get_player_location,
    npcs_near_player,
)
from backend.pin_classifier import classify_pin_source

logger = logging.getLogger("chronos")

app = FastAPI(title="CHRONOS", version="0.2.0")

_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

_NPC_PERCEPTION_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "npc_perception.md"
)


# ------------------------------------------------------------------
# Cost tracking helpers (two-tier LLM provider)
# ------------------------------------------------------------------

def _finalize_turn_cost(state: WorldState, bucket: list) -> float:
    """Accumulate bucket into state, update cap state, return turn delta.

    Returns turn_cost_usd (the sum across this turn), to be persisted in
    turn_logs.turn_cost_usd. Mutates `state.cumulative_cost_usd` and
    `state.cost_cap_state` in place.
    """
    turn_delta = sum(u.cost_usd for u in bucket)
    state.cumulative_cost_usd = float(state.cumulative_cost_usd) + turn_delta
    _enforce_cost_caps(state)
    return turn_delta


def _enforce_cost_caps(state: WorldState) -> None:
    """Update state.cost_cap_state based on cumulative EUR cost.

    State machine:
      none           -> initial
      soft_crossed   -> >= COST_CAP_SOFT_EUR (banner shown in frontend)
      hard           -> >= COST_CAP_HARD_EUR (turn advancement blocked)
    """
    cost_eur = float(state.cumulative_cost_usd) * config.USD_TO_EUR
    if cost_eur >= config.COST_CAP_HARD_EUR:
        if state.cost_cap_state != "hard":
            logger.warning(
                "HARD COST CAP reached for run %s: %.4f USD (EUR %.2f)",
                state.run_id, state.cumulative_cost_usd, cost_eur,
            )
            state.cost_cap_state = "hard"
    elif cost_eur >= config.COST_CAP_SOFT_EUR:
        if state.cost_cap_state == "none":
            logger.warning(
                "Soft cost cap crossed for run %s: %.4f USD (EUR %.2f)",
                state.run_id, state.cumulative_cost_usd, cost_eur,
            )
            state.cost_cap_state = "soft_crossed"


def _check_hard_cap_or_raise(state: WorldState) -> None:
    """Raise 402 if the run has hit its hard cost cap.

    Applied at the entry of every turn-advancing endpoint. Read-only
    endpoints (/state, /perception, /region, /context) are NOT gated —
    the player can still observe the world and end the run manually.
    """
    if state.cost_cap_state == "hard":
        cost_eur = float(state.cumulative_cost_usd) * config.USD_TO_EUR
        raise HTTPException(
            status_code=402,
            detail={
                "code": "cost_cap_hard",
                "cost_usd": float(state.cumulative_cost_usd),
                "cost_eur": cost_eur,
                "cap_eur": config.COST_CAP_HARD_EUR,
                "message": (
                    f"Hard cost cap reached (€{cost_eur:.2f} / "
                    f"€{config.COST_CAP_HARD_EUR:.2f}). End run manually "
                    "to continue."
                ),
            },
        )


class TurnRequest(BaseModel):
    player_input: str


class RunRequest(BaseModel):
    era: str = ""


# ------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    await init_db()
    config.startup_log(logger)
    if config.GEMINI_API_KEY:
        ok, detail = await gemini_ok()
        if ok:
            logger.info(
                "Gemini startup smoke test OK (%s, %s)",
                config.CHRONOS_GEMINI_MODEL, detail,
            )
        else:
            logger.warning(
                "Gemini startup smoke test FAILED (%s). LLM calls will return "
                "NoOp responses until the circuit recovers. "
                "Check GEMINI_API_KEY and model name '%s'.",
                detail, config.CHRONOS_GEMINI_MODEL,
            )


# ------------------------------------------------------------------
# Health + Geo
# ------------------------------------------------------------------

@app.get("/api/health")
async def health():
    gemini_status, gemini_detail = await gemini_ok()
    return {"status": "ok", "phase": 2, "gemini": gemini_status, "gemini_detail": gemini_detail}


@app.get("/api/geo/{era_key}")
async def get_geo(era_key: str):
    geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
    border_file = geo_dir / f"borders_{era_key}.geojson"
    if not border_file.exists():
        raise HTTPException(404, f"No border data for era '{era_key}'")
    try:
        return json.loads(border_file.read_text())
    except (json.JSONDecodeError, IOError) as exc:
        raise HTTPException(500, f"Failed to load border data: {exc}")


# Phase 2.6 (Spatial Substrate) — DEM heightmap for the war-table.
#
# Returns an 8-bit grayscale PNG sized to TILE_PIXELS (1024) covering
# the era's regional bounding box. The frontend war-table reads this
# as a displacement texture for its terrain mesh.
#
# See backend/geo/terrain.py for the honest limitation: real SRTM data
# is not bundled in the kickoff commit; the source today is a
# deterministic procedural noise. The endpoint contract is stable;
# real DEM data drops in via a follow-up build script.
#
# bbox is returned in headers so the frontend doesn't need to keep its
# own copy of the era bounding box.
@app.get("/api/geo/terrain/{era_key}")
async def get_terrain(era_key: str):
    from fastapi.responses import Response
    from backend.geo.terrain import get_terrain_png, get_bbox

    bbox = get_bbox(era_key)
    if bbox is None:
        raise HTTPException(404, f"No terrain bbox configured for era '{era_key}'")
    try:
        png_bytes = get_terrain_png(era_key)
    except Exception as exc:  # noqa: BLE001 - surface a useful 500 either way
        raise HTTPException(500, f"Failed to generate terrain: {exc}") from exc
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Terrain-Bbox-South": str(bbox.south_lat),
            "X-Terrain-Bbox-West": str(bbox.west_lon),
            "X-Terrain-Bbox-North": str(bbox.north_lat),
            "X-Terrain-Bbox-East": str(bbox.east_lon),
        },
    )


# Place labels (cities + small named regions) for zoom-dependent
# rendering on the map. Returned with a 'tier' field so the frontend
# can fade them in at different zoom levels:
#   "city"     radius_km <= 80    - shown from zoom 6+
#   "town"     radius_km <= 200   - shown from zoom 7+
#   "region"   radius_km <= 500   - shown from zoom 5+
# Broad regions (radius_km > 500) are deliberately excluded;
# rendering "Mediterranean" as a single label point is meaningless.
@app.get("/api/geo/places/labels")
async def get_place_labels():
    from backend.geo.centroids import load_centroids
    centroids = load_centroids()

    out: list[dict] = []
    for name, c in centroids.items():
        r = c["radius_km"]
        if r > 500:
            continue
        if r <= 80:
            tier = "city"
        elif r <= 200:
            tier = "town"
        else:
            tier = "region"
        out.append({
            "name": name,
            "lat": c["lat"],
            "lon": c["lon"],
            "tier": tier,
            "radius_km": r,
        })
    return {"places": out}


# ------------------------------------------------------------------
# Run management
# ------------------------------------------------------------------

@app.post("/api/run/preview")
async def preview_run(req: RunRequest = RunRequest()):
    """Return era info instantly for the loading screen, before character generation."""
    if req.era and req.era in ALL_ERAS:
        era_key, era_config = req.era, ALL_ERAS[req.era]
    else:
        era_key, era_config = random_era()

    loading_events = []
    loading_events_structured = []
    try:
        year = era_config["year_start"]
        raw_events = await query_historical_events(
            year_start=year - 55,
            year_end=year + 5,
        )
        civ = [e for e in raw_events if e["significance"] == "civilizational"]
        reg = [e for e in raw_events if e["significance"] == "regional"]
        recent_first = sorted(civ + reg, key=lambda e: e["year"], reverse=True)
        seen_text = set()
        seen_years = {}
        deduped = []
        for e in recent_first:
            txt_key = e["event"][:60]
            if txt_key in seen_text:
                continue
            seen_text.add(txt_key)
            yr = e["year"]
            if seen_years.get(yr, 0) >= 1:
                continue
            seen_years[yr] = seen_years.get(yr, 0) + 1
            deduped.append(e)
        selected = deduped[:6]
        selected.sort(key=lambda e: e["year"])
        loading_events = [
            f"{e['year']} AD \u2014 {e['event']}" for e in selected
        ]
        loading_events_structured = [
            {
                "year": e["year"],
                "event": e["event"],
                "significance": e.get("significance", ""),
                "type": e.get("type", ""),
            }
            for e in selected
        ]
    except Exception:
        pass

    if not loading_events:
        loading_events = era_config.get("loading_events", [])

    return {
        "era_key": era_key,
        "era_name": era_config["name"],
        "year_start": era_config["year_start"],
        "description": era_config["description"],
        "region": era_config["region"],
        "loading_events": loading_events,
        "loading_events_structured": loading_events_structured,
        "loading_voices": era_config.get("loading_voices", []),
    }


@app.post("/api/run")
async def new_run(req: RunRequest = RunRequest()):
    if req.era and req.era in ALL_ERAS:
        era_key, era_config = req.era, ALL_ERAS[req.era]
    else:
        era_key, era_config = random_era()

    with track_turn_cost() as bucket:
        state = await generate_run(era_config)
        _finalize_turn_cost(state, bucket)

    await save_session(state)
    return {
        "run_id": state.run_id,
        "era": era_key,
        "player_view": build_player_view(state, state.run_id).model_dump(),
    }


@app.get("/api/runs")
async def get_runs():
    return await list_sessions()


@app.get("/api/run/{run_id}")
async def get_run_state(run_id: str):
    state = await _load_or_404(run_id)
    return build_player_view(state, run_id).model_dump()


@app.delete("/api/run/{run_id}")
async def delete_run(run_id: str):
    await delete_session(run_id)
    return {"status": "deleted", "run_id": run_id}


@app.post("/api/run/{run_id}/reset")
async def reset_run(run_id: str):
    state = create_initial_state()
    state.run_id = run_id
    await save_session(state)
    return {"status": "reset", "player_view": build_player_view(state, run_id).model_dump()}


# ------------------------------------------------------------------
# Unified turn — simulation-first
#
# Flow: 1) world simulates (NPCs act) → 2) player action parsed →
#        3) player action applied → 4) death check → 5) save
#
# Returns: ambient_activity (what NPCs did) + player result + npc_responses
# ------------------------------------------------------------------

@app.post("/api/run/{run_id}/turn")
async def take_turn(run_id: str, req: TurnRequest):
    async with _session_locks[run_id]:
        return await _execute_turn(run_id, req)


# Phase 2.9 (2026-05-07): the 3D corridor manuscript and its
# /api/run/{id}/board endpoint were deleted. They are replaced by the
# 2D pinboard. The /board endpoint is intentionally retained for ONE
# release as a 410 Gone shim so any in-flight frontend that still
# tries to POST a board snapshot fails loudly with a clear message
# instead of mysteriously appearing to succeed. Remove this shim
# after one release if no client logs reference it.
@app.post("/api/run/{run_id}/board")
async def update_board_gone(run_id: str):  # noqa: ARG001
    raise HTTPException(
        status_code=410,
        detail=(
            "The /board endpoint was removed when the 3D corridor manuscript "
            "was deleted. Use POST /api/run/{run_id}/pinboard or "
            "POST /api/run/{run_id}/pin instead. See "
            "context/game logic context/manuscript-as-artifact.md."
        ),
    )


# Phase 2.9 — Pinboard persistence.
#
# Two endpoints serve the pinboard:
#
#   POST /api/run/{id}/pin       — creates a single new pin.
#                                  Server classifies source_confidence
#                                  by reading the turn-log row for
#                                  source_turn_id (player-perspective).
#                                  Returns the full Pin object so the
#                                  frontend can render it immediately.
#
#   POST /api/run/{id}/pinboard  — bulk-update pins and/or
#                                  pin_connections. Both fields
#                                  optional; partial-update semantics
#                                  preserve whichever side is not sent.
#                                  Used by the frontend for drag
#                                  position updates and connection
#                                  add/cut events.
#
# Sanitization caps: 200 pins per run, 1000 connections per run. Pin
# text capped at 4000 chars (a long paragraph). Position clamped to
# [-50000, 50000] to keep absurd numbers out of the JSON blob without
# pinning the frontend to a particular coordinate scheme.

class PinCreateRequest(BaseModel):
    text: str
    source_turn_id: str = ""
    source_offset_start: int = 0
    source_offset_end: int = 0
    # Initial position on the panel. The frontend computes a default
    # if the player hasn't dragged the pin yet.
    x: float = 0.0
    y: float = 0.0


@app.post("/api/run/{run_id}/pin")
async def create_pin(run_id: str, req: PinCreateRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > 4000:
        text = text[:4000]

    async with _session_locks[run_id]:
        state = await _load_or_404(run_id)
        if len(state.pins or []) >= 200:
            raise HTTPException(
                status_code=400,
                detail="pinboard is full (200 pin cap)",
            )

        # Classify outside the obvious code paths -- if the lookup fails
        # for any reason we still write the pin with the conservative
        # default ("inferred"), so the player never loses a pin to a
        # transient lookup error.
        try:
            confidence, attribution = await classify_pin_source(
                text=text,
                run_id=run_id,
                source_turn_id=req.source_turn_id or "",
            )
        except Exception:
            confidence, attribution = "inferred", ""

        if confidence not in PIN_SOURCE_CONFIDENCES:
            confidence = "inferred"

        x = float(req.x) if math.isfinite(req.x) else 0.0
        y = float(req.y) if math.isfinite(req.y) else 0.0
        x = max(-50000.0, min(50000.0, x))
        y = max(-50000.0, min(50000.0, y))

        pin = Pin(
            text=text,
            x=x,
            y=y,
            source_turn_id=(req.source_turn_id or "")[:200],
            source_offset=PinSourceOffset(
                start=max(0, min(int(req.source_offset_start or 0), 1_000_000)),
                end=max(0, min(int(req.source_offset_end or 0), 1_000_000)),
            ),
            source_confidence=confidence,
            source_attribution=(attribution or "")[:200],
            created_at=time.time(),
        )
        state.pins = list(state.pins or []) + [pin]
        await save_session(state)
        return {"saved": True, "pin": pin.model_dump()}


class PinPositionUpdate(BaseModel):
    id: str
    x: float
    y: float


class PinConnectionUpdate(BaseModel):
    id: str = ""
    from_pin_id: str
    to_pin_id: str
    kind: str = "player"
    cut: bool = False
    label: str = ""


class PinboardUpdateRequest(BaseModel):
    # Both optional with partial-update semantics. Frontend may send
    # only a position update from a drag, only a new connection from
    # a connect-action, only a cut, etc.
    pin_positions: list[PinPositionUpdate] | None = None
    delete_pin_ids: list[str] | None = None
    pin_connections: list[PinConnectionUpdate] | None = None
    # Convenience: setting cut=true on existing connections by id.
    cut_connection_ids: list[str] | None = None


@app.post("/api/run/{run_id}/pinboard")
async def update_pinboard(run_id: str, req: PinboardUpdateRequest):
    async with _session_locks[run_id]:
        state = await _load_or_404(run_id)
        pins = list(state.pins or [])
        connections = list(state.pin_connections or [])

        # ── Pin position updates ─────────────────────────────────────
        if req.pin_positions is not None:
            by_id = {p.id: p for p in pins}
            for upd in req.pin_positions[:200]:  # cap incoming entries
                if not isinstance(upd.id, str):
                    continue
                target = by_id.get(upd.id)
                if target is None:
                    continue
                if not math.isfinite(upd.x) or not math.isfinite(upd.y):
                    continue
                target.x = max(-50000.0, min(50000.0, float(upd.x)))
                target.y = max(-50000.0, min(50000.0, float(upd.y)))

        # ── Pin deletions ────────────────────────────────────────────
        if req.delete_pin_ids is not None:
            doomed = set(req.delete_pin_ids[:200])
            pins = [p for p in pins if p.id not in doomed]
            # Connections that reference a deleted pin become orphans;
            # drop them so the client never tries to render an arrow
            # to a missing endpoint.
            connections = [
                c for c in connections
                if c.from_pin_id not in doomed and c.to_pin_id not in doomed
            ]

        # ── Connection upserts ───────────────────────────────────────
        if req.pin_connections is not None:
            by_id = {c.id: c for c in connections}
            seen_pair: set[tuple[str, str]] = {
                (c.from_pin_id, c.to_pin_id) for c in connections
            }
            valid_pin_ids = {p.id for p in pins}
            for upd in req.pin_connections[:1000]:
                fid = (upd.from_pin_id or "")[:200]
                tid = (upd.to_pin_id or "")[:200]
                if not fid or not tid or fid == tid:
                    continue
                if fid not in valid_pin_ids or tid not in valid_pin_ids:
                    # Orphan reference; refuse rather than write a
                    # connection that can never be rendered.
                    continue
                kind = upd.kind if upd.kind in PIN_CONNECTION_KINDS else "player"
                if upd.id and upd.id in by_id:
                    existing = by_id[upd.id]
                    existing.kind = kind
                    existing.cut = bool(upd.cut)
                    existing.label = (upd.label or "")[:200]
                else:
                    if (fid, tid) in seen_pair or (tid, fid) in seen_pair:
                        # No duplicate edges in either direction.
                        continue
                    if len(connections) >= 1000:
                        break
                    new_kwargs = {
                        "from_pin_id": fid,
                        "to_pin_id": tid,
                        "kind": kind,
                        "cut": bool(upd.cut),
                        "label": (upd.label or "")[:200],
                    }
                    # Honor a client-provided id only if it's a real
                    # string; otherwise let Pydantic generate one.
                    if upd.id:
                        new_kwargs["id"] = upd.id[:200]
                    connections.append(PinConnection(**new_kwargs))
                    seen_pair.add((fid, tid))

        # ── Mark cuts on existing connections by id ──────────────────
        if req.cut_connection_ids is not None:
            ids = set(req.cut_connection_ids[:1000])
            for c in connections:
                if c.id in ids:
                    c.cut = True

        state.pins = pins
        state.pin_connections = connections
        await save_session(state)
        return {
            "saved": True,
            "pin_count": len(pins),
            "connection_count": len(connections),
            "cut_count": sum(1 for c in connections if c.cut),
        }


# Phase 2.7 — instant inline inner thought.
#
# Fires from the frontend the moment the player hits Enter, in PARALLEL
# with the main /turn POST. Returns a single sentence in the character's
# voice. Renders under the input field while the rest of the turn loads.
#
# Why a separate endpoint and not folded into /turn:
#   - Latency. /turn does up to 12+ LLM calls (NPC POVs, ambient,
#     consequences). The inner thought needs to render in <1.5s; bundling
#     it into /turn would mean waiting for the whole simulation.
#   - Independent failure mode. If the thought call errors, we want the
#     turn to continue cleanly without the noise.
#   - The thought is informationally orthogonal to the turn outcome —
#     it's the player's reaction to their OWN action, not to what the
#     world does next. No reason to gate it behind world simulation.
#
# Cost: ~$0.0002 per call → ~€0.002 / 10-turn run, well under the cap.
# State changes: NONE. Read-only against the current state snapshot.
@app.post("/api/run/{run_id}/inner_thought")
async def inner_thought_endpoint(run_id: str, req: TurnRequest):
    state = await _load_or_404(run_id)
    if state.run_status not in {"active"}:
        return {"inner_thought": ""}
    text = (req.player_input or "").strip()
    if not text:
        return {"inner_thought": ""}
    thought = await generate_inner_thought(text, state)
    return {"inner_thought": thought}


async def _execute_turn(run_id: str, req: TurnRequest) -> dict:
    state = await _load_or_404(run_id)

    if state.run_status == "ended":
        raise HTTPException(403, "Run has ended")

    if state.run_status == "dead_observing":
        return await _handle_observation(state, req.player_input.strip())

    if state.run_status != "active":
        raise HTTPException(403, f"Run is '{state.run_status}'")

    _check_hard_cap_or_raise(state)

    text = req.player_input.strip()
    if not text:
        raise HTTPException(400, "Empty input")

    state_before = state.model_dump()

    with track_turn_cost() as bucket:
        # --- Step 1: World simulates (NPCs act autonomously) ---
        state, ambient = await simulate_turn(state)

        # --- Step 2: Parse player action ---
        parsed = await parse_action(text, state)

        if parsed.get("is_travel") and parsed.get("destination"):
            return await _handle_travel(state, parsed, ambient, text, state_before, bucket)

        if parsed.get("is_inaction"):
            return await _handle_inaction(state, parsed, ambient, text, state_before, bucket)

        # --- Step 3: Apply player action ---
        state = apply_action(state, parsed)

        # --- Step 3b: Schedule consequences from significant actions ---
        sig = parsed.get("significance_score", 0.0)
        if sig >= 0.5:
            _schedule_player_consequences(state, parsed)

        # --- Step 3c: Check for historical divergence ---
        divergences_before = len(state.historical_divergences)
        if sig >= 0.6:
            await _check_historical_divergence(state, parsed)
        new_divergences = [
            {
                "canonical_event": d["canonical_event"],
                "player_action": d["player_action"],
                "significance": sig,
                "superseded": True,
            }
            for d in state.historical_divergences[divergences_before:]
        ]

        # --- Step 4: Death check ---
        death_result = await check_death(state, parsed)

        # --- Step 5: Generate NPC reactions to player (selective) ---
        relevant = _filter_relevant(
            npcs_near_player(state),
            parsed.get("npc_impacts", []),
            target=parsed.get("target"),
        )
        addressed_npc, ambient_npcs = _split_addressed(relevant, parsed, state)

        # Addressed NPC (if any) gets a direct-reply call; ambient NPCs get POV.
        pov_tasks = []
        task_npcs = []
        if addressed_npc:
            pov_tasks.append(
                generate_npc_addressed(
                    addressed_npc, parsed, state,
                    player_input=text,
                    this_turn_events=ambient,
                )
            )
            task_npcs.append((addressed_npc, "addressed"))
        for npc in ambient_npcs:
            pov_tasks.append(generate_npc_pov(npc, parsed, state, this_turn_events=ambient))
            task_npcs.append((npc, "ambient"))

        all_results = await asyncio.gather(*pov_tasks, return_exceptions=True)
        npc_responses = _build_npc_responses_mixed(task_npcs, all_results)
        _store_povs_mixed(state, task_npcs, all_results)

        death_info = death_result if death_result["died"] else None
        if death_result["died"]:
            state = apply_death(state, death_result["cause"])

        trigger_log = await _check_and_record_illustration_trigger(
            state,
            parsed=parsed,
            death_info=death_info,
            new_divergences=new_divergences,
        )
        turn_cost_usd = _finalize_turn_cost(state, bucket)

    await save_session(state)

    pv = build_player_view(state, run_id)
    narrative = build_narrative_output(ambient, parsed, npc_responses, death=death_info)
    await append_turn_log(
        run_id=run_id, turn_number=state.turn, player_input=text,
        parsed_action=parsed, ambient_activity=ambient,
        npc_responses=npc_responses,
        state_changes=compute_state_diff(state_before, state.model_dump()),
        narrative_output=narrative,
        player_view_snapshot=pv.model_dump(),
        illustration_trigger=trigger_log,
        turn_cost_usd=turn_cost_usd,
    )

    return {
        "ambient_activity": ambient,
        "parsed_action": parsed,
        "player_view": pv.model_dump(),
        "npc_responses": npc_responses,
        "death": death_info,
        "divergences": new_divergences,
    }


# ------------------------------------------------------------------
# Skip / time advance
# ------------------------------------------------------------------

class SkipRequest(BaseModel):
    ticks: int = 1


@app.post("/api/run/{run_id}/skip")
async def skip_turns(run_id: str, req: SkipRequest):
    async with _session_locks[run_id]:
        return await _execute_skip(run_id, req)


async def _execute_skip(run_id: str, req: SkipRequest) -> dict:
    state = await _load_or_404(run_id)

    if state.run_status != "active":
        raise HTTPException(403, f"Run is '{state.run_status}'")

    _check_hard_cap_or_raise(state)

    ticks = max(1, min(30, req.ticks))
    state_before = state.model_dump()

    with track_turn_cost() as bucket:
        state = await advance_world_skip(state, ticks=ticks)

        nearby = npcs_near_player(state)
        player_loc = get_player_location(state)

        regrounding = (
            f"Time passes. It is now year {state.current_year} AD. "
            f"You are in {player_loc.name}. "
        )
        if nearby:
            npc_names = ", ".join(n.name for n in nearby[:3])
            regrounding += f"{npc_names} {'is' if len(nearby[:3]) == 1 else 'are'} nearby."
        else:
            regrounding += "The area seems quiet."

        trigger_log = await _check_and_record_illustration_trigger(state)
        turn_cost_usd = _finalize_turn_cost(state, bucket)

    await save_session(state)

    pv = build_player_view(state, run_id)
    narrative = build_narrative_output([], {"action_type": "skip", "era_description": regrounding}, [])
    await append_turn_log(
        run_id=run_id, turn_number=state.turn,
        player_input=f"[skip {ticks} turns]",
        parsed_action={"action_type": "skip", "ticks": ticks},
        ambient_activity=[], npc_responses=[],
        state_changes=compute_state_diff(state_before, state.model_dump()),
        narrative_output=narrative,
        player_view_snapshot=pv.model_dump(),
        illustration_trigger=trigger_log,
        turn_cost_usd=turn_cost_usd,
    )

    return {
        "ticks_advanced": ticks,
        "regrounding": regrounding,
        "player_view": pv.model_dump(),
    }


# ------------------------------------------------------------------
# NPC perception (hover)
# ------------------------------------------------------------------

@app.get("/api/run/{run_id}/npc/{npc_id}/perception")
async def npc_perception(run_id: str, npc_id: str):
    state = await _load_or_404(run_id)
    npc = next((n for n in state.npcs if n.id == npc_id), None)
    if not npc:
        raise HTTPException(404, f"NPC '{npc_id}' not found")

    raw_template = load_prompt(_NPC_PERCEPTION_PATH)
    from backend.world_state import build_story_summary

    mem_level = "vivid" if npc.memory_of_player > 0.7 else (
        "faint" if npc.memory_of_player > 0.3 else "barely remember them"
    )

    prompt = Template(raw_template).safe_substitute(
        player_name=state.player.name,
        player_role=state.player.role,
        player_description=state.player.description,
        player_disposition=state.player.disposition,
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        relationship_to_player=npc.relationship_to_player,
        memory_level=mem_level,
        story_so_far=build_story_summary(state),
    )

    # Read-only endpoint; wrap in a local bucket so ContextVar warnings
    # don't fire. The cost (FAST tier = $0) is intentionally not added
    # to state.cumulative_cost_usd — this endpoint does not advance the
    # world or mutate state.
    with track_turn_cost():
        try:
            text, _ = await call_llm(
                prompt,
                tier="fast",
                call_site="npc_perception",
            )
            if leaks_raw_numbers(text):
                text = scrub_leaked_numbers(text)
        except Exception:
            text = f"You are not sure what to make of {npc.name}."

    return {"npc_id": npc.id, "npc_name": npc.name, "perception": text}


# ------------------------------------------------------------------
# Historical context (highlight a sentence)
# ------------------------------------------------------------------

class ContextRequest(BaseModel):
    text: str
    era_name: str = ""
    year: int = 0

@app.post("/api/run/{run_id}/context")
async def explain_context(run_id: str, req: ContextRequest):
    state = await _load_or_404(run_id)
    snippet = req.text.strip()[:500]
    if not snippet:
        raise HTTPException(400, "No text provided")

    era = state.era.name
    year = state.current_year or state.era.year_start

    prompt = (
        f"You are a concise historical narrator for a game set in {era}, {year} AD. "
        f"The player highlighted this passage:\n\n\"{snippet}\"\n\n"
        f"In 2-3 sentences, explain the real historical context behind what is described. "
        f"Be specific about real people, places, or events referenced. "
        f"Do not repeat the passage. Do not use modern language. Stay in the voice of a scholarly chronicler."
    )

    with track_turn_cost():
        try:
            text, _ = await call_llm(
                prompt,
                tier="fast",
                call_site="historical_context",
            )
        except Exception:
            text = "The archives offer no further illumination on this matter."

    return {"context": text}


# ------------------------------------------------------------------
# Region knowledge (map click)
# ------------------------------------------------------------------

class RegionKnowledge(BaseModel):
    polity_name: str
    known_facts: list
    rumors: list
    ignorance_acknowledged: bool
    character_note: str

_REGION_KNOWLEDGE_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "region_knowledge.md"
)


@app.get("/api/run/{run_id}/region/{polity_name}")
async def region_knowledge(run_id: str, polity_name: str):
    state = await _load_or_404(run_id)

    year = state.current_year or state.era.year_start
    try:
        raw_events = await query_historical_events(
            year_start=year - 25, year_end=year + 5, region=polity_name,
        )
    except Exception:
        raw_events = []

    filtered = filter_historical_events(raw_events, state)

    _SIG_ORDER = {"civilizational": 0, "regional": 1, "local": 2}
    filtered.sort(key=lambda ev: (_SIG_ORDER.get(ev.significance, 9), -ev.year))
    _MAX_REGION_EVENTS = 12
    capped = filtered[:_MAX_REGION_EVENTS]

    known_facts = [
        ev.event for ev in capped
        if ev.knowledge_quality in ("witnessed", "known")
    ]
    rumors = [
        ev.event for ev in capped
        if ev.knowledge_quality.startswith("rumor")
    ]

    tier = _knowledge_tier(state.player.archetype)
    ignorance = len(known_facts) == 0 and tier == "low"

    character_note = ""
    with track_turn_cost():
        try:
            raw_template = load_prompt(_REGION_KNOWLEDGE_PROMPT_PATH)
            player_loc = get_player_location(state)
            prompt = Template(raw_template).safe_substitute(
                character_name=state.player.name,
                character_role=state.player.role,
                character_archetype=state.player.archetype,
                location_name=player_loc.name,
                year=year,
                era_description=state.era.description,
                region_name=polity_name,
                known_facts="\n".join(f"- {f}" for f in known_facts) or "Nothing specific.",
                rumors="\n".join(f"- {r}" for r in rumors) or "No rumors heard.",
            )
            character_note, _ = await call_llm(
                prompt,
                tier="fast",
                call_site="region_knowledge",
            )
            character_note = character_note.strip().split("\n")[0][:200]
        except Exception:
            character_note = f"You know little of {polity_name}."

    return RegionKnowledge(
        polity_name=polity_name,
        known_facts=known_facts,
        rumors=rumors,
        ignorance_acknowledged=ignorance,
        character_note=character_note,
    ).model_dump()


# ------------------------------------------------------------------
# Visible events for map (knowledge-filtered + geocoded)
# ------------------------------------------------------------------

# Forward-looking buffer (years). Keeps short-horizon "things just
# about to happen in your era" eligible — historical-record events
# dated slightly after the current turn the player could plausibly
# hear forewarning about, and that absorb time-skips cleanly.
_VISIBLE_EVENTS_WINDOW_AFTER = 5

# Floor used when birth_year is unset or sentinel (e.g. test sessions
# created without going through character_gen). Roughly an adult
# lifetime in pre-modern eras.
_VISIBLE_EVENTS_LIFETIME_FALLBACK = 50

# Significance levels we consider important enough to render as map
# pins. Local-significance events (a vizier in Mecca being assassinated
# while the player is in Florence in 1416) are real history but they
# are noise on a player-facing map.
_VISIBLE_EVENT_SIGNIFICANCE = frozenset({"civilizational", "regional"})

# For dense eras like Fall of Constantinople, even civilizational+
# regional produces hundreds of pins because the era's region is
# heavily documented. Civilizational events are world-historical
# (Sack of Rome, Black Death, fall of Constantinople) and stay
# globally visible. Regional events are pruned to the player's own
# era region — the Greek living in Constantinople in 1453 hears
# Mediterranean / Byzantine / Balkan news, not the latest from
# Hungary or Lombardy.
_REGION_STOPWORDS = frozenset({
    "and", "the", "of", "or", "at", "in", "to", "with",
    "empire", "kingdom", "republic", "duchy", "state", "states",
    "frontier", "region", "area",
})

# Historical naming variants. The events DB uses Latin and English
# names interchangeably ("Italia" vs "Italy", "Byzantium" vs
# "Byzantine"). Each token in this map normalizes to a canonical form
# so a Northern Italian player at year 1348 sees "Italia"-tagged
# events as in-region. New eras and event sources should add here.
_REGION_ALIASES = {
    "italy": "italia", "italian": "italia",
    "byzantium": "byzantine",
    "francia": "france", "frankish": "france", "gaul": "france", "gallia": "france",
    "germany": "germania", "german": "germania",
    "britain": "britannia", "british": "britannia", "english": "britannia", "england": "britannia",
    "spain": "hispania", "spanish": "hispania", "iberian": "hispania", "iberia": "hispania",
    "greek": "greece", "hellenic": "greece", "hellas": "greece",
    "nordic": "scandinavia", "scandinavian": "scandinavia",
    "palestine": "levant", "palestinian": "levant", "syria": "levant", "syrian": "levant",
    "minor": "anatolia",  # "Asia Minor" -> anatolia
    "europa": "europe", "european": "europe",
}


def _region_tokens(region: str) -> frozenset[str]:
    """Lowercase keyword set for fuzzy region overlap matching, with
    historical-naming aliases applied so Italia/Italy etc collapse."""
    if not region:
        return frozenset()
    cleaned = []
    for ch in region.lower():
        if ch.isalpha() or ch.isspace():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = "".join(cleaned).split()
    out: set[str] = set()
    for t in tokens:
        if not t or t in _REGION_STOPWORDS:
            continue
        out.add(_REGION_ALIASES.get(t, t))
    return frozenset(out)


def _event_in_player_region(event_region: str, era_region: str) -> bool:
    """True if the event's region shares at least one meaningful keyword
    with the era's home region. Used only for regional-significance
    pruning; civilizational events bypass this check."""
    a = _region_tokens(event_region)
    b = _region_tokens(era_region)
    if not a or not b:
        return False
    return bool(a & b)


def _visible_events_window_before(state: WorldState) -> int:
    """How far back to look. Defaults to the player character's lifetime
    so the map shows "things you grew up hearing about", not 50 years
    of ambient background news.
    """
    year = state.current_year or state.era.year_start
    by = state.player.birth_year
    if by and by > 0 and year >= by:
        return max(1, year - by)
    return _VISIBLE_EVENTS_LIFETIME_FALLBACK


def _era_key_for_state(state: WorldState) -> str:
    """Reverse-lookup era_key from state.era.name. Defaults to first key."""
    for key, cfg in ALL_ERAS.items():
        if cfg["name"] == state.era.name:
            return key
    return next(iter(ALL_ERAS.keys()))


@app.get("/api/run/{run_id}/events/visible")
async def events_visible(run_id: str):
    """Knowledge-filtered historical events with resolved coordinates.

    Used by the map to render event markers.  Per-turn recompute (no
    cache): the player's knowledge changes as they travel.

    Events are filtered through the Knowledge Matrix
    (filter_historical_events); `unknown`-tier events are omitted at
    that layer.  Events whose `region` does not resolve to a
    centroid are also omitted — no pin we could plausibly render.
    """
    from backend.geo.centroids import (
        resolve_region,
        resolve_event_location,
        jitter_point,
    )

    state = await _load_or_404(run_id)
    year = state.current_year or state.era.year_start
    window_before = _visible_events_window_before(state)

    try:
        raw_events = await query_historical_events(
            year_start=year - window_before,
            year_end=year + _VISIBLE_EVENTS_WINDOW_AFTER,
            region=state.era.region,
        )
        # Widen to all regions if region-scoped query is empty — matches
        # HCE behavior and ensures we show what the character could
        # plausibly hear from abroad.
        if not raw_events:
            raw_events = await query_historical_events(
                year_start=year - window_before,
                year_end=year + _VISIBLE_EVENTS_WINDOW_AFTER,
            )
    except Exception as exc:
        logger.warning("events/visible: DB query failed: %s", exc)
        raw_events = []

    # Build a quick id lookup so we can carry the DB id through the
    # HistoricalEventView layer (which doesn't expose it).
    id_by_sig = {
        (ev.get("year"), ev.get("event"), ev.get("region")): ev.get("id")
        for ev in raw_events
    }

    filtered = filter_historical_events(raw_events, state)

    out: list[dict] = []
    for ev_view in filtered:
        # Map only surfaces big history. Local-significance events
        # (assassinations of distant viziers, minor city ordinances)
        # remain in the DB for the HCE / NPC-grounding pipelines but
        # are filtered out of the player-facing pin layer.
        if ev_view.significance not in _VISIBLE_EVENT_SIGNIFICANCE:
            continue
        # Regional-significance events are further constrained to the
        # player's era region. Civilizational events bypass this check
        # because they are by definition world-historical news that
        # propagates everywhere.
        if ev_view.significance == "regional":
            if not _event_in_player_region(
                ev_view.region or "", state.era.region or "",
            ):
                continue
        # Per-event placement: try to land near a specific city or
        # named place mentioned in the event text, and fall back to
        # the region centroid otherwise. Then apply a small
        # deterministic jitter so events that share a centroid don't
        # stack as one pixel.
        centroid = resolve_event_location(ev_view.region, ev_view.event)
        if centroid is None:
            continue
        ev_id = id_by_sig.get((ev_view.year, ev_view.event, ev_view.region))
        jitter_key = str(ev_id) if ev_id is not None else (
            f"{ev_view.year}|{ev_view.event[:60]}|{ev_view.region}"
        )
        jlat, jlon = jitter_point(
            centroid["lat"], centroid["lon"], jitter_key, centroid["radius_km"],
        )
        out.append({
            "id": ev_id,
            "year": ev_view.year,
            "type": ev_view.event_type,
            "significance": ev_view.significance,
            "tier": ev_view.knowledge_quality,
            "accuracy": ev_view.accuracy,
            "lat": jlat,
            "lon": jlon,
            "radius_km": centroid["radius_km"],
            "broad": centroid["broad"],
            "summary": ev_view.event,
            "region": ev_view.region or "",
        })

    return {
        "era_key": _era_key_for_state(state),
        "events": out,
    }


# ------------------------------------------------------------------
# Player-centric NPC interaction graph (read-only visualization)
#
# Computed from existing state — no new tracking infrastructure, no
# LLM calls, no schema changes. Per-run, per-character snapshot used
# by the frontend Connections page (frontend/graph.js).
#
# Node selection: every NPC with at least one entry in
# npc.player_interactions OR who matches (by name/role substring,
# case-insensitive — same rule as world_state._apply_target_fallback)
# the target field of any entry in state.events. Avoids surfacing
# every NPC at every location the player passed through.
# ------------------------------------------------------------------

# Sentiment vocabulary derives from the canonical action types in
# action_parser._CANONICAL_TYPES. Hostile set is reused verbatim from
# scene_triggers._HOSTILE_ACTION_TYPES so we don't drift. Prosocial
# includes both peaceful (speak/trade) and formal/triumphant
# (petition/negotiate/alliance/defend/save/prevent) actions —
# defending an NPC is positive from the player's POV.
_GRAPH_HOSTILE_ACTIONS = frozenset({
    "attack", "threaten", "betray", "steal", "fight", "siege",
})
_GRAPH_POSITIVE_ACTIONS = frozenset({
    "speak", "trade", "petition", "negotiate", "alliance",
    "defend", "save", "prevent",
})


def _graph_sentiment_for(action_type: str) -> str:
    at = (action_type or "").lower()
    if at in _GRAPH_HOSTILE_ACTIONS:
        return "negative"
    if at in _GRAPH_POSITIVE_ACTIONS:
        return "positive"
    return "neutral"


def _graph_memory_label(memory: float) -> str:
    """Mirror the bucketing used by /api/run/{id}/npc/{id}/perception."""
    if memory > 0.7:
        return "vivid"
    if memory > 0.3:
        return "faint"
    return "barely remember"


def _graph_npc_matches_event_target(npc, target_raw: str) -> bool:
    """Mirror world_state._apply_target_fallback's matching rule."""
    if not target_raw:
        return False
    t = target_raw.lower()
    return t in npc.name.lower() or t in npc.role.lower()


@app.get("/api/run/{run_id}/interaction_graph")
async def interaction_graph(run_id: str):
    state = await _load_or_404(run_id)

    targets_in_events = {
        (ev.target or "").lower()
        for ev in state.events
        if ev.target
    }
    targets_in_events.discard("")

    nodes: list[dict] = []
    # Map id -> set of turns the player engaged with this NPC. Used
    # below to derive NPC<->NPC "witnessed-together" edges. Stays
    # loyal to the design rule "information through interaction":
    # the player only sees a connection between two NPCs if they
    # personally walked into a turn that engaged both at once.
    turns_by_npc: dict[str, set[int]] = {}

    for npc in state.npcs:
        has_recorded = bool(npc.player_interactions)
        matches_event = any(
            _graph_npc_matches_event_target(npc, t)
            for t in targets_in_events
        )
        if not (has_recorded or matches_event):
            continue

        interactions = []
        npc_turns: set[int] = set()
        for entry in npc.player_interactions:
            action_type = entry.get("action_type", "other")
            t = int(entry.get("turn", 0) or 0)
            if t > 0:
                npc_turns.add(t)
            interactions.append({
                "turn": t,
                "year": entry.get("year", 0),
                "action_type": action_type,
                "intent": entry.get("intent", ""),
                "sentiment": _graph_sentiment_for(action_type),
            })
        turns_by_npc[npc.id] = npc_turns

        nodes.append({
            "id": npc.id,
            "name": npc.name,
            "archetype": npc.archetype or "",
            "role": npc.role,
            "memory_of_player": round(npc.memory_of_player, 3),
            "memory_label": _graph_memory_label(npc.memory_of_player),
            "disposition": npc.disposition,
            "last_interaction_turn": npc.last_interaction_turn,
            "interactions": interactions,
            "interaction_count": len(interactions),
        })

    # Witnessed NPC<->NPC links: any pair of nodes whose recorded
    # player_interactions share at least one turn number. shared_turns
    # lets the frontend scale edge weight by how often the player saw
    # them together.
    npc_links: list[dict] = []
    ids = [n["id"] for n in nodes]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            shared = sorted(turns_by_npc.get(a, set()) & turns_by_npc.get(b, set()))
            if shared:
                npc_links.append({
                    "source": a,
                    "target": b,
                    "shared_turns": shared,
                    "weight": len(shared),
                })

    return {
        "run_id": run_id,
        "year": state.current_year or state.era.year_start,
        "turn": state.turn,
        "player": {
            "id": state.player.id,
            "name": state.player.name,
            "archetype": state.player.archetype or "",
            "role": state.player.role,
        },
        "nodes": nodes,
        "npc_links": npc_links,
    }


# ------------------------------------------------------------------
# Turn handlers
# ------------------------------------------------------------------

async def _handle_inaction(
    state: WorldState, parsed: dict, ambient: list,
    player_input: str = "", state_before: dict = None,
    cost_bucket: list | None = None,
) -> dict:
    auto = await player_skip_turn(state)
    auto["era_description"] = parsed.get("era_description") or auto.get("era_description", "")
    state = apply_action(state, auto)
    death_result = await check_death(state, auto)

    death_info = death_result if death_result["died"] else None
    if death_result["died"]:
        state = apply_death(state, death_result["cause"])

    trigger_log = await _check_and_record_illustration_trigger(
        state, parsed=auto, death_info=death_info,
    )
    turn_cost_usd = (
        _finalize_turn_cost(state, cost_bucket) if cost_bucket is not None else 0.0
    )
    await save_session(state)

    pv = build_player_view(state, state.run_id)
    narrative = build_narrative_output(ambient, auto, [], death=death_info)
    if state_before is not None:
        await append_turn_log(
            run_id=state.run_id, turn_number=state.turn,
            player_input=player_input, parsed_action=auto,
            ambient_activity=ambient, npc_responses=[],
            state_changes=compute_state_diff(state_before, state.model_dump()),
            narrative_output=narrative,
            player_view_snapshot=pv.model_dump(),
            illustration_trigger=trigger_log,
            turn_cost_usd=turn_cost_usd,
        )

    return {
        "ambient_activity": ambient,
        "parsed_action": auto,
        "player_view": pv.model_dump(),
        "npc_responses": [],
        "death": death_info,
    }


async def _handle_travel(
    state: WorldState, parsed: dict, ambient: list,
    player_input: str = "", state_before: dict = None,
    cost_bucket: list | None = None,
) -> dict:
    dest_id = parsed["destination"].lower().strip()
    player_loc = get_player_location(state)

    if dest_id not in player_loc.neighbors:
        state = apply_action(state, parsed)
        trigger_log = await _check_and_record_illustration_trigger(
            state, parsed=parsed,
        )
        turn_cost_usd = (
            _finalize_turn_cost(state, cost_bucket) if cost_bucket is not None else 0.0
        )
        await save_session(state)
        pv = build_player_view(state, state.run_id)
        narrative = build_narrative_output(ambient, parsed, [])
        if state_before is not None:
            await append_turn_log(
                run_id=state.run_id, turn_number=state.turn,
                player_input=player_input, parsed_action=parsed,
                ambient_activity=ambient, npc_responses=[],
                state_changes=compute_state_diff(state_before, state.model_dump()),
                narrative_output=narrative,
                player_view_snapshot=pv.model_dump(),
                illustration_trigger=trigger_log,
                turn_cost_usd=turn_cost_usd,
            )
        return {
            "ambient_activity": ambient,
            "parsed_action": parsed,
            "player_view": pv.model_dump(),
            "npc_responses": [],
            "death": None,
        }

    travel_turns = player_loc.neighbors[dest_id]
    state = await advance_world(state, ticks=travel_turns)

    state.player.location = dest_id
    if dest_id not in state.visited_locations:
        state.visited_locations.append(dest_id)

    try:
        from backend.hce import generate_ground_context
        state.ground_context = await generate_ground_context(state)
        state.ground_context_stale = False
        logger.info("Ground context refreshed on arrival at %s", dest_id)
    except Exception as exc:
        logger.warning("Ground context refresh on arrival failed: %s", exc)
        state.ground_context_stale = True

    try:
        dest_name = get_location(state, dest_id).name
    except ValueError:
        dest_name = dest_id

    state.events.append(Event(
        turn=state.turn,
        action_type="travel",
        description=f"{state.player.name} travels from {player_loc.name} to {dest_name}, arriving after {travel_turns} turns.",
        target=dest_id,
        location=dest_id,
    ))

    arrival_action = {
        "action_type": "arrival",
        "target": dest_name,
        "intent": f"Arrived in {dest_name}",
        "era_description": parsed.get("era_description", f"{state.player.name} arrives in {dest_name}."),
    }

    nearby = npcs_near_player(state)
    arrival_povs = []
    if nearby:
        pov_tasks = [generate_npc_pov(npc, arrival_action, state, this_turn_events=ambient) for npc in nearby[:3]]
        pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)
        arrival_povs = _build_npc_responses(nearby[:3], pov_results)
        _store_povs(state, nearby[:3], pov_results)

    trigger_log = await _check_and_record_illustration_trigger(
        state, parsed=parsed,
    )
    turn_cost_usd = (
        _finalize_turn_cost(state, cost_bucket) if cost_bucket is not None else 0.0
    )
    await save_session(state)

    pv = build_player_view(state, state.run_id)
    travel_info = {"from": player_loc.name, "to": dest_name, "turns_spent": travel_turns}
    narrative = build_narrative_output(
        ambient, parsed, arrival_povs, travel=travel_info,
    )
    if state_before is not None:
        await append_turn_log(
            run_id=state.run_id, turn_number=state.turn,
            player_input=player_input, parsed_action=parsed,
            ambient_activity=ambient, npc_responses=arrival_povs,
            state_changes=compute_state_diff(state_before, state.model_dump()),
            narrative_output=narrative,
            player_view_snapshot=pv.model_dump(),
            illustration_trigger=trigger_log,
            turn_cost_usd=turn_cost_usd,
        )

    return {
        "ambient_activity": ambient,
        "parsed_action": parsed,
        "player_view": pv.model_dump(),
        "npc_responses": arrival_povs,
        "travel": travel_info,
        "death": None,
    }


async def _handle_observation(state: WorldState, text: str) -> dict:
    # Observation mode still burns tokens (NPC actions, memory-fade, erasure).
    # The hard cap applies — a run capped at €2 stays frozen until the player
    # ends it manually via DELETE /api/run/{run_id}.
    _check_hard_cap_or_raise(state)

    state_before = state.model_dump()
    parsed = await parse_action(text, state)
    state = state.model_copy(deep=True)

    with track_turn_cost() as bucket:
        if parsed.get("is_travel") and parsed.get("destination"):
            dest_id = parsed["destination"].lower().strip()
            player_loc = get_player_location(state)
            if dest_id in player_loc.neighbors:
                travel_turns = player_loc.neighbors[dest_id]
                state = await advance_world(state, ticks=travel_turns)
                for _ in range(travel_turns):
                    state = decay_memories(state)
                if state.run_status == "ended":
                    erasure_text = await generate_erasure(state)
                    state.player.location = dest_id
                    trigger_log = await _check_and_record_illustration_trigger(
                        state, parsed=parsed,
                    )
                    turn_cost_usd = _finalize_turn_cost(state, bucket)
                    await save_session(state)
                    pv = build_player_view(state, state.run_id)
                    narrative = build_narrative_output([], parsed, [], erasure=erasure_text)
                    await append_turn_log(
                        run_id=state.run_id, turn_number=state.turn,
                        player_input=text, parsed_action=parsed,
                        ambient_activity=[], npc_responses=[],
                        state_changes=compute_state_diff(state_before, state.model_dump()),
                        narrative_output=narrative,
                        player_view_snapshot=pv.model_dump(),
                        illustration_trigger=trigger_log,
                        turn_cost_usd=turn_cost_usd,
                    )
                    return {"erasure": erasure_text, "player_view": pv.model_dump()}
                state.player.location = dest_id
                if dest_id not in state.visited_locations:
                    state.visited_locations.append(dest_id)
                try:
                    from backend.hce import generate_ground_context
                    state.ground_context = await generate_ground_context(state)
                    state.ground_context_stale = False
                except Exception:
                    state.ground_context_stale = True
                fade_text = await generate_memory_fade(state)
                trigger_log = await _check_and_record_illustration_trigger(
                    state, parsed=parsed,
                )
                turn_cost_usd = _finalize_turn_cost(state, bucket)
                await save_session(state)
                pv = build_player_view(state, state.run_id)
                narrative = build_narrative_output([], parsed, [])
                await append_turn_log(
                    run_id=state.run_id, turn_number=state.turn,
                    player_input=text, parsed_action=parsed,
                    ambient_activity=[], npc_responses=[],
                    state_changes=compute_state_diff(state_before, state.model_dump()),
                    narrative_output=narrative,
                    player_view_snapshot=pv.model_dump(),
                    illustration_trigger=trigger_log,
                    turn_cost_usd=turn_cost_usd,
                )
                return {
                    "ambient_activity": [],
                    "parsed_action": parsed,
                    "player_view": pv.model_dump(),
                    "npc_responses": [],
                    "death": None,
                    "memory_fade": fade_text,
                }

        # World keeps moving even after death — run full simulation
        state, ambient = await simulate_turn(state)
        state = decay_memories(state)

        # Generate fade framing
        fade_text = await generate_memory_fade(state)

        if state.run_status == "ended":
            erasure_text = await generate_erasure(state)
            trigger_log = await _check_and_record_illustration_trigger(
                state, parsed=parsed,
            )
            turn_cost_usd = _finalize_turn_cost(state, bucket)
            await save_session(state)
            pv = build_player_view(state, state.run_id)
            narrative = build_narrative_output(ambient, parsed, [], erasure=erasure_text)
            await append_turn_log(
                run_id=state.run_id, turn_number=state.turn,
                player_input=text, parsed_action=parsed,
                ambient_activity=ambient, npc_responses=[],
                state_changes=compute_state_diff(state_before, state.model_dump()),
                narrative_output=narrative,
                player_view_snapshot=pv.model_dump(),
                illustration_trigger=trigger_log,
                turn_cost_usd=turn_cost_usd,
            )
            return {"erasure": erasure_text, "player_view": pv.model_dump()}

        trigger_log = await _check_and_record_illustration_trigger(
            state, parsed=parsed,
        )
        turn_cost_usd = _finalize_turn_cost(state, bucket)
        await save_session(state)
        pv = build_player_view(state, state.run_id)
        narrative = build_narrative_output(ambient, parsed, [])
        await append_turn_log(
            run_id=state.run_id, turn_number=state.turn,
            player_input=text, parsed_action=parsed,
            ambient_activity=ambient, npc_responses=[],
            state_changes=compute_state_diff(state_before, state.model_dump()),
            narrative_output=narrative,
            player_view_snapshot=pv.model_dump(),
            illustration_trigger=trigger_log,
            turn_cost_usd=turn_cost_usd,
        )
        return {
            "ambient_activity": ambient,
            "parsed_action": parsed,
            "player_view": pv.model_dump(),
            "npc_responses": [],
            "death": None,
            "memory_fade": fade_text,
        }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _filter_relevant(nearby_npcs, npc_impacts, target: str | None = None):
    """Select which NPCs receive a POV call this turn.

    Selection rules (in order):
      1. If parsed.target names an NPC in nearby_npcs, that NPC is ALWAYS
         included regardless of npc_impacts. The Addressed-mode upgrade in
         _split_addressed routes them through generate_npc_addressed; if the
         filter dropped them here, the upgrade could never fire.
      2. Otherwise, fall back to npc_impacts: NPCs marked relevant=True.
      3. Otherwise (no impacts or no relevant flags): the first 2 nearby NPCs.
    """
    target_npc = None
    if target:
        target_lower = target.lower().strip()
        if target_lower:
            target_npc = next(
                (n for n in nearby_npcs if target_lower in n.name.lower()),
                None,
            )

    def _ensure_target_first(npcs):
        """Make sure the addressed NPC is in the result and appears once."""
        if target_npc is None:
            return npcs
        result = [n for n in npcs if n.id != target_npc.id]
        return [target_npc, *result]

    if not npc_impacts:
        base = nearby_npcs[:2] if nearby_npcs else []
        return _ensure_target_first(base)

    relevant_names = set()
    has_relevant_field = False
    for impact in npc_impacts:
        if not isinstance(impact, dict):
            continue
        if "relevant" in impact:
            has_relevant_field = True
            if impact.get("relevant"):
                relevant_names.add((impact.get("name") or "").lower())

    if not has_relevant_field:
        base = nearby_npcs[:2] if nearby_npcs else []
        return _ensure_target_first(base)
    if not relevant_names:
        # Even if nothing is "relevant" per the parser, an explicitly named
        # target at the player's location should still get a reaction.
        return _ensure_target_first([])

    matched = [
        npc for npc in nearby_npcs
        if any(rn in npc.name.lower() for rn in relevant_names)
    ]
    return _ensure_target_first(matched)


def _split_addressed(relevant_npcs, parsed: dict, state):
    """Identify the addressed NPC (if any) and split off the ambient remainder.

    Returns (addressed_npc | None, [ambient_npcs]).

    Addressed mode fires when parsed.target is non-null and matches an NPC
    at the player's current location. All other relevant NPCs get Ambient mode.
    """
    target_raw = (parsed.get("target") or "").lower().strip()
    if not target_raw:
        return None, relevant_npcs

    addressed = None
    ambient = []
    player_loc = state.player.location
    for npc in relevant_npcs:
        if (
            addressed is None
            and npc.location == player_loc
            and target_raw in npc.name.lower()
        ):
            addressed = npc
        else:
            ambient.append(npc)

    return addressed, ambient


# Cap reduced 2026-05-01: stored_povs is no longer injected into prompts
# (Change 3 replaced it with player_actions_toward_you). The only remaining
# read is player_knowledge.py:512 -> VisibleNPCHere.last_pov, which exposes
# the most recent entry. Storing 10 served the deprecated prompt-injection
# pipeline; one entry is sufficient for the surviving consumer.
_MAX_STORED_POVS = 1


def _store_povs(state, npcs, pov_results):
    """Append generated POV text to each NPC's stored_povs. Cap at 1."""
    for npc, pov in zip(npcs, pov_results):
        if not isinstance(pov, str) or pov.startswith("["):
            continue
        target = next((n for n in state.npcs if n.id == npc.id), None)
        if target:
            target.stored_povs.append(pov)
            if len(target.stored_povs) > _MAX_STORED_POVS:
                target.stored_povs = target.stored_povs[-_MAX_STORED_POVS:]


def _store_povs_mixed(state, task_npcs, all_results):
    """Store POV text for both addressed and ambient results.

    Also extracts sensory grounding phrases from each successful POV
    (reply + internal for addressed mode; perspective for ambient) and
    merges them into state.used_grounding_details (FIFO-capped at 30).

    task_npcs: list of (npc, mode) where mode is "addressed" or "ambient".
    all_results: parallel list of LLM results (dict for addressed, str for ambient).
    """
    from backend.grounding_extractor import extract_grounding_details, merge_into_tracker

    for (npc, mode), result in zip(task_npcs, all_results):
        target = next((n for n in state.npcs if n.id == npc.id), None)
        if not target:
            continue
        if mode == "addressed" and isinstance(result, dict):
            primary_text = result.get("reply", "")
            secondary_text = result.get("internal") or ""
        elif mode == "ambient" and isinstance(result, str):
            primary_text = result
            secondary_text = ""
        else:
            continue

        if primary_text and not primary_text.startswith("["):
            target.stored_povs.append(primary_text)
            if len(target.stored_povs) > _MAX_STORED_POVS:
                target.stored_povs = target.stored_povs[-_MAX_STORED_POVS:]

        # Extract sensory grounding phrases from both reply and internal
        # thought, then merge into the run-level tracker (FIFO cap 30).
        for src in (primary_text, secondary_text):
            if not src or src.startswith("["):
                continue
            new_phrases = extract_grounding_details(src)
            if new_phrases:
                merge_into_tracker(state.used_grounding_details, new_phrases)


def _build_npc_responses_mixed(task_npcs, all_results):
    """Build npc_responses list from mixed addressed/ambient results.

    Addressed responses carry both 'pov' (the reply) and 'internal' (private thought).
    Ambient responses carry only 'pov'.
    """
    responses = []
    for (npc, mode), result in zip(task_npcs, all_results):
        if mode == "addressed":
            if isinstance(result, dict):
                reply = result.get("reply") or f"[{npc.name} says nothing]"
                internal = result.get("internal") or None
            else:
                reply = f"[{npc.name} says nothing]"
                internal = None
            responses.append({
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "pov": reply,
                "internal": internal,
                "mode": "addressed",
            })
        else:
            pov_text = result if isinstance(result, str) else f"[{npc.name} is silent]"
            responses.append({
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "pov": pov_text,
                "internal": None,
                "mode": "ambient",
            })
    return responses


def _build_npc_responses(npcs, pov_results):
    responses = []
    for npc, pov in zip(npcs, pov_results):
        pov_text = pov if isinstance(pov, str) else f"[{npc.name} is silent]"
        responses.append({
            "npc_id": npc.id,
            "npc_name": npc.name,
            "npc_role": npc.role,
            "pov": pov_text,
        })
    return responses


async def _load_or_404(run_id: str) -> WorldState:
    state = await load_session(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return state


async def _check_and_record_illustration_trigger(
    state: WorldState,
    *,
    parsed: dict | None = None,
    death_info: dict | None = None,
    new_divergences: list | None = None,
) -> dict | None:
    """Phase 3 Step 3.1 — Stage 6.5 trigger detection.

    Runs at every save-point across the five turn-advancing paths.
    On fire, appends a minimal entry to state.illustration_triggers_fired
    and returns the full log dict for turn_logs.illustration_trigger.

    Side effects in this helper:
      1. state.illustration_triggers_fired.append(...) on fire.
      2. state.previously_visited_locations = list(state.visited_locations)
         — ALWAYS, regardless of fire. End-of-turn snapshot so the next
         turn's first-arrival check has a stable prior state.

    Does NOT call save_session. The caller saves immediately after.
    """
    try:
        witnessed = await compute_witnessed_events_this_turn(state)
    except Exception as exc:
        logger.warning("witnessed-events query failed (non-fatal): %s", exc)
        witnessed = []

    trigger = check_illustration_trigger(
        state,
        parsed=parsed,
        death_info=death_info,
        new_divergences=new_divergences,
        witnessed_events_this_turn=witnessed,
    )

    log_dict: dict | None = None
    if trigger is not None:
        state.illustration_triggers_fired.append({
            "turn": state.turn,
            "type": trigger.type,
            "reason": trigger.reason,
        })
        log_dict = trigger.log_dict()
        logger.info(
            "illustration_trigger fired turn=%d run=%s type=%s tone=%s reason=%s",
            state.turn, state.run_id, trigger.type, trigger.tone_hint,
            trigger.reason,
        )

    # Always snapshot visited_locations for the NEXT turn's first-arrival
    # check. Mutating outside the trigger branch so the snapshot exists
    # even on no-fire turns.
    state.previously_visited_locations = list(state.visited_locations)
    return log_dict


def _schedule_player_consequences(state: WorldState, parsed: dict) -> None:
    """Schedule downstream consequences from a significant player action.

    Dispatch table routes each canonical action_type to specific
    consequences at sig >= 0.5.  Generic tiers (rumor at 0.6, tension
    at 0.8) layer on top for ALL types.

    Writes directly to state.consequence_queue (in-memory).
    """
    action_type = parsed.get("action_type", "other")
    target = parsed.get("target")
    sig = parsed.get("significance_score", 0.5)
    player_loc = state.player.location
    player_name = state.player.name
    era_desc = parsed.get("era_description", "something noteworthy")

    # --- Per-type specific consequences (sig >= 0.5) ---
    handler = _CONSEQUENCE_DISPATCH.get(action_type)
    if handler is not None:
        handler(state, action_type, target, sig, player_loc, player_name, era_desc)

    # --- Generic graduated tiers (all types) ---
    if sig >= 0.6:
        state.consequence_queue.append(ScheduledConsequence(
            trigger_turn=state.turn + 2,
            target_type="location", target_id=player_loc,
            effect_type="rumor",
            effect_payload={
                "rumor_text": f"People talk about what {player_name} did — {era_desc}.",
            },
        ))

    if sig >= 0.8:
        state.consequence_queue.append(ScheduledConsequence(
            trigger_turn=state.turn + 3,
            target_type="location", target_id=player_loc,
            effect_type="tension_shift",
            effect_payload={"delta": 1},
        ))


def _find_target_npc(state: WorldState, target: str):
    """Resolve a target string to an NPC, or None."""
    if not target:
        return None
    target_lower = target.lower()
    return next(
        (n for n in state.npcs if target_lower in n.name.lower()),
        None,
    )


def _cq_rumor_fallback(state, player_loc, player_name, era_desc):
    """Target-miss fallback: a rumor at player location.

    Replaces (does not stack with) the target-dependent specific
    consequence when the target string doesn't resolve to an NPC.
    Same density shape as the petition/hoard handlers.
    """
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 2,
        target_type="location", target_id=player_loc,
        effect_type="rumor",
        effect_payload={
            "rumor_text": f"People talk about what {player_name} did — {era_desc}.",
        },
    ))


def _cq_hostile(state, action_type, target, sig, player_loc, player_name, era_desc):
    """attack, threaten, steal: tension at target NPC's location.

    Target-miss fallback: rumor at player location.
    """
    target_npc = _find_target_npc(state, target)
    if target_npc is None:
        _cq_rumor_fallback(state, player_loc, player_name, era_desc)
        return
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="location", target_id=target_npc.location,
        effect_type="tension_shift",
        effect_payload={"delta": 1},
    ))


def _cq_betray(state, action_type, target, sig, player_loc, player_name, era_desc):
    """betray: tension at target location + disposition -1 on target.

    Target-miss fallback: rumor at player location. Inlined (not
    delegated to _cq_hostile) to avoid double-firing the fallback.
    """
    target_npc = _find_target_npc(state, target)
    if target_npc is None:
        _cq_rumor_fallback(state, player_loc, player_name, era_desc)
        return
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="location", target_id=target_npc.location,
        effect_type="tension_shift",
        effect_payload={"delta": 1},
    ))
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="npc", target_id=target_npc.id,
        effect_type="disposition_shift",
        effect_payload={"delta": -1},
    ))


def _cq_trade(state, action_type, target, sig, player_loc, player_name, era_desc):
    """trade, negotiate: event_spawn at player location."""
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 3,
        target_type="location", target_id=player_loc,
        effect_type="event_spawn",
        effect_payload={
            "description": f"The consequences of {player_name}'s {action_type} continue to unfold.",
            "location": player_loc,
            "action_type": "ambient",
        },
    ))


def _cq_petition(state, action_type, target, sig, player_loc, player_name, era_desc):
    """petition: rumor — petitions generate talk."""
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 2,
        target_type="location", target_id=player_loc,
        effect_type="rumor",
        effect_payload={
            "rumor_text": f"{player_name}'s petition is the talk of {next((l.name for l in state.locations if l.id == player_loc), 'the area')}.",
        },
    ))


def _cq_fight(state, action_type, target, sig, player_loc, player_name, era_desc):
    """fight: tension +1 at player location."""
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="location", target_id=player_loc,
        effect_type="tension_shift",
        effect_payload={"delta": 1},
    ))


def _cq_siege(state, action_type, target, sig, player_loc, player_name, era_desc):
    """siege: tension +1 immediately + trade disruption later."""
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="location", target_id=player_loc,
        effect_type="tension_shift",
        effect_payload={"delta": 1},
    ))
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 3,
        target_type="location", target_id=player_loc,
        effect_type="trade_disruption",
        effect_payload={
            "description": f"The siege disrupts trade at {next((l.name for l in state.locations if l.id == player_loc), 'the area')}.",
            "delta": 1,
        },
    ))


def _cq_event_spawn(state, action_type, target, sig, player_loc, player_name, era_desc):
    """alliance, defend, prevent: neutral event_spawn ripple."""
    delay = 3 if action_type == "alliance" else 2
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + delay,
        target_type="location", target_id=player_loc,
        effect_type="event_spawn",
        effect_payload={
            "description": f"The consequences of {player_name}'s actions continue to unfold.",
            "location": player_loc,
            "action_type": "ambient",
        },
    ))


def _cq_hoard(state, action_type, target, sig, player_loc, player_name, era_desc):
    """hoard: rumor — hoarding is the archetypal gossip trigger."""
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 2,
        target_type="location", target_id=player_loc,
        effect_type="rumor",
        effect_payload={
            "rumor_text": f"Someone has been hoarding goods in {next((l.name for l in state.locations if l.id == player_loc), 'the area')}. People are talking.",
        },
    ))


def _cq_save(state, action_type, target, sig, player_loc, player_name, era_desc):
    """save: disposition +1 on target NPC — saving creates a bond.

    Target-miss fallback: rumor at player location.
    """
    target_npc = _find_target_npc(state, target)
    if target_npc is None:
        _cq_rumor_fallback(state, player_loc, player_name, era_desc)
        return
    state.consequence_queue.append(ScheduledConsequence(
        trigger_turn=state.turn + 1,
        target_type="npc", target_id=target_npc.id,
        effect_type="disposition_shift",
        effect_payload={"delta": 1},
    ))


_CONSEQUENCE_DISPATCH: dict[str, callable] = {
    "betray":    _cq_betray,
    "attack":    _cq_hostile,
    "threaten":  _cq_hostile,
    "steal":     _cq_hostile,
    "trade":     _cq_trade,
    "negotiate": _cq_trade,
    "petition":  _cq_petition,
    "fight":     _cq_fight,
    "siege":     _cq_siege,
    "alliance":  _cq_event_spawn,
    "defend":    _cq_event_spawn,
    "prevent":   _cq_event_spawn,
    "hoard":     _cq_hoard,
    "save":      _cq_save,
}


async def _check_historical_divergence(state: WorldState, parsed: dict) -> None:
    """Detect if a significant player action contradicts canonical history.

    Uses keyword matching on action_type + location + year proximity.
    No LLM call — pure heuristic.
    """
    action_type = parsed.get("action_type", "")
    target = (parsed.get("target") or "").lower()
    player_loc = state.player.location
    year = state.current_year or state.era.year_start

    type_map = {
        "defend": "war", "attack": "war", "fight": "war", "siege": "war",
        "betray": "political", "negotiate": "political", "alliance": "political",
        "petition": "political", "threaten": "political",
        "trade": "economic", "hoard": "economic", "steal": "economic",
        "prevent": "war", "save": "war",
    }
    search_type = type_map.get(action_type)

    try:
        candidates = await query_historical_events(
            year_start=year - 5, year_end=year + 5,
            region=state.era.region,
            event_type=search_type,
        )

        if not candidates:
            candidates = await query_historical_events(
                year_start=year - 5, year_end=year + 5,
            )

        for ev in candidates:
            if not ev.get("canonical"):
                continue
            ev_text = ev.get("event", "").lower()
            if target and target in ev_text:
                divergence = {
                    "turn": state.turn,
                    "canonical_event_id": ev["id"],
                    "canonical_event": ev["event"],
                    "player_action": parsed.get("era_description", ""),
                    "action_type": action_type,
                }
                state.historical_divergences.append(divergence)
                mark_consequence_superseded_mem(state, str(ev["id"]))
                logger.info(
                    "Historical divergence: player action '%s' contradicts '%s'",
                    parsed.get("intent", ""), ev["event"],
                )
                break
    except Exception as exc:
        logger.warning("Divergence check failed (non-fatal): %s", exc)


# ------------------------------------------------------------------
# Static files
# ------------------------------------------------------------------

app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
