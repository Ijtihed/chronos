"""Generate NPC point-of-view responses via local Ollama.

Model tier: LOCAL — this is the highest-volume LLM call in the game.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from backend.llm import chat, load_prompt
from backend.world_state import NPC, WorldState, build_story_summary

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_pov.md"


async def generate_npc_pov(
    npc: NPC, action: dict, state: WorldState
) -> str:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    prompt = template.safe_substitute(
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        npc_disposition=npc.disposition,
        relationship_to_player=npc.relationship_to_player,
        player_name=state.player.name,
        era_description=state.era.description,
        location_name=state.location.name,
        year=state.era.year,
        story_so_far=build_story_summary(state),
        era_description_of_action=action.get(
            "era_description", "Something has happened in town."
        ),
        action_intent=action.get("intent", "unknown"),
    )

    try:
        return await chat(prompt)
    except Exception as exc:
        return f"[{npc.name} is silent — Ollama error: {exc}]"
