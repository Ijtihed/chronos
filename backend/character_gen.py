"""Generate characters from era configs via the LLM provider.

Model tier: QUALITY — player + 8-15 concurrent NPCs at run start. NPC
voice fidelity matters here; the fan-out is capped by the Gemini
concurrency semaphore in llm_provider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from pathlib import Path
from string import Template
from typing import List

from pydantic import ValidationError

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import CharacterGenResponse, character_gen_default
from backend.npc_personality import generate_personality, calculate_needs, get_initial_preoccupation
from backend.world_state import Location, NPC, PlayerCharacter, WorldState, Era

logger = logging.getLogger("chronos.character_gen")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "character_gen.md"


async def generate_run(era_config: dict) -> WorldState:
    """Generate a complete WorldState from an era config dict."""
    raw_template = load_prompt(_TEMPLATE_PATH)

    locations = [Location(**loc) for loc in era_config["locations"]]
    start_location = locations[0]
    era = Era(
        name=era_config["name"],
        year_start=era_config["year_start"],
        description=era_config["description"],
        region=era_config["region"],
        years_per_turn=era_config.get("years_per_turn", 0.25),
        lifespan_turns=era_config.get("lifespan_turns", [40, 60]),
    )

    player_archetype = random.choice(era_config["player_archetypes"])
    player = await _generate_player(
        raw_template, era_config, player_archetype, start_location
    )

    npc_archetypes = era_config["npc_archetypes"]
    npc_count = min(len(npc_archetypes), random.randint(8, 15))
    selected = random.sample(npc_archetypes, npc_count)

    npcs = await _generate_npcs(
        raw_template, era_config, selected, locations, player.role,
        player_start_location=start_location.id,
    )

    state = WorldState(
        run_id=uuid.uuid4().hex[:12],
        run_status="active",
        era=era,
        current_year=era_config["year_start"],
        player=player,
        npcs=npcs,
        locations=locations,
        visited_locations=[start_location.id],
    )

    try:
        from backend.hce import generate_ground_context, schedule_canonical_consequences
        state.ground_context = await generate_ground_context(state)
        await schedule_canonical_consequences(state)
    except Exception as exc:
        logger.warning("HCE ground context generation failed (non-fatal): %s", exc)

    return state


async def _generate_player(
    template_text: str,
    era_config: dict,
    archetype: dict,
    start_location: Location,
) -> PlayerCharacter:
    prompt = Template(template_text).safe_substitute(
        region=era_config["region"],
        year=era_config["year_start"],
        era_description=era_config["description"],
        role=archetype["role"],
        archetype=archetype["archetype"],
        social_class=archetype["social_class"],
        location_name=start_location.name,
        player_role="the player",
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=CharacterGenResponse,
            call_site="character_gen.player",
        )
        from backend.utils import strip_json_fences
        data = CharacterGenResponse.model_validate(json.loads(strip_json_fences(raw)))
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.warning("Player character gen validation failed: %s", exc)
        data = character_gen_default(archetype["role"], start_location.name)

    lifespan = era_config.get("lifespan_turns", [40, 60])
    avg_age_at_start = 30
    birth_year = era_config["year_start"] - avg_age_at_start

    return PlayerCharacter(
        id="player",
        name=data.name or "Unknown",
        role=archetype["role"],
        archetype=archetype["archetype"],
        location=start_location.id,
        description=data.description,
        disposition=data.disposition or "anxious",
        birth_year=birth_year,
    )


async def _generate_npcs(
    template_text: str,
    era_config: dict,
    archetypes: list,
    locations: List[Location],
    player_role: str,
    player_start_location: str = "",
) -> List[NPC]:
    """Generate NPCs concurrently."""
    tasks = []
    for i, arch in enumerate(archetypes):
        loc = locations[i % len(locations)]
        tasks.append(
            _generate_single_npc(
                template_text, era_config, arch, loc, player_role, i,
                is_player_location=(loc.id == player_start_location),
            )
        )
    return await asyncio.gather(*tasks)


async def _generate_single_npc(
    template_text: str,
    era_config: dict,
    archetype: dict,
    location: Location,
    player_role: str,
    index: int,
    is_player_location: bool = False,
) -> NPC:
    prompt = Template(template_text).safe_substitute(
        region=era_config["region"],
        year=era_config["year_start"],
        era_description=era_config["description"],
        role=archetype["role"],
        archetype=archetype["archetype"],
        social_class=archetype["social_class"],
        location_name=location.name,
        player_role=player_role,
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=CharacterGenResponse,
            call_site="character_gen.npc",
        )
        from backend.utils import strip_json_fences
        data = CharacterGenResponse.model_validate(json.loads(strip_json_fences(raw)))
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.warning("NPC gen validation failed (index %d): %s", index, exc)
        data = character_gen_default(archetype["role"], location.name, index=index)

    npc_id = f"npc_{archetype['archetype']}_{index}"
    arch_key = archetype["archetype"]
    personality = generate_personality(arch_key)
    needs = calculate_needs(arch_key, personality)

    return NPC(
        id=npc_id,
        name=data.name or f"NPC {index}",
        role=archetype["role"],
        archetype=arch_key,
        social_class=archetype.get("social_class", ""),
        location=location.id,
        description=data.description,
        disposition=data.disposition or "cautious",
        relationship_to_player=data.relationship_to_player or f"Aware of the {player_role}.",
        memory_of_player=0.4 if is_player_location else 0.15,
        last_interaction_turn=0,
        personality=personality,
        needs=needs,
        current_activity=data.current_activity or f"Going about their duties as a {archetype['role']}.",
        current_preoccupation=get_initial_preoccupation(arch_key),
        last_preoccupation_shift_turn=0,
    )
