"""CHRONOS — FastAPI entry point.

Simulation-first architecture: the world advances every turn,
then the player optionally acts. The player is a perspective,
not a protagonist.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from string import Template

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.action_parser import parse_action
from backend.character_gen import generate_run
from backend.death_engine import (
    apply_death,
    check_death,
    decay_memories,
    generate_erasure,
)
from backend.eras import ALL_ERAS, random_era
from backend.llm import chat, load_prompt, ollama_ok
from backend.npc_engine import generate_npc_pov
from backend.persistence import (
    delete_session,
    init_db,
    list_sessions,
    load_session,
    save_session,
)
from backend.world_engine import advance_world, player_skip_turn, simulate_turn
from backend.world_state import (
    Event,
    WorldState,
    apply_action,
    create_initial_state,
    get_location,
    get_player_location,
    npcs_near_player,
)

logger = logging.getLogger("chronos")

app = FastAPI(title="CHRONOS", version="0.2.0")

_NPC_PERCEPTION_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "npc_perception.md"
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
    ok = await ollama_ok()
    if ok:
        logger.info("Ollama is reachable")
    else:
        logger.warning("Ollama is NOT reachable — LLM calls will fail")


# ------------------------------------------------------------------
# Health + Geo
# ------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "phase": 2, "ollama": await ollama_ok()}


@app.get("/api/geo/{era_key}")
async def get_geo(era_key: str):
    geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
    border_file = geo_dir / f"borders_{era_key}.geojson"
    if not border_file.exists():
        raise HTTPException(404, f"No border data for era '{era_key}'")
    return json.loads(border_file.read_text())


# ------------------------------------------------------------------
# Run management
# ------------------------------------------------------------------

@app.post("/api/run")
async def new_run(req: RunRequest = RunRequest()):
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
    return {
        "run_id": state.run_id,
        "era": era_key,
        "world_state": state.model_dump(),
        "loading_events": era_config.get("loading_events", []),
        "loading_voices": era_config.get("loading_voices", []),
    }


@app.get("/api/runs")
async def get_runs():
    return await list_sessions()


@app.get("/api/run/{run_id}")
async def get_run_state(run_id: str):
    state = await _load_or_404(run_id)
    return state.model_dump()


@app.delete("/api/run/{run_id}")
async def delete_run(run_id: str):
    await delete_session(run_id)
    return {"status": "deleted", "run_id": run_id}


@app.post("/api/run/{run_id}/reset")
async def reset_run(run_id: str):
    state = create_initial_state()
    state.run_id = run_id
    await save_session(state)
    return {"status": "reset", "world_state": state.model_dump()}


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
    state = await _load_or_404(run_id)

    if state.run_status == "ended":
        raise HTTPException(403, "Run has ended")

    if state.run_status == "dead_observing":
        return await _handle_observation(state, req.player_input.strip())

    if state.run_status != "active":
        raise HTTPException(403, f"Run is '{state.run_status}'")

    text = req.player_input.strip()
    if not text:
        raise HTTPException(400, "Empty input")

    # --- Step 1: World simulates (NPCs act autonomously) ---
    state, ambient = await simulate_turn(state)

    # --- Step 2: Parse player action ---
    parsed = await parse_action(text, state)

    if parsed.get("is_travel") and parsed.get("destination"):
        return await _handle_travel(state, parsed, ambient)

    if parsed.get("is_inaction"):
        return await _handle_inaction(state, parsed, ambient)

    # --- Step 3: Apply player action ---
    state = apply_action(state, parsed)

    # --- Step 4: Death check ---
    death_result = await check_death(state, parsed)

    # --- Step 5: Generate NPC reactions to player (selective) ---
    relevant = _filter_relevant(npcs_near_player(state), parsed.get("npc_impacts", []))
    pov_tasks = [generate_npc_pov(npc, parsed, state) for npc in relevant]
    pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)
    npc_responses = _build_npc_responses(relevant, pov_results)

    if death_result["died"]:
        state = apply_death(state, death_result["cause"])

    await save_session(state)

    return {
        "ambient_activity": ambient,
        "parsed_action": parsed,
        "world_state": state.model_dump(),
        "npc_responses": npc_responses,
        "death": death_result if death_result["died"] else None,
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

    try:
        text = await chat(prompt)
    except Exception:
        text = f"You are not sure what to make of {npc.name}."

    return {"npc_id": npc.id, "npc_name": npc.name, "perception": text}


# ------------------------------------------------------------------
# Turn handlers
# ------------------------------------------------------------------

async def _handle_inaction(state: WorldState, parsed: dict, ambient: list) -> dict:
    auto = await player_skip_turn(state)
    auto["era_description"] = parsed.get("era_description") or auto.get("era_description", "")
    state = apply_action(state, auto)
    death_result = await check_death(state, auto)

    if death_result["died"]:
        state = apply_death(state, death_result["cause"])

    await save_session(state)

    return {
        "ambient_activity": ambient,
        "parsed_action": auto,
        "world_state": state.model_dump(),
        "npc_responses": [],
        "death": death_result if death_result["died"] else None,
    }


async def _handle_travel(state: WorldState, parsed: dict, ambient: list) -> dict:
    dest_id = parsed["destination"].lower().strip()
    player_loc = get_player_location(state)

    if dest_id not in player_loc.neighbors:
        state = apply_action(state, parsed)
        await save_session(state)
        return {
            "ambient_activity": ambient,
            "parsed_action": parsed,
            "world_state": state.model_dump(),
            "npc_responses": [],
            "death": None,
        }

    travel_turns = player_loc.neighbors[dest_id]
    state = await advance_world(state, ticks=travel_turns)

    state.player.location = dest_id
    if dest_id not in state.visited_locations:
        state.visited_locations.append(dest_id)

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
        pov_tasks = [generate_npc_pov(npc, arrival_action, state) for npc in nearby[:3]]
        pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)
        arrival_povs = _build_npc_responses(nearby[:3], pov_results)

    await save_session(state)

    return {
        "ambient_activity": ambient,
        "parsed_action": parsed,
        "world_state": state.model_dump(),
        "npc_responses": arrival_povs,
        "travel": {"from": player_loc.name, "to": dest_name, "turns_spent": travel_turns},
        "death": None,
    }


async def _handle_observation(state: WorldState, text: str) -> dict:
    parsed = await parse_action(text, state)
    state = state.model_copy(deep=True)

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
                await save_session(state)
                return {"erasure": erasure_text, "world_state": state.model_dump()}
            state.player.location = dest_id
            if dest_id not in state.visited_locations:
                state.visited_locations.append(dest_id)
            await save_session(state)
            return {
                "ambient_activity": [],
                "parsed_action": parsed,
                "world_state": state.model_dump(),
                "npc_responses": [],
                "death": None,
            }

    state.turn += 1
    state = decay_memories(state)
    if state.run_status == "ended":
        erasure_text = await generate_erasure(state)
        await save_session(state)
        return {"erasure": erasure_text, "world_state": state.model_dump()}

    await save_session(state)
    return {
        "ambient_activity": [],
        "parsed_action": parsed,
        "world_state": state.model_dump(),
        "npc_responses": [],
        "death": None,
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _filter_relevant(nearby_npcs, npc_impacts):
    if not npc_impacts:
        return nearby_npcs[:2] if nearby_npcs else []

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
        return nearby_npcs[:2] if nearby_npcs else []
    if not relevant_names:
        return nearby_npcs[:1] if nearby_npcs else []

    return [
        npc for npc in nearby_npcs
        if any(rn in npc.name.lower() for rn in relevant_names)
    ]


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


# ------------------------------------------------------------------
# Static files
# ------------------------------------------------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
