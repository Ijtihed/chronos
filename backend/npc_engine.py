"""Generate NPC point-of-view responses via local Ollama.

Model tier: LOCAL — this is the highest-volume LLM call in the game.
Returns structured NPCPOVResponse; stores emotional_state on the NPC.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template

from pydantic import ValidationError

from backend.hke.retrieve import retrieve_context
from backend.llm import chat, load_prompt
from backend.llm_schemas import NPCPOVResponse, leaks_raw_numbers, scrub_leaked_numbers
from backend.npc_personality import get_dominant_need, get_urgent_needs
from backend.world_state import (
    NPC,
    WorldState,
    build_story_summary,
    get_player_location,
)

logger = logging.getLogger("chronos.npc_engine")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_pov.md"


async def generate_npc_pov(
    npc: NPC, action: dict, state: WorldState
) -> str:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    player_loc = get_player_location(state)

    query = action.get("era_description", action.get("intent", ""))
    historical_context = retrieve_context(state.era.name, query) if query else ""

    gc = state.ground_context or {}

    what_knows = gc.get("what_character_knows") or "What anyone in your position would know."
    raw_rumors = gc.get("local_rumors", [])
    if not raw_rumors:
        rumors_str = "Nothing specific."
    elif len(raw_rumors) == 1:
        rumors_str = raw_rumors[0]
    else:
        rumors_str = "; ".join(raw_rumors)

    urgent = get_urgent_needs(npc.needs)
    urgent_str = ", ".join(n.replace("_", " ") for n in urgent) if urgent else "nothing urgent"

    prompt = template.safe_substitute(
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        social_class=npc.social_class or npc.archetype,
        npc_disposition=npc.disposition,
        dominant_need=get_dominant_need(npc.needs).replace("_", " "),
        urgent_needs=urgent_str,
        relationship_to_player=npc.relationship_to_player,
        player_name=state.player.name,
        era_description=state.era.description,
        era_feel=gc.get("era_feel", ""),
        material_conditions=gc.get("material_conditions", player_loc.material_conditions),
        what_character_knows=what_knows,
        local_rumors=rumors_str,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        story_so_far=build_story_summary(state),
        historical_context=historical_context or "No additional historical sources available.",
        era_description_of_action=action.get(
            "era_description", "Something has happened in town."
        ),
        action_intent=action.get("intent", "unknown"),
    )

    try:
        raw = await chat(prompt, json_mode=True)
        parsed = NPCPOVResponse.model_validate(json.loads(raw))
        text = parsed.perspective or f"[{npc.name} is silent]"
        if leaks_raw_numbers(text):
            logger.warning("NPC POV for %s leaked raw numbers, scrubbing", npc.name)
            text = scrub_leaked_numbers(text)
        if parsed.emotional_state:
            npc.emotional_state = parsed.emotional_state
        return text
    except (json.JSONDecodeError, ValidationError):
        try:
            raw_text = await chat(prompt)
            if leaks_raw_numbers(raw_text):
                raw_text = scrub_leaked_numbers(raw_text)
            return raw_text
        except Exception as exc:
            return f"[{npc.name} is silent — Ollama error: {exc}]"
    except Exception as exc:
        return f"[{npc.name} is silent — Ollama error: {exc}]"
