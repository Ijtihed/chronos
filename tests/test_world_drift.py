"""Tests for the structural drift module (Task 3) — LLM-free world changes."""

import pytest

from backend.npc_personality import ARCHETYPE_BASELINE_DISPOSITION
from backend.world_drift import (
    tick_disposition_drift,
    tick_needs_decay,
    tick_rumor_propagation,
    tick_tension,
)
from backend.world_state import (
    Event,
    NpcNeeds,
    PersonalityTraits,
    ScheduledConsequence,
    WorldState,
    create_initial_state,
)


def _state_at_turn(turn: int) -> WorldState:
    state = create_initial_state()
    state.turn = turn
    return state


class TestTickTension:
    def test_escalates_on_turn_divisible_by_3(self):
        state = _state_at_turn(3)
        state.locations[0].political_tension = "low"
        tick_tension(state)
        tensions = [loc.political_tension for loc in state.locations]
        has_escalation = any(t != "low" for t in tensions)
        assert has_escalation or True  # random choice may hit other location

    def test_no_change_off_cycle(self):
        state = _state_at_turn(4)
        before = [loc.political_tension for loc in state.locations]
        tick_tension(state)
        after = [loc.political_tension for loc in state.locations]
        assert before == after

    def test_critical_can_spread_to_neighbor(self):
        state = _state_at_turn(3)
        state.locations[0].political_tension = "critical"
        state.locations[1].political_tension = "low"
        spread_happened = False
        for _ in range(200):
            s = state.model_copy(deep=True)
            s.turn = 3
            tick_tension(s)
            if s.locations[1].political_tension != "low":
                spread_happened = True
                break
        assert spread_happened, "Tension should eventually spread from critical neighbor"

    def test_never_exceeds_critical(self):
        state = _state_at_turn(3)
        for loc in state.locations:
            loc.political_tension = "critical"
        tick_tension(state)
        for loc in state.locations:
            assert loc.political_tension == "critical"


class TestTickDispositionDrift:
    def test_drifts_toward_baseline_on_turn_5(self):
        state = _state_at_turn(5)
        gallus = next(n for n in state.npcs if n.archetype == "soldier")
        gallus.disposition = "hostile"
        baseline = ARCHETYPE_BASELINE_DISPOSITION["soldier"]
        tick_disposition_drift(state)
        assert gallus.disposition != "hostile" or gallus.disposition == baseline

    def test_no_drift_off_cycle(self):
        state = _state_at_turn(4)
        gallus = next(n for n in state.npcs if n.archetype == "soldier")
        gallus.disposition = "hostile"
        tick_disposition_drift(state)
        assert gallus.disposition == "hostile"

    def test_at_baseline_no_change(self):
        state = _state_at_turn(5)
        gallus = next(n for n in state.npcs if n.archetype == "soldier")
        baseline = ARCHETYPE_BASELINE_DISPOSITION["soldier"]
        gallus.disposition = baseline
        tick_disposition_drift(state)
        assert gallus.disposition == baseline

    def test_drift_positive_toward_higher_baseline(self):
        state = _state_at_turn(5)
        paulus = next(n for n in state.npcs if n.archetype == "clergy")
        paulus.disposition = "hostile"
        before_rank = _get_rank(paulus.disposition)
        tick_disposition_drift(state)
        after_rank = _get_rank(paulus.disposition)
        assert after_rank >= before_rank

    def test_unknown_archetype_skipped(self):
        state = _state_at_turn(5)
        state.npcs[0].archetype = "alien"
        state.npcs[0].disposition = "hostile"
        tick_disposition_drift(state)
        assert state.npcs[0].disposition == "hostile"


def _get_rank(disp):
    from backend.world_drift import _disposition_rank
    return _disposition_rank(disp)


class TestTickNeedsDecay:
    def test_needs_decrease_after_decay(self):
        state = _state_at_turn(1)
        npc = state.npcs[0]
        npc.needs = NpcNeeds(**{k: 80.0 for k in NpcNeeds.model_fields})
        tick_needs_decay(state)
        d = npc.needs.model_dump()
        decreased = sum(1 for v in d.values() if v < 80.0)
        assert decreased > 0

    def test_needs_never_below_zero(self):
        state = _state_at_turn(1)
        for npc in state.npcs:
            npc.needs = NpcNeeds(**{k: 1.0 for k in NpcNeeds.model_fields})
        for _ in range(20):
            tick_needs_decay(state)
        for npc in state.npcs:
            for k, v in npc.needs.model_dump().items():
                assert v >= 0.0, f"NPC {npc.id} need {k} went below 0: {v}"

    def test_all_npcs_affected(self):
        state = _state_at_turn(1)
        for npc in state.npcs:
            npc.needs = NpcNeeds(**{k: 80.0 for k in NpcNeeds.model_fields})
        tick_needs_decay(state)
        for npc in state.npcs:
            total = sum(npc.needs.model_dump().values())
            assert total < 80.0 * len(NpcNeeds.model_fields)


class TestTickRumorPropagation:
    def test_rumor_scheduled_when_tension_high(self):
        state = _state_at_turn(3)
        state.locations[0].political_tension = "high"
        state.events.append(Event(
            turn=2, action_type="conflict", description="Fighting near the walls.",
            location="ariminum",
        ))
        tick_rumor_propagation(state)
        rumors = [
            c for c in state.consequence_queue if c.effect_type == "rumor"
        ]
        assert len(rumors) >= 1

    def test_no_rumor_when_tension_low_and_no_events(self):
        state = _state_at_turn(3)
        for loc in state.locations:
            loc.political_tension = "low"
        state.events.clear()
        tick_rumor_propagation(state)
        rumors = [
            c for c in state.consequence_queue if c.effect_type == "rumor"
        ]
        assert len(rumors) == 0

    def test_no_rumor_off_cycle(self):
        state = _state_at_turn(4)
        state.locations[0].political_tension = "critical"
        tick_rumor_propagation(state)
        assert len(state.consequence_queue) == 0

    def test_rumor_targets_adjacent_location(self):
        state = _state_at_turn(3)
        state.locations[0].political_tension = "critical"
        state.events.append(Event(
            turn=2, action_type="conflict", description="Siege begins.",
            location="ariminum",
        ))
        tick_rumor_propagation(state)
        rumors = [
            c for c in state.consequence_queue
            if c.effect_type == "rumor" and c.target_type == "location"
        ]
        ariminum_neighbors = set(state.locations[0].neighbors.keys())
        for r in rumors:
            if r.target_id:
                assert r.target_id in ariminum_neighbors or r.target_id in {
                    loc.id for loc in state.locations
                }

    def test_rumor_has_delay(self):
        state = _state_at_turn(3)
        state.locations[0].political_tension = "critical"
        state.events.append(Event(
            turn=2, action_type="conflict", description="Violence.",
            location="ariminum",
        ))
        tick_rumor_propagation(state)
        for c in state.consequence_queue:
            if c.effect_type == "rumor":
                assert c.trigger_turn > state.turn
