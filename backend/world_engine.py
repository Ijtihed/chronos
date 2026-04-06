"""World engine — runs the living simulation every turn.

The world advances whether or not the player acts. NPCs act autonomously,
travel between locations, and interact with each other. The player's
action is one thread among many.

The consequence queue fires scheduled effects at the start of each turn
(before NPC actions), using the two-phase validation pattern: consequences
are checked for validity both when scheduled and when they fire.

Model tier: LOCAL — lightweight per-NPC autonomous actions via Ollama.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from backend.llm import chat, load_prompt
from backend.llm_schemas import (
    AutonomousActionResponse,
    NPCEffect,
    autonomous_action_default,
)
from backend.persistence import (
    get_pending_consequences,
    mark_consequence_fired,
    mark_consequence_superseded,
)
from backend.world_state import (
    TENSION_LEVELS,
    Event,
    NPC,
    WorldState,
    apply_npc_effect,
    build_story_summary,
    get_location,
    get_player_location,
    npcs_near_player,
)

logger = logging.getLogger("chronos.world_engine")

_AUTONOMOUS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "autonomous_action.md"
)


async def simulate_turn(state: WorldState) -> Tuple[WorldState, List[dict]]:
    """Run one simulation tick. Returns (new_state, ambient_events).

    ambient_events is a list of dicts describing what NPCs did this turn,
    to be included in the narrative. Only includes activity at the player's
    location (the rest happens silently).
    """
    new = state.model_copy(deep=True)
    new.turn += 1
    new.current_year = int(
        new.era.year_start + new.turn * new.era.years_per_turn
    )

    if new.player.location not in new.visited_locations:
        new.visited_locations.append(new.player.location)

    # --- Fire pending consequences (before NPC actions) ---
    await _process_consequences(new)

    nearby = [n for n in new.npcs if n.location == new.player.location]
    elsewhere = [n for n in new.npcs if n.location != new.player.location]

    visible_activity = []

    if nearby:
        active_nearby = random.sample(nearby, min(len(nearby), random.randint(2, 4)))
        results = await asyncio.gather(
            *[_npc_autonomous_action(npc, new, nearby) for npc in active_nearby],
            return_exceptions=True,
        )
        for npc, result in zip(active_nearby, results):
            if isinstance(result, dict):
                action_desc = result.get("action", f"{npc.name} goes about their day.")
                visible_activity.append({
                    "npc_id": npc.id,
                    "npc_name": npc.name,
                    "npc_role": npc.role,
                    "activity": action_desc,
                    "interacts_with": result.get("interacts_with"),
                })
                new.events.append(Event(
                    turn=new.turn,
                    action_type="ambient",
                    description=action_desc,
                    target=result.get("interacts_with"),
                    location=npc.location,
                ))
                effect = _to_npc_effect(npc, result)
                apply_npc_effect(new, effect)

    if elsewhere:
        active_elsewhere = random.sample(elsewhere, min(len(elsewhere), max(1, len(elsewhere) // 3)))
        bg_results = await asyncio.gather(
            *[_npc_autonomous_action(npc, new, []) for npc in active_elsewhere],
            return_exceptions=True,
        )
        for npc, result in zip(active_elsewhere, bg_results):
            if isinstance(result, dict):
                new.events.append(Event(
                    turn=new.turn,
                    action_type="ambient_distant",
                    description=result.get("action", f"{npc.name} acts."),
                    target=result.get("interacts_with"),
                    location=npc.location,
                ))
                effect = _to_npc_effect(npc, result)
                apply_npc_effect(new, effect)

    _tick_tension(new)

    return new, visible_activity


async def advance_world(state: WorldState, ticks: int = 1) -> WorldState:
    """Advance the world by N ticks without generating visible activity.
    Used during travel when the player is in transit."""
    for _ in range(ticks):
        state, _ = await simulate_turn(state)
    return state


async def player_skip_turn(state: WorldState) -> dict:
    """The player chose inaction — their character acts autonomously."""
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)
    player_loc = get_player_location(state)
    nearby = npcs_near_player(state)
    other_names = ", ".join(n.name for n in nearby) or "no one"

    gc = state.ground_context or {}
    prompt = Template(raw_template).safe_substitute(
        character_name=state.player.name,
        character_role=state.player.role,
        character_description=state.player.description,
        character_disposition=state.player.disposition,
        other_npcs_here=other_names,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        era_feel=gc.get("era_feel", ""),
        material_conditions=gc.get("material_conditions", player_loc.material_conditions),
        story_so_far=build_story_summary(state),
        player_name=state.player.name,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        data = AutonomousActionResponse.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, Exception):
        data = autonomous_action_default(state.player.name)

    return {
        "action_type": "autonomous",
        "target": data.interacts_with,
        "intent": "inaction — character acts on their own",
        "era_description": data.action or f"{state.player.name} waits.",
        "npc_impacts": [],
    }


async def _npc_autonomous_action(npc: NPC, state: WorldState, nearby_npcs: List[NPC]) -> dict:
    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)

    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        if not state.locations:
            return autonomous_action_default(npc.name).model_dump()
        npc_loc = state.locations[0]

    other_names = ", ".join(
        n.name for n in nearby_npcs if n.id != npc.id
    ) or "no one"

    gc = state.ground_context or {}
    prompt = Template(raw_template).safe_substitute(
        character_name=npc.name,
        character_role=npc.role,
        character_description=npc.description,
        character_disposition=npc.disposition,
        other_npcs_here=other_names,
        location_name=npc_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        era_feel=gc.get("era_feel", ""),
        material_conditions=gc.get("material_conditions", npc_loc.material_conditions),
        story_so_far=build_story_summary(state),
        player_name=state.player.name,
    )

    try:
        raw = await chat(prompt, json_mode=True)
        return AutonomousActionResponse.model_validate(json.loads(raw)).model_dump()
    except (json.JSONDecodeError, ValidationError, Exception):
        return autonomous_action_default(npc.name).model_dump()


def _to_npc_effect(npc: NPC, result: dict) -> NPCEffect:
    """Convert raw LLM autonomous action output to a bounded NPCEffect."""
    disposition_shift = None
    mood = result.get("mood_shift")
    if mood and isinstance(mood, str) and mood != npc.disposition:
        from backend.world_state import _POSITIVE_SHIFTS, _NEGATIVE_SHIFTS
        if mood in _POSITIVE_SHIFTS.values() or mood == npc.disposition:
            disposition_shift = 1
        else:
            disposition_shift = -1

    location_change = None
    if result.get("wants_to_travel") and result.get("travel_destination"):
        location_change = result["travel_destination"]

    return NPCEffect(
        npc_id=npc.id,
        disposition_shift=disposition_shift,
        location_change=location_change,
    )


def _schedule_npc_travel(npc: NPC, destination: str, state: WorldState) -> None:
    """Move an NPC to a new location if the destination is valid."""
    dest_id = destination.lower().strip()
    valid_ids = {loc.id for loc in state.locations}
    if dest_id in valid_ids and dest_id != npc.location:
        npc.location = dest_id


def _tick_tension(state: WorldState) -> None:
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


# ---------------------------------------------------------------------------
# Consequence queue processing
# ---------------------------------------------------------------------------

async def _process_consequences(state: WorldState) -> None:
    """Fire all pending consequences for this turn.

    Two-phase validation: consequences are checked at fire time, not just
    at schedule time. Invalid consequences are superseded silently.
    """
    try:
        pending = await get_pending_consequences(state.run_id, state.turn)
    except Exception:
        return

    for c in pending:
        if _validate_consequence(c, state):
            _apply_consequence(c, state)
            try:
                await mark_consequence_fired(c["id"])
            except Exception:
                logger.error("Failed to mark consequence %d as fired", c["id"])
        else:
            try:
                await mark_consequence_superseded(c["id"])
            except Exception:
                logger.error("Failed to mark consequence %d as superseded", c["id"])


def _validate_consequence(consequence: dict, state: WorldState) -> bool:
    """Check whether a scheduled consequence is still valid given current state.

    Returns False if the target no longer exists or the world has diverged
    in a way that makes the consequence nonsensical.
    """
    target_type = consequence.get("target_type", "")
    target_id = consequence.get("target_id")

    if target_type == "location" and target_id:
        valid_ids = {loc.id for loc in state.locations}
        if target_id not in valid_ids:
            return False

    if target_type == "npc" and target_id:
        npc_ids = {npc.id for npc in state.npcs}
        if target_id not in npc_ids:
            return False

    if state.run_status not in ("active", "dead_observing"):
        return False

    return True


def _apply_consequence(consequence: dict, state: WorldState) -> None:
    """Apply a validated consequence's effect_payload to world state.

    Effects are bounded — each effect_type can only modify specific things.
    """
    effect_type = consequence["effect_type"]
    payload = consequence["effect_payload"]
    target_id = consequence.get("target_id")

    if effect_type == "tension_shift":
        _apply_tension_shift(state, target_id, payload)
    elif effect_type == "rumor":
        _apply_rumor(state, target_id, payload)
    elif effect_type == "trade_disruption":
        _apply_trade_disruption(state, target_id, payload)
    elif effect_type == "npc_arrival":
        _apply_npc_arrival(state, target_id, payload)
    elif effect_type == "event_spawn":
        _apply_event_spawn(state, payload)
    elif effect_type == "material_change":
        _apply_material_change(state, target_id, payload)
    else:
        logger.warning("Unknown effect_type: %s", effect_type)


def _apply_tension_shift(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Shift political_tension at a location by delta steps (+1/-1)."""
    delta = payload.get("delta", 0)
    if not delta:
        return
    for loc in state.locations:
        if loc.id == target_id:
            idx = (
                TENSION_LEVELS.index(loc.political_tension)
                if loc.political_tension in TENSION_LEVELS
                else 1
            )
            new_idx = max(0, min(len(TENSION_LEVELS) - 1, idx + delta))
            loc.political_tension = TENSION_LEVELS[new_idx]
            break


