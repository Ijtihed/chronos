"""Scene illustration trigger detection — Phase 3 Step 3.1.

Pure state inspection. Returns at most one IllustrationTrigger per call.
No LLM, no network, no mflux, no image generation. Step 3.1 ships the
trigger + observability layer only.

Design source: context/game logic context/visuals.md, the Phase 3 plan
approved 2026-04-22, and the Step 3.1 audit approved 2026-04-22.

Four trigger types:
  1. erasure                 — terminal, once per run
  2. character_death         — terminal, once per run
  3. run_start               — near-terminal, once on turn 1
  4. major_narrative_moment  — recurring, subject to cooldown + hard cap

Signals for major_narrative_moment (OR'd, priority in check order):
  Signal 1: witnessed canonical event this turn (from param)
  Signal 2: player action significance_score >= 0.8
  Signal 4: first arrival at a location (visited_locations delta)

Signal 3 ("first encounter with a major NPC") is intentionally deferred
to post-Step 3.1 — no first-class "major" flag on NPC today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.world_state import WorldState


# ---------------------------------------------------------------------------
# Module constants (tunable, will be reviewed after Step 3.1 log audit)
# ---------------------------------------------------------------------------

TERMINAL_TRIGGER_TYPES = frozenset({"character_death", "erasure"})
ALL_TRIGGER_TYPES = frozenset({
    "run_start", "character_death", "erasure", "major_narrative_moment",
})

MAJOR_NARRATIVE_COOLDOWN_TURNS = 5
HARD_CAP_PER_RUN = 10
MAJOR_NARRATIVE_SIGNIFICANCE_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Tone hints
#
# Scoped to Step 3.1 metadata only. Step 3.2 prompt construction will
# consume these hints to bias film-stock / lighting / framing choices.
# ---------------------------------------------------------------------------

# Tones for player actions (Signal 2).
_HOSTILE_ACTION_TYPES = frozenset({
    "attack", "threaten", "betray", "steal", "fight", "siege",
})
_FORMAL_ACTION_TYPES = frozenset({
    "petition", "negotiate", "alliance", "defend",
})
_PEACEFUL_ACTION_TYPES = frozenset({
    "trade", "speak",
})
_TRIUMPHANT_ACTION_TYPES = frozenset({
    "save", "prevent",
})


def _tone_for_player_action(action_type: str) -> str:
    at = (action_type or "").lower()
    if at in _HOSTILE_ACTION_TYPES:
        return "tense"
    if at in _FORMAL_ACTION_TYPES:
        return "formal"
    if at in _PEACEFUL_ACTION_TYPES:
        return "peaceful"
    if at in _TRIUMPHANT_ACTION_TYPES:
        return "triumphant"
    return "neutral"


_GRAVE_EVENT_TYPES = frozenset({"epidemic", "famine", "war"})
_FORMAL_EVENT_TYPES = frozenset({"political", "religious"})


def _tone_for_witnessed_event(event_type: str) -> str:
    et = (event_type or "").lower()
    if et in _GRAVE_EVENT_TYPES:
        return "grave"
    if et in _FORMAL_EVENT_TYPES:
        return "formal"
    return "neutral"


# ---------------------------------------------------------------------------
# Trigger record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IllustrationTrigger:
    """A single scene-illustration trigger decision.

    Produced by check_illustration_trigger(). Consumed by main.py for
    state-mutation and turn_logs audit in Step 3.1. Step 3.2 will also
    feed this object into the prompt construction module.
    """

    type: str            # one of ALL_TRIGGER_TYPES
    reason: str          # human-readable explanation
    tone_hint: str       # "tense" | "grave" | "formal" | "peaceful" |
                         # "triumphant" | "arrival" | "discovery" |
                         # "dying" | "fading" | "neutral"
    context: Dict[str, Any] = field(default_factory=dict)
    alt_text_hint: str = ""

    def log_dict(self) -> Dict[str, Any]:
        """Record for turn_logs.illustration_trigger JSON column."""
        return {
            "type": self.type,
            "reason": self.reason,
            "tone_hint": self.tone_hint,
            "context": self.context,
            "alt_text_hint": self.alt_text_hint,
        }


# ---------------------------------------------------------------------------
# State inspection helpers
# ---------------------------------------------------------------------------


def _has_fired(state: "WorldState", trigger_type: str) -> bool:
    return any(
        entry.get("type") == trigger_type
        for entry in state.illustration_triggers_fired
    )


def _last_major_narrative_turn(state: "WorldState") -> Optional[int]:
    """Turn number of the most recent major_narrative_moment firing, or
    None if it has never fired in this run.
    """
    entries = [
        e for e in state.illustration_triggers_fired
        if e.get("type") == "major_narrative_moment"
    ]
    if not entries:
        return None
    return max(e.get("turn", 0) for e in entries)


def _major_narrative_in_cooldown(state: "WorldState") -> bool:
    """True only if a prior firing exists AND we are within the cooldown
    window. Never blocks the first firing (sentinel semantics).
    """
    last = _last_major_narrative_turn(state)
    if last is None:
        return False
    return (state.turn - last) < MAJOR_NARRATIVE_COOLDOWN_TURNS


def _cap_hit(state: "WorldState") -> bool:
    return len(state.illustration_triggers_fired) >= HARD_CAP_PER_RUN


def _is_first_arrival_this_turn(state: "WorldState") -> bool:
    """True if the player is at a location they had not previously
    visited as of the end of the previous turn. Uses
    previously_visited_locations (snapshotted at end of prior turn),
    not the growing visited_locations.
    """
    return state.player.location not in state.previously_visited_locations


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------


def check_illustration_trigger(
    state: "WorldState",
    *,
    parsed: Optional[Dict[str, Any]] = None,
    death_info: Optional[Dict[str, Any]] = None,
    new_divergences: Optional[List[Dict[str, Any]]] = None,
    witnessed_events_this_turn: Optional[List[Dict[str, Any]]] = None,
) -> Optional[IllustrationTrigger]:
    """Determine whether this turn warrants a scene illustration trigger.

    Pure function. No I/O. Returns at most one trigger per call.
    Priority: erasure > character_death > run_start > major_narrative_moment.
    """
    year_fallback = state.current_year or state.era.year_start

    # --- Terminal: erasure -------------------------------------------------
    if state.run_status == "ended" and not _has_fired(state, "erasure"):
        return IllustrationTrigger(
            type="erasure",
            reason="run_status transitioned to ended — final memory fade",
            tone_hint="fading",
            context={
                "last_location": state.player.location,
                "year": year_fallback,
            },
            alt_text_hint=f"Memory fading. The last trace of {state.player.name}",
        )

    # --- Terminal: character_death -----------------------------------------
    if (
        state.run_status == "dead_observing"
        and not _has_fired(state, "character_death")
    ):
        cause = (death_info or {}).get("cause") or ""
        reason_suffix = f": {cause}" if cause else ""
        return IllustrationTrigger(
            type="character_death",
            reason=f"run_status transitioned to dead_observing{reason_suffix}",
            tone_hint="dying",
            context={
                "cause": cause,
                "year": year_fallback,
                "location": state.player.location,
            },
            alt_text_hint=(
                f"The moment of {state.player.name}'s death, year {year_fallback}"
            ),
        )

    # --- run_start: first-turn marker, once --------------------------------
    if state.turn == 1 and not _has_fired(state, "run_start"):
        return IllustrationTrigger(
            type="run_start",
            reason="first turn of the run",
            tone_hint="arrival",
            context={
                "archetype": state.player.archetype,
                "location": state.player.location,
                "year": year_fallback,
                "role": state.player.role,
            },
            alt_text_hint=(
                f"Arrival as {state.player.name}, a {state.player.role}, "
                f"year {year_fallback}"
            ),
        )

    # --- major_narrative_moment: gated by cooldown + cap -------------------
    if _cap_hit(state) or _major_narrative_in_cooldown(state):
        return None

    # Signal 2: player action at high significance.
    if parsed is not None:
        sig = 0.0
        try:
            sig = float(parsed.get("significance_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            sig = 0.0
        action_type = (parsed.get("action_type") or "other").lower()
        if sig >= MAJOR_NARRATIVE_SIGNIFICANCE_THRESHOLD:
            desc = (parsed.get("era_description") or "").strip()
            return IllustrationTrigger(
                type="major_narrative_moment",
                reason=f"significance: {sig:.2f} on {action_type}",
                tone_hint=_tone_for_player_action(action_type),
                context={
                    "source": "player_action",
                    "description": desc,
                    "action_type": action_type,
                    "significance": sig,
                    "year": year_fallback,
                    "location": state.player.location,
                },
                alt_text_hint=desc[:140] if desc else (
                    f"A moment of consequence, year {year_fallback}"
                ),
            )

    # Signal 1: witnessed canonical event this turn.
    if witnessed_events_this_turn:
        first = witnessed_events_this_turn[0]
        event_text = (first.get("event") or "").strip()
        event_type = (first.get("type") or "cultural").lower()
        event_year = first.get("year") or year_fallback
        event_region = first.get("region") or ""
        return IllustrationTrigger(
            type="major_narrative_moment",
            reason=f"witnessed canonical event: {event_text[:80]}",
            tone_hint=_tone_for_witnessed_event(event_type),
            context={
                "source": "witnessed_event",
                "description": event_text,
                "event_type": event_type,
                "year": event_year,
                "region": event_region,
                "location": state.player.location,
            },
            alt_text_hint=f"{event_text[:100]}, year {event_year}",
        )

    # Signal 4: first arrival at a new location.
    #
    # Requires previously_visited_locations to be populated (end-of-
    # previous-turn snapshot). Excluded on turn 1 so run_start is not
    # shadowed if the priority check above allows it through.
    if state.turn > 1 and _is_first_arrival_this_turn(state):
        loc_id = state.player.location
        loc_name = loc_id
        for loc in state.locations:
            if loc.id == loc_id:
                loc_name = loc.name
                break
        return IllustrationTrigger(
            type="major_narrative_moment",
            reason=f"first arrival at {loc_name}",
            tone_hint="discovery",
            context={
                "source": "first_arrival",
                "location": loc_id,
                "location_name": loc_name,
                "year": year_fallback,
            },
            alt_text_hint=f"Arrival at {loc_name}, year {year_fallback}",
        )

    return None


# ---------------------------------------------------------------------------
# Async helper for Signal 1 data
# ---------------------------------------------------------------------------


async def compute_witnessed_events_this_turn(
    state: "WorldState",
) -> List[Dict[str, Any]]:
    """Query the Events DB for witnessed-quality canonical events at the
    player's current year and era region. Returns a list of dicts
    suitable for passing to check_illustration_trigger.

    Keeps check_illustration_trigger pure by doing the async DB query
    here and letting the caller feed the result back as data. Returns
    [] on any query failure — never raises.
    """
    from backend.persistence import query_historical_events
    from backend.player_knowledge import filter_historical_events

    year = state.current_year or state.era.year_start
    try:
        raw = await query_historical_events(
            year_start=year - 1,
            year_end=year + 1,
            region=state.era.region,
        )
    except Exception:
        return []
    if not raw:
        return []
    try:
        filtered = filter_historical_events(raw, state)
    except Exception:
        return []
    return [
        {
            "event": ev.event,
            "year": ev.year,
            "type": ev.event_type,
            "region": ev.region,
        }
        for ev in filtered
        if ev.knowledge_quality == "witnessed"
    ]
