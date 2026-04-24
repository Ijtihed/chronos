"""Reusable harness for divergence / density / target-miss tests.

Exercises the real simulate_turn + _schedule_player_consequences +
_check_historical_divergence + stage 2 validation path. Mocks only
the LLM calls (parse_action, generate_npc_pov, and world_engine.chat).

Usage:

    state = create_initial_state()
    parsed = {
        "action_type": "fight",
        "target": "Lucius Gallus",
        "intent": "duel the centurion",
        "era_description": "Corvinus draws his blade.",
        "significance_score": 0.7,
        "npc_impacts": [],
        "is_travel": False,
        "is_inaction": False,
    }
    snap = await run_player_turn(state, parsed)
    assert snap.count_scheduled() > 0
    assert snap.count_superseded() == 0

The harness does NOT persist anything to disk or run the FastAPI
handler. It executes the same in-memory code path that _execute_turn
uses for the scheduling + stage-2 portion of a turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock, patch

from backend import main as _main_module
from backend import world_engine as _world_engine
from backend.world_state import (
    Event,
    ScheduledConsequence,
    WorldState,
    apply_action,
)


# ---------------------------------------------------------------------------
# Snapshot types
# ---------------------------------------------------------------------------

@dataclass
class ConsequenceOutcome:
    """The fate of a single player-scheduled consequence."""
    id: str
    effect_type: str
    trigger_turn: int
    target_id: Optional[str]
    outcome: str  # "pending" | "fired" | "superseded"


@dataclass
class TurnSnapshot:
    """Captured state from one harnessed player turn."""
    parsed_action: dict
    queue_before_stage2: List[ScheduledConsequence]
    consequence_outcomes: List[ConsequenceOutcome]
    events_appended: List[Event]
    divergences_appended: List[dict]
    state_before: WorldState
    state_after: WorldState

    def count_scheduled(self) -> int:
        return len(self.consequence_outcomes)

    def count_fired(self) -> int:
        return sum(1 for o in self.consequence_outcomes if o.outcome == "fired")

    def count_superseded(self) -> int:
        return sum(1 for o in self.consequence_outcomes if o.outcome == "superseded")

    def count_pending(self) -> int:
        return sum(1 for o in self.consequence_outcomes if o.outcome == "pending")


# ---------------------------------------------------------------------------
# LLM mocking (internal)
# ---------------------------------------------------------------------------

_AUTO_STUB_JSON = (
    '{"action": "goes about their day", '
    '"new_activity": "routine duties", '
    '"interacts_with": null, '
    '"mood_shift": null, '
    '"wants_to_travel": false, '
    '"travel_destination": null}'
)


async def _stub_call_llm(prompt, *, tier=None, schema=None, json_mode=False, **_):
    """Deterministic LLM stub for harness use.

    Matches the new call_llm signature: returns (text, UsageInfo|None).
    When a schema is supplied (or json_mode is true), returns valid
    AutonomousActionResponse JSON (covers _npc_autonomous_action and
    _npc_light_action paths). Plain text otherwise.
    """
    if schema is not None or json_mode:
        return _AUTO_STUB_JSON, None
    return "[stub narrative]", None


# ---------------------------------------------------------------------------
# Stage-2 capture wrapper
# ---------------------------------------------------------------------------

def _patched_process_no_cleanup(state: WorldState) -> None:
    """Replacement for world_engine._process_in_memory_consequences.

    Runs the real validation + firing logic but skips the final cleanup
    that strips fired/superseded items from the queue. This lets us
    inspect the fired/superseded flags after stage 2 completes.
    The harness does the cleanup manually after snapshotting.
    """
    from backend.world_engine import (
        _apply_consequence,
        _validate_consequence,
        get_pending_consequences_mem,
        mark_consequence_fired_mem,
    )

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
    # Intentionally NO cleanup — harness inspects flags post-hoc.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_player_turn(
    state: WorldState,
    parsed_action: dict,
    skip_simulate: bool = False,
    ticks_after: int = 4,
) -> TurnSnapshot:
    """Run one player turn through the real production path.

    Order of operations (mirrors main._execute_turn, excluding FastAPI
    glue and persistence):

      1. Snapshot `state_before`, record event/divergence counts.
      2. If not skip_simulate: run simulate_turn once (world ticks).
      3. apply_action(state, parsed_action).
      4. _schedule_player_consequences if significance >= 0.5.
      5. _check_historical_divergence if significance >= 0.6.
      6. Snapshot queue_before_stage2 (player-scheduled items only).
      7. Run `ticks_after` more simulate_turn calls. Stage 2 processes
         each scheduled consequence at its trigger_turn. The
         _process_in_memory_consequences cleanup is patched out so we
         can inspect the fired/superseded flags afterward.
      8. Build outcomes by matching scheduled IDs to post-processing
         flag state.
      9. Apply the deferred cleanup so `state_after` is consistent.

    Args:
        state: starting world state (deep-copied internally; caller's
            object is never mutated).
        parsed_action: what parse_action would have returned. Must
            include action_type, significance_score, era_description.
        skip_simulate: if True, skip step 2 (pre-action world tick).
            Useful when the test wants to control turn progression.
        ticks_after: how many simulate_turn calls to run after the
            player action. Default 4 covers all current handlers
            (max trigger_turn offset is +3).

    Returns:
        TurnSnapshot with outcome breakdown and state deltas.
    """
    state_before = state.model_copy(deep=True)
    work = state.model_copy(deep=True)
    events_before_count = len(work.events)
    divergences_before_count = len(work.historical_divergences)

    # Mock the two LLM entry points used by the path we exercise.
    with patch.object(_world_engine, "call_llm", _stub_call_llm), \
         patch("backend.hce.call_llm", _stub_call_llm):

        # Step 2: optional pre-action world tick.
        if not skip_simulate:
            work, _ = await _world_engine.simulate_turn(work)

        # Step 3: apply_action (event log, disposition shifts, memory).
        work = apply_action(work, parsed_action)

        # Steps 4-5: scheduler + divergence check.
        sig = parsed_action.get("significance_score", 0.0)
        if sig >= 0.5:
            _main_module._schedule_player_consequences(work, parsed_action)
        if sig >= 0.6:
            await _main_module._check_historical_divergence(work, parsed_action)

        # Step 6: snapshot queue (player-scheduled only).
        # All unfired, non-superseded items here were added by the
        # scheduler above — nothing else has run between steps 4 and 6.
        scheduled_items = [
            c for c in work.consequence_queue
            if not c.fired and not c.superseded
        ]
        scheduled_ids = {c.id for c in scheduled_items}
        queue_before_stage2 = [c.model_copy(deep=True) for c in scheduled_items]

        # Step 7: advance the world with patched stage 2.
        with patch.object(
            _world_engine,
            "_process_in_memory_consequences",
            _patched_process_no_cleanup,
        ):
            for _ in range(ticks_after):
                work, _ = await _world_engine.simulate_turn(work)

        # Step 8: derive outcomes from post-processing flag state.
        post_map = {c.id: c for c in work.consequence_queue}
        outcomes: List[ConsequenceOutcome] = []
        for pre in queue_before_stage2:
            post = post_map.get(pre.id)
            if post is None:
                # Should not happen with patched cleanup, but be defensive.
                continue
            if post.fired:
                label = "fired"
            elif post.superseded:
                label = "superseded"
            else:
                label = "pending"
            outcomes.append(ConsequenceOutcome(
                id=pre.id,
                effect_type=pre.effect_type,
                trigger_turn=pre.trigger_turn,
                target_id=pre.target_id,
                outcome=label,
            ))

        # Step 9: apply the deferred cleanup.
        work.consequence_queue = [
            c for c in work.consequence_queue
            if not (c.fired or c.superseded)
        ]

    events_appended = work.events[events_before_count:]
    divergences_appended = work.historical_divergences[divergences_before_count:]

    return TurnSnapshot(
        parsed_action=parsed_action,
        queue_before_stage2=queue_before_stage2,
        consequence_outcomes=outcomes,
        events_appended=events_appended,
        divergences_appended=divergences_appended,
        state_before=state_before,
        state_after=work,
    )


# ---------------------------------------------------------------------------
# Convenience: build a parsed_action dict with sensible defaults
# ---------------------------------------------------------------------------

def make_parsed(
    action_type: str,
    significance_score: float,
    target: Optional[str] = None,
    intent: str = "",
    era_description: str = "",
    npc_impacts: Optional[list] = None,
    is_travel: bool = False,
    is_inaction: bool = False,
    destination: Optional[str] = None,
) -> dict:
    """Build a parsed_action dict in the shape parse_action would emit."""
    return {
        "action_type": action_type,
        "target": target,
        "intent": intent or f"Test: {action_type}",
        "era_description": era_description or f"The player performs a {action_type}.",
        "npc_impacts": npc_impacts or [],
        "is_travel": is_travel,
        "is_inaction": is_inaction,
        "destination": destination,
        "significance_score": significance_score,
    }
