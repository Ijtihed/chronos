"""Tests for NPC relevance filtering — criterion 5: nobody cares is possible."""

from backend.main import _filter_relevant
from backend.world_state import NPC, PersonalityTraits, NpcNeeds


def _npc(npc_id, name):
    return NPC(
        id=npc_id, name=name, role="test", archetype="merchant",
        location="loc", description="test", disposition="cautious",
        relationship_to_player="none",
        personality=PersonalityTraits(), needs=NpcNeeds(),
    )


class TestFilterRelevant:
    def test_all_relevant_returns_all(self):
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus")]
        impacts = [
            {"name": "Gallus", "relevant": True},
            {"name": "Paulus", "relevant": True},
        ]
        result = _filter_relevant(npcs, impacts)
        assert len(result) == 2

    def test_one_relevant_returns_one(self):
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus")]
        impacts = [
            {"name": "Gallus", "relevant": True},
            {"name": "Paulus", "relevant": False},
        ]
        result = _filter_relevant(npcs, impacts)
        assert len(result) == 1
        assert result[0].name == "Gallus"

    def test_nobody_relevant_returns_empty(self):
        """Criterion 5: when the LLM says nobody cares, nobody reacts."""
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus")]
        impacts = [
            {"name": "Gallus", "relevant": False},
            {"name": "Paulus", "relevant": False},
        ]
        result = _filter_relevant(npcs, impacts)
        assert result == []

    def test_empty_impacts_defaults_to_two(self):
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus"), _npc("c", "Marcus")]
        result = _filter_relevant(npcs, [])
        assert len(result) == 2

    def test_no_relevant_field_defaults_to_two(self):
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus")]
        impacts = [{"name": "Gallus", "sentiment": "positive"}]
        result = _filter_relevant(npcs, impacts)
        assert len(result) == 2

    def test_empty_npc_list(self):
        assert _filter_relevant([], [{"name": "X", "relevant": True}]) == []
        assert _filter_relevant([], []) == []

    def test_trivial_action_nobody_cares(self):
        """A player rests. The LLM marks nobody as relevant. Zero responses."""
        npcs = [_npc("a", "Gallus"), _npc("b", "Paulus")]
        impacts = [
            {"name": "Gallus", "sentiment": "neutral", "relevant": False, "reason": "irrelevant"},
            {"name": "Paulus", "sentiment": "neutral", "relevant": False, "reason": "irrelevant"},
        ]
        result = _filter_relevant(npcs, impacts)
        assert result == [], "Nobody should react to a trivial action"
