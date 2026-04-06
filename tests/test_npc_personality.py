"""Tests for the NPC personality and needs system (Task 1)."""

import pytest

from backend.npc_personality import (
    ARCHETYPE_BASELINE_DISPOSITION,
    ARCHETYPE_BASE_NEEDS,
    ARCHETYPE_TRAIT_RANGES,
    apply_need_shift,
    calculate_needs,
    decay_needs,
    generate_personality,
    get_critical_needs,
    get_dominant_need,
    get_urgent_needs,
)
from backend.world_state import NPC, NpcNeeds, PersonalityTraits, create_initial_state


class TestGeneratePersonality:
    def test_known_archetype_within_range(self):
        for archetype, ranges in ARCHETYPE_TRAIT_RANGES.items():
            p = generate_personality(archetype)
            for trait, (lo, hi) in ranges.items():
                val = getattr(p, trait)
                assert lo <= val <= hi, (
                    f"{archetype}.{trait} = {val} not in [{lo}, {hi}]"
                )

    def test_unknown_archetype_uses_defaults(self):
        p = generate_personality("unknown_archetype")
        assert 20 <= p.ambition <= 80
        assert 20 <= p.courage <= 80

    def test_returns_personality_traits_model(self):
        p = generate_personality("merchant")
        assert isinstance(p, PersonalityTraits)

    def test_randomness(self):
        results = [generate_personality("soldier").courage for _ in range(20)]
        assert len(set(results)) > 1, "Should have some variation across calls"


class TestCalculateNeeds:
    def test_all_values_clamped_0_100(self):
        for archetype in ARCHETYPE_TRAIT_RANGES:
            p = generate_personality(archetype)
            needs = calculate_needs(archetype, p)
            d = needs.model_dump()
            for k, v in d.items():
                assert 0.0 <= v <= 100.0, f"{archetype}.{k} = {v}"

    def test_archetype_base_needs_boosted(self):
        p = PersonalityTraits(ambition=50, compassion=50, courage=50, piety=50, pragmatism=50)
        merchant_needs = calculate_needs("merchant", p)
        farmer_needs = calculate_needs("farmer", p)
        assert merchant_needs.trade > farmer_needs.trade
        assert farmer_needs.harvest > merchant_needs.harvest

    def test_soldier_has_duty_and_honor(self):
        p = generate_personality("soldier")
        needs = calculate_needs("soldier", p)
        assert needs.duty > 30
        assert needs.honor > 15

    def test_priest_has_faith_and_community(self):
        p = generate_personality("priest")
        needs = calculate_needs("priest", p)
        assert needs.faith > 30
        assert needs.community > 30


class TestNeedUrgency:
    def test_get_urgent_needs(self):
        needs = NpcNeeds(survival=10.0, safety=25.0, trade=50.0, faith=80.0)
        urgent = get_urgent_needs(needs)
        assert "survival" in urgent
        assert "safety" in urgent
        assert "trade" not in urgent

    def test_get_critical_needs(self):
        needs = NpcNeeds(survival=5.0, safety=14.0, trade=50.0)
        critical = get_critical_needs(needs)
        assert "survival" in critical
        assert "safety" in critical
        assert "trade" not in critical

    def test_get_dominant_need(self):
        d = {k: 80.0 for k in NpcNeeds.model_fields}
        d["survival"] = 5.0
        needs = NpcNeeds(**d)
        assert get_dominant_need(needs) == "survival"

    def test_urgent_sorted_ascending(self):
        needs = NpcNeeds(survival=10.0, safety=20.0, family=5.0)
        urgent = get_urgent_needs(needs)
        vals = [getattr(needs, n) for n in urgent]
        assert vals == sorted(vals)


