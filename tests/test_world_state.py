"""Unit tests for world state: models, initial state, mutation, memory, and story summary."""

from backend.world_state import (
    TENSION_LEVELS,
    WorldState,
    _shift_negative,
    _shift_positive,
    apply_action,
    build_story_summary,
    create_initial_state,
    get_player_location,
    npcs_near_player,
)


class TestInitialState:
    def test_creates_valid_world_state(self, initial_state: WorldState):
        assert isinstance(initial_state, WorldState)

    def test_era_is_roman_late_empire(self, initial_state: WorldState):
        assert initial_state.era.name == "Roman Late Empire"
        assert initial_state.era.year_start == 410

    def test_player_exists(self, initial_state: WorldState):
        assert initial_state.player.name == "Marcus Aurelius Corvinus"
        assert initial_state.player.role == "Grain merchant"
        assert initial_state.player.location == "ariminum"

    def test_player_has_birth_year(self, initial_state):
        assert initial_state.player.birth_year > 0

    def test_has_at_least_one_npc(self, initial_state: WorldState):
        assert len(initial_state.npcs) >= 1

    def test_npcs_have_distinct_roles(self, initial_state: WorldState):
        roles = [npc.role for npc in initial_state.npcs]
        assert len(roles) == len(set(roles))

    def test_npcs_have_relationship_to_player(self, initial_state: WorldState):
        for npc in initial_state.npcs:
            assert npc.relationship_to_player, f"{npc.name} missing relationship"

    def test_npcs_have_memory_field(self, initial_state):
        for npc in initial_state.npcs:
            assert isinstance(npc.memory_of_player, float)

    def test_has_multiple_locations(self, initial_state):
        assert len(initial_state.locations) >= 2

    def test_locations_have_neighbors(self, initial_state):
        loc = get_player_location(initial_state)
        assert len(loc.neighbors) >= 1

    def test_run_status_is_active(self, initial_state):
        assert initial_state.run_status == "active"

    def test_has_run_id(self, initial_state):
        assert initial_state.run_id
        assert len(initial_state.run_id) > 0

    def test_starts_at_turn_zero(self, initial_state: WorldState):
        assert initial_state.turn == 0
        assert initial_state.events == []


class TestLocationHelpers:
    def test_get_player_location(self, initial_state):
        loc = get_player_location(initial_state)
        assert loc.name == "Ariminum"

    def test_npcs_near_player(self, initial_state):
        nearby = npcs_near_player(initial_state)
        assert len(nearby) == 2
        for npc in nearby:
            assert npc.location == initial_state.player.location


