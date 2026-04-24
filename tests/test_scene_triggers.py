"""Tests for Phase 3 Step 3.1 scene-illustration trigger detection.

Offline only. No LLM, no Ollama, no mflux, no network. Covers:
  - Priority ordering (erasure > death > run_start > narrative_moment)
  - Idempotent per-type fire-once semantics (run_start, death, erasure)
  - Signal 1 (witnessed canonical event)
  - Signal 2 (player action significance >= threshold)
  - Signal 4 (first arrival at a new location)
  - Cooldown (MAJOR_NARRATIVE_COOLDOWN_TURNS)
  - Sentinel handling (first firing never blocked)
  - Hard cap (HARD_CAP_PER_RUN) and terminal overrides
  - Tone hint mapping for player actions
"""

from __future__ import annotations

import pytest

from backend.scene_triggers import (
    HARD_CAP_PER_RUN,
    IllustrationTrigger,
    MAJOR_NARRATIVE_COOLDOWN_TURNS,
    MAJOR_NARRATIVE_SIGNIFICANCE_THRESHOLD,
    check_illustration_trigger,
)
from backend.world_state import WorldState, create_initial_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_state(turn: int = 1) -> WorldState:
    """Canonical Roman Late Empire state at Ariminum, no prior triggers."""
    state = create_initial_state()
    state.turn = turn
    state.illustration_triggers_fired = []
    # Simulate "end of previous turn" snapshot for first-arrival tests.
    # On turn 1, the player has not been anywhere prior — previously_visited
    # is empty, which is correct (any location reads as "first arrival"
    # but run_start priority fires instead of Signal 4 on turn 1).
    state.previously_visited_locations = []
    return state


def _make_parsed(
    action_type: str,
    significance: float = 0.2,
    era_description: str = "",
    target: str | None = None,
) -> dict:
    return {
        "action_type": action_type,
        "target": target,
        "significance_score": significance,
        "era_description": era_description or f"Test action: {action_type}.",
    }


def _mark_fired(
    state: WorldState, trigger_type: str, turn: int, reason: str = "prior",
) -> None:
    state.illustration_triggers_fired.append(
        {"turn": turn, "type": trigger_type, "reason": reason}
    )


# ---------------------------------------------------------------------------
# Test 1: run_start fires on turn 1
# ---------------------------------------------------------------------------


def test_run_start_fires_on_turn_1():
    state = _fresh_state(turn=1)
    trigger = check_illustration_trigger(state)
    assert trigger is not None
    assert trigger.type == "run_start"
    assert trigger.tone_hint == "arrival"


# ---------------------------------------------------------------------------
# Test 2: run_start fires only once
# ---------------------------------------------------------------------------


def test_run_start_fires_only_once():
    state = _fresh_state(turn=1)
    _mark_fired(state, "run_start", turn=1, reason="prior run_start")
    trigger = check_illustration_trigger(state)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 3: run_start does not fire on later turns
# ---------------------------------------------------------------------------


def test_run_start_not_on_later_turns():
    state = _fresh_state(turn=5)
    # Seed previously_visited so Signal 4 doesn't shadow.
    state.previously_visited_locations = list(state.visited_locations)
    trigger = check_illustration_trigger(state)
    # No parsed, no witnessed events, not first-arrival — nothing fires.
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 4: character_death on dead_observing transition
# ---------------------------------------------------------------------------


def test_character_death_on_dead_observing():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "dead_observing"
    death_info = {"died": True, "cause": "killed in combat"}
    trigger = check_illustration_trigger(state, death_info=death_info)
    assert trigger is not None
    assert trigger.type == "character_death"
    assert trigger.tone_hint == "dying"
    assert "killed in combat" in trigger.reason


# ---------------------------------------------------------------------------
# Test 5: character_death fires only once
# ---------------------------------------------------------------------------


def test_character_death_only_once():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "dead_observing"
    _mark_fired(state, "character_death", turn=5)
    trigger = check_illustration_trigger(state, death_info={"cause": "x"})
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 6: erasure on ended transition
# ---------------------------------------------------------------------------


