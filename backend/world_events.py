"""Probabilistic world events — LLM-free.

Each tick, location-level and NPC-level rules fire independently based on
world state conditions and probability rolls. No LLM calls in this module.
"""

from __future__ import annotations

import random
import uuid
from typing import List, Optional

from backend.world_state import (
    TENSION_LEVELS,
    Event,
    Location,
    NPC,
    ScheduledConsequence,
    WorldState,
    npcs_at_location,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tension_numeric(tension: str) -> int:
    return {"low": 10, "moderate": 40, "high": 70, "critical": 95}.get(tension, 40)


def _tension_index(tension: str) -> int:
    if tension in TENSION_LEVELS:
        return TENSION_LEVELS.index(tension)
    return 1


def _get_npcs_at(location_id: str, state: WorldState) -> List[NPC]:
    return npcs_at_location(state, location_id)


def _lowest_tension_adjacent(npc_location: str, state: WorldState) -> Optional[str]:
    """Find the adjacent location with the lowest tension."""
    npc_loc = None
    for loc in state.locations:
        if loc.id == npc_location:
            npc_loc = loc
            break
    if not npc_loc or not npc_loc.neighbors:
        return None

    best_id = None
    best_tension = 999
    for neighbor_id in npc_loc.neighbors:
        for loc in state.locations:
            if loc.id == neighbor_id:
                t = _tension_numeric(loc.political_tension)
                if t < best_tension:
                    best_tension = t
                    best_id = neighbor_id
                break
    return best_id


# ---------------------------------------------------------------------------
# Location-level rules
# ---------------------------------------------------------------------------

def _check_armed_skirmish(loc: Location, state: WorldState) -> Optional[Event]:
    if _tension_numeric(loc.political_tension) < 80:
        return None
    if not any(n.archetype in ("soldier", "general") for n in _get_npcs_at(loc.id, state)):
        return None
    if random.random() >= 0.30:
        return None
    return Event(
        turn=state.turn,
        action_type="armed_skirmish",
        description=f"Armed conflict has broken out near {loc.name}.",
        location=loc.id,
    )


def _check_civilian_unrest(loc: Location, state: WorldState) -> Optional[Event]:
    if _tension_numeric(loc.political_tension) < 60:
        return None
    if any(n.archetype in ("soldier", "general") for n in _get_npcs_at(loc.id, state)):
        return None
    if random.random() >= 0.20:
        return None
    return Event(
        turn=state.turn,
        action_type="civilian_unrest",
        description=f"Unrest among the population at {loc.name}.",
        location=loc.id,
    )


def _check_tension_spread(loc: Location, state: WorldState) -> Optional[dict]:
    if _tension_numeric(loc.political_tension) < 90:
        return None
    if random.random() >= 0.15:
        return None
    neighbor_ids = list(loc.neighbors.keys())
    if not neighbor_ids:
        return None
    target = random.choice(neighbor_ids)
    return {"type": "tension_spread", "target_id": target, "delta": 1}


def _check_food_shortage_rumor(loc: Location, state: WorldState) -> Optional[ScheduledConsequence]:
    if state.turn <= 5:
        return None
    has_famine = any(
        e.action_type == "famine" and e.location == loc.id
        for e in state.events
    )
    if not has_famine:
        return None
    if random.random() >= 0.25:
        return None
    return ScheduledConsequence(
        id=uuid.uuid4().hex[:12],
        trigger_turn=state.turn + 1,
        target_type="location",
        target_id=loc.id,
        effect_type="rumor",
        effect_payload={"rumor_text": f"Word spreads of food shortages in {loc.name}."},
    )


def _check_siege_trade_disruption(loc: Location, state: WorldState) -> Optional[ScheduledConsequence]:
    has_siege = any(
        e.action_type == "siege" and e.location == loc.id
        for e in state.events
    )
    if not has_siege or state.turn <= 3:
        return None
    if random.random() >= 0.40:
        return None
    return ScheduledConsequence(
        id=uuid.uuid4().hex[:12],
        trigger_turn=state.turn + 2,
        target_type="location",
        target_id=loc.id,
        effect_type="trade_disruption",
        effect_payload={
            "description": f"The siege at {loc.name} has cut trade routes.",
            "delta": 1,
        },
    )


def _check_attract_merchant(loc: Location, state: WorldState) -> Optional[Event]:
    if _tension_numeric(loc.political_tension) >= 30:
        return None
    if random.random() >= 0.20:
        return None
    return Event(
        turn=state.turn,
        action_type="merchant_arrival",
        description=f"A traveling merchant arrives in {loc.name}, drawn by the relative peace.",
        location=loc.id,
    )


# ---------------------------------------------------------------------------
# NPC-level rules
# ---------------------------------------------------------------------------

def _check_refugee_flight(npc: NPC, state: WorldState) -> Optional[str]:
    """Returns destination location id if the refugee should flee, else None."""
    if npc.archetype != "refugee":
        return None
    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        return None
    if _tension_numeric(npc_loc.political_tension) < 70:
        return None
    if random.random() >= 0.50:
        return None
    return _lowest_tension_adjacent(npc.location, state)


# ---------------------------------------------------------------------------
# Main tick function
# ---------------------------------------------------------------------------

def tick_world_events(state: WorldState) -> WorldState:
    """Run all probabilistic world event rules for this tick.

    Location rules fire per-location. NPC rules fire per-NPC.
    Effects are applied directly for immediate effects,
    or scheduled via consequence_queue for delayed effects.
    """
    for loc in state.locations:
        evt = _check_armed_skirmish(loc, state)
        if evt:
            state.events.append(evt)

        evt = _check_civilian_unrest(loc, state)
        if evt:
            state.events.append(evt)

        spread = _check_tension_spread(loc, state)
        if spread:
            for target_loc in state.locations:
                if target_loc.id == spread["target_id"]:
                    idx = _tension_index(target_loc.political_tension)
                    new_idx = min(len(TENSION_LEVELS) - 1, idx + spread["delta"])
                    target_loc.political_tension = TENSION_LEVELS[new_idx]
                    break

        consequence = _check_food_shortage_rumor(loc, state)
        if consequence:
            state.consequence_queue.append(consequence)

        consequence = _check_siege_trade_disruption(loc, state)
        if consequence:
            state.consequence_queue.append(consequence)

        evt = _check_attract_merchant(loc, state)
        if evt:
            state.events.append(evt)

    for npc in list(state.npcs):
        dest = _check_refugee_flight(npc, state)
        if dest:
            valid_ids = {l.id for l in state.locations}
            if dest in valid_ids and dest != npc.location:
                old_loc = npc.location
                npc.location = dest
                state.events.append(Event(
                    turn=state.turn,
                    action_type="refugee_flight",
                    description=f"{npc.name} flees from the danger, heading to safer ground.",
                    target=dest,
                    location=old_loc,
                ))

    return state
