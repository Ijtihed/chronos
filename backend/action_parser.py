"""Parse player natural language into a structured action via LLM.

Model tier: LOCAL (Ollama) — frontier stub.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template

from pydantic import ValidationError

from backend.llm import chat, load_prompt
from backend.llm_schemas import ActionParserResponse, action_parser_default
from backend.world_state import (
    WorldState,
    build_story_summary,
    get_location,
    get_player_location,
    npcs_near_player,
)

logger = logging.getLogger("chronos.action_parser")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "action_parser.md"


async def parse_action(player_input: str, state: WorldState) -> dict:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    nearby = npcs_near_player(state)
    npc_list = ", ".join(f"{n.name} ({n.role})" for n in nearby)
    player_loc = get_player_location(state)

    reachable = []
    for nid, cost in player_loc.neighbors.items():
        try:
            dest = get_location(state, nid)
            reachable.append(f"{dest.name} ({nid}, {cost} turns)")
        except ValueError:
            reachable.append(f"{nid} ({cost} turns)")
    reachable_str = ", ".join(reachable) if reachable else "none"

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
        reachable_locations=reachable_str,
        player_input=player_input,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        parsed = ActionParserResponse.model_validate(json.loads(raw))
        return parsed.model_dump()
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Action parser validation failed: %s", exc)
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
        "is_travel": False,
        "destination": None,
        "is_inaction": False,
        "_parse_error": error,
    }
