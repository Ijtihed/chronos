"""Tests for the consequence queue — scheduling, firing, validation, and application."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from backend.persistence import (
    get_pending_consequences,
    init_db,
    mark_consequence_fired,
    mark_consequence_superseded,
    schedule_consequence,
    supersede_downstream_consequences,
)
from backend.world_engine import (
    _apply_consequence,
    _validate_consequence,
)
from backend.world_state import (
    TENSION_LEVELS,
    Event,
    WorldState,
    create_initial_state,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    test_db = tmp_path / "test_chronos.db"
    with patch("backend.persistence.DB_PATH", test_db):
        await init_db()
        yield


RUN_ID = "test_run_001"


class TestScheduleAndQuery:
    @pytest.mark.asyncio
    async def test_schedule_and_retrieve(self):
        cid = await schedule_consequence(
            run_id=RUN_ID,
            source_event_id=42,
            trigger_turn=5,
            target_type="location",
            target_id="ariminum",
            effect_type="tension_shift",
            effect_payload={"delta": 1},
        )
        assert cid > 0
        pending = await get_pending_consequences(RUN_ID, 5)
        assert len(pending) == 1
        assert pending[0]["trigger_turn"] == 5
        assert pending[0]["effect_payload"] == {"delta": 1}

    @pytest.mark.asyncio
    async def test_not_returned_before_trigger_turn(self):
        await schedule_consequence(
            run_id=RUN_ID, source_event_id=None, trigger_turn=10,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "Future event"},
        )
        pending = await get_pending_consequences(RUN_ID, 5)
        assert len(pending) == 0
        pending = await get_pending_consequences(RUN_ID, 10)
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_returns_past_due_consequences(self):
        await schedule_consequence(
            run_id=RUN_ID, source_event_id=None, trigger_turn=3,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "Past due"},
        )
        pending = await get_pending_consequences(RUN_ID, 10)
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_fired_not_returned(self):
        cid = await schedule_consequence(
            run_id=RUN_ID, source_event_id=None, trigger_turn=5,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "Once only"},
        )
        await mark_consequence_fired(cid)
        pending = await get_pending_consequences(RUN_ID, 10)
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_superseded_not_returned(self):
        cid = await schedule_consequence(
            run_id=RUN_ID, source_event_id=None, trigger_turn=5,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "Obsolete"},
        )
        await mark_consequence_superseded(cid)
        pending = await get_pending_consequences(RUN_ID, 10)
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_supersede_downstream(self):
        src_id = 99
        for turn in (3, 5, 7):
            await schedule_consequence(
                run_id=RUN_ID, source_event_id=src_id, trigger_turn=turn,
                target_type="global", target_id=None,
                effect_type="event_spawn",
                effect_payload={"description": f"Turn {turn}"},
            )
        # Fire the first one
        pending = await get_pending_consequences(RUN_ID, 3)
        await mark_consequence_fired(pending[0]["id"])

        # Supersede all remaining from this source
        count = await supersede_downstream_consequences(RUN_ID, src_id)
        assert count == 2

        pending = await get_pending_consequences(RUN_ID, 10)
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_different_run_ids_isolated(self):
        await schedule_consequence(
            run_id="run_a", source_event_id=None, trigger_turn=5,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "For run A"},
        )
        await schedule_consequence(
            run_id="run_b", source_event_id=None, trigger_turn=5,
            target_type="global", target_id=None,
            effect_type="event_spawn",
            effect_payload={"description": "For run B"},
        )
        assert len(await get_pending_consequences("run_a", 10)) == 1
        assert len(await get_pending_consequences("run_b", 10)) == 1


class TestValidateConsequence:
    def test_valid_location_target(self):
        state = create_initial_state()
        c = {"target_type": "location", "target_id": "ariminum"}
        assert _validate_consequence(c, state) is True

    def test_invalid_location_target(self):
        state = create_initial_state()
        c = {"target_type": "location", "target_id": "atlantis"}
        assert _validate_consequence(c, state) is False

    def test_valid_npc_target(self):
        state = create_initial_state()
        c = {"target_type": "npc", "target_id": "centurion_gallus"}
        assert _validate_consequence(c, state) is True

    def test_invalid_npc_target(self):
        state = create_initial_state()
        c = {"target_type": "npc", "target_id": "nonexistent_npc"}
        assert _validate_consequence(c, state) is False

    def test_global_always_valid(self):
        state = create_initial_state()
        c = {"target_type": "global", "target_id": None}
        assert _validate_consequence(c, state) is True

    def test_ended_run_invalid(self):
        state = create_initial_state()
        state.run_status = "ended"
        c = {"target_type": "global", "target_id": None}
        assert _validate_consequence(c, state) is False

    def test_dead_observing_still_valid(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        c = {"target_type": "global", "target_id": None}
        assert _validate_consequence(c, state) is True


class TestApplyConsequence:
    def test_tension_shift_up(self):
        state = create_initial_state()
        state.locations[0].political_tension = "moderate"
        _apply_consequence({
            "effect_type": "tension_shift",
            "target_id": "ariminum",
            "effect_payload": {"delta": 1},
        }, state)
        assert state.locations[0].political_tension == "high"

    def test_tension_shift_down(self):
        state = create_initial_state()
        state.locations[0].political_tension = "high"
        _apply_consequence({
            "effect_type": "tension_shift",
            "target_id": "ariminum",
            "effect_payload": {"delta": -1},
        }, state)
        assert state.locations[0].political_tension == "moderate"

    def test_tension_shift_clamped_at_top(self):
        state = create_initial_state()
        state.locations[0].political_tension = "critical"
        _apply_consequence({
            "effect_type": "tension_shift",
            "target_id": "ariminum",
            "effect_payload": {"delta": 5},
        }, state)
        assert state.locations[0].political_tension == "critical"

    def test_tension_shift_clamped_at_bottom(self):
        state = create_initial_state()
        state.locations[0].political_tension = "low"
        _apply_consequence({
            "effect_type": "tension_shift",
            "target_id": "ariminum",
            "effect_payload": {"delta": -5},
        }, state)
        assert state.locations[0].political_tension == "low"

    def test_rumor_injects_event(self):
        state = create_initial_state()
        count_before = len(state.events)
        _apply_consequence({
            "effect_type": "rumor",
            "target_id": "ravenna",
            "effect_payload": {"rumor_text": "Ships seen fleeing the harbor"},
        }, state)
        assert len(state.events) == count_before + 1
        assert "Ships seen fleeing" in state.events[-1].description
        assert state.events[-1].action_type == "ambient_distant"

    def test_trade_disruption_moves_route_and_worsens_food(self):
        state = create_initial_state()
        state.locations[0].political_tension = "moderate"
        assert "ravenna" in state.locations[0].trade_routes
        initial_food = state.locations[0].food_scarcity
        count_before = len(state.events)
        _apply_consequence({
            "effect_type": "trade_disruption",
            "target_id": "ariminum",
            "effect_payload": {"delta": 1, "description": "Grain shipments halted."},
        }, state)
        assert state.locations[0].political_tension == "high"
        assert "ravenna" in state.locations[0].disrupted_routes
        assert "ravenna" not in state.locations[0].trade_routes
        food_levels = ["abundant", "normal", "scarce", "critical"]
        assert food_levels.index(state.locations[0].food_scarcity) > food_levels.index(initial_food) or state.locations[0].food_scarcity == "critical"
        assert len(state.events) == count_before + 1

    def test_npc_arrival_adds_npc(self):
        state = create_initial_state()
        npc_count_before = len(state.npcs)
        _apply_consequence({
            "effect_type": "npc_arrival",
            "target_id": "ariminum",
            "effect_payload": {
                "name": "Flavius the Refugee",
                "role": "Displaced farmer from the north",
                "archetype": "refugee",
                "description": "A gaunt man with haunted eyes.",
            },
        }, state)
        assert len(state.npcs) == npc_count_before + 1
        new_npc = state.npcs[-1]
        assert new_npc.name == "Flavius the Refugee"
        assert new_npc.location == "ariminum"
        assert new_npc.memory_of_player == 0.0

    def test_event_spawn_adds_event(self):
        state = create_initial_state()
        _apply_consequence({
            "effect_type": "event_spawn",
            "effect_payload": {
                "description": "A distant army is on the march.",
                "location": "mediolanum",
                "action_type": "ambient_distant",
            },
        }, state)
        assert state.events[-1].description == "A distant army is on the march."
        assert state.events[-1].location == "mediolanum"

    def test_material_change_updates_location_and_adds_event(self):
        state = create_initial_state()
        _apply_consequence({
            "effect_type": "material_change",
            "target_id": "ariminum",
            "effect_payload": {
                "description": "Bread prices have doubled.",
                "food_scarcity": "critical",
            },
        }, state)
        assert state.locations[0].material_conditions == "Bread prices have doubled."
        assert state.locations[0].food_scarcity == "critical"
        assert state.events[-1].action_type == "material_change"
        assert "Bread prices" in state.events[-1].description
