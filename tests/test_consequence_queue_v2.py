"""Tests for Task 2 additions: ScheduledConsequence model on WorldState,
in-memory queue operations, disposition_shift and need_pressure effect types."""

import pytest

from backend.world_engine import (
    _apply_consequence,
    _validate_consequence,
    get_pending_consequences_mem,
    mark_consequence_fired_mem,
    mark_consequence_superseded_mem,
    schedule_consequence_mem,
)
from backend.world_state import (
    NpcNeeds,
    PersonalityTraits,
    ScheduledConsequence,
    WorldState,
    create_initial_state,
)


class TestScheduledConsequenceModel:
    def test_default_id_generated(self):
        c = ScheduledConsequence(trigger_turn=5, target_type="global", effect_type="rumor")
        assert len(c.id) == 12

    def test_fields_serialize(self):
        c = ScheduledConsequence(
            id="abc123",
            source_event_id="evt_1",
            trigger_turn=5,
            target_type="location",
            target_id="ariminum",
            effect_type="tension_shift",
            effect_payload={"delta": 1},
        )
        d = c.model_dump()
        assert d["id"] == "abc123"
        assert d["trigger_turn"] == 5
        assert d["effect_payload"] == {"delta": 1}
        assert d["superseded"] is False
        assert d["fired"] is False

    def test_on_world_state(self):
        state = create_initial_state()
        assert state.consequence_queue == []
        state.consequence_queue.append(
            ScheduledConsequence(trigger_turn=3, target_type="global", effect_type="rumor")
        )
        assert len(state.consequence_queue) == 1

    def test_survives_deep_copy(self):
        state = create_initial_state()
        state.consequence_queue.append(
            ScheduledConsequence(
                id="test1", trigger_turn=3, target_type="global",
                effect_type="event_spawn", effect_payload={"description": "test"},
            )
        )
        copy = state.model_copy(deep=True)
        assert len(copy.consequence_queue) == 1
        assert copy.consequence_queue[0].id == "test1"

    def test_survives_json_roundtrip(self):
        state = create_initial_state()
        state.consequence_queue.append(
            ScheduledConsequence(
                id="rt1", trigger_turn=5, target_type="npc",
                target_id="centurion_gallus", effect_type="disposition_shift",
                effect_payload={"delta": 1},
            )
        )
        json_str = state.model_dump_json()
        restored = WorldState.model_validate_json(json_str)
        assert len(restored.consequence_queue) == 1
        assert restored.consequence_queue[0].effect_type == "disposition_shift"


class TestInMemoryQueueOps:
    def test_schedule_and_get_pending(self):
        state = create_initial_state()
        state.turn = 5
        c = ScheduledConsequence(
            trigger_turn=5, target_type="global", effect_type="event_spawn",
            effect_payload={"description": "Something happens."},
        )
        schedule_consequence_mem(state, c)
        pending = get_pending_consequences_mem(state, 5)
        assert len(pending) == 1

    def test_future_not_returned(self):
        state = create_initial_state()
        schedule_consequence_mem(state, ScheduledConsequence(
            trigger_turn=10, target_type="global", effect_type="rumor",
        ))
        assert len(get_pending_consequences_mem(state, 5)) == 0

    def test_past_due_returned(self):
        state = create_initial_state()
        schedule_consequence_mem(state, ScheduledConsequence(
            trigger_turn=3, target_type="global", effect_type="rumor",
        ))
        assert len(get_pending_consequences_mem(state, 10)) == 1

    def test_fired_not_returned(self):
        state = create_initial_state()
        c = ScheduledConsequence(
            id="fire_me", trigger_turn=5, target_type="global", effect_type="rumor",
        )
        schedule_consequence_mem(state, c)
        mark_consequence_fired_mem(state, "fire_me")
        assert len(get_pending_consequences_mem(state, 10)) == 0

    def test_superseded_not_returned(self):
        state = create_initial_state()
        c = ScheduledConsequence(
            id="sup_me", trigger_turn=5, target_type="global",
            effect_type="rumor", source_event_id="evt_1",
        )
        schedule_consequence_mem(state, c)
        mark_consequence_superseded_mem(state, "evt_1")
        assert len(get_pending_consequences_mem(state, 10)) == 0

    def test_supersede_only_unfired(self):
        state = create_initial_state()
        c1 = ScheduledConsequence(
            id="c1", trigger_turn=3, target_type="global",
            effect_type="rumor", source_event_id="evt_x",
        )
        c2 = ScheduledConsequence(
            id="c2", trigger_turn=5, target_type="global",
            effect_type="rumor", source_event_id="evt_x",
        )
        schedule_consequence_mem(state, c1)
        schedule_consequence_mem(state, c2)
        mark_consequence_fired_mem(state, "c1")
        mark_consequence_superseded_mem(state, "evt_x")
        assert state.consequence_queue[0].fired is True
        assert state.consequence_queue[0].superseded is False
        assert state.consequence_queue[1].superseded is True


class TestDispositionShiftEffect:
    def test_positive_shift(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "grim"
        _apply_consequence({
            "effect_type": "disposition_shift",
            "target_id": "centurion_gallus",
            "effect_payload": {"delta": 1},
        }, state)
        assert gallus.disposition == "guarded"

    def test_negative_shift(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        _apply_consequence({
            "effect_type": "disposition_shift",
            "target_id": "centurion_gallus",
            "effect_payload": {"delta": -1},
        }, state)
        assert gallus.disposition == "hostile"

    def test_no_target_is_noop(self):
        state = create_initial_state()
        _apply_consequence({
            "effect_type": "disposition_shift",
            "target_id": None,
            "effect_payload": {"delta": 1},
        }, state)

    def test_nonexistent_npc_is_noop(self):
        state = create_initial_state()
        _apply_consequence({
            "effect_type": "disposition_shift",
            "target_id": "nobody",
            "effect_payload": {"delta": 1},
        }, state)


class TestNeedPressureEffect:
    def test_increases_need(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        old_survival = gallus.needs.survival
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "survival", "delta": 15},
        }, state)
        assert gallus.needs.survival == min(100.0, old_survival + 15)

    def test_decreases_need(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        old_duty = gallus.needs.duty
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "duty", "delta": -20},
        }, state)
        assert gallus.needs.duty == max(0.0, old_duty - 20)

    def test_logs_to_needs_history(self):
        state = create_initial_state()
        state.turn = 7
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "honor", "delta": -10},
        }, state)
        assert any(h.get("event") == "need_pressure" for h in gallus.needs_history)

    def test_clamped_at_0_and_100(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "survival", "delta": 999},
        }, state)
        assert gallus.needs.survival <= 100.0
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "survival", "delta": -999},
        }, state)
        assert gallus.needs.survival >= 0.0

    def test_invalid_need_name_is_noop(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        before = gallus.needs.model_dump()
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": "centurion_gallus",
            "effect_payload": {"need": "nonexistent_need", "delta": 50},
        }, state)
        assert gallus.needs.model_dump() == before

    def test_no_target_is_noop(self):
        state = create_initial_state()
        _apply_consequence({
            "effect_type": "need_pressure",
            "target_id": None,
            "effect_payload": {"need": "survival", "delta": 10},
        }, state)
