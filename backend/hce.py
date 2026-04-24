"""Historical Context Engine (HCE) — ground-level context at run initialization.

Layer 1: Events DB (static, queried at runtime)
Layer 2: Ground-Level Context Generator (dynamic, generated once at run init)

The HCE answers: "What was the world actually like at this moment, from the
ground up, for a specific person in a specific place?"

Model tier: LOCAL (llama3.1:8b) — one call at run init, not per-turn.
Prompt template: prompts/ground_context.md (design artifact, reviewed separately).

Design source: context/game logic context/historical-context-engine.md
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import GroundContextResponse
from backend.persistence import query_historical_events
from backend.player_knowledge import (
    filter_historical_events,
    _knowledge_tier,
)
from backend.world_state import ScheduledConsequence, WorldState, get_player_location

logger = logging.getLogger("chronos.hce")

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "ground_context.md"

# Events within this window of the run's start year are considered
# for the ground context and consequence scheduling.
_EVENT_WINDOW_YEARS = 50


async def generate_ground_context(state: WorldState) -> Dict[str, Any]:
    """Generate ground-level context for the current moment.

    Queries Events DB using the current year (not just era start), filters
    through Knowledge Matrix, passes known + rumor events to LLM, returns
    a GroundContext dict. Called at run init and whenever ground_context_stale
    is set (location change, significant world event).
    """
    current_year = state.current_year or state.era.year_start
    region = state.era.region

    raw_events = await query_historical_events(
        year_start=current_year - _EVENT_WINDOW_YEARS,
        year_end=current_year + 5,
        region=region,
    )

    if not raw_events:
        raw_events = await query_historical_events(
            year_start=current_year - _EVENT_WINDOW_YEARS,
            year_end=current_year + 5,
        )

    filtered = filter_historical_events(raw_events, state)

    known_events = [
        ev for ev in filtered
        if ev.knowledge_quality in ("witnessed", "known")
    ]
    rumor_events = [
        ev for ev in filtered
        if ev.knowledge_quality.startswith("rumor")
    ]

    known_text = _format_events_for_prompt(known_events) or "No major events known."
    rumor_text = _format_rumors_for_prompt(rumor_events) or "No rumors heard."

    player_loc = get_player_location(state)
    raw_template = load_prompt(_PROMPT_PATH)

    prompt = Template(raw_template).safe_substitute(
        character_name=state.player.name,
        character_role=state.player.role,
        character_archetype=state.player.archetype,
        location_name=player_loc.name,
        year=state.current_year or year_start,
        era_description=state.era.description,
        known_events=known_text,
        rumor_events=rumor_text,
    )

    try:
        raw_response, _ = await call_llm(
            prompt,
            tier="quality",
            schema=GroundContextResponse,
            call_site="ground_context",
        )
        parsed = json.loads(raw_response)
        context = GroundContextResponse.model_validate(parsed)
        return context.model_dump()
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.warning("Ground context generation failed: %s", exc)
        return _fallback_context(state, known_events, rumor_events)


async def schedule_canonical_consequences(state: WorldState) -> int:
    """Schedule consequences from canonical events in progress at run start.

    Writes directly to state.consequence_queue (in-memory, persisted with state).
    Returns the number of consequences scheduled.
    """
    year_start = state.era.year_start
    region = state.era.region

    raw_events = await query_historical_events(
        year_start=year_start - 5,
        year_end=year_start + 2,
        region=region,
    )

    if not raw_events:
        return 0

    scheduled = 0
    for ev in raw_events:
        consequences = _derive_consequences(ev, state)
        for c in consequences:
            state.consequence_queue.append(ScheduledConsequence(
                source_event_id=str(ev.get("id")) if ev.get("id") else None,
                trigger_turn=c["trigger_turn"],
                target_type=c["target_type"],
                target_id=c["target_id"],
                effect_type=c["effect_type"],
                effect_payload=c["effect_payload"],
            ))
            scheduled += 1

    logger.info("Scheduled %d canonical consequences for run %s", scheduled, state.run_id)
    return scheduled


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_events_for_prompt(events: list) -> str:
    lines = []
    for ev in events:
        lines.append(f"- [{ev.year}] {ev.event} (type: {ev.event_type}, significance: {ev.significance})")
    return "\n".join(lines)


def _format_rumors_for_prompt(events: list) -> str:
    lines = []
    for ev in events:
        reliability = "reliable" if (ev.accuracy and ev.accuracy >= 0.5) else "unreliable"
        lines.append(f"- [{ev.year}] {ev.event} (accuracy: {reliability})")
    return "\n".join(lines)


def _fallback_context(
    state: WorldState,
    known: list,
    rumors: list,
) -> Dict[str, Any]:
    """Build a minimal GroundContext without an LLM call."""
    player_loc = get_player_location(state)
    return GroundContextResponse(
        era_feel=f"Life in {player_loc.name} is uncertain. The air is thick with worry.",
        what_character_knows=f"As a {state.player.archetype}, you know what anyone in your position would know.",
        local_rumors=[ev.event for ev in rumors[:5]],
        material_conditions="Conditions are difficult but survivable.",
        recent_events_known=[ev.event for ev in known[:4]],
        recent_events_unknown=[],
    ).model_dump()


def _derive_consequences(
    event: Dict[str, Any], state: WorldState,
) -> List[Dict[str, Any]]:
    """Derive scheduled consequences from a canonical event near run start.

    Uses the event's type and significance to generate appropriate
    downstream effects without an LLM call.
    """
    consequences: List[Dict[str, Any]] = []
    ev_type = event.get("type", "")
    significance = event.get("significance", "local")
    affects = event.get("affects", [])
    region = event.get("region", "")

    target_loc = _best_target_location(region, state)

    if ev_type == "war" or "military" in affects:
        consequences.append({
            "trigger_turn": 2,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "tension_shift",
            "effect_payload": {"delta": 1},
        })
        if significance in ("regional", "civilizational"):
            consequences.append({
                "trigger_turn": 4,
                "target_type": "location",
                "target_id": target_loc,
                "effect_type": "rumor",
                "effect_payload": {
                    "rumor_text": f"Refugees speak of {event.get('event', 'conflict in the region')}.",
                },
            })

    if ev_type == "famine" or "agriculture" in affects:
        consequences.append({
            "trigger_turn": 3,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "trade_disruption",
            "effect_payload": {
                "delta": 1,
                "description": "Food supplies have grown scarce. Prices rise.",
            },
        })

    if ev_type == "epidemic" or "population" in affects:
        consequences.append({
            "trigger_turn": 3,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "tension_shift",
            "effect_payload": {"delta": 1},
        })
        consequences.append({
            "trigger_turn": 5,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "material_change",
            "effect_payload": {
                "description": "Sickness spreads. Fewer faces in the streets each day.",
            },
        })

    if "trade" in affects:
        consequences.append({
            "trigger_turn": 4,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "trade_disruption",
            "effect_payload": {
                "delta": 1,
                "description": "Trade routes have been disrupted by recent events.",
            },
        })

    if significance == "civilizational":
        consequences.append({
            "trigger_turn": 6,
            "target_type": "location",
            "target_id": target_loc,
            "effect_type": "event_spawn",
            "effect_payload": {
                "description": f"The consequences of {event.get('event', 'great upheaval')} continue to reshape the region.",
                "location": target_loc,
                "action_type": "ambient_distant",
            },
        })

    return consequences


def _best_target_location(
    region: str, state: WorldState,
) -> Optional[str]:
    """Find the best location ID for a region string, or default to player's."""
    region_lower = region.lower()
    for loc in state.locations:
        if region_lower in loc.id.lower() or region_lower in loc.name.lower():
            return loc.id
        if loc.id.lower() in region_lower or loc.name.lower() in region_lower:
            return loc.id
    return state.player.location
