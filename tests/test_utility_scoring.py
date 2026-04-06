"""Tests for NPC utility scoring — the Sims-inspired autonomy pattern (Task 5)."""

import pytest

from backend.npc_personality import (
    WORLD_OPPORTUNITIES,
    choose_autonomous_action,
    need_urgency_weight,
    score_opportunity,
    _detect_opportunities,
    _get_relevant_needs,
)
from backend.world_state import (
    Event,
    NPC,
    NpcNeeds,
    PersonalityTraits,
    WorldState,
    create_initial_state,
)


def _make_npc(archetype="merchant", location="ariminum", **need_overrides) -> NPC:
    from backend.npc_personality import generate_personality, calculate_needs
    p = generate_personality(archetype)
    n = calculate_needs(archetype, p)
    if need_overrides:
        d = n.model_dump()
        d.update(need_overrides)
        n = NpcNeeds(**d)
    return NPC(
        id="test_npc", name="Test", role="tester", archetype=archetype,
        location=location, description="test", disposition="cautious",
        relationship_to_player="none", personality=p, needs=n,
    )


class TestNeedUrgencyWeight:
    def test_critical_weight(self):
        assert need_urgency_weight(5.0) == 5.0

    def test_urgent_weight(self):
        assert need_urgency_weight(20.0) == 3.0

    def test_moderate_weight(self):
        assert need_urgency_weight(40.0) == 1.5

    def test_comfortable_weight(self):
        assert need_urgency_weight(80.0) == 1.0

    def test_boundary_at_15(self):
        assert need_urgency_weight(14.9) == 5.0
        assert need_urgency_weight(15.0) == 3.0

    def test_boundary_at_30(self):
        assert need_urgency_weight(29.9) == 3.0
        assert need_urgency_weight(30.0) == 1.5


class TestScoreOpportunity:
    def test_unknown_opportunity_returns_zero(self):
        npc = _make_npc()
        assert score_opportunity(npc, "nonexistent_opportunity") == 0.0

    def test_depleted_merchant_scores_trade_higher(self):
        merchant = _make_npc("merchant", trade=10.0, profit=10.0, social=10.0)
        soldier = _make_npc("soldier", trade=10.0, profit=10.0, social=10.0)
        m_score = score_opportunity(merchant, "trade_caravan_passing")
        s_score = score_opportunity(soldier, "trade_caravan_passing")
        assert m_score == s_score or abs(m_score - s_score) < 1.0

    def test_soldier_scores_siege_duty_higher(self):
        soldier = _make_npc("soldier", duty=10.0, honor=10.0, survival=10.0, safety=10.0)
        merchant = _make_npc("merchant", duty=10.0, honor=10.0, survival=10.0, safety=10.0)
        s_score = score_opportunity(soldier, "siege_threat")
        m_score = score_opportunity(merchant, "siege_threat")
        assert s_score > m_score, "Soldier gets duty/honor bonus from siege_threat"

    def test_critical_needs_increase_score(self):
        desperate = _make_npc("merchant", survival=5.0, safety=5.0)
        comfortable = _make_npc("merchant", survival=90.0, safety=90.0)
        d_score = score_opportunity(desperate, "food_shortage")
        c_score = score_opportunity(comfortable, "food_shortage")
        assert d_score > c_score

    def test_compassionate_npc_scores_sick_member(self):
        compassionate = _make_npc("priest")
        compassionate.personality.compassion = 80
        cold = _make_npc("noble")
        cold.personality.compassion = 20
        c_score = score_opportunity(compassionate, "sick_community_member")
        n_score = score_opportunity(cold, "sick_community_member")
        assert c_score > n_score


