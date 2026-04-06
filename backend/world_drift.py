"""Structural drift — LLM-free world changes every tick.

Runs before NPC actions. No LLM calls anywhere in this module.
Tension escalates, dispositions drift toward archetype baselines,
NPC needs decay, and rumors propagate between adjacent locations.
"""

from __future__ import annotations

import random
import uuid
from typing import List

from backend.npc_personality import (
    ARCHETYPE_BASELINE_DISPOSITION,
    decay_needs,
)
from backend.utils import TENSION_LEVELS, tension_index, tension_numeric
from backend.world_state import (
    ScheduledConsequence,
    WorldState,
    shift_disposition,
)


def tick_tension(state: WorldState) -> WorldState:
    """Escalate tension at a random location every 3 turns.

    If tension >= 90 (critical) at any location, 15% chance to spread
    +10 tension (1 step) to a randomly chosen adjacent location.
    """
    if state.turn % 3 != 0:
        return state

    if not state.locations:
        return state

    loc = random.choice(state.locations)
    idx = tension_index(loc.political_tension)
    if idx < len(TENSION_LEVELS) - 1:
        loc.political_tension = TENSION_LEVELS[idx + 1]

    for loc in state.locations:
        if tension_numeric(loc.political_tension) >= 90:
            if random.random() < 0.15:
                neighbor_ids = list(loc.neighbors.keys())
                if neighbor_ids:
                    spread_to = random.choice(neighbor_ids)
                    for other in state.locations:
                        if other.id == spread_to:
                            other_idx = tension_index(other.political_tension)
                            if other_idx < len(TENSION_LEVELS) - 1:
                                other.political_tension = TENSION_LEVELS[other_idx + 1]
                            break

    return state


# ---------------------------------------------------------------------------
# 3b: Disposition drift
# ---------------------------------------------------------------------------

_DISPOSITION_ORDER = [
    "hostile", "fearful", "wary", "suspicious", "grim",
    "cautious", "neutral", "guarded", "reserved", "formal",
    "commanding", "engaged", "fervent", "warming",
]


def _disposition_rank(disp: str) -> int:
    if disp in _DISPOSITION_ORDER:
        return _DISPOSITION_ORDER.index(disp)
    return _DISPOSITION_ORDER.index("neutral")


def tick_disposition_drift(state: WorldState) -> WorldState:
    """Every 5 turns, each NPC's disposition drifts 1 step toward baseline."""
    if state.turn % 5 != 0:
        return state

    for npc in state.npcs:
        baseline = ARCHETYPE_BASELINE_DISPOSITION.get(npc.archetype)
        if not baseline:
            continue
        if npc.disposition == baseline:
            continue

        current_rank = _disposition_rank(npc.disposition)
        baseline_rank = _disposition_rank(baseline)

        if current_rank < baseline_rank:
            npc.disposition = shift_disposition(npc.disposition, 1)
        elif current_rank > baseline_rank:
            npc.disposition = shift_disposition(npc.disposition, -1)

    return state


# ---------------------------------------------------------------------------
# 3c: Needs decay
# ---------------------------------------------------------------------------

def tick_needs_decay(state: WorldState) -> WorldState:
    """Decay all NPC needs based on world tension and era context."""
    for npc in state.npcs:
        try:
            npc_loc = next(l for l in state.locations if l.id == npc.location)
            tension = npc_loc.political_tension
        except StopIteration:
            tension = "moderate"

        decay_needs(
            npc,
            world_tension=tension,
            era_stability="normal",
            current_turn=state.turn,
        )

    return state


# ---------------------------------------------------------------------------
# 3d: Rumor propagation
# ---------------------------------------------------------------------------

RUMOR_TEMPLATES = [
    "Word from {location} speaks of {event_summary}.",
    "A traveler passing through claims {event_summary} in {location}.",
    "There are reports, unconfirmed, of {event_summary} near {location}.",
]


def tick_rumor_propagation(state: WorldState) -> WorldState:
    """Every 3 turns: locations with high tension or active events
    generate rumors that propagate to adjacent locations."""
    if state.turn % 3 != 0:
        return state

    for loc in state.locations:
        if tension_numeric(loc.political_tension) < 60:
            significant = [
                e for e in state.events
                if e.location == loc.id
                and e.turn >= state.turn - 3
                and e.action_type not in ("ambient_distant",)
            ]
            if not significant:
                continue

        neighbor_ids = list(loc.neighbors.keys())
        if not neighbor_ids:
            continue

        recent_events = [
            e for e in state.events
            if e.location == loc.id and e.turn >= state.turn - 3
        ]
        if not recent_events:
            event_summary = f"growing unrest at {loc.name}"
        else:
            event_summary = recent_events[-1].description[:80]

        target_id = random.choice(neighbor_ids)
        template = random.choice(RUMOR_TEMPLATES)
        rumor_text = template.format(
            location=loc.name, event_summary=event_summary,
        )

        delay = random.randint(1, 2)
        state.consequence_queue.append(ScheduledConsequence(
            id=uuid.uuid4().hex[:12],
            source_event_id=None,
            trigger_turn=state.turn + delay,
            target_type="location",
            target_id=target_id,
            effect_type="rumor",
            effect_payload={"rumor_text": rumor_text},
        ))

    return state
