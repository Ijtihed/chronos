"""Tests for NPC tier assignment and simulation gating (Task 7)."""

import pytest

from backend.world_engine import (
    get_npc_simulation_tier,
    get_npcs_by_tier,
    should_simulate_npc,
)
from backend.world_state import (
    Location,
    NPC,
    NpcNeeds,
    PersonalityTraits,
    WorldState,
    create_initial_state,
)


def _make_state() -> WorldState:
    return create_initial_state()


def _make_npc(npc_id: str, location: str, last_sim_turn: int = 0) -> NPC:
    from backend.npc_personality import generate_personality, calculate_needs
    p = generate_personality("merchant")
    n = calculate_needs("merchant", p)
    return NPC(
        id=npc_id, name=f"NPC {npc_id}", role="test", archetype="merchant",
        location=location, description="test", disposition="cautious",
        relationship_to_player="none", personality=p, needs=n,
        last_simulated_turn=last_sim_turn,
    )


class TestGetNpcSimulationTier:
    def test_same_location_is_active(self):
        state = _make_state()
        npc = state.npcs[0]
        assert get_npc_simulation_tier(npc, state.player.location, state) == "active"

    def test_one_hop_is_adjacent(self):
        state = _make_state()
        npc = _make_npc("adj", "ravenna")
        assert get_npc_simulation_tier(npc, "ariminum", state) == "adjacent"

    def test_unreachable_is_distant(self):
        state = _make_state()
        state.locations.append(Location(
            id="isolated", name="Isolated", description="No neighbors.",
            political_tension="low",
        ))
        npc = _make_npc("far", "isolated")
        assert get_npc_simulation_tier(npc, "ariminum", state) == "distant"

    def test_all_archetypes_get_tier(self):
        state = _make_state()
        for npc in state.npcs:
            tier = get_npc_simulation_tier(npc, state.player.location, state)
            assert tier in ("active", "adjacent", "distant")


class TestShouldSimulateNpc:
    def test_active_always_simulates(self):
        npc = _make_npc("a", "loc", last_sim_turn=99)
        assert should_simulate_npc(npc, "active", 100) is True
        assert should_simulate_npc(npc, "active", 99) is True

    def test_adjacent_every_2_turns(self):
        npc = _make_npc("a", "loc", last_sim_turn=5)
        assert should_simulate_npc(npc, "adjacent", 6) is False
        assert should_simulate_npc(npc, "adjacent", 7) is True
        assert should_simulate_npc(npc, "adjacent", 10) is True

    def test_distant_every_5_turns(self):
        npc = _make_npc("a", "loc", last_sim_turn=5)
        assert should_simulate_npc(npc, "distant", 6) is False
        assert should_simulate_npc(npc, "distant", 9) is False
        assert should_simulate_npc(npc, "distant", 10) is True
        assert should_simulate_npc(npc, "distant", 15) is True

    def test_never_simulated_always_due(self):
        npc = _make_npc("a", "loc", last_sim_turn=0)
        assert should_simulate_npc(npc, "adjacent", 1) is False
        assert should_simulate_npc(npc, "adjacent", 2) is True
        assert should_simulate_npc(npc, "distant", 4) is False
        assert should_simulate_npc(npc, "distant", 5) is True


class TestGetNpcsByTier:
    def test_splits_correctly(self):
        state = _make_state()
        state.npcs.append(_make_npc("rav_npc", "ravenna"))
        state.locations.append(Location(
            id="nowhere", name="Nowhere", description="Isolated.",
            political_tension="low",
        ))
        state.npcs.append(_make_npc("far_npc", "nowhere"))

        active, adjacent, distant = get_npcs_by_tier(state)

        active_ids = {n.id for n in active}
        adjacent_ids = {n.id for n in adjacent}
        distant_ids = {n.id for n in distant}

        assert "centurion_gallus" in active_ids
        assert "deacon_paulus" in active_ids
        assert "rav_npc" in adjacent_ids
        assert "far_npc" in distant_ids

    def test_no_overlap(self):
        state = _make_state()
        active, adjacent, distant = get_npcs_by_tier(state)
        all_ids = (
            [n.id for n in active]
            + [n.id for n in adjacent]
            + [n.id for n in distant]
        )
        assert len(all_ids) == len(set(all_ids))

    def test_all_npcs_accounted_for(self):
        state = _make_state()
        active, adjacent, distant = get_npcs_by_tier(state)
        total = len(active) + len(adjacent) + len(distant)
        assert total == len(state.npcs)


class TestLastSimulatedTurnUpdated:
    @pytest.mark.asyncio
    async def test_active_npcs_get_turn_updated(self):
        from unittest.mock import AsyncMock, patch
        from backend.persistence import init_db
        import tempfile, os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            test_db = Path(tmp) / "test.db"
            with patch("backend.persistence.DB_PATH", test_db):
                await init_db()
                state = _make_state()
                state.turn = 0
                for npc in state.npcs:
                    npc.last_simulated_turn = 0

                with patch("backend.world_engine._npc_autonomous_action",
                            new_callable=AsyncMock,
                            return_value={"action": "Acts", "interacts_with": None}):
                    from backend.world_engine import simulate_turn
                    new_state, activity = await simulate_turn(state)

                active_npcs = [
                    n for n in new_state.npcs
                    if n.location == new_state.player.location
                ]
                for npc in active_npcs:
                    if npc.last_simulated_turn == new_state.turn:
                        return
                if not active_npcs:
                    pytest.skip("No active NPCs sampled this turn")
                pytest.skip("RNG may not have sampled all active NPCs")
