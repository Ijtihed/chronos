"""Parse player natural language into a structured action via LLM.

Model tier: LOCAL (Ollama) — frontier stub for Phase 0.
When frontier parsing is enabled, swap the chat() call for a frontier client.
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

from backend.llm import chat, load_prompt
from backend.world_state import WorldState, build_story_summary

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "action_parser.md"


async def parse_action(player_input: str, state: WorldState) -> dict:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    npc_list = ", ".join(f"{n.name} ({n.role})" for n in state.npcs)

    prompt = template.safe_substitute(
        year=state.era.year,
        era_description=state.era.description,
        player_name=state.player.name,
        player_role=state.player.role,
        location_name=state.location.name,
        location_description=state.location.description,
        npcs=npc_list,
        story_so_far=build_story_summary(state),
        political_tension=state.location.political_tension,
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
    return {
        "action_type": "other",
        "target": None,
        "intent": player_input,
        "era_description": (
            f"{state.player.name} attempts something in {state.location.name}."
        ),
        "_parse_error": error,
    }