class TestDecayNeeds:
    def _make_npc(self, **overrides) -> NPC:
        defaults = dict(
            id="test", name="Test", role="tester", archetype="soldier",
            location="loc", description="desc", disposition="grim",
            relationship_to_player="none",
            personality=PersonalityTraits(ambition=50, compassion=50, courage=50, piety=50, pragmatism=50),
            needs=NpcNeeds(survival=50.0, safety=50.0, family=50.0, social=50.0,
                           trade=50.0, profit=50.0, power=50.0, reputation=50.0,
                           honor=50.0, duty=50.0, loyalty=50.0, faith=50.0,
                           knowledge=50.0, order=50.0, community=50.0,
                           harvest=50.0, stability=50.0),
        )
        defaults.update(overrides)
        return NPC(**defaults)

    def test_all_needs_decrease(self):
        npc = self._make_npc()
        before = npc.needs.model_dump()
        decay_needs(npc, "low", current_turn=1)
        after = npc.needs.model_dump()
        decreased = sum(1 for k in before if after[k] < before[k])
        assert decreased > 0

    def test_needs_never_go_below_zero(self):
        npc = self._make_npc(
            needs=NpcNeeds(**{k: 1.0 for k in NpcNeeds.model_fields})
        )
        for _ in range(10):
            decay_needs(npc, "critical", current_turn=1)
        d = npc.needs.model_dump()
        for k, v in d.items():
            assert v >= 0.0, f"{k} went below 0: {v}"

    def test_high_tension_accelerates_survival_decay(self):
        npc_low = self._make_npc()
        npc_high = self._make_npc()
        for _ in range(5):
            decay_needs(npc_low, "low")
            decay_needs(npc_high, "critical")
        assert npc_high.needs.survival < npc_low.needs.survival

    def test_critical_threshold_logged(self):
        npc = self._make_npc(
            needs=NpcNeeds(**{k: 16.0 for k in NpcNeeds.model_fields})
        )
        decay_needs(npc, "critical", current_turn=5)
        critical_logs = [h for h in npc.needs_history if h.get("event") == "critical_threshold"]
        assert len(critical_logs) > 0


class TestApplyNeedShift:
    def _make_npc(self, **overrides) -> NPC:
        defaults = dict(
            id="test", name="Test", role="tester", archetype="soldier",
            location="loc", description="desc", disposition="grim",
            relationship_to_player="none",
            personality=PersonalityTraits(ambition=70, compassion=50, courage=80, piety=60, pragmatism=50),
            needs=NpcNeeds(survival=50.0, safety=50.0, family=50.0, social=50.0,
                           trade=50.0, profit=50.0, power=50.0, reputation=50.0,
                           honor=50.0, duty=50.0, loyalty=50.0, faith=50.0,
                           knowledge=50.0, order=50.0, community=50.0,
                           harvest=50.0, stability=50.0),
        )
        defaults.update(overrides)
        return NPC(**defaults)

    def test_witness_death(self):
        npc = self._make_npc()
        apply_need_shift(npc, "witness_death", current_turn=1)
        assert npc.needs.survival == 65.0
        assert npc.needs.safety == 60.0
        assert len(npc.needs_history) == 1

    def test_betrayed_lowers_loyalty(self):
        npc = self._make_npc()
        apply_need_shift(npc, "betrayed", current_turn=1)
        assert npc.needs.loyalty == 30.0

    def test_betrayed_power_boost_if_ambitious(self):
        npc = self._make_npc()
        apply_need_shift(npc, "betrayed", current_turn=1)
        assert npc.needs.power == 60.0

    def test_family_death_spikes_family(self):
        npc = self._make_npc()
        apply_need_shift(npc, "family_death", current_turn=1)
        assert npc.needs.family == 100.0
        assert npc.personality.compassion == 45

    def test_imprisoned_suppresses_non_survival(self):
        npc = self._make_npc()
        apply_need_shift(npc, "imprisoned", current_turn=1)
        assert npc.needs.survival >= 90.0
        assert npc.needs.safety >= 90.0
        assert npc.needs.social < 50.0

    def test_religious_event_permanent_piety_change(self):
        npc = self._make_npc()
        old_piety = npc.personality.piety
        apply_need_shift(npc, "religious_event", current_turn=1)
        assert npc.personality.piety == old_piety + 5
        assert npc.needs.faith > 50.0

    def test_prolonged_hunger_permanent_trait_changes(self):
        npc = self._make_npc()
        old_pragmatism = npc.personality.pragmatism
        old_compassion = npc.personality.compassion
        apply_need_shift(npc, "prolonged_hunger", current_turn=1)
        assert npc.personality.pragmatism == old_pragmatism + 5
        assert npc.personality.compassion == old_compassion - 5
        assert npc.needs.survival >= 95.0

    def test_relationship_death_collapses_loyalty(self):
        npc = self._make_npc()
        apply_need_shift(npc, "relationship_death", current_turn=1)
        assert npc.needs.loyalty < 15.0

    def test_unknown_event_no_crash(self):
        npc = self._make_npc()
        apply_need_shift(npc, "some_unknown_event", current_turn=1)
        assert len(npc.needs_history) == 1


class TestInitialStateHasPersonality:
    def test_hardcoded_npcs_have_personality(self):
        state = create_initial_state()
        for npc in state.npcs:
            assert isinstance(npc.personality, PersonalityTraits)
            assert isinstance(npc.needs, NpcNeeds)
            assert npc.personality.courage > 0

    def test_needs_are_archetype_appropriate(self):
        state = create_initial_state()
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        paulus = next(n for n in state.npcs if n.id == "deacon_paulus")
        assert gallus.needs.duty > 20
        assert paulus.needs.faith > 20
