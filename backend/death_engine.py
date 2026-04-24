"""Death, memory decay, and erasure system.

Handles:
- Death check (aging + consequence-driven)
- Transition to observation mode
- Per-turn memory decay after death
- Run end when all memory is gone
- Erasure narrative generation
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from string import Template

from pydantic import ValidationError

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import (
    DEATH_CHECK_SAFE,
    DeathCheckResponse,
    leaks_raw_numbers,
    scrub_leaked_numbers,
)
from backend.world_state import (
    WorldState,
    build_story_summary,
    get_player_location,
)

logger = logging.getLogger("chronos.death_engine")

_DEATH_CHECK_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "death_check.md"
)
_ERASURE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "erasure.md"
)

DEATH_RISK_THRESHOLD = 0.7
BASE_MEMORY_DECAY = 0.08


async def check_death(state: WorldState, action: dict) -> dict:
    """Evaluate whether the player dies this turn.

    Returns {"died": bool, "cause": str|None, "death_risk": float}.
    Death triggers from: (a) aging past lifespan ceiling, (b) LLM-judged
    consequence risk above threshold.
    """
    player_age = state.current_year - state.player.birth_year
    lifespan_min, lifespan_max = state.era.lifespan_turns
    max_age = int(lifespan_max * state.era.years_per_turn) + 30

    if player_age >= max_age:
        return {
            "died": True,
            "cause": (
                f"{state.player.name} succumbs to the weight of years, "
                f"aged {player_age}, in {get_player_location(state).name}."
            ),
            "death_risk": 1.0,
        }

    age_factor = max(0.0, (player_age - 40) / max(1, max_age - 40))

    try:
        risk_data = await _llm_death_check(state, action)
        base_risk = risk_data.get("death_risk", 0.0)
        combined_risk = min(1.0, base_risk + age_factor * 0.3)

        if risk_data.get("could_die") and combined_risk >= DEATH_RISK_THRESHOLD:
            return {
                "died": True,
                "cause": risk_data.get("cause", f"{state.player.name} dies."),
                "death_risk": combined_risk,
            }

        return {"died": False, "cause": None, "death_risk": combined_risk}
    except Exception:
        return {"died": False, "cause": None, "death_risk": age_factor * 0.3}


async def _llm_death_check(state: WorldState, action: dict) -> dict:
    raw_template = load_prompt(_DEATH_CHECK_PATH)
    player_loc = get_player_location(state)
    player_age = state.current_year - state.player.birth_year

    prompt = Template(raw_template).safe_substitute(
        location_name=player_loc.name,
        year=state.current_year,
        era_description=state.era.description,
        player_name=state.player.name,
        player_role=state.player.role,
        player_age=player_age,
        player_disposition=state.player.disposition,
        era_description_of_action=action.get(
            "era_description", "Something happened."
        ),
        story_so_far=build_story_summary(state),
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="fast",
            schema=DeathCheckResponse,
            call_site="death_check",
        )
        return DeathCheckResponse.model_validate(json.loads(raw)).model_dump()
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Death check validation failed: %s", exc)
        return DEATH_CHECK_SAFE.model_dump()


def apply_death(state: WorldState, cause: str) -> WorldState:
    """Transition the run to observation mode."""
    from backend.world_state import Event
    new = state.model_copy(deep=True)
    new.run_status = "dead_observing"
    new.events.append(
        Event(
            turn=new.turn,
            action_type="death",
            description=cause,
            target=new.player.name,
            location=new.player.location,
        )
    )
    return new


def decay_memories(state: WorldState) -> WorldState:
    """Decay NPC memories of the player after death. Called each tick
    during observation mode. When all memories reach 0, the run ends.
    """
    new = state.model_copy(deep=True)

    all_forgotten = True
    for npc in new.npcs:
        if npc.memory_of_player <= 0:
            continue
        decay = BASE_MEMORY_DECAY * _decay_modifier(npc)
        npc.memory_of_player = max(0.0, npc.memory_of_player - decay)
        if npc.memory_of_player > 0:
            all_forgotten = False

    if all_forgotten:
        new.run_status = "ended"

    return new


def _decay_modifier(npc) -> float:
    """NPCs who interacted more recently or more deeply forget slower."""
    if npc.memory_of_player >= 0.8:
        return 0.5
    if npc.memory_of_player >= 0.5:
        return 0.75
    return 1.0


_MEMORY_FADE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "memory_fade.md"


def _build_memory_summary(state: WorldState) -> str:
    """Build a plain-text summary of who remembers the player and how strongly."""
    rememberers = [
        (npc.name, npc.role, npc.memory_of_player)
        for npc in state.npcs
        if npc.memory_of_player > 0
    ]
    if not rememberers:
        return "No one remembers."
    rememberers.sort(key=lambda x: -x[2])
    lines = []
    for name, role, mem in rememberers:
        if mem > 0.7:
            lines.append(f"{name} ({role}) — remembers clearly")
        elif mem > 0.3:
            lines.append(f"{name} ({role}) — remembers faintly")
        else:
            lines.append(f"{name} ({role}) — barely remembers")
    return "\n".join(lines)


async def generate_memory_fade(state: WorldState) -> str:
    """Generate one fade-framing sentence for observation mode."""
    rememberers = [n for n in state.npcs if n.memory_of_player > 0]
    if not rememberers:
        return f"No one in {get_player_location(state).name} remembers {state.player.name}."

    try:
        raw_template = load_prompt(_MEMORY_FADE_PATH)
        player_loc = get_player_location(state)
        prompt = Template(raw_template).safe_substitute(
            player_name=state.player.name,
            player_role=state.player.role,
            location_name=player_loc.name,
            year=state.current_year or state.era.year_start,
            memory_summary=_build_memory_summary(state),
        )
        text, _ = await call_llm(
            prompt,
            tier="fast",
            call_site="memory_fade",
        )
        if leaks_raw_numbers(text):
            text = scrub_leaked_numbers(text)
        return text.strip().split("\n")[0][:200]
    except Exception:
        count = len(rememberers)
        if count == 1:
            return f"Only {rememberers[0].name} still remembers {state.player.name}."
        return f"{count} people still remember {state.player.name}. Fewer than last week."


async def generate_erasure(state: WorldState) -> str:
    """Generate the final erasure passage when the run ends."""
    raw_template = load_prompt(_ERASURE_PATH)
    player_loc = get_player_location(state)

    prompt = Template(raw_template).safe_substitute(
        player_name=state.player.name,
        player_role=state.player.role,
        location_name=player_loc.name,
        era_name=state.era.name,
        year=state.current_year,
        era_description=state.era.description,
        story_so_far=build_story_summary(state),
    )

    try:
        # Erasure is the emotional climax of every run — QUALITY tier.
        # Fires exactly once per run; cost is negligible, narrative
        # fidelity matters.
        text, _ = await call_llm(
            prompt,
            tier="quality",
            call_site="erasure",
        )
        if leaks_raw_numbers(text):
            logger.warning("Erasure text leaked raw numbers, scrubbing")
            text = scrub_leaked_numbers(text)
        return text
    except Exception:
        return (
            f"No record remains of {state.player.name}. "
            f"The world continued without them."
        )
