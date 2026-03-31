"""Parse player natural language into a structured action via LLM.

Model tier: LOCAL (Ollama) — frontier stub for Phase 0/1.
When frontier parsing is enabled, swap the chat() call for a frontier client.
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

from backend.llm import chat, load_prompt
from backend.world_state import (
    WorldState,
    build_story_summary,
    get_player_location,
    npcs_near_player,
)

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "action_parser.md"


async def parse_action(player_input: str, state: WorldState) -> dict:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    nearby = npcs_near_player(state)
    npc_list = ", ".join(f"{n.name} ({n.role})" for n in nearby)
    player_loc = get_player_location(state)

    prompt = template.safe_substitute(
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        player_name=state.player.name,
        player_role=state.player.role,
        location_name=player_loc.name,
        location_description=player_loc.description,
        npcs=npc_list,
        story_so_far=build_story_summary(state),
        political_tension=player_loc.political_tension,
        player_input=player_input,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return _fallback(player_input, state, str(exc))
    except Exception as exc:
        return _fallback(player_input, state, str(exc))


def _fallback(player_input: str, state: WorldState, error: str) -> dict:
    try:
        loc_name = get_player_location(state).name
    except ValueError:
        loc_name = "the area"
    return {
        "action_type": "other",
        "target": None,
        "intent": player_input,
        "era_description": (
            f"{state.player.name} attempts something in {loc_name}."
        ),
        "_parse_error": error,
    }
