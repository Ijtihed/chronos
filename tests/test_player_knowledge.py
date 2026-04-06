"""Tests for the Player Knowledge Agent — PlayerView filtering from WorldState."""

from backend.player_knowledge import (
    KNOWLEDGE_MATRIX,
    HistoricalEventView,
    PlayerView,
    Rumor,
    VisibleEvent,
    VisibleNPCHere,
    VisibleNPCKnown,
    _knowledge_tier,
    _filter_tension,
    _get_overrides,
    build_player_view,
    classify_event_knowledge,
    filter_historical_events,
    graph_distance,
    rumor_accuracy,
)
from backend.world_state import (
    Event,
    NPC,
    WorldState,
    create_initial_state,
)


class TestKnowledgeTier:
    def test_scholar_is_high(self):
        assert _knowledge_tier("scholar") == "high"

    def test_noble_is_high(self):
        assert _knowledge_tier("noble") == "high"

    def test_merchant_is_medium(self):
        assert _knowledge_tier("merchant") == "medium"

    def test_soldier_is_medium(self):
        assert _knowledge_tier("soldier") == "medium"

    def test_farmer_is_low(self):
        assert _knowledge_tier("farmer") == "low"

    def test_peasant_is_low(self):
        assert _knowledge_tier("peasant") == "low"

    def test_unknown_defaults_to_medium(self):
        assert _knowledge_tier("wanderer") == "medium"

    def test_case_insensitive(self):
        assert _knowledge_tier("Scholar") == "high"
        assert _knowledge_tier("MERCHANT") == "medium"

    def test_multi_word_archetype(self):
        assert _knowledge_tier("retired soldier") == "medium"
        assert _knowledge_tier("minor noble") == "high"


class TestFilterTension:
    def test_high_tier_sees_exact(self):
        assert _filter_tension("critical", "high") == "critical"
        assert _filter_tension("low", "high") == "low"

    def test_medium_tier_sees_simplified(self):
        assert _filter_tension("low", "medium") == "calm"
        assert _filter_tension("moderate", "medium") == "uneasy"
        assert _filter_tension("high", "medium") == "dangerous"
        assert _filter_tension("critical", "medium") == "dangerous"

    def test_low_tier_sees_nothing(self):
        assert _filter_tension("critical", "low") is None
        assert _filter_tension("low", "low") is None


