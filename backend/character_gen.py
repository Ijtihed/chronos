"""Generate characters from era configs via local Ollama.

Model tier: LOCAL — character generation is a one-time burst at run start.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from pathlib import Path
from string import Template
from typing import List, Tuple

from backend.llm import chat, load_prompt
from backend.world_state import Location, NPC, PlayerCharacter, WorldState, Era

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
        raw_template, era_config, selected, locations, player.role
    )

    return WorldState(
        run_id=uuid.uuid4().hex[:12],
        run_status="active",
        era=era,
        current_year=era_config["year_start"],
        player=player,
        npcs=npcs,
        locations=locations,
    )


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
        raw = await chat(prompt, json_mode=True)
        data = json.loads(raw)
    except Exception:
        data = {
            "name": "Unknown Wanderer",
            "description": f"A {archetype['role']} in {start_location.name}.",
            "disposition": "anxious",
            "relationship_to_player": "",
        }

    lifespan = era_config.get("lifespan_turns", [40, 60])
    avg_age_at_start = 30
    birth_year = era_config["year_start"] - avg_age_at_start

    return PlayerCharacter(
        id="player",
        name=data.get("name", "Unknown"),
        role=archetype["role"],
        archetype=archetype["archetype"],
        location=start_location.id,
        description=data.get("description", ""),
        disposition=data.get("disposition", "anxious"),
        birth_year=birth_year,
    )


async def _generate_npcs(
    template_text: str,
    era_config: dict,
    archetypes: list,
    locations: List[Location],
    player_role: str,
) -> List[NPC]:
    """Generate NPCs concurrently."""
    tasks = []
    for i, arch in enumerate(archetypes):
        loc = locations[i % len(locations)]
        tasks.append(
            _generate_single_npc(
                template_text, era_config, arch, loc, player_role, i
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
        raw = await chat(prompt, json_mode=True)
        data = json.loads(raw)
    except Exception:
        data = {
            "name": f"NPC {index}",
            "description": f"A {archetype['role']} in {location.name}.",
            "disposition": "cautious",
            "relationship_to_player": f"Aware of the {player_role} in town.",
        }

    npc_id = f"npc_{archetype['archetype']}_{index}"

    return NPC(
        id=npc_id,
        name=data.get("name", f"NPC {index}"),
        role=archetype["role"],
        archetype=archetype["archetype"],
        social_class=archetype.get("social_class", ""),
        location=location.id,
        description=data.get("description", ""),
        disposition=data.get("disposition", "cautious"),
        relationship_to_player=data.get(
            "relationship_to_player",
            f"Aware of the {player_role}.",
        ),
        memory_of_player=0.1,
        last_interaction_turn=0,
    )
