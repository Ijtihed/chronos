"""Unit tests for world state: models, initial state, mutation, and story summary.

These run without Ollama — pure Python, no LLM calls.
"""

from backend.world_state import (
    TENSION_LEVELS,
    WorldState,
    _shift_negative,
    _shift_positive,
    apply_action,
    build_story_summary,
    create_initial_state,
)


class TestInitialState:
    def test_creates_valid_world_state(self, initial_state: WorldState):
        assert isinstance(initial_state, WorldState)

    def test_era_is_roman_late_empire(self, initial_state: WorldState):
        assert initial_state.era.name == "Roman Late Empire"
        assert initial_state.era.year == 410

    def test_player_exists(self, initial_state: WorldState):
        assert initial_state.player.name == "Marcus Aurelius Corvinus"
        assert initial_state.player.role == "Grain merchant"
        assert initial_state.player.location == "Ariminum"

    def test_has_at_least_one_npc(self, initial_state: WorldState):
        assert len(initial_state.npcs) >= 1

    def test_npcs_have_distinct_roles(self, initial_state: WorldState):
        roles = [npc.role for npc in initial_state.npcs]
        assert len(roles) == len(set(roles)), "NPC roles should be unique"

    def test_npcs_have_relationship_to_player(self, initial_state: WorldState):
        for npc in initial_state.npcs:
            assert npc.relationship_to_player, f"{npc.name} missing relationship"

    def test_location_is_ariminum(self, initial_state: WorldState):
        assert initial_state.location.name == "Ariminum"
        assert initial_state.location.political_tension in TENSION_LEVELS

    def test_starts_at_turn_zero(self, initial_state: WorldState):
        assert initial_state.turn == 0
        assert initial_state.events == []


class TestApplyAction:
    def test_increments_turn(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.turn == 1

    def test_appends_event(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert len(new.events) == 1
        assert new.events[0].turn == 1
        assert new.events[0].action_type == "speak"
        assert new.events[0].target == "Lucius Gallus"

    def test_does_not_mutate_original(self, initial_state, sample_parsed_action):
        apply_action(initial_state, sample_parsed_action)
        assert initial_state.turn == 0
        assert initial_state.events == []

    def test_speak_shifts_targeted_npc_disposition(self, initial_state):
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "talk",
            "era_description": "Corvinus speaks to Gallus.",
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition != "grim", "Speaking should shift disposition"
        assert gallus.disposition == "cautious"

    def test_speak_does_not_shift_untargeted_npc(self, initial_state):
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "talk",
            "era_description": "Corvinus speaks to Gallus.",
        }
        new = apply_action(initial_state, action)
        paulus = next(n for n in new.npcs if n.id == "deacon_paulus")
        assert paulus.disposition == "fervent", "Untargeted NPC should not shift"

    def test_observe_does_not_shift_disposition(self, initial_state):
        action = {
            "action_type": "observe",
            "target": "Lucius Gallus",
            "intent": "watch",
            "era_description": "Corvinus watches Gallus.",
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "grim"

    def test_tension_escalates_every_three_turns(self, initial_state):
        state = initial_state
        action = {"action_type": "observe", "target": None, "intent": "wait",
                  "era_description": "Corvinus waits."}
        for _ in range(3):
            state = apply_action(state, action)
        assert state.turn == 3
        assert state.location.political_tension == "critical"

    def test_tension_does_not_exceed_critical(self, initial_state):
        state = initial_state
        action = {"action_type": "observe", "target": None, "intent": "wait",
                  "era_description": "Corvinus waits."}
        for _ in range(9):
            state = apply_action(state, action)
        assert state.location.political_tension == "critical"

    def test_handles_missing_action_fields_gracefully(self, initial_state):
        new = apply_action(initial_state, {})
        assert new.turn == 1
        assert new.events[0].action_type == "other"
        assert new.events[0].description == "Something happened."

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

    def test_threaten_makes_npc_hostile(self, initial_state):
        action = {
            "action_type": "threaten",
            "target": "Lucius Gallus",
            "intent": "intimidate",
            "era_description": "Corvinus threatens Gallus.",
        }
        new = apply_action(initial_state, action)
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert gallus.disposition == "hostile"


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

    def test_mixed_impacts_affect_different_npcs(self, initial_state):
        action = {
            "action_type": "petition",
            "target": "Deacon Paulus",
            "intent": "donate grain to refugees",
            "era_description": "Corvinus donates grain.",
            "npc_impacts": [
                {"name": "Deacon Paulus", "sentiment": "positive", "reason": "charity"},
                {"name": "Lucius Gallus", "sentiment": "negative", "reason": "less grain for garrison"},
            ],
        }
        new = apply_action(initial_state, action)
        paulus = next(n for n in new.npcs if n.id == "deacon_paulus")
        gallus = next(n for n in new.npcs if n.id == "centurion_gallus")
        assert paulus.disposition == "engaged"
        assert gallus.disposition == "hostile"

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

    def test_cautious_to_wary_negative(self):
        assert _shift_negative("cautious") == "wary"

    def test_wary_to_hostile_negative(self):
        assert _shift_negative("wary") == "hostile"

    def test_grim_to_hostile_negative(self):
        assert _shift_negative("grim") == "hostile"

    def test_fervent_to_suspicious_negative(self):
        assert _shift_negative("fervent") == "suspicious"

    def test_engaged_to_wary_negative(self):
        assert _shift_negative("engaged") == "wary"

    def test_unknown_negative_stays_same(self):
        assert _shift_negative("confused") == "confused"


class TestWorldStateSerialization:
    def test_round_trips_through_json(self, initial_state):
        dumped = initial_state.model_dump()
        restored = WorldState(**dumped)
        assert restored == initial_state

    def test_dump_includes_all_fields(self, initial_state):
        d = initial_state.model_dump()
        assert "era" in d
        assert "player" in d
        assert "npcs" in d
        assert "location" in d
        assert "events" in d
        assert "turn" in d


class TestStorySummary:
    def test_empty_state_says_just_begun(self, initial_state):
        summary = build_story_summary(initial_state)
        assert "just begun" in summary.lower()

    def test_includes_events_after_action(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "Turn 1" in summary
        assert "Corvinus" in summary

    def test_includes_npc_dispositions(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "Lucius Gallus" in summary
        assert "Deacon Paulus" in summary

    def test_includes_tension(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "tension" in summary.lower()

    def test_accumulates_across_turns(self, initial_state):
        state = initial_state
        for i in range(3):
            state = apply_action(state, {
                "action_type": "observe",
                "target": None,
                "intent": f"action {i}",
                "era_description": f"Event number {i + 1} happened.",
            })
        summary = build_story_summary(state)
        assert "Turn 1" in summary
        assert "Turn 2" in summary
        assert "Turn 3" in summary
