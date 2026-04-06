"""Tests for LLM→engine boundary enforcement.

Verifies that LLM output goes through NPCEffect and that only allowed
fields can be mutated. Direct assignment from LLM to WorldState fields
should be impossible.
"""

from backend.llm_schemas import NPCEffect
from backend.world_state import (
    WorldState,
    apply_action,
    apply_npc_effect,
    create_initial_state,
    shift_disposition,
    _shift_positive,
    _shift_negative,
)


class TestNPCEffect:
    def test_disposition_shift_clamped(self):
        effect = NPCEffect(npc_id="test", disposition_shift=5)
        assert effect.disposition_shift == 1

    def test_disposition_shift_clamped_negative(self):
        effect = NPCEffect(npc_id="test", disposition_shift=-10)
        assert effect.disposition_shift == -1

    def test_disposition_shift_zero_allowed(self):
        effect = NPCEffect(npc_id="test", disposition_shift=0)
        assert effect.disposition_shift == 0

    def test_disposition_shift_none_allowed(self):
        effect = NPCEffect(npc_id="test", disposition_shift=None)
        assert effect.disposition_shift is None

    def test_non_numeric_shift_defaults_to_zero(self):
        effect = NPCEffect(npc_id="test", disposition_shift="hostile")
        assert effect.disposition_shift == 0


class TestShiftDisposition:
    def test_positive_shift(self):
        assert shift_disposition("grim", 1) == "cautious"

    def test_negative_shift(self):
        assert shift_disposition("grim", -1) == "hostile"

    def test_zero_shift(self):
        assert shift_disposition("grim", 0) == "grim"


class TestApplyNPCEffect:
    def test_positive_disposition_shift(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "grim"

        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=1)
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "cautious"

    def test_negative_disposition_shift(self):
        state = create_initial_state()
        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=-1)
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "hostile"

    def test_valid_location_change(self):
        state = create_initial_state()
        effect = NPCEffect(npc_id="centurion_gallus", location_change="ravenna")
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.location == "ravenna"

    def test_invalid_location_rejected(self):
        state = create_initial_state()
        effect = NPCEffect(npc_id="centurion_gallus", location_change="atlantis")
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.location == "ariminum"

    def test_same_location_not_moved(self):
        state = create_initial_state()
        effect = NPCEffect(npc_id="centurion_gallus", location_change="ariminum")
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.location == "ariminum"

    def test_unknown_npc_id_ignored(self):
        state = create_initial_state()
        effect = NPCEffect(npc_id="nonexistent", disposition_shift=1)
        apply_npc_effect(state, effect)

    def test_none_shift_leaves_disposition_unchanged(self):
        state = create_initial_state()
        gallus_before = next(n for n in state.npcs if n.id == "centurion_gallus")
        disp_before = gallus_before.disposition

        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=None)
        apply_npc_effect(state, effect)

        gallus_after = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus_after.disposition == disp_before


class TestBoundedMutationScope:
    """Verify that apply_npc_effect cannot change fields outside the allowed set."""

    def test_memory_not_changed_by_effect(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        mem_before = gallus.memory_of_player

        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=1)
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.memory_of_player == mem_before

    def test_name_not_changed_by_effect(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        name_before = gallus.name

        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=-1)
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.name == name_before

    def test_description_not_changed_by_effect(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        desc_before = gallus.description

        effect = NPCEffect(npc_id="centurion_gallus", disposition_shift=1, location_change="ravenna")
        apply_npc_effect(state, effect)

        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.description == desc_before


class TestThreatenNowBounded:
    """The 'threaten' action type used to jump directly to 'hostile'.
    It now uses _shift_negative (±1 step) like everything else."""

    def test_threaten_shifts_one_step(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        gallus.disposition = "cautious"

        action = {
            "action_type": "threaten",
            "target": "Lucius Gallus",
            "intent": "threaten",
            "era_description": "Corvinus threatens.",
        }
        new = apply_action(state, action)

        gallus_after = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus_after.disposition == "wary"
        assert gallus_after.disposition != "hostile"

    def test_threaten_from_grim_goes_hostile(self):
        """grim → hostile is one step in _NEGATIVE_SHIFTS, so this is correct."""
        state = create_initial_state()
        action = {
            "action_type": "threaten",
            "target": "Lucius Gallus",
            "intent": "threaten",
            "era_description": "Corvinus threatens.",
        }
        new = apply_action(state, action)

        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "hostile"
