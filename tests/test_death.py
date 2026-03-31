"""Unit tests for death, memory decay, and erasure system."""

from backend.death_engine import apply_death, decay_memories, BASE_MEMORY_DECAY
from backend.world_state import WorldState, create_initial_state, apply_action


class TestApplyDeath:
    def test_transitions_to_dead_observing(self):
        state = create_initial_state()
        new = apply_death(state, "Killed by bandits.")
        assert new.run_status == "dead_observing"

    def test_adds_death_event(self):
        state = create_initial_state()
        new = apply_death(state, "Killed by bandits.")
        death_events = [e for e in new.events if e.action_type == "death"]
        assert len(death_events) == 1
        assert "bandits" in death_events[0].description

    def test_does_not_mutate_original(self):
        state = create_initial_state()
        apply_death(state, "Killed.")
        assert state.run_status == "active"


class TestMemoryDecay:
    def test_memories_decrease_after_decay(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        for npc in state.npcs:
            npc.memory_of_player = 0.5

        new = decay_memories(state)
        for npc in new.npcs:
            assert npc.memory_of_player < 0.5

    def test_memory_does_not_go_below_zero(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        for npc in state.npcs:
            npc.memory_of_player = 0.01

        new = decay_memories(state)
        for npc in new.npcs:
            assert npc.memory_of_player >= 0.0

    def test_run_ends_when_all_forgotten(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        for npc in state.npcs:
            npc.memory_of_player = 0.0

        new = decay_memories(state)
        assert new.run_status == "ended"

    def test_run_continues_if_any_memory_remains(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        state.npcs[0].memory_of_player = 0.5
        state.npcs[1].memory_of_player = 0.0

        new = decay_memories(state)
        assert new.run_status == "dead_observing"

    def test_high_memory_decays_slower(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        state.npcs[0].memory_of_player = 0.9
        state.npcs[1].memory_of_player = 0.2

        new = decay_memories(state)
        decay_high = 0.9 - new.npcs[0].memory_of_player
        decay_low = 0.2 - new.npcs[1].memory_of_player
        assert decay_high < decay_low, "Strong memory should decay slower"

    def test_eventually_all_forgotten(self):
        state = create_initial_state()
        state.run_status = "dead_observing"
        for npc in state.npcs:
            npc.memory_of_player = 1.0

        for _ in range(200):
            state = decay_memories(state)
            if state.run_status == "ended":
                break

        assert state.run_status == "ended", "All memories should eventually reach 0"


class TestDeathWithAgingContext:
    def test_player_age_calculated_correctly(self):
        state = create_initial_state()
        action = {"action_type": "observe", "era_description": "Corvinus waits."}
        for _ in range(10):
            state = apply_action(state, action)
        player_age = state.current_year - state.player.birth_year
        assert player_age > 30
