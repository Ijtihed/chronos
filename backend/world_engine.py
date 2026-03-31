"""World advancement engine — runs simulation ticks when the player
travels or skips turns.

Model tier: LOCAL — lightweight per-tick NPC actions via Ollama.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from string import Template
from typing import List

from backend.llm import chat, load_prompt
from backend.world_state import (
    TENSION_LEVELS,
    Event,
    NPC,
    WorldState,
    build_story_summary,
    get_player_location,
)

_AUTONOMOUS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "autonomous_action.md"
)


async def advance_world(state: WorldState, ticks: int = 1) -> WorldState:
    """Advance the world by N ticks. Each tick: a subset of NPCs act
    autonomously, tension may shift, calendar advances.

    Mutates in place for efficiency (caller should have a copy).
    """
    for _ in range(ticks):
        state.turn += 1
        state.current_year = int(
            state.era.year_start + state.turn * state.era.years_per_turn
        )

        active_npcs = _select_active_npcs(state)
        if active_npcs:
            results = await asyncio.gather(
                *[_autonomous_npc_action(npc, state) for npc in active_npcs],
                return_exceptions=True,
            )
            for npc, result in zip(active_npcs, results):
                if isinstance(result, dict):
                    desc = result.get("action", f"{npc.name} goes about their day.")
                    state.events.append(
                        Event(
                            turn=state.turn,
                            action_type="autonomous",
                            description=desc,
                            target=npc.name,
                            location=npc.location,
                        )
                    )

        _tick_tension(state)

    return state


async def player_skip_turn(state: WorldState) -> dict:
    """The player skips — their character acts autonomously.

    Returns a dict describing what the player character did,
    shaped like a parsed action for compatibility with apply_action.
    """
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)
    player_loc = get_player_location(state)

    prompt = Template(raw_template).safe_substitute(
        character_name=state.player.name,
        character_role=state.player.role,
        character_description=state.player.description,
        character_disposition=state.player.disposition,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        story_so_far=build_story_summary(state),
    )

    try:
        raw = await chat(prompt, json_mode=True)
        data = json.loads(raw)
    except Exception:
        data = {
            "action": f"{state.player.name} rests and waits.",
            "effect": "Nothing changes.",
        }

    return {
        "action_type": "autonomous",
        "target": None,
        "intent": "inaction — character acts on their own",
        "era_description": data.get("action", f"{state.player.name} waits."),
        "npc_impacts": [],
    }


def _select_active_npcs(state: WorldState) -> List[NPC]:
    """Pick a random subset of NPCs to act this tick. Keep it lightweight."""
    count = max(1, len(state.npcs) // 3)
    return random.sample(state.npcs, min(count, len(state.npcs)))


async def _autonomous_npc_action(npc: NPC, state: WorldState) -> dict:
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)

    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        npc_loc = state.locations[0]

    prompt = Template(raw_template).safe_substitute(
        character_name=npc.name,
        character_role=npc.role,
        character_description=npc.description,
        character_disposition=npc.disposition,
        location_name=npc_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        story_so_far=build_story_summary(state),
    )

    try:
        raw = await chat(prompt, json_mode=True)
        return json.loads(raw)
    except Exception:
        return {"action": f"{npc.name} goes about their day.", "effect": ""}


def _tick_tension(state: WorldState) -> None:
    """Tension creeps up at random locations during world advancement."""
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
