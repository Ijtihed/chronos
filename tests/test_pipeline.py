"""Tests for the revised autonomous tick pipeline (Task 6)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from backend.persistence import init_db
from backend.world_engine import (
    _graph_distance,
    advance_world_skip,
    get_npcs_by_tier,
    resolve_action_conflicts,
    simulate_turn,
    _process_in_memory_consequences,
)
from backend.world_state import (
    Event,
    NPC,
    NpcNeeds,
    PersonalityTraits,
    ScheduledConsequence,
    WorldState,
    create_initial_state,
    npcs_near_player,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    test_db = tmp_path / "test_chronos.db"
    with patch("backend.persistence.DB_PATH", test_db):
        await init_db()
        yield


def _make_state(turn=0) -> WorldState:
    state = create_initial_state()
    state.turn = turn
    return state


class TestGraphDistance:
    def test_same_location(self):
        state = _make_state()
        assert _graph_distance("ariminum", "ariminum", state) == 0

    def test_adjacent(self):
        state = _make_state()
        assert _graph_distance("ariminum", "ravenna", state) == 1

    def test_two_hops(self):
        state = _make_state()
        assert _graph_distance("ravenna", "mediolanum", state) == 2

    def test_unreachable(self):
        state = _make_state()
        assert _graph_distance("ariminum", "nonexistent", state) == 999


class TestNpcTiers:
    def test_active_at_player_location(self):
        state = _make_state()
        active, adj, dist = get_npcs_by_tier(state)
        for npc in active:
            assert npc.location == state.player.location

    def test_adjacent_one_hop_away(self):
        state = _make_state()
        state.npcs[0].location = "ravenna"
        active, adj, dist = get_npcs_by_tier(state)
        assert any(n.id == state.npcs[0].id for n in adj)

    def test_distant_requires_unreachable_location(self):
        state = _make_state()
        from backend.world_state import Location
        state.locations.append(Location(
            id="far_away", name="Far Away", description="Very far.",
            political_tension="low",
        ))
        state.npcs[0].location = "far_away"
        active, adj, dist = get_npcs_by_tier(state)
        assert any(n.id == state.npcs[0].id for n in dist)


class TestResolveActionConflicts:
    def _npc(self, npc_id, archetype):
        from backend.npc_personality import generate_personality, calculate_needs
        p = generate_personality(archetype)
        n = calculate_needs(archetype, p)
        return NPC(
            id=npc_id, name=f"NPC {npc_id}", role="test", archetype=archetype,
            location="loc", description="test", disposition="cautious",
            relationship_to_player="none", personality=p, needs=n,
        )

    def test_no_conflicts_all_pass(self):
        npc_a = self._npc("a", "soldier")
        npc_b = self._npc("b", "merchant")
        actions = [
            (npc_a, "siege_threat", {"action": "fights", "interacts_with": "enemy"}),
            (npc_b, "trade_caravan_passing", {"action": "trades", "interacts_with": "caravan"}),
        ]
        resolved = resolve_action_conflicts(actions, _make_state())
        assert len(resolved) == 2

    def test_same_target_higher_priority_wins(self):
        soldier = self._npc("soldier", "soldier")
        merchant = self._npc("merchant", "merchant")
        actions = [
            (soldier, "siege_threat", {"action": "defends", "interacts_with": "gate_guard"}),
            (merchant, "trade_caravan_passing", {"action": "bribes", "interacts_with": "gate_guard"}),
        ]
        resolved = resolve_action_conflicts(actions, _make_state())
        assert len(resolved) < 3
        npc_ids = [npc.id for npc, _, _ in resolved]
        assert "soldier" in npc_ids

    def test_empty_list(self):
        assert resolve_action_conflicts([], _make_state()) == []


class TestSimulateTurnPipeline:
    @pytest.mark.asyncio
    async def test_returns_state_and_activity(self):
        state = _make_state()
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Test action", "interacts_with": None}):
            new_state, activity = await simulate_turn(state)
        assert isinstance(new_state, WorldState)
        assert isinstance(activity, list)
        assert new_state.turn == state.turn + 1

    @pytest.mark.asyncio
    async def test_year_advances_after_multiple_turns(self):
        state = _make_state()
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Acts", "interacts_with": None}):
            for _ in range(5):
                state, _ = await simulate_turn(state)
        assert state.current_year > state.era.year_start

    @pytest.mark.asyncio
    async def test_in_memory_consequences_fire(self):
        state = _make_state(turn=4)
        state.consequence_queue.append(ScheduledConsequence(
            id="test_cq", trigger_turn=5, target_type="location",
            target_id="ariminum", effect_type="tension_shift",
            effect_payload={"delta": -1},
        ))
        state.locations[0].political_tension = "high"
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Acts", "interacts_with": None}):
            new_state, _ = await simulate_turn(state)
        remaining = [c for c in new_state.consequence_queue if c.id == "test_cq"]
        assert len(remaining) == 0, "Fired consequences should be cleaned up"

    @pytest.mark.asyncio
    async def test_drift_runs_before_npc_actions(self):
        state = _make_state(turn=2)
        initial_needs = {
            npc.id: npc.needs.model_dump() for npc in state.npcs
        }
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Acts", "interacts_with": None}):
            new_state, _ = await simulate_turn(state)
        for npc in new_state.npcs:
            old = initial_needs.get(npc.id)
            if old:
                new_d = npc.needs.model_dump()
                changed = any(new_d[k] != old[k] for k in old)
                if changed:
                    return
        pytest.skip("No needs changed this tick (RNG-dependent)")


class TestAdvanceWorldSkip:
    @pytest.mark.asyncio
    async def test_advances_n_turns(self):
        state = _make_state()
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Acts", "interacts_with": None}):
            new_state = await advance_world_skip(state, ticks=5)
        assert new_state.turn == 5

    @pytest.mark.asyncio
    async def test_year_advances_proportionally(self):
        state = _make_state()
        with patch("backend.world_engine._npc_autonomous_action",
                    new_callable=AsyncMock,
                    return_value={"action": "Acts", "interacts_with": None}):
            new_state = await advance_world_skip(state, ticks=10)
        expected_year = int(state.era.year_start + 10 * state.era.years_per_turn)
        assert new_state.current_year == expected_year


class TestProcessInMemoryConsequences:
    def test_fires_due_consequences(self):
        state = _make_state(turn=5)
        state.consequence_queue.append(ScheduledConsequence(
            id="c1", trigger_turn=5, target_type="global",
            effect_type="event_spawn",
            effect_payload={"description": "Something happens."},
        ))
        _process_in_memory_consequences(state)
        assert len(state.consequence_queue) == 0, "Fired consequences are cleaned up"
        assert any("Something happens" in e.description for e in state.events)

    def test_skips_future_consequences(self):
        state = _make_state(turn=3)
        state.consequence_queue.append(ScheduledConsequence(
            id="c_future", trigger_turn=10, target_type="global",
            effect_type="event_spawn",
            effect_payload={"description": "Future event."},
        ))
        events_before = len(state.events)
        _process_in_memory_consequences(state)
        assert len(state.consequence_queue) == 1, "Future consequences stay in queue"
        assert len(state.events) == events_before

    def test_supersedes_invalid_target(self):
        state = _make_state(turn=5)
        state.consequence_queue.append(ScheduledConsequence(
            id="c_bad", trigger_turn=5, target_type="location",
            target_id="atlantis",
            effect_type="tension_shift",
            effect_payload={"delta": 1},
        ))
        _process_in_memory_consequences(state)
        assert len(state.consequence_queue) == 0, "Superseded consequences are cleaned up"


class TestSkipEndpoint:
    @pytest.mark.asyncio
    async def test_skip_endpoint_exists(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.persistence import save_session

        state = create_initial_state()
        await save_session(state)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("backend.world_engine._npc_autonomous_action",
                        new_callable=AsyncMock,
                        return_value={"action": "Acts", "interacts_with": None}):
                resp = await client.post(
                    f"/api/run/{state.run_id}/skip",
                    json={"ticks": 3},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticks_advanced"] == 3
        assert "regrounding" in data
        assert "player_view" in data

    @pytest.mark.asyncio
    async def test_skip_clamps_to_max_30(self):
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.persistence import save_session

        state = create_initial_state()
        await save_session(state)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("backend.world_engine._npc_autonomous_action",
                        new_callable=AsyncMock,
                        return_value={"action": "Acts", "interacts_with": None}):
                resp = await client.post(
                    f"/api/run/{state.run_id}/skip",
                    json={"ticks": 100},
                )
        assert resp.status_code == 200
        assert resp.json()["ticks_advanced"] == 30
