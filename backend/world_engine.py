"""World engine — runs the living simulation every turn.

7-stage autonomous pipeline:
  1. Structural drift (no LLM)
  2. Scheduled consequences (no LLM)
  3. World events (no LLM, probabilistic)
  4. NPC autonomous actions (LLM for active tier, rule-based for adjacent)
  5. Player input (optional, handled by main.py)
  6. Narrative assembly (handled by main.py)
  7. Persistence (handled by main.py)

Stages 1-4 run inside simulate_turn(). Stages 5-7 are in main.py.
The world advances whether or not the player acts.

Model tier: QUALITY for active NPCs, player skip-turn, and arrival
catch-up (all use prompts/autonomous_action.md — prose-critical, the
player reads these directly). FAST (Ollama) for offscreen NPCs via
prompts/autonomous_action_light.md — one-sentence ambient activity
where model fidelity matters less than cost, fired many times per turn.
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

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import (
    AutonomousActionResponse,
    NPCEffect,
    autonomous_action_default,
)
from backend.npc_personality import choose_autonomous_action, tick_preoccupation_drift
from backend.world_drift import (
    tick_disposition_drift,
    tick_needs_decay,
    tick_rumor_propagation,
    tick_tension,
)
from backend.world_events import tick_world_events
from backend.utils import graph_distance as _graph_distance_shared
from backend.world_state import (
    TENSION_LEVELS,
    Event,
    NPC,
    ScheduledConsequence,
    WorldState,
    apply_npc_effect,
    build_story_summary,
    get_location,
    get_player_location,
    npcs_at_location,
    npcs_near_player,
    shift_disposition,
)

logger = logging.getLogger("chronos.world_engine")

_AUTONOMOUS_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "autonomous_action.md"
)


# ---------------------------------------------------------------------------
# Location graph helpers
# ---------------------------------------------------------------------------

def _graph_distance(
    loc_a: str, loc_b: str, state: WorldState,
) -> int:
    """BFS distance between two locations. Returns 999 if unreachable."""
    return _graph_distance_shared(loc_a, loc_b, state)


def get_npc_simulation_tier(
    npc: NPC, player_location: str, state: WorldState,
) -> str:
    """Determine an NPC's simulation tier based on graph distance to player.

    Returns "active", "adjacent", or "distant".
    """
    distance = _graph_distance(npc.location, player_location, state)
    if distance == 0:
        return "active"
    if distance == 1:
        return "adjacent"
    return "distant"


def should_simulate_npc(npc: NPC, tier: str, current_turn: int) -> bool:
    """Check whether an NPC should receive simulation this turn based on tier.

    Active: every turn.
    Adjacent: every 2 turns (based on last_simulated_turn).
    Distant: every 5 turns (based on last_simulated_turn).
    """
    if tier == "active":
        return True
    turns_since = current_turn - npc.last_simulated_turn
    if tier == "adjacent":
        return turns_since >= 2
    return turns_since >= 5


def get_npcs_by_tier(
    state: WorldState,
) -> Tuple[List[NPC], List[NPC], List[NPC]]:
    """Split NPCs into active/adjacent/distant tiers relative to the player."""
    active = []
    adjacent = []
    distant = []
    for npc in state.npcs:
        tier = get_npc_simulation_tier(npc, state.player.location, state)
        if tier == "active":
            active.append(npc)
        elif tier == "adjacent":
            adjacent.append(npc)
        else:
            distant.append(npc)
    return active, adjacent, distant


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

_ARCHETYPE_PRIORITY = {
    "general": 10, "noble": 9, "soldier": 8, "priest": 7,
    "clergy": 7, "merchant": 6, "scribe": 5, "farmer": 4, "refugee": 3,
}


def resolve_action_conflicts(
    actions: List[Tuple[NPC, str, Optional[dict]]],
    state: WorldState,
) -> List[Tuple[NPC, str, Optional[dict]]]:
    """Conflict resolution: when multiple NPCs target the same entity,
    only the highest-priority archetype's action proceeds. Others are dropped."""
    if len(actions) <= 1:
        return actions

    target_claims: Dict[str, List[Tuple[int, int, NPC, str, Optional[dict]]]] = {}
    for idx, (npc, opp_type, result) in enumerate(actions):
        target = None
        if result and isinstance(result, dict):
            target = result.get("interacts_with")
        if target:
            priority = _ARCHETYPE_PRIORITY.get(npc.archetype, 5)
            target_claims.setdefault(target, []).append(
                (priority, idx, npc, opp_type, result)
            )

    blocked_indices: set = set()
    for target, claims in target_claims.items():
        if len(claims) <= 1:
            continue
        claims.sort(key=lambda x: -x[0])
        for _, idx, npc, _, _ in claims[1:]:
            blocked_indices.add(idx)

    return [
        actions[i] for i in range(len(actions))
        if i not in blocked_indices
    ]


