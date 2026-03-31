"""CHRONOS Phase 1 — FastAPI entry point."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.action_parser import parse_action
from backend.character_gen import generate_run
from backend.eras import ALL_ERAS, random_era
from backend.llm import ollama_ok
from backend.npc_engine import generate_npc_pov
from backend.persistence import (
    delete_session,
    init_db,
    list_sessions,
    load_session,
    save_session,
)
from backend.death_engine import apply_death, check_death, decay_memories, generate_erasure
from backend.world_engine import advance_world, player_skip_turn
from backend.world_state import (
    WorldState,
    apply_action,
    create_initial_state,
    get_location,
    get_player_location,
    npcs_near_player,
)

logger = logging.getLogger("chronos")

app = FastAPI(title="CHRONOS", version="0.1.0")


class TurnRequest(BaseModel):
    player_input: str


# ------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    await init_db()
    ok = await ollama_ok()
    if ok:
        logger.info("Ollama is reachable")
    else:
        logger.warning("Ollama is NOT reachable — LLM calls will fail")


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "phase": 1,
        "ollama": await ollama_ok(),
    }


# ------------------------------------------------------------------
# Run management
# ------------------------------------------------------------------

class RunRequest(BaseModel):
    era: str = ""


@app.post("/api/run")
async def new_run(req: RunRequest = RunRequest()):
    """Create a new game run. If era is empty, picks randomly.

    With Ollama running, generates characters via LLM.
    Without Ollama, falls back to the hardcoded test state.
    """
    if req.era and req.era in ALL_ERAS:
        era_key, era_config = req.era, ALL_ERAS[req.era]
    else:
        era_key, era_config = random_era()

    if await ollama_ok():
        state = await generate_run(era_config)
    else:
        logger.warning("Ollama down — using hardcoded initial state")
        state = create_initial_state()

    await save_session(state)
    return {"run_id": state.run_id, "era": era_key, "world_state": state.model_dump()}


@app.get("/api/runs")
async def get_runs():
    """List all saved runs."""
    return await list_sessions()


@app.get("/api/run/{run_id}")
async def get_run_state(run_id: str):
    state = await _load_or_404(run_id)
    return state.model_dump()


@app.delete("/api/run/{run_id}")
async def delete_run(run_id: str):
    await delete_session(run_id)
    return {"status": "deleted", "run_id": run_id}


# ------------------------------------------------------------------
# Turn
# ------------------------------------------------------------------

@app.post("/api/run/{run_id}/turn")
async def take_turn(run_id: str, req: TurnRequest):
    state = await _load_or_404(run_id)

    if state.run_status != "active":
        raise HTTPException(
            403, f"Run is '{state.run_status}' — cannot take actions"
        )

    text = req.player_input.strip()
    if not text:
        raise HTTPException(400, "Empty input")

    parsed = await parse_action(text, state)
    state = apply_action(state, parsed)

    death_result = await check_death(state, parsed)

    relevant_npcs = _filter_relevant_npcs(
        npcs_near_player(state), parsed.get("npc_impacts", [])
    )
    pov_tasks = [generate_npc_pov(npc, parsed, state) for npc in relevant_npcs]
    pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)

    npc_responses = []
    for npc, pov in zip(relevant_npcs, pov_results):
        pov_text = pov if isinstance(pov, str) else f"[{npc.name} is silent]"
        npc_responses.append(
            {
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "pov": pov_text,
            }
        )

    if death_result["died"]:
        state = apply_death(state, death_result["cause"])

    await save_session(state)

    return {
        "parsed_action": parsed,
        "world_state": state.model_dump(),
        "npc_responses": npc_responses,
        "death": death_result if death_result["died"] else None,
    }


# ------------------------------------------------------------------
# Skip turn (inaction)
# ------------------------------------------------------------------

@app.post("/api/run/{run_id}/skip")
async def skip_turn(run_id: str):
    state = await _load_or_404(run_id)

    if state.run_status != "active":
        raise HTTPException(
            403, f"Run is '{state.run_status}' — cannot take actions"
        )

    auto_action = await player_skip_turn(state)
    state = apply_action(state, auto_action)

    nearby = npcs_near_player(state)
    pov_tasks = [generate_npc_pov(npc, auto_action, state) for npc in nearby]
    pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)

    npc_responses = []
    for npc, pov in zip(nearby, pov_results):
        pov_text = pov if isinstance(pov, str) else f"[{npc.name} is silent]"
        npc_responses.append(
            {
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "pov": pov_text,
            }
        )

    await save_session(state)

    return {
        "parsed_action": auto_action,
        "world_state": state.model_dump(),
        "npc_responses": npc_responses,
    }


# ------------------------------------------------------------------
# Travel
# ------------------------------------------------------------------

class TravelRequest(BaseModel):
    destination: str


@app.post("/api/run/{run_id}/travel")
async def travel(run_id: str, req: TravelRequest):
    state = await _load_or_404(run_id)

    if state.run_status == "ended":
        raise HTTPException(403, "Run has ended")

    player_loc = get_player_location(state)
    dest_id = req.destination.lower().strip()

    if dest_id not in player_loc.neighbors:
        available = list(player_loc.neighbors.keys())
        raise HTTPException(
            400,
            f"Cannot travel to '{dest_id}' from '{player_loc.id}'. "
            f"Available: {available}",
        )

    travel_turns = player_loc.neighbors[dest_id]

    state = state.model_copy(deep=True)
    state = await advance_world(state, ticks=travel_turns)

    if state.run_status == "dead_observing":
        for _ in range(travel_turns):
            state = decay_memories(state)
        if state.run_status == "ended":
            erasure_text = await generate_erasure(state)
            state.player.location = dest_id
            await save_session(state)
            return {"erasure": erasure_text, "world_state": state.model_dump()}

    state.player.location = dest_id
    from backend.world_state import Event
    state.events.append(
        Event(
            turn=state.turn,
            action_type="travel",
            description=(
                f"{state.player.name} travels from {player_loc.name} "
                f"to {get_location(state, dest_id).name}, "
                f"arriving after {travel_turns} turns."
            ),
            target=dest_id,
            location=dest_id,
        )
    )

    new_loc = get_player_location(state)
    nearby = npcs_near_player(state)

    stored_povs = {}
    for npc in nearby:
        if npc.stored_povs:
            stored_povs[npc.id] = {
                "npc_name": npc.name,
                "npc_role": npc.role,
                "povs": list(npc.stored_povs),
            }
            npc.stored_povs = []

    arrival_action = {
        "action_type": "travel",
        "target": new_loc.name,
        "intent": f"Arrived in {new_loc.name} after traveling from {player_loc.name}",
        "era_description": (
            f"{state.player.name} arrives in {new_loc.name} after "
            f"{travel_turns} turns on the road from {player_loc.name}. "
            f"The journey was long and the world has changed."
        ),
    }

    arrival_povs = []
    if state.run_status == "active" and nearby:
        pov_tasks = [generate_npc_pov(npc, arrival_action, state) for npc in nearby]
        pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)
        for npc, pov in zip(nearby, pov_results):
            pov_text = pov if isinstance(pov, str) else f"[{npc.name} is silent]"
            arrival_povs.append(
                {
                    "npc_id": npc.id,
                    "npc_name": npc.name,
                    "npc_role": npc.role,
                    "pov": pov_text,
                }
            )

    await save_session(state)

    return {
        "travel": {
            "from": player_loc.name,
            "to": new_loc.name,
            "turns_spent": travel_turns,
        },
        "world_state": state.model_dump(),
        "nearby_npcs": [
            {"npc_id": n.id, "npc_name": n.name, "npc_role": n.role}
            for n in nearby
        ],
        "stored_povs": stored_povs,
        "arrival_reactions": arrival_povs,
    }


# ------------------------------------------------------------------
# Reset (convenience — restarts the same run_id)
# ------------------------------------------------------------------

@app.post("/api/run/{run_id}/reset")
async def reset_run(run_id: str):
    state = create_initial_state()
    state.run_id = run_id
    await save_session(state)
    return {"status": "reset", "world_state": state.model_dump()}


# ------------------------------------------------------------------
# Backward-compat endpoints (Phase 0 style — use latest run)
# ------------------------------------------------------------------

_compat_run_id: str = ""


@app.get("/api/state")
async def get_state_compat():
    state = await _get_compat_state()
    return state.model_dump()


@app.post("/api/turn")
async def take_turn_compat(req: TurnRequest):
    global _compat_run_id
    state = await _get_compat_state()
    _compat_run_id = state.run_id
    return await take_turn(state.run_id, req)


@app.post("/api/reset")
async def reset_compat():
    global _compat_run_id
    state = create_initial_state()
    _compat_run_id = state.run_id
    await save_session(state)
    return {"status": "reset", "world_state": state.model_dump()}


async def _get_compat_state() -> WorldState:
    """Get or create a run for backward-compat endpoints."""
    global _compat_run_id
    if _compat_run_id:
        state = await load_session(_compat_run_id)
        if state:
            return state
    runs = await list_sessions()
    if runs:
        _compat_run_id = runs[0]["run_id"]
        state = await load_session(_compat_run_id)
        if state:
            return state
    state = create_initial_state()
    _compat_run_id = state.run_id
    await save_session(state)
    return state


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _filter_relevant_npcs(nearby_npcs, npc_impacts):
    """Only return NPCs the game determined are relevant to this action.

    Falls back to all nearby NPCs if no impacts have the 'relevant' field.
    """
    if not npc_impacts:
        return nearby_npcs

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
        return nearby_npcs

    if not relevant_names:
        return nearby_npcs[:1] if nearby_npcs else []

    return [
        npc for npc in nearby_npcs
        if any(rn in npc.name.lower() for rn in relevant_names)
    ]


async def _load_or_404(run_id: str) -> WorldState:
    state = await load_session(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return state


# ------------------------------------------------------------------
# Static files (frontend)
# ------------------------------------------------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
