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


class TestFilterRelevantTargetForcing:
    """Targeted NPC must always make it through the filter, no matter what
    npc_impacts says. The Addressed-mode upgrade depends on this."""

    def test_target_forced_when_impacts_empty(self):
        """Player addresses NPC #3 with no impacts list -- they must be in result."""
        npcs = [_npc("a", "Alpha"), _npc("b", "Beta"), _npc("c", "Helena")]
        result = _filter_relevant(npcs, [], target="Helena")
        assert any(n.id == "c" for n in result), "Targeted Helena must be included"

    def test_target_forced_when_marked_irrelevant(self):
        """LLM says nobody cares, but player named Helena -- she still reacts."""
        npcs = [_npc("a", "Helena"), _npc("b", "Marcus")]
        impacts = [
            {"name": "Helena", "relevant": False},
            {"name": "Marcus", "relevant": False},
        ]
        result = _filter_relevant(npcs, impacts, target="Helena")
        assert any(n.id == "a" for n in result)
        assert all(n.id != "b" for n in result), "Marcus should not be added"

    def test_target_appears_first(self):
        """Targeted NPC is at the head of the list so _split_addressed picks them."""
        npcs = [_npc("a", "Alpha"), _npc("b", "Beta"), _npc("c", "Helena")]
        result = _filter_relevant(npcs, [], target="Helena")
        assert result[0].name == "Helena"

    def test_target_no_match_falls_through(self):
        """Target string that doesn't match any nearby NPC: behave like no target."""
        npcs = [_npc("a", "Alpha"), _npc("b", "Beta"), _npc("c", "Marcus")]
        result = _filter_relevant(npcs, [], target="Helena")
        assert len(result) == 2
        assert {n.name for n in result} == {"Alpha", "Beta"}

    def test_target_not_duplicated_when_already_relevant(self):
        """If the target was already in the relevant list, they appear once."""
        npcs = [_npc("a", "Helena"), _npc("b", "Marcus")]
        impacts = [
            {"name": "Helena", "relevant": True},
            {"name": "Marcus", "relevant": True},
        ]
        result = _filter_relevant(npcs, impacts, target="Helena")
        helena_count = sum(1 for n in result if n.id == "a")
        assert helena_count == 1, f"Helena appears {helena_count} times, expected 1"
        assert len(result) == 2

    def test_target_param_is_optional(self):
        """Existing callers without target= still work."""
        npcs = [_npc("a", "Alpha"), _npc("b", "Beta")]
        result_old = _filter_relevant(npcs, [])
        assert len(result_old) == 2

    def test_target_empty_string_treated_as_none(self):
        npcs = [_npc("a", "Alpha"), _npc("b", "Beta"), _npc("c", "Helena")]
        result = _filter_relevant(npcs, [], target="")
        assert len(result) == 2
        assert {n.name for n in result} == {"Alpha", "Beta"}