class TestBuildPlayerView:
    def test_returns_player_view_model(self, initial_state: WorldState):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert isinstance(pv, PlayerView)

    def test_basic_fields_present(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.run_id == initial_state.run_id
        assert pv.run_status == "active"
        assert pv.turn == 0
        assert pv.player_name == "Marcus Aurelius Corvinus"
        assert pv.player_archetype == "merchant"
        assert pv.era_name == "Roman Late Empire"

    def test_current_location_populated(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.current_location.id == "ariminum"
        assert pv.current_location.name == "Ariminum"
        assert len(pv.current_location.neighbors) >= 1

    def test_merchant_sees_simplified_tension(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.current_location.political_tension == "dangerous"

    def test_scholar_sees_exact_tension(self, initial_state):
        initial_state.player.archetype = "scholar"
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.current_location.political_tension == "high"

    def test_farmer_sees_no_tension(self, initial_state):
        initial_state.player.archetype = "farmer"
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.current_location.political_tension is None


class TestNPCFiltering:
    def test_npcs_at_player_location_visible(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.npcs_here) == 2
        names = {n.name for n in pv.npcs_here}
        assert "Lucius Gallus" in names
        assert "Deacon Paulus" in names

    def test_npcs_here_have_full_detail(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        gallus = next(n for n in pv.npcs_here if n.name == "Lucius Gallus")
        assert gallus.disposition == "grim"
        assert gallus.role != ""
        assert gallus.description != ""
        assert gallus.relationship_to_player != ""

    def test_npcs_here_never_contain_memory(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        for npc in pv.npcs_here:
            d = npc.model_dump()
            assert "memory_of_player" not in d
            assert "last_interaction_turn" not in d

    def test_last_pov_included_when_available(self, initial_state):
        initial_state.npcs[0].stored_povs = ["I see the merchant approach."]
        pv = build_player_view(initial_state, initial_state.run_id)
        gallus = next(n for n in pv.npcs_here if n.name == "Lucius Gallus")
        assert gallus.last_pov == "I see the merchant approach."

    def test_last_pov_is_none_without_stored_povs(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        for npc in pv.npcs_here:
            assert npc.last_pov is None

    def test_npcs_at_visited_location_name_and_archetype_only(self, initial_state):
        initial_state.npcs[0].location = "ravenna"
        initial_state.visited_locations.append("ravenna")
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.npcs_known) == 1
        gallus = pv.npcs_known[0]
        assert gallus.name == "Lucius Gallus"
        assert gallus.archetype == "soldier"
        d = gallus.model_dump()
        assert "disposition" not in d
        assert "description" not in d
        assert "memory_of_player" not in d

    def test_npcs_at_unvisited_location_excluded(self, initial_state):
        initial_state.npcs[0].location = "mediolanum"
        pv = build_player_view(initial_state, initial_state.run_id)
        all_npc_ids = {n.id for n in pv.npcs_here} | {n.id for n in pv.npcs_known}
        assert "centurion_gallus" not in all_npc_ids


class TestEventFiltering:
    def test_events_at_player_location_are_witnessed(self, initial_state):
        initial_state.events.append(Event(
            turn=1, action_type="speak",
            description="Corvinus speaks to Gallus.",
            location="ariminum",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.confirmed_events) == 1
        assert pv.confirmed_events[0].knowledge_type == "witnessed"

    def test_events_at_visited_location_are_known(self, initial_state):
        initial_state.visited_locations.append("ravenna")
        initial_state.events.append(Event(
            turn=2, action_type="trade",
            description="A deal was struck in Ravenna.",
            location="ravenna",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.confirmed_events) == 1
        assert pv.confirmed_events[0].knowledge_type == "known"

    def test_events_at_unvisited_location_excluded(self, initial_state):
        initial_state.events.append(Event(
            turn=1, action_type="battle",
            description="Battle rages in Mediolanum.",
            location="mediolanum",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.confirmed_events) == 0


class TestRumors:
    def test_ambient_events_at_neighbor_locations_become_rumors(self, initial_state):
        initial_state.events.append(Event(
            turn=1, action_type="ambient",
            description="Soldiers drill outside Ravenna.",
            location="ravenna",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.rumors) == 1
        assert "Ravenna" in pv.rumors[0].description or pv.rumors[0].source_location == "ravenna"

    def test_non_ambient_events_at_neighbor_not_rumors(self, initial_state):
        initial_state.events.append(Event(
            turn=1, action_type="speak",
            description="Corvinus talks in Ravenna.",
            location="ravenna",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.rumors) == 0

    def test_events_at_distant_locations_not_rumors(self, initial_state):
        initial_state.locations.append(
            type(initial_state.locations[0])(
                id="roma", name="Roma", description="The eternal city",
                political_tension="critical", lat=41.9, lon=12.5,
            )
        )
        initial_state.events.append(Event(
            turn=1, action_type="ambient",
            description="Fire in Roma.",
            location="roma",
        ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.rumors) == 0

    def test_rumors_capped_at_five(self, initial_state):
        for i in range(10):
            initial_state.events.append(Event(
                turn=i, action_type="ambient",
                description=f"Rumor {i} from Ravenna.",
                location="ravenna",
            ))
        pv = build_player_view(initial_state, initial_state.run_id)
        assert len(pv.rumors) <= 5


class TestNoRawStateLeaks:
    def test_no_memory_of_player_in_output(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "memory_of_player" not in dump

    def test_no_last_interaction_turn_in_output(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "last_interaction_turn" not in dump

    def test_no_stored_povs_list_in_output(self, initial_state):
        initial_state.npcs[0].stored_povs = ["pov1", "pov2", "pov3"]
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "stored_povs" not in dump

    def test_no_birth_year_in_output(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "birth_year" not in dump

    def test_no_years_per_turn_in_output(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "years_per_turn" not in dump

    def test_no_lifespan_turns_in_output(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dump = pv.model_dump_json()
        assert "lifespan_turns" not in dump


class TestPlayerViewSerialization:
    def test_round_trips_through_json(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        dumped = pv.model_dump()
        restored = PlayerView(**dumped)
        assert restored == pv


# ===================================================================
# Knowledge Matrix, graph distance, rumor accuracy
# ===================================================================

class TestGraphDistance:
    def test_same_location_is_zero(self, initial_state):
        assert graph_distance("ariminum", "ariminum", initial_state) == 0

    def test_direct_neighbor(self, initial_state):
        assert graph_distance("ariminum", "ravenna", initial_state) == 1

    def test_two_hops(self, initial_state):
        assert graph_distance("ravenna", "mediolanum", initial_state) == 2

    def test_unreachable_returns_999(self, initial_state):
        assert graph_distance("ariminum", "nonexistent", initial_state) == 999

    def test_symmetric(self, initial_state):
        d1 = graph_distance("ariminum", "mediolanum", initial_state)
        d2 = graph_distance("mediolanum", "ariminum", initial_state)
        assert d1 == d2


class TestKnowledgeMatrix:
    def test_all_tiers_and_types_have_entries(self):
        for tier in ("high", "medium", "low"):
            for t in ("war", "epidemic", "famine", "political",
                      "religious", "economic", "natural_disaster", "cultural"):
                assert (tier, t) in KNOWLEDGE_MATRIX, f"Missing ({tier}, {t})"

    def test_high_tier_has_greater_reach_than_low(self):
        for t in ("war", "political", "famine"):
            high = KNOWLEDGE_MATRIX[("high", t)]
            low = KNOWLEDGE_MATRIX[("low", t)]
            assert high["known"] >= low["known"]
            assert high["rumor"] >= low["rumor"]


class TestClassifyEventKnowledge:
    def test_distance_zero_is_witnessed(self):
        assert classify_event_knowledge("low", "farmer", "war", 0) == "witnessed"

    def test_within_known_threshold(self):
        result = classify_event_knowledge("high", "scholar", "war", 3)
        assert result == "known"

    def test_beyond_known_within_rumor(self):
        result = classify_event_knowledge("high", "scholar", "war", 7)
        assert result.startswith("rumor")

    def test_beyond_rumor_is_unknown(self):
        result = classify_event_knowledge("low", "farmer", "political", 50)
        assert result == "unknown"

    def test_merchant_economic_override(self):
        base = classify_event_knowledge("medium", "craftsman", "economic", 4)
        boosted = classify_event_knowledge("medium", "merchant", "economic", 4)
        assert base == "unknown" or boosted in ("known", "rumor_reliable", "rumor_unreliable")
        assert boosted != "unknown"

    def test_farmer_famine_override(self):
        result = classify_event_knowledge("low", "farmer", "famine", 2)
        assert result == "known"

    def test_clergy_religious_override(self):
        result = classify_event_knowledge("medium", "clergy", "religious", 3)
        assert result == "known"


class TestArchetypeOverrides:
    def test_merchant_has_economic_boost(self):
        overrides = _get_overrides("merchant")
        assert "economic" in overrides
        assert overrides["economic"] >= 1

    def test_farmer_has_famine_boost(self):
        overrides = _get_overrides("farmer")
        assert "famine" in overrides

    def test_soldier_has_war_boost(self):
        overrides = _get_overrides("soldier")
        assert "war" in overrides

    def test_unknown_archetype_no_overrides(self):
        assert _get_overrides("wanderer") == {}


class TestRumorAccuracy:
    def test_at_known_boundary_is_high(self):
        acc = rumor_accuracy(distance=4, known_threshold=3)
        assert acc >= 0.8

    def test_degrades_with_distance(self):
        acc_near = rumor_accuracy(distance=4, known_threshold=3)
        acc_far = rumor_accuracy(distance=8, known_threshold=3)
        assert acc_near > acc_far

    def test_intermediary_penalty(self):
        no_hops = rumor_accuracy(distance=5, known_threshold=3, intermediary_hops=0)
        with_hops = rumor_accuracy(distance=5, known_threshold=3, intermediary_hops=3)
        assert no_hops > with_hops

    def test_never_below_floor(self):
        acc = rumor_accuracy(distance=100, known_threshold=1, intermediary_hops=50)
        assert acc == 0.3

    def test_exact_values(self):
        from pytest import approx
        assert rumor_accuracy(4, 3, 0) == approx(0.85)
        assert rumor_accuracy(5, 3, 0) == approx(0.7)
        assert rumor_accuracy(5, 3, 2) == approx(0.5)


class TestFilterHistoricalEvents:
    def _make_event(self, region="Ariminum", event_type="war", year=410):
        return {
            "id": 1,
            "year": year,
            "region": region,
            "event": f"Test {event_type} event in {region}",
            "significance": "regional",
            "type": event_type,
            "affects": ["military"],
            "canonical": True,
        }

    def test_event_at_player_location_is_known(self, initial_state):
        ev = self._make_event(region="Ariminum")
        results = filter_historical_events([ev], initial_state)
        assert len(results) >= 1
        assert results[0].knowledge_quality in ("witnessed", "known")

    def test_distant_event_excluded_for_low_tier(self, initial_state):
        initial_state.player.archetype = "farmer"
        ev = self._make_event(region="Faraway Land", event_type="political")
        results = filter_historical_events([ev], initial_state)
        assert len(results) == 0

    def test_scholar_knows_more_than_farmer(self, initial_state):
        events = [
            self._make_event(region="Ravenna", event_type="political"),
            self._make_event(region="Mediolanum", event_type="political"),
        ]
        initial_state.player.archetype = "scholar"
        scholar_results = filter_historical_events(events, initial_state)

        initial_state.player.archetype = "farmer"
        farmer_results = filter_historical_events(events, initial_state)

        assert len(scholar_results) >= len(farmer_results)

    def test_results_include_accuracy_for_rumors(self, initial_state):
        initial_state.player.archetype = "farmer"
        ev = self._make_event(region="Ravenna", event_type="war")
        results = filter_historical_events([ev], initial_state)
        for r in results:
            if r.knowledge_quality.startswith("rumor"):
                assert r.accuracy is not None
                assert 0.3 <= r.accuracy <= 1.0

    def test_empty_input_returns_empty(self, initial_state):
        assert filter_historical_events([], initial_state) == []

    def test_build_player_view_with_historical_events(self, initial_state):
        events = [self._make_event(region="Ariminum")]
        pv = build_player_view(initial_state, initial_state.run_id, historical_events_raw=events)
        assert len(pv.historical_events) >= 1
        assert pv.historical_events[0].event_type == "war"

    def test_build_player_view_without_historical_events(self, initial_state):
        pv = build_player_view(initial_state, initial_state.run_id)
        assert pv.historical_events == []
