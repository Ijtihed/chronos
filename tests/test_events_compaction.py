"""Tests for state.events compaction in world_engine.

Compaction runs every EVENTS_COMPACTION_INTERVAL turns inside simulate_turn.
It drops ambient events older than EVENTS_COMPACTION_KEEP_RECENT turns and
preserves priority events (player actions, deaths, travel) regardless of age.

Coverage:
  - Compaction triggers at the right turn boundary (every 25 turns)
  - Priority events survive
  - Old ambient events drop
"""

from __future__ import annotations

import pytest

from backend.event_vocab import PRIORITY_EVENT_TYPES
from backend.world_engine import (
    EVENTS_COMPACTION_INTERVAL,
    EVENTS_COMPACTION_KEEP_RECENT,
    compact_events,
    simulate_turn,
)
from backend.world_state import Event, create_initial_state


class TestEventsCompaction:
    def _seed_old_events(self, state, count_ambient: int, count_priority: int):
        """Add old events at turn=0 so they're guaranteed older than cutoff."""
        for i in range(count_ambient):
            state.events.append(Event(
                turn=0,
                action_type="ambient",
                description=f"old_ambient_{i}",
                location=state.player.location,
            ))
        for i in range(count_priority):
            state.events.append(Event(
                turn=0,
                action_type="speak",  # in PRIORITY_EVENT_TYPES
                description=f"old_priority_{i}",
                location=state.player.location,
            ))

    def test_priority_events_preserved(self):
        """Old priority-typed events must survive compaction regardless of age."""
        state = create_initial_state()
        self._seed_old_events(state, count_ambient=0, count_priority=5)
        state.turn = 100  # well past cutoff (50)

        dropped = compact_events(state)

        assert dropped == 0
        assert len(state.events) == 5
        for ev in state.events:
            assert ev.action_type in PRIORITY_EVENT_TYPES

    def test_ambient_events_dropped(self):
        """Old ambient events past the cutoff must be removed."""
        state = create_initial_state()
        self._seed_old_events(state, count_ambient=10, count_priority=0)
        state.turn = 100  # cutoff = 100 - 50 = 50; turn-0 events are below

        dropped = compact_events(state)

        assert dropped == 10
        assert state.events == []

    def test_ambient_events_within_window_kept(self):
        """Ambient events within the recent window (turn >= cutoff) survive."""
        state = create_initial_state()
        # Turn 100, cutoff = 50.  Turn-60 ambient events should survive.
        for i in range(5):
            state.events.append(Event(
                turn=60,
                action_type="ambient",
                description=f"recent_ambient_{i}",
                location=state.player.location,
            ))
        state.turn = 100

        dropped = compact_events(state)

        assert dropped == 0
        assert len(state.events) == 5

    def test_compaction_no_op_when_run_short(self):
        """Before turn KEEP_RECENT (50), no events are old enough to drop."""
        state = create_initial_state()
        self._seed_old_events(state, count_ambient=10, count_priority=2)
        state.turn = 30  # cutoff would be -20, so no-op

        dropped = compact_events(state)

        assert dropped == 0
        assert len(state.events) == 12

    def test_compaction_mixed_preserves_only_priority(self):
        """Mixed log: only old ambient drops, old priority stays."""
        state = create_initial_state()
        self._seed_old_events(state, count_ambient=20, count_priority=3)
        state.turn = 100

        dropped = compact_events(state)

        assert dropped == 20
        assert len(state.events) == 3
        assert all(e.action_type == "speak" for e in state.events)

    def test_priority_set_includes_all_canonical_actions(self):
        """If a new canonical action_type ships, this set must include it.
        Guards against compaction silently dropping a future event type."""
        # Sanity: the 17 canonical types from action_parser must all be priority,
        # plus death and travel.  Spot-check a critical subset.
        for at in ("attack", "betray", "save", "petition", "death", "travel"):
            assert at in PRIORITY_EVENT_TYPES, (
                f"Action type {at!r} missing from PRIORITY_EVENT_TYPES; "
                "compaction would silently drop these events."
            )


class TestEventsCompactionIntegration:
    """Verify compaction fires at the right turn boundary inside simulate_turn."""

    def test_compaction_constants_sane(self):
        assert EVENTS_COMPACTION_INTERVAL == 25
        assert EVENTS_COMPACTION_KEEP_RECENT == 50
        assert EVENTS_COMPACTION_INTERVAL < EVENTS_COMPACTION_KEEP_RECENT, (
            "Interval must be less than keep_recent or events compact "
            "before they're old enough to be eligible -- a no-op trap."
        )

    @pytest.mark.asyncio
    async def test_compaction_fires_at_turn_boundary(self):
        """simulate_turn must invoke compact_events at every multiple of
        EVENTS_COMPACTION_INTERVAL, but not at off-multiples."""
        from unittest.mock import patch

        state = create_initial_state()
        # Seed with events that would be compacted IF turn is high enough
        self._add_old_ambient(state, n=5)
        state.turn = EVENTS_COMPACTION_INTERVAL - 1  # next sim_turn lands on interval

        # Patch tick functions and NPC actions to keep this fast and
        # deterministic; we only care that compact_events fires.
        compact_calls = []

        def _record_compact(s):
            compact_calls.append(s.turn)
            return 0

        with patch("backend.world_engine.compact_events", side_effect=_record_compact):
            with patch("backend.world_engine._run_npc_actions", return_value=[]):
                with patch("backend.world_engine.tick_world_events"):
                    new_state, _ = await simulate_turn(state)

        assert compact_calls == [EVENTS_COMPACTION_INTERVAL], (
            f"Expected compaction at turn {EVENTS_COMPACTION_INTERVAL}, "
            f"got calls at: {compact_calls}"
        )

    @pytest.mark.asyncio
    async def test_compaction_does_not_fire_off_boundary(self):
        """At turns not divisible by INTERVAL, compact_events must NOT run."""
        from unittest.mock import patch

        state = create_initial_state()
        self._add_old_ambient(state, n=5)
        # Land on turn 7 (not a multiple of 25)
        state.turn = 6

        compact_calls = []

        def _record_compact(s):
            compact_calls.append(s.turn)
            return 0

        with patch("backend.world_engine.compact_events", side_effect=_record_compact):
            with patch("backend.world_engine._run_npc_actions", return_value=[]):
                with patch("backend.world_engine.tick_world_events"):
                    await simulate_turn(state)

        assert compact_calls == [], (
            f"Compaction should not fire at turn 7, got: {compact_calls}"
        )

    def _add_old_ambient(self, state, n: int):
        for i in range(n):
            state.events.append(Event(
                turn=0,
                action_type="ambient",
                description=f"ambient_{i}",
                location=state.player.location,
            ))