# ---------------------------------------------------------------------------
# Core simulation tick — stages 1-4
# ---------------------------------------------------------------------------

async def simulate_turn(state: WorldState) -> Tuple[WorldState, List[dict]]:
    """Run one simulation tick (stages 1-4). Returns (new_state, ambient_events).

    Stage 1: Structural drift (tension, disposition, needs, rumors)
    Stage 2: Scheduled consequences (in-memory + DB queue)
    Stage 3: World events (probabilistic)
    Stage 4: NPC autonomous actions (tiered: active/adjacent/distant)

    ambient_events contains only activity at the player's location.
    """
    new = state.model_copy(deep=True)
    new.turn += 1
    new.current_year = round(
        new.era.year_start + new.turn * new.era.years_per_turn
    )

    if new.player.location not in new.visited_locations:
        new.visited_locations.append(new.player.location)

    # --- STAGE 0: Refresh ground context if stale ---
    if new.ground_context_stale:
        try:
            from backend.hce import generate_ground_context
            new.ground_context = await generate_ground_context(new)
            new.ground_context_stale = False
            logger.info("Ground context refreshed at turn %d", new.turn)
        except Exception as exc:
            logger.warning("Ground context refresh failed, will retry next turn: %s", exc)

    # --- STAGE 1: Structural drift (no LLM) ---
    tick_tension(new)
    tick_disposition_drift(new)
    tick_needs_decay(new)
    tick_rumor_propagation(new)
    tick_preoccupation_drift(new)

    # --- STAGE 2: Scheduled consequences (no LLM) ---
    _process_in_memory_consequences(new)

    # --- STAGE 3: World events (no LLM) ---
    tick_world_events(new)

    # --- STAGE 4: NPC autonomous actions (tiered) ---
    visible_activity = await _run_npc_actions(new)

    return new, visible_activity


_LIGHT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "autonomous_action_light.md"
)


async def _npc_light_action(npc: NPC, state: WorldState) -> dict:
    """Lighter LLM call for offscreen NPCs — less context, 1 sentence output."""
    from backend.npc_personality import get_dominant_need

    raw_template = load_prompt(_LIGHT_TEMPLATE_PATH)

    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        return autonomous_action_default(npc.name).model_dump()

    dominant = get_dominant_need(npc.needs)
    prompt = Template(raw_template).safe_substitute(
        character_name=npc.name,
        character_role=npc.role,
        location_name=npc_loc.name,
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        character_disposition=npc.disposition,
        dominant_need=dominant.replace("_", " "),
        current_activity=npc.current_activity or f"Going about duties as a {npc.role}.",
        local_tension=npc_loc.political_tension,
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="fast",
            schema=AutonomousActionResponse,
            call_site="autonomous_action_light",
        )
        return AutonomousActionResponse.model_validate(json.loads(raw)).model_dump()
    except (json.JSONDecodeError, ValidationError, Exception):
        return autonomous_action_default(npc.name).model_dump()


