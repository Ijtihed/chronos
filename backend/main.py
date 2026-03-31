"""CHRONOS Phase 0 — FastAPI entry point."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.action_parser import parse_action
from backend.llm import ollama_ok
from backend.npc_engine import generate_npc_pov
from backend.world_state import WorldState, apply_action, create_initial_state

logger = logging.getLogger("chronos")

app = FastAPI(title="CHRONOS", version="0.0.1")

_state: WorldState = create_initial_state()


class TurnRequest(BaseModel):
    player_input: str


@app.on_event("startup")
async def _startup() -> None:
    ok = await ollama_ok()
    if ok:
        logger.info("Ollama is reachable")
    else:
        logger.warning("Ollama is NOT reachable — LLM calls will fail")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "phase": 0,
        "ollama": await ollama_ok(),
    }


@app.get("/api/state")
async def get_state():
    return _state.model_dump()


@app.post("/api/turn")
async def take_turn(req: TurnRequest):
    global _state

    text = req.player_input.strip()
    if not text:
        raise HTTPException(400, "Empty input")

    parsed = await parse_action(text, _state)
    _state = apply_action(_state, parsed)

    pov_tasks = [generate_npc_pov(npc, parsed, _state) for npc in _state.npcs]
    pov_results = await asyncio.gather(*pov_tasks, return_exceptions=True)

    npc_responses = []
    for npc, pov in zip(_state.npcs, pov_results):
        pov_text = pov if isinstance(pov, str) else f"[{npc.name} is silent]"
        npc_responses.append(
            {
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "pov": pov_text,
            }
        )

    return {
        "parsed_action": parsed,
        "world_state": _state.model_dump(),
        "npc_responses": npc_responses,
    }


@app.post("/api/reset")
async def reset():
    global _state
    _state = create_initial_state()
    return {"status": "reset", "world_state": _state.model_dump()}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
