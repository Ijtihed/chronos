"""Generate NPC point-of-view responses via local Ollama.

Model tier: LOCAL — this is the highest-volume LLM call in the game.
"""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template

from backend.hke.retrieve import retrieve_context
from backend.llm import chat, load_prompt
from backend.llm_schemas import leaks_raw_numbers, scrub_leaked_numbers
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

    prompt = template.safe_substitute(
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        npc_disposition=npc.disposition,
        relationship_to_player=npc.relationship_to_player,
        player_name=state.player.name,
        era_description=state.era.description,
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
        text = await chat(prompt)
        if leaks_raw_numbers(text):
            logger.warning("NPC POV for %s leaked raw numbers, scrubbing", npc.name)
            text = scrub_leaked_numbers(text)
        return text
    except Exception as exc:
        return f"[{npc.name} is silent — Ollama error: {exc}]"
