"""Tests for probabilistic world events (Task 4) — LLM-free."""

import pytest

from backend.world_events import (
    _check_armed_skirmish,
    _check_attract_merchant,
    _check_civilian_unrest,
    _check_food_shortage_rumor,
    _check_refugee_flight,
    _check_siege_trade_disruption,
    _check_tension_spread,
    _lowest_tension_adjacent,
    tick_world_events,
)
from backend.world_state import (
    Event,
    NPC,
    NpcNeeds,
    PersonalityTraits,
    WorldState,
    create_initial_state,
)


def _state_at_turn(turn: int) -> WorldState:
    state = create_initial_state()
    state.turn = turn
    return state


def _add_refugee(state: WorldState, location: str = "ariminum") -> NPC:
    from backend.npc_personality import generate_personality, calculate_needs
    p = generate_personality("refugee")
    n = calculate_needs("refugee", p)
    npc = NPC(
        id="refugee_1", name="Displaced Farmer", role="Refugee",
        archetype="refugee", location=location, description="Fleeing.",
        disposition="fearful", relationship_to_player="Unknown.",
        personality=p, needs=n,
    )
    state.npcs.append(npc)
    return npc


class TestArmedSkirmish:
    def test_fires_at_high_tension_with_soldiers(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        fired = False
        for _ in range(100):
            evt = _check_armed_skirmish(state.locations[0], state)
            if evt:
                fired = True
                assert evt.action_type == "armed_skirmish"
                assert "ariminum" in evt.description.lower() or evt.location == "ariminum"
                break
        assert fired, "Should fire within 100 rolls at 30% probability"

    def test_no_fire_at_low_tension(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "low"
        for _ in range(50):
            assert _check_armed_skirmish(state.locations[0], state) is None

    def test_no_fire_without_soldiers(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        for npc in state.npcs:
            npc.archetype = "merchant"
        for _ in range(50):
            assert _check_armed_skirmish(state.locations[0], state) is None


class TestCivilianUnrest:
    def test_fires_at_high_tension_without_soldiers(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "high"
        for npc in state.npcs:
            if npc.location == "ariminum":
                npc.archetype = "merchant"
        fired = False
        for _ in range(100):
            evt = _check_civilian_unrest(state.locations[0], state)
            if evt:
                fired = True
                assert evt.action_type == "civilian_unrest"
                break
        assert fired

    def test_no_fire_with_soldiers_present(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "high"
        for _ in range(50):
            assert _check_civilian_unrest(state.locations[0], state) is None


class TestTensionSpread:
    def test_can_spread_from_critical(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        spread = False
        for _ in range(200):
            result = _check_tension_spread(state.locations[0], state)
            if result:
                spread = True
                assert result["delta"] == 1
                assert result["target_id"] in state.locations[0].neighbors
                break
        assert spread

    def test_no_spread_below_90(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "high"
        for _ in range(50):
            assert _check_tension_spread(state.locations[0], state) is None


class TestFoodShortageRumor:
    def test_fires_with_famine_event(self):
        state = _state_at_turn(10)
        state.events.append(Event(
            turn=8, action_type="famine",
            description="Famine grips the region.", location="ariminum",
        ))
        fired = False
        for _ in range(100):
            result = _check_food_shortage_rumor(state.locations[0], state)
            if result:
                fired = True
                assert result.effect_type == "rumor"
                assert "food" in result.effect_payload["rumor_text"].lower()
                break
        assert fired

    def test_no_fire_without_famine(self):
        state = _state_at_turn(10)
        for _ in range(50):
            assert _check_food_shortage_rumor(state.locations[0], state) is None

    def test_no_fire_before_turn_5(self):
        state = _state_at_turn(3)
        state.events.append(Event(
            turn=2, action_type="famine",
            description="Famine.", location="ariminum",
        ))
        assert _check_food_shortage_rumor(state.locations[0], state) is None


class TestSiegeTradeDisruption:
    def test_fires_with_siege_event(self):
        state = _state_at_turn(10)
        state.events.append(Event(
            turn=5, action_type="siege",
            description="Siege begins.", location="ariminum",
        ))
        fired = False
        for _ in range(100):
            result = _check_siege_trade_disruption(state.locations[0], state)
            if result:
                fired = True
                assert result.effect_type == "trade_disruption"
                assert result.trigger_turn == state.turn + 2
                break
        assert fired

    def test_no_fire_without_siege(self):
        state = _state_at_turn(10)
        for _ in range(50):
            assert _check_siege_trade_disruption(state.locations[0], state) is None


class TestAttractMerchant:
    def test_fires_at_low_tension(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "low"
        fired = False
        for _ in range(100):
            evt = _check_attract_merchant(state.locations[0], state)
            if evt:
                fired = True
                assert evt.action_type == "merchant_arrival"
                break
        assert fired

    def test_no_fire_at_high_tension(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "high"
        for _ in range(50):
            assert _check_attract_merchant(state.locations[0], state) is None


class TestRefugeeFlight:
    def test_refugee_flees_high_tension(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        state.locations[1].political_tension = "low"
        refugee = _add_refugee(state, "ariminum")
        fled = False
        for _ in range(100):
            dest = _check_refugee_flight(refugee, state)
            if dest:
                fled = True
                break
        assert fled

    def test_non_refugee_never_flees(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        soldier = state.npcs[0]
        soldier.archetype = "soldier"
        for _ in range(50):
            assert _check_refugee_flight(soldier, state) is None

    def test_no_flight_at_low_tension(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "low"
        refugee = _add_refugee(state, "ariminum")
        for _ in range(50):
            assert _check_refugee_flight(refugee, state) is None


class TestLowestTensionAdjacent:
    def test_finds_lowest(self):
        state = _state_at_turn(1)
        state.locations[0].political_tension = "critical"
        state.locations[1].political_tension = "low"
        state.locations[2].political_tension = "high"
        result = _lowest_tension_adjacent("ariminum", state)
        assert result == "ravenna"

    def test_no_neighbors_returns_none(self):
        state = _state_at_turn(1)
        state.locations[0].neighbors = {}
        result = _lowest_tension_adjacent("ariminum", state)
        assert result is None


class TestTickWorldEvents:
    def test_returns_state(self):
        state = _state_at_turn(5)
        result = tick_world_events(state)
        assert isinstance(result, WorldState)

    def test_events_can_be_generated(self):
        state = _state_at_turn(10)
        state.locations[0].political_tension = "critical"
        state.events.append(Event(
            turn=5, action_type="siege", description="Siege.", location="ariminum",
        ))
        state.events.append(Event(
            turn=5, action_type="famine", description="Famine.", location="ariminum",
        ))
        events_before = len(state.events)
        cq_before = len(state.consequence_queue)
        any_change = False
        for _ in range(50):
            s = state.model_copy(deep=True)
            tick_world_events(s)
            if len(s.events) > events_before or len(s.consequence_queue) > cq_before:
                any_change = True
                break
        assert any_change, "Some event or consequence should fire with critical tension + siege + famine"

    def test_refugee_moves_in_tick(self):
        state = _state_at_turn(5)
        state.locations[0].political_tension = "critical"
        state.locations[1].political_tension = "low"
        refugee = _add_refugee(state, "ariminum")
        moved = False
        for _ in range(100):
            s = state.model_copy(deep=True)
            r = next(n for n in s.npcs if n.id == "refugee_1")
            tick_world_events(s)
            if r.location != "ariminum":
                moved = True
                break
        assert moved, "Refugee should eventually flee from critical tension"
