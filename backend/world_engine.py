"""World engine — runs the living simulation every turn.

The world advances whether or not the player acts. NPCs act autonomously,
travel between locations, and interact with each other. The player's
action is one thread among many.

Model tier: LOCAL — lightweight per-NPC autonomous actions via Ollama.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Tuple

from backend.llm import chat, load_prompt
from backend.world_state import (
    TENSION_LEVELS,
    Event,
    NPC,
    WorldState,
    build_story_summary,
    get_location,
    get_player_location,
    npcs_near_player,
)

_AUTONOMOUS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "autonomous_action.md"
)


async def simulate_turn(state: WorldState) -> Tuple[WorldState, List[dict]]:
    """Run one simulation tick. Returns (new_state, ambient_events).

    ambient_events is a list of dicts describing what NPCs did this turn,
    to be included in the narrative. Only includes activity at the player's
    location (the rest happens silently).
    """
    new = state.model_copy(deep=True)
    new.turn += 1
    new.current_year = int(
        new.era.year_start + new.turn * new.era.years_per_turn
    )

    if new.player.location not in new.visited_locations:
        new.visited_locations.append(new.player.location)

    nearby = [n for n in new.npcs if n.location == new.player.location]
    elsewhere = [n for n in new.npcs if n.location != new.player.location]

    visible_activity = []

    if nearby:
        active_nearby = random.sample(nearby, min(len(nearby), random.randint(2, 4)))
        results = await asyncio.gather(
            *[_npc_autonomous_action(npc, new, nearby) for npc in active_nearby],
            return_exceptions=True,
        )
        for npc, result in zip(active_nearby, results):
            if isinstance(result, dict):
                action_desc = result.get("action", f"{npc.name} goes about their day.")
                visible_activity.append({
                    "npc_id": npc.id,
                    "npc_name": npc.name,
                    "npc_role": npc.role,
                    "activity": action_desc,
                    "interacts_with": result.get("interacts_with"),
                })
                new.events.append(Event(
                    turn=new.turn,
                    action_type="ambient",
                    description=action_desc,
                    target=result.get("interacts_with"),
                    location=npc.location,
                ))
                if result.get("mood_shift") and result["mood_shift"] != npc.disposition:
                    npc.disposition = result["mood_shift"]
                if result.get("wants_to_travel") and result.get("travel_destination"):
                    _schedule_npc_travel(npc, result["travel_destination"], new)

    if elsewhere:
        active_elsewhere = random.sample(elsewhere, min(len(elsewhere), max(1, len(elsewhere) // 3)))
        bg_results = await asyncio.gather(
            *[_npc_autonomous_action(npc, new, []) for npc in active_elsewhere],
            return_exceptions=True,
        )
        for npc, result in zip(active_elsewhere, bg_results):
            if isinstance(result, dict):
                new.events.append(Event(
                    turn=new.turn,
                    action_type="ambient_distant",
                    description=result.get("action", f"{npc.name} acts."),
                    target=result.get("interacts_with"),
                    location=npc.location,
                ))
                if result.get("mood_shift") and result["mood_shift"] != npc.disposition:
                    npc.disposition = result["mood_shift"]
                if result.get("wants_to_travel") and result.get("travel_destination"):
                    _schedule_npc_travel(npc, result["travel_destination"], new)

    _tick_tension(new)

    return new, visible_activity


async def advance_world(state: WorldState, ticks: int = 1) -> WorldState:
    """Advance the world by N ticks without generating visible activity.
    Used during travel when the player is in transit."""
    for _ in range(ticks):
        state, _ = await simulate_turn(state)
    return state


async def player_skip_turn(state: WorldState) -> dict:
    """The player chose inaction — their character acts autonomously."""
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)
    player_loc = get_player_location(state)
    nearby = npcs_near_player(state)
    other_names = ", ".join(n.name for n in nearby) or "no one"

    prompt = Template(raw_template).safe_substitute(
        character_name=state.player.name,
        character_role=state.player.role,
        character_description=state.player.description,
        character_disposition=state.player.disposition,
        other_npcs_here=other_names,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        story_so_far=build_story_summary(state),
        player_name=state.player.name,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        data = json.loads(raw)
    except Exception:
        data = {"action": f"{state.player.name} rests and waits.", "interacts_with": None}

    return {
        "action_type": "autonomous",
        "target": data.get("interacts_with"),
        "intent": "inaction — character acts on their own",
        "era_description": data.get("action", f"{state.player.name} waits."),
        "npc_impacts": [],
    }


async def _npc_autonomous_action(npc: NPC, state: WorldState, nearby_npcs: List[NPC]) -> dict:
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)

    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        npc_loc = state.locations[0]

    other_names = ", ".join(
        n.name for n in nearby_npcs if n.id != npc.id
    ) or "no one"

    prompt = Template(raw_template).safe_substitute(
        character_name=npc.name,
        character_role=npc.role,
        character_description=npc.description,
        character_disposition=npc.disposition,
        other_npcs_here=other_names,
        location_name=npc_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        story_so_far=build_story_summary(state),
        player_name=state.player.name,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        return json.loads(raw)
    except Exception:
        return {"action": f"{npc.name} goes about their day.", "interacts_with": None}


def _schedule_npc_travel(npc: NPC, destination: str, state: WorldState) -> None:
    """Move an NPC to a new location if the destination is valid."""
    dest_id = destination.lower().strip()
    valid_ids = {loc.id for loc in state.locations}
    if dest_id in valid_ids and dest_id != npc.location:
        npc.location = dest_id


def _tick_tension(state: WorldState) -> None:
    if state.turn % 3 != 0:
        return
    loc = random.choice(state.locations)
    idx = (
        TENSION_LEVELS.index(loc.political_tension)
        if loc.political_tension in TENSION_LEVELS
        else 2
    )
    if idx < len(TENSION_LEVELS) - 1:
        loc.political_tension = TENSION_LEVELS[idx + 1]