async def _run_npc_actions(state: WorldState) -> List[dict]:
    """Stage 4: tiered NPC autonomous actions.

    Every NPC gets an LLM call every turn — the world is always alive.
    Active (player's location): full LLM call with rich context.
    Adjacent/Distant: lighter LLM call with less context, 1 sentence output.
    """
    active_npcs, adjacent_npcs, distant_npcs = get_npcs_by_tier(state)
    offscreen_npcs = adjacent_npcs + distant_npcs

    state_snapshot = state.model_copy(deep=True)
    visible_activity = []
    all_actions: List[Tuple[NPC, str, Optional[dict]]] = []

    # Active tier: full LLM call with rich context (sampled subset)
    active_tasks = []
    active_sample = []
    active_unseen = []
    if active_npcs:
        sample_count = min(len(active_npcs), random.randint(2, 4))
        active_sample = random.sample(active_npcs, sample_count)
        sampled_ids = {n.id for n in active_sample}
        active_unseen = [n for n in active_npcs if n.id not in sampled_ids]
        active_tasks = [
            _npc_autonomous_action(npc, state_snapshot,
                                   [n for n in active_npcs if n.id != npc.id])
            for npc in active_sample
        ]

    # All non-sampled NPCs get light LLM calls (active unseen + offscreen)
    light_npcs = active_unseen + offscreen_npcs
    offscreen_tasks = [
        _npc_light_action(npc, state_snapshot)
        for npc in light_npcs
    ]

    # Run all LLM calls concurrently
    all_results = await asyncio.gather(
        *(active_tasks + offscreen_tasks),
        return_exceptions=True,
    )

    active_results = all_results[:len(active_tasks)]
    offscreen_results = all_results[len(active_tasks):]

    # Process active results (visible to player)
    for npc, result in zip(active_sample, active_results):
        npc.last_simulated_turn = state.turn
        opp_type = choose_autonomous_action(npc, state_snapshot)
        opp_text = _resolve_opportunity_text(npc, opp_type, state_snapshot)
        if isinstance(result, dict):
            action_desc = result.get("action", f"{npc.name} goes about their day.")
            visible_activity.append({
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_role": npc.role,
                "activity": action_desc,
                "interacts_with": result.get("interacts_with"),
                "opportunity": opp_text,
            })
            all_actions.append((npc, opp_type, result))

    # Process all non-sampled NPC results (world keeps turning)
    for npc, result in zip(light_npcs, offscreen_results):
        npc.last_simulated_turn = state.turn
        opp_type = choose_autonomous_action(npc, state_snapshot)
        if isinstance(result, dict):
            all_actions.append((npc, opp_type, result))

    # Resolve conflicts then apply effects
    resolved = resolve_action_conflicts(all_actions, state)
    for npc, opp_type, result in resolved:
        if result and isinstance(result, dict):
            state.events.append(Event(
                turn=state.turn,
                action_type="ambient" if npc.location == state.player.location else "ambient_distant",
                description=result.get("action", f"{npc.name} acts."),
                target=result.get("interacts_with"),
                location=npc.location,
            ))
            new_act = result.get("new_activity", "")
            if new_act:
                npc.current_activity = new_act
            elif not npc.current_activity:
                npc.current_activity = result.get("action", "")
            effect = _to_npc_effect(npc, result)
            apply_npc_effect(state, effect)

    return visible_activity


async def advance_world(state: WorldState, ticks: int = 1) -> WorldState:
    """Advance the world by N ticks without generating visible activity.
    Used during travel when the player is in transit."""
    for _ in range(ticks):
        state, _ = await simulate_turn(state)
    return state


async def advance_world_skip(state: WorldState, ticks: int = 1) -> WorldState:
    """Advance the world by N ticks for time-skip / speed-up.
    Runs stages 1-4 only. No player input."""
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
        dominant_need="getting through the day",
        urgent_needs="nothing urgent",
        current_activity="Waiting and watching.",
        chosen_opportunity="daily life",
        what_character_knows=_format_ground_context_field(gc, "what_character_knows", "What anyone in your position would know."),
        local_rumors=_format_ground_context_field(gc, "local_rumors", "Nothing specific."),
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
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=AutonomousActionResponse,
            call_site="autonomous_action.player_skip",
        )
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


def _format_urgent_needs(npc: NPC) -> str:
    """Format urgent needs as a human-readable string. Never returns empty."""
    from backend.npc_personality import get_urgent_needs
    urgent = get_urgent_needs(npc.needs)
    if not urgent:
        return "nothing urgent"
    return ", ".join(n.replace("_", " ") for n in urgent)


def _format_ground_context_field(gc: dict, field: str, fallback: str) -> str:
    """Extract a ground context field. Never returns empty."""
    val = gc.get(field)
    if not val:
        return fallback
    if isinstance(val, list):
        if not val:
            return fallback
        if len(val) == 1:
            return val[0]
        return "; ".join(val)
    return str(val)