def test_erasure_on_ended():
    state = _fresh_state(turn=10)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "ended"
    trigger = check_illustration_trigger(state)
    assert trigger is not None
    assert trigger.type == "erasure"
    assert trigger.tone_hint == "fading"


# ---------------------------------------------------------------------------
# Test 7: erasure outranks character_death when both conditions exist
# ---------------------------------------------------------------------------


def test_erasure_outranks_character_death_when_both_conditions():
    """If run_status == ended and neither erasure nor death has fired,
    erasure wins (it's checked first by priority order).
    """
    state = _fresh_state(turn=10)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "ended"
    trigger = check_illustration_trigger(state, death_info={"cause": "x"})
    assert trigger is not None
    assert trigger.type == "erasure"


# ---------------------------------------------------------------------------
# Test 8: erasure fires only once
# ---------------------------------------------------------------------------


def test_erasure_only_once():
    state = _fresh_state(turn=10)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "ended"
    _mark_fired(state, "erasure", turn=10)
    trigger = check_illustration_trigger(state)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 9: significance >= 0.8 fires major_narrative_moment
# ---------------------------------------------------------------------------


def test_significance_0_8_fires_major_narrative_moment():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    parsed = _make_parsed(
        "attack", significance=MAJOR_NARRATIVE_SIGNIFICANCE_THRESHOLD + 0.05
    )
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"
    assert "significance" in trigger.reason
    assert trigger.context["source"] == "player_action"


# ---------------------------------------------------------------------------
# Test 10: significance below threshold does not fire
# ---------------------------------------------------------------------------


def test_significance_below_threshold_does_not_fire():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    parsed = _make_parsed("attack", significance=0.5)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 11: witnessed canonical event fires major_narrative_moment
# ---------------------------------------------------------------------------


def test_witnessed_canonical_event_fires_major_narrative_moment():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    witnessed = [
        {
            "event": "Plague strikes the city",
            "year": 1348,
            "type": "epidemic",
            "region": "Tuscany",
        }
    ]
    trigger = check_illustration_trigger(
        state, witnessed_events_this_turn=witnessed,
    )
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"
    assert trigger.tone_hint == "grave"
    assert trigger.context["source"] == "witnessed_event"


# ---------------------------------------------------------------------------
# Test 12: cooldown blocks re-fire within window
# ---------------------------------------------------------------------------


def test_cooldown_blocks_within_5_turns():
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    _mark_fired(state, "major_narrative_moment", turn=3)
    # Delta = 2, less than cooldown threshold of 5 → blocked.
    parsed = _make_parsed("attack", significance=0.9)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 13: cooldown clears after window
# ---------------------------------------------------------------------------


def test_cooldown_clears_after_5_turns():
    state = _fresh_state(turn=9)
    state.previously_visited_locations = list(state.visited_locations)
    _mark_fired(state, "major_narrative_moment", turn=3)
    # Delta = 6, meets the >= 5 threshold → allowed.
    assert (9 - 3) >= MAJOR_NARRATIVE_COOLDOWN_TURNS
    parsed = _make_parsed("attack", significance=0.9)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"


# ---------------------------------------------------------------------------
# Test 14: cooldown sentinel — first firing is never blocked
# ---------------------------------------------------------------------------


def test_cooldown_sentinel_first_firing_not_blocked():
    """No prior major_narrative_moment entry in illustration_triggers_fired
    → cooldown logic must return False (sentinel), not accidentally block.
    """
    state = _fresh_state(turn=10)
    state.previously_visited_locations = list(state.visited_locations)
    # No prior firings whatsoever.
    assert state.illustration_triggers_fired == []
    parsed = _make_parsed("attack", significance=0.95)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"


# ---------------------------------------------------------------------------
# Test 15: hard cap blocks non-terminal after 10 firings
# ---------------------------------------------------------------------------


def test_cap_blocks_non_terminal_after_10_firings():
    state = _fresh_state(turn=100)
    state.previously_visited_locations = list(state.visited_locations)
    # Stuff the fired list with exactly the cap count. Use old turns so
    # cooldown does not additionally apply — we want to isolate cap.
    for i in range(HARD_CAP_PER_RUN):
        _mark_fired(state, "major_narrative_moment", turn=i * 10)
    assert len(state.illustration_triggers_fired) == HARD_CAP_PER_RUN
    parsed = _make_parsed("attack", significance=0.95)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 16: cap does not block character_death