class TestApplyAction:
    def test_increments_turn(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.turn == 1

    def test_advances_year(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.current_year >= initial_state.current_year

    def test_appends_event(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert len(new.events) == 1
        assert new.events[0].turn == 1
        assert new.events[0].action_type == "speak"

    def test_event_records_location(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.events[0].location == "ariminum"

    def test_does_not_mutate_original(self, initial_state, sample_parsed_action):
        apply_action(initial_state, sample_parsed_action)
        assert initial_state.turn == 0
        assert initial_state.events == []

    def test_tension_escalates_every_three_turns(self, initial_state):
        state = initial_state
        action = {"action_type": "observe", "target": None, "intent": "wait",
                  "era_description": "Corvinus waits."}
        for _ in range(3):
            state = apply_action(state, action)
        assert state.turn == 3
        loc = get_player_location(state)
        assert loc.political_tension == "critical"

    def test_handles_missing_action_fields_gracefully(self, initial_state):
        new = apply_action(initial_state, {})
        assert new.turn == 1
        assert new.events[0].action_type == "other"

    def test_multiple_actions_accumulate_events(self, initial_state):
        state = initial_state
        for i in range(5):
            state = apply_action(state, {
                "action_type": "observe",
                "target": None,
                "intent": f"action {i}",
                "era_description": f"Turn {i + 1} event.",
            })
        assert state.turn == 5
        assert len(state.events) == 5


class TestNpcImpacts:
    def test_positive_impact_shifts_disposition(self, initial_state):
        action = {
            "action_type": "trade",
            "target": "Lucius Gallus",
            "intent": "supply grain",
            "era_description": "Corvinus supplies grain.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "positive", "reason": "grain supply"},
            ],
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "cautious"

    def test_negative_impact_shifts_disposition(self, initial_state):
        action = {
            "action_type": "trade",
            "target": "warehouses",
            "intent": "hoard grain",
            "era_description": "Corvinus hoards grain.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "negative", "reason": "hoarding"},
                {"name": "Deacon Paulus", "sentiment": "negative", "reason": "profiteering"},
            ],
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        paulus = next(n for n in new.npcs if n.id == "deacon_paulus")
        assert gallus.disposition == "hostile"
        assert paulus.disposition == "suspicious"

    def test_neutral_impact_does_not_shift(self, initial_state):
        action = {
            "action_type": "observe",
            "target": None,
            "intent": "watch harbor",
            "era_description": "Corvinus watches.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "neutral", "reason": "irrelevant"},
            ],
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "grim"

    def test_falls_back_to_target_matching_without_impacts(self, initial_state):
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "talk",
            "era_description": "Corvinus speaks.",
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "cautious"

    def test_ignores_malformed_impacts(self, initial_state):
        action = {
            "action_type": "observe",
            "target": None,
            "intent": "watch",
            "era_description": "Corvinus watches.",
            "npc_impacts": ["bad", None, 42, {"no_name": True}],
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "grim"


class TestNpcMemory:
    def test_interaction_increases_memory(self, initial_state):
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "talk",
            "era_description": "Corvinus speaks to Gallus.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "positive", "reason": "talk"},
            ],
        }
        before = next(n for n in initial_state.npcs if n.id == "centurion_gallus")
        new = apply_action(initial_state, action)
        after = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert after.memory_of_player > before.memory_of_player

    def test_nearby_npcs_get_passive_memory_bump(self, initial_state):
        action = {
            "action_type": "observe",
            "target": None,
            "intent": "watch",
            "era_description": "Corvinus watches the harbor.",
        }
        before_paulus = next(n for n in initial_state.npcs if n.id == "deacon_paulus")
        new = apply_action(initial_state, action)
        after_paulus = next(n for n in new.npcs if n.id == "deacon_paulus")
        assert after_paulus.memory_of_player >= before_paulus.memory_of_player

    def test_memory_capped_at_one(self, initial_state):
        state = initial_state
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "talk",
            "era_description": "Corvinus speaks.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "positive", "reason": "talk"},
            ],
        }
        for _ in range(20):
            state = apply_action(state, action)
        gallus = next(n for n in state.npcs if n.id == "centurion_gallus")
        assert gallus.memory_of_player <= 1.0


class TestDispositionShifts:
    def test_grim_to_cautious(self):
        assert _shift_positive("grim") == "cautious"

    def test_fervent_to_engaged(self):
        assert _shift_positive("fervent") == "engaged"

    def test_hostile_to_wary(self):
        assert _shift_positive("hostile") == "wary"

    def test_cautious_to_warming(self):
        assert _shift_positive("cautious") == "warming"

    def test_unknown_positive_stays_same(self):
        assert _shift_positive("confused") == "confused"

    def test_warming_to_cautious_negative(self):
        assert _shift_negative("warming") == "cautious"

    def test_grim_to_hostile_negative(self):
        assert _shift_negative("grim") == "hostile"

    def test_fervent_to_suspicious_negative(self):
        assert _shift_negative("fervent") == "suspicious"

    def test_unknown_negative_stays_same(self):
        assert _shift_negative("confused") == "confused"


class TestWorldStateSerialization:
    def test_round_trips_through_json(self, initial_state):
        dumped = initial_state.model_dump()
        restored = WorldState(**dumped)
        assert restored == initial_state

    def test_dump_includes_all_fields(self, initial_state):
        d = initial_state.model_dump()
        for field in ("era", "player", "npcs", "locations", "events", "turn",
                      "run_id", "run_status", "current_year"):
            assert field in d, f"Missing field: {field}"


class TestStorySummary:
    def test_empty_state_says_just_begun(self, initial_state):
        summary = build_story_summary(initial_state)
        assert "just begun" in summary.lower()

    def test_includes_events_after_action(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "Turn 1" in summary
        assert "Corvinus" in summary

    def test_includes_tension(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "tension" in summary.lower()

    def test_includes_year(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "410" in summary