def _resolve_opportunity_text(npc: NPC, opp_type: str, state: WorldState) -> str:
    """Pick an era-specific opportunity description for this NPC's archetype.
    Falls back to the generic opportunity type string."""
    try:
        from backend.eras import ALL_ERAS
        era_key = state.era.name.lower().replace(" ", "_").replace("fall_of_", "fall_of_")
        for key, cfg in ALL_ERAS.items():
            if cfg["name"] == state.era.name:
                era_key = key
                break
        era_config = ALL_ERAS.get(era_key, {})
        era_opps = era_config.get("npc_opportunities", {})
        archetype_opps = era_opps.get(npc.archetype, [])
        if archetype_opps:
            return random.choice(archetype_opps)
    except Exception:
        pass
    return opp_type.replace("_", " ")


async def _npc_autonomous_action(npc: NPC, state: WorldState, nearby_npcs: List[NPC]) -> dict:
    from backend.npc_personality import get_dominant_need

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

    opp_type = choose_autonomous_action(npc, state)
    opp_text = _resolve_opportunity_text(npc, opp_type, state)

    gc = state.ground_context or {}
    prompt = Template(raw_template).safe_substitute(
        character_name=npc.name,
        character_role=npc.role,
        character_description=npc.description,
        character_disposition=npc.disposition,
        dominant_need=get_dominant_need(npc.needs).replace("_", " "),
        urgent_needs=_format_urgent_needs(npc),
        current_activity=npc.current_activity or f"Going about duties as a {npc.role}.",
        chosen_opportunity=opp_text,
        what_character_knows=_format_ground_context_field(gc, "what_character_knows", "What anyone in your position would know."),
        local_rumors=_format_ground_context_field(gc, "local_rumors", "Nothing specific."),
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
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=AutonomousActionResponse,
            call_site="autonomous_action.active",
        )
        return AutonomousActionResponse.model_validate(json.loads(raw)).model_dump()
    except (json.JSONDecodeError, ValidationError, Exception):
        return autonomous_action_default(npc.name).model_dump()


def _to_npc_effect(npc: NPC, result: dict) -> NPCEffect:
    """Convert raw LLM autonomous action output to a bounded NPCEffect."""
    disposition_shift = None
    mood = result.get("mood_shift")
    if mood and isinstance(mood, str) and mood != npc.disposition:
        from backend.world_state import _POSITIVE_SHIFTS
        if mood in _POSITIVE_SHIFTS.values():
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


# ---------------------------------------------------------------------------
# In-memory consequence queue processing (stage 2a)
# ---------------------------------------------------------------------------

def _process_in_memory_consequences(state: WorldState) -> None:
    """Fire all pending in-memory consequences for this turn."""
    pending = get_pending_consequences_mem(state, state.turn)
    for c in pending:
        c_dict = {
            "target_type": c.target_type,
            "target_id": c.target_id,
            "effect_type": c.effect_type,
            "effect_payload": c.effect_payload,
        }
        if _validate_consequence(c_dict, state):
            _apply_consequence(c_dict, state)
            mark_consequence_fired_mem(state, c.id)
        else:
            c.superseded = True

    state.consequence_queue = [
        c for c in state.consequence_queue
        if not (c.fired or c.superseded)
    ]


# ---------------------------------------------------------------------------
# Arrival catch-up
# ---------------------------------------------------------------------------