def _apply_rumor(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Inject a rumor event at the target location."""
    rumor_text = payload.get("rumor_text", "")
    if not rumor_text:
        return
    location = target_id or (state.locations[0].id if state.locations else None)
    state.events.append(Event(
        turn=state.turn,
        action_type="ambient_distant",
        description=rumor_text,
        location=location,
    ))


_FOOD_SCARCITY_LEVELS = ["abundant", "normal", "scarce", "critical"]


def _apply_trade_disruption(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Disrupt a trade route at the target location.

    Moves the specified route (or first active route) from trade_routes
    to disrupted_routes. Also shifts tension and worsens food scarcity.
    """
    route_id = payload.get("route_id")
    for loc in state.locations:
        if loc.id == target_id:
            if route_id and route_id in loc.trade_routes:
                loc.trade_routes.remove(route_id)
                if route_id not in loc.disrupted_routes:
                    loc.disrupted_routes.append(route_id)
            elif loc.trade_routes:
                disrupted = loc.trade_routes.pop(0)
                if disrupted not in loc.disrupted_routes:
                    loc.disrupted_routes.append(disrupted)

            idx = _FOOD_SCARCITY_LEVELS.index(loc.food_scarcity) \
                if loc.food_scarcity in _FOOD_SCARCITY_LEVELS else 1
            new_idx = min(len(_FOOD_SCARCITY_LEVELS) - 1, idx + 1)
            loc.food_scarcity = _FOOD_SCARCITY_LEVELS[new_idx]
            break

    _apply_tension_shift(state, target_id, {"delta": payload.get("delta", 1)})
    desc = payload.get("description", "Trade routes have been disrupted.")
    state.events.append(Event(
        turn=state.turn,
        action_type="ambient",
        description=desc,
        location=target_id,
    ))


def _apply_npc_arrival(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Spawn a new NPC at the target location from payload data."""
    name = payload.get("name", "Unknown Stranger")
    role = payload.get("role", "traveler")
    archetype = payload.get("archetype", "civilian")
    description = payload.get("description", f"A {role} who recently arrived.")

    npc = NPC(
        id=f"cq_{uuid.uuid4().hex[:8]}",
        name=name,
        role=role,
        archetype=archetype,
        social_class=payload.get("social_class", ""),
        location=target_id or (state.locations[0].id if state.locations else ""),
        description=description,
        disposition=payload.get("disposition", "cautious"),
        relationship_to_player="Unknown — you have never met.",
        memory_of_player=0.0,
        last_interaction_turn=0,
    )
    state.npcs.append(npc)

    state.events.append(Event(
        turn=state.turn,
        action_type="ambient",
        description=f"{name}, a {role}, arrives in the area.",
        location=target_id,
    ))


def _apply_event_spawn(state: WorldState, payload: dict) -> None:
    """Add a new world event to state.events."""
    state.events.append(Event(
        turn=state.turn,
        action_type=payload.get("action_type", "ambient"),
        description=payload.get("description", "Something significant happened."),
        target=payload.get("target"),
        location=payload.get("location"),
    ))


def _apply_material_change(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Update material conditions and food scarcity at a location."""
    desc = payload.get("description", "Conditions have changed.")
    food = payload.get("food_scarcity")

    for loc in state.locations:
        if loc.id == target_id:
            if desc:
                loc.material_conditions = desc
            if food and food in _FOOD_SCARCITY_LEVELS:
                loc.food_scarcity = food
            break

    state.events.append(Event(
        turn=state.turn,
        action_type="material_change",
        description=desc,
        location=target_id,
    ))