# ---------------------------------------------------------------------------


def test_cap_does_not_block_character_death():
    state = _fresh_state(turn=100)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "dead_observing"
    for i in range(HARD_CAP_PER_RUN):
        _mark_fired(state, "major_narrative_moment", turn=i * 10)
    # No character_death entry — terminal must still fire.
    trigger = check_illustration_trigger(state, death_info={"cause": "age"})
    assert trigger is not None
    assert trigger.type == "character_death"


# ---------------------------------------------------------------------------
# Test 17: cap does not block erasure
# ---------------------------------------------------------------------------


def test_cap_does_not_block_erasure():
    state = _fresh_state(turn=100)
    state.previously_visited_locations = list(state.visited_locations)
    state.run_status = "ended"
    for i in range(HARD_CAP_PER_RUN):
        _mark_fired(state, "major_narrative_moment", turn=i * 10)
    trigger = check_illustration_trigger(state)
    assert trigger is not None
    assert trigger.type == "erasure"


# ---------------------------------------------------------------------------
# Test 18: first arrival fires Signal 4 (major_narrative_moment)
# ---------------------------------------------------------------------------


def test_first_arrival_fires_signal_4():
    state = _fresh_state(turn=5)
    # End-of-previous-turn snapshot shows the player had only been at
    # Ariminum. They have now traveled to Ravenna (different location).
    state.previously_visited_locations = ["ariminum"]
    state.player.location = "ravenna"
    # visited_locations reflects the arrival having happened this turn.
    state.visited_locations = ["ariminum", "ravenna"]
    trigger = check_illustration_trigger(state)
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"
    assert trigger.tone_hint == "discovery"
    assert trigger.context["source"] == "first_arrival"
    assert trigger.context["location"] == "ravenna"


# ---------------------------------------------------------------------------
# Test 19: first arrival does not fire on revisit
# ---------------------------------------------------------------------------


def test_first_arrival_does_not_fire_on_revisit():
    state = _fresh_state(turn=5)
    # Player has visited both and is now back at Ariminum — not new.
    state.previously_visited_locations = ["ariminum", "ravenna"]
    state.player.location = "ariminum"
    state.visited_locations = ["ariminum", "ravenna"]
    trigger = check_illustration_trigger(state)
    assert trigger is None


# ---------------------------------------------------------------------------
# Test 20: tone hint mapping for hostile vs formal vs peaceful
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_type,expected_tone",
    [
        ("attack", "tense"),
        ("threaten", "tense"),
        ("betray", "tense"),
        ("steal", "tense"),
        ("fight", "tense"),
        ("siege", "tense"),
        ("petition", "formal"),
        ("negotiate", "formal"),
        ("alliance", "formal"),
        ("defend", "formal"),
        ("trade", "peaceful"),
        ("speak", "peaceful"),
        ("save", "triumphant"),
        ("prevent", "triumphant"),
        ("other", "neutral"),
        ("flee", "neutral"),
    ],
)
def test_tone_hint_for_player_action(action_type: str, expected_tone: str):
    state = _fresh_state(turn=5)
    state.previously_visited_locations = list(state.visited_locations)
    parsed = _make_parsed(action_type, significance=0.9)
    trigger = check_illustration_trigger(state, parsed=parsed)
    assert trigger is not None
    assert trigger.type == "major_narrative_moment"
    assert trigger.tone_hint == expected_tone


# ---------------------------------------------------------------------------
# Extra: log_dict shape
# ---------------------------------------------------------------------------


def test_log_dict_shape():
    trig = IllustrationTrigger(
        type="run_start",
        reason="test",
        tone_hint="arrival",
        context={"archetype": "merchant"},
        alt_text_hint="Hello",
    )
    d = trig.log_dict()
    assert d["type"] == "run_start"
    assert d["reason"] == "test"
    assert d["tone_hint"] == "arrival"
    assert d["context"] == {"archetype": "merchant"}
    assert d["alt_text_hint"] == "Hello"