async def generate_arrival_catchup(
    npcs: List[NPC], state: WorldState,
) -> List[str]:
    """Generate what NPCs at a new location have been doing since last visit.

    One LLM call per NPC — they are mid-action when the player arrives.
    Uses needs + recent events at location as context.
    """
    if not npcs:
        return []

    raw_template = load_prompt(_AUTONOMOUS_TEMPLATE_PATH)
    gc = state.ground_context or {}

    async def _catchup_for_npc(npc: NPC) -> str:
        try:
            npc_loc = next(l for l in state.locations if l.id == npc.location)
        except StopIteration:
            return f"{npc.name} is here, going about their business."

        nearby = [n for n in state.npcs if n.location == npc.location and n.id != npc.id]
        other_names = ", ".join(n.name for n in nearby) or "no one"

        from backend.npc_personality import get_dominant_need
        opp_type = choose_autonomous_action(npc, state)

        prompt = Template(raw_template).safe_substitute(
            character_name=npc.name,
            character_role=npc.role,
            character_description=npc.description,
            character_disposition=npc.disposition,
            dominant_need=get_dominant_need(npc.needs).replace("_", " "),
            urgent_needs=_format_urgent_needs(npc),
            current_activity=npc.current_activity or f"Going about duties as a {npc.role}.",
            chosen_opportunity=opp_type.replace("_", " "),
            what_character_knows=_format_ground_context_field(gc, "what_character_knows", "What anyone in your position would know."),
            local_rumors=_format_ground_context_field(gc, "local_rumors", "Nothing specific."),
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
            raw, _ = await call_llm(
                prompt,
                tier="quality",
                schema=AutonomousActionResponse,
                call_site="autonomous_action.arrival_catchup",
            )
            data = AutonomousActionResponse.model_validate(json.loads(raw))
            return data.action or f"{npc.name} is here."
        except Exception:
            return f"{npc.name} is here, going about their business."

    results = await asyncio.gather(
        *[_catchup_for_npc(npc) for npc in npcs[:3]],
        return_exceptions=True,
    )
    return [
        r if isinstance(r, str) else f"Someone is here."
        for r in results
    ]




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
    elif effect_type == "disposition_shift":
        _apply_disposition_shift(state, target_id, payload)
    elif effect_type == "need_pressure":
        _apply_need_pressure(state, target_id, payload)
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
    from backend.npc_personality import generate_personality, calculate_needs

    name = payload.get("name", "Unknown Stranger")
    role = payload.get("role", "traveler")
    archetype = payload.get("archetype", "civilian")
    description = payload.get("description", f"A {role} who recently arrived.")

    personality = generate_personality(archetype)
    needs = calculate_needs(archetype, personality)

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
        personality=personality,
        needs=needs,
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


def _apply_disposition_shift(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Shift an NPC's disposition by delta steps."""
    delta = payload.get("delta", 0)
    if not delta or not target_id:
        return
    for npc in state.npcs:
        if npc.id == target_id:
            npc.disposition = shift_disposition(npc.disposition, delta)
            break


def _apply_need_pressure(
    state: WorldState, target_id: Optional[str], payload: dict,
) -> None:
    """Apply pressure to specific NPC needs (increase or decrease)."""
    if not target_id:
        return
    need_name = payload.get("need")
    delta = payload.get("delta", 0)
    if not need_name or not delta:
        return
    for npc in state.npcs:
        if npc.id == target_id:
            d = npc.needs.model_dump()
            if need_name in d:
                from backend.npc_personality import _clamp
                d[need_name] = _clamp(d[need_name] + delta)
                from backend.world_state import NpcNeeds
                npc.needs = NpcNeeds(**d)
                npc.needs_history.append({
                    "turn": state.turn,
                    "need": need_name,
                    "value": round(d[need_name], 1),
                    "event": "need_pressure",
                    "delta": delta,
                })
            break


# ---------------------------------------------------------------------------
# In-memory consequence queue operations
# ---------------------------------------------------------------------------

def schedule_consequence_mem(
    state: WorldState, consequence: ScheduledConsequence,
) -> None:
    """Add a consequence to the in-memory queue on WorldState."""
    state.consequence_queue.append(consequence)


def get_pending_consequences_mem(
    state: WorldState, current_turn: int,
) -> List[ScheduledConsequence]:
    """Return all unfired, non-superseded consequences due by current_turn."""
    return [
        c for c in state.consequence_queue
        if c.trigger_turn <= current_turn and not c.fired and not c.superseded
    ]


def mark_consequence_fired_mem(
    state: WorldState, consequence_id: str,
) -> None:
    """Mark a consequence as fired in the in-memory queue."""
    for c in state.consequence_queue:
        if c.id == consequence_id:
            c.fired = True
            break


def mark_consequence_superseded_mem(
    state: WorldState, source_event_id: str,
) -> None:
    """Supersede all unfired consequences from a given source event."""
    for c in state.consequence_queue:
        if c.source_event_id == source_event_id and not c.fired:
            c.superseded = True