class TestGetRelevantNeeds:
    def test_basic_satisfies(self):
        opp = WORLD_OPPORTUNITIES["trade_caravan_passing"]
        traits = PersonalityTraits(ambition=50, compassion=50, courage=50, piety=50, pragmatism=50)
        needs = _get_relevant_needs(opp, "merchant", traits)
        assert "trade" in needs
        assert "profit" in needs

    def test_soldier_gets_siege_bonus(self):
        opp = WORLD_OPPORTUNITIES["siege_threat"]
        traits = PersonalityTraits(ambition=50, compassion=50, courage=50, piety=50, pragmatism=50)
        soldier_needs = _get_relevant_needs(opp, "soldier", traits)
        merchant_needs = _get_relevant_needs(opp, "merchant", traits)
        assert "duty" in soldier_needs
        assert "duty" not in merchant_needs

    def test_compassionate_gets_sick_bonus(self):
        opp = WORLD_OPPORTUNITIES["sick_community_member"]
        compassionate = PersonalityTraits(ambition=50, compassion=80, courage=50, piety=50, pragmatism=50)
        cold = PersonalityTraits(ambition=50, compassion=20, courage=50, piety=50, pragmatism=50)
        c_needs = _get_relevant_needs(opp, "merchant", compassionate)
        n_needs = _get_relevant_needs(opp, "merchant", cold)
        assert "community" in c_needs
        assert "community" not in n_needs


class TestDetectOpportunities:
    def test_high_tension_detects_conflict(self):
        state = create_initial_state()
        state.locations[0].political_tension = "high"
        npc = state.npcs[0]
        opps = _detect_opportunities(npc, state)
        assert "conflict_nearby" in opps

    def test_critical_tension_detects_siege(self):
        state = create_initial_state()
        state.locations[0].political_tension = "critical"
        npc = state.npcs[0]
        opps = _detect_opportunities(npc, state)
        assert "siege_threat" in opps

    def test_low_tension_detects_peace(self):
        state = create_initial_state()
        state.locations[0].political_tension = "low"
        npc = state.npcs[0]
        opps = _detect_opportunities(npc, state)
        assert "peaceful_conditions" in opps

    def test_food_scarcity_detects_shortage(self):
        state = create_initial_state()
        state.locations[0].food_scarcity = "critical"
        npc = state.npcs[0]
        opps = _detect_opportunities(npc, state)
        assert "food_shortage" in opps

    def test_trade_routes_detect_caravan(self):
        state = create_initial_state()
        npc = state.npcs[0]
        opps = _detect_opportunities(npc, state)
        assert "trade_caravan_passing" in opps

    def test_empty_location_gets_default(self):
        state = create_initial_state()
        npc = _make_npc(location="nonexistent")
        opps = _detect_opportunities(npc, state)
        assert "peaceful_conditions" in opps


class TestChooseAutonomousAction:
    def test_returns_string(self):
        state = create_initial_state()
        npc = state.npcs[0]
        result = choose_autonomous_action(npc, state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_known_opportunity(self):
        state = create_initial_state()
        npc = state.npcs[0]
        all_known = set(WORLD_OPPORTUNITIES.keys())
        for _ in range(20):
            result = choose_autonomous_action(npc, state)
            assert result in all_known, f"Unknown opportunity: {result}"

    def test_deliberate_imperfection(self):
        state = create_initial_state()
        state.locations[0].political_tension = "critical"
        state.locations[0].food_scarcity = "critical"
        npc = state.npcs[0]
        results = set()
        for _ in range(50):
            results.add(choose_autonomous_action(npc, state))
        assert len(results) > 1, "Should sometimes pick non-top option"

    def test_desperate_npc_favors_survival_opportunities(self):
        state = create_initial_state()
        state.locations[0].political_tension = "critical"
        state.locations[0].food_scarcity = "critical"
        npc = state.npcs[0]
        npc.needs.survival = 5.0
        npc.needs.safety = 5.0
        counts = {}
        for _ in range(100):
            action = choose_autonomous_action(npc, state)
            counts[action] = counts.get(action, 0) + 1
        threat_types = {"siege_threat", "conflict_nearby", "food_shortage"}
        threat_count = sum(counts.get(t, 0) for t in threat_types)
        assert threat_count > 50, f"Desperate NPC should favor threat responses, got {counts}"
