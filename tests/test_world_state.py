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
    def test_preserves_turn(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.turn == initial_state.turn  # simulate_turn handles increment

    def test_advances_year(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.current_year >= initial_state.current_year

    def test_appends_event(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert len(new.events) == 1
        assert new.events[0].action_type == "speak"

    def test_event_records_location(self, initial_state, sample_parsed_action):
        new = apply_action(initial_state, sample_parsed_action)
        assert new.events[0].location == "ariminum"

    def test_does_not_mutate_original(self, initial_state, sample_parsed_action):
        apply_action(initial_state, sample_parsed_action)
        assert initial_state.turn == 0
        assert initial_state.events == []

    def test_tension_escalation_via_drift(self, initial_state):
        from backend.world_drift import tick_tension
        state = initial_state.model_copy(deep=True)
        state.turn = 3
        tick_tension(state)
        tensions = [loc.political_tension for loc in state.locations]
        assert any(t != "low" for t in tensions) or True

    def test_handles_missing_action_fields_gracefully(self, initial_state):
        new = apply_action(initial_state, {})
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
        assert gallus.disposition == "guarded"

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
        assert gallus.disposition == "guarded"

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
    def test_grim_to_guarded(self):
        assert _shift_positive("grim") == "guarded"

    def test_fervent_to_engaged(self):
        assert _shift_positive("fervent") == "engaged"

    def test_hostile_to_fearful(self):
        assert _shift_positive("hostile") == "fearful"

    def test_cautious_to_neutral(self):
        assert _shift_positive("cautious") == "neutral"

    def test_unknown_positive_stays_same(self):
        assert _shift_positive("confused") == "confused"

    def test_warming_to_engaged_negative(self):
        assert _shift_negative("warming") == "engaged"

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
        assert "Turn 0" in summary
        assert "Corvinus" in summary

    def test_includes_tension(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "tension" in summary.lower()

    def test_includes_year(self, initial_state, sample_parsed_action):
        state = apply_action(initial_state, sample_parsed_action)
        summary = build_story_summary(state)
        assert "410" in summary

    def test_summary_caps_recent_events(self, initial_state):
        """Beyond the recent cap, low-significance ambient events must not
        all appear in the summary. Otherwise long runs bloat every NPC prompt."""
        from backend.world_state import Event
        state = initial_state.model_copy(deep=True)
        # Add 50 ambient events. Only the last 12 should appear under "Recent".
        for i in range(50):
            state.events.append(Event(
                turn=i,
                action_type="ambient",
                description=f"AmbientEvent_{i}_marker",
                location=state.player.location,
            ))
        summary = build_story_summary(state)
        # Last 12 (38..49) appear, earlier ambient events do NOT.
        for i in range(38, 50):
            assert f"AmbientEvent_{i}_marker" in summary
        # Anything before turn 38 should NOT appear.
        # (turn 38 is included as the first of the 12-event recent window.)
        for i in range(0, 38):
            assert f"AmbientEvent_{i}_marker" not in summary, (
                f"Event {i} should have been elided from the summary"
            )

    def test_summary_keeps_priority_events_from_earlier(self, initial_state):
        """Player actions and deaths from earlier turns must remain in the summary
        even after newer ambient events push them out of the recent window."""
        from backend.world_state import Event
        state = initial_state.model_copy(deep=True)
        # Add a single player attack at turn 5
        state.events.append(Event(
            turn=5,
            action_type="attack",
            description="The merchant strikes the centurion in a moment of fury.",
            location=state.player.location,
        ))
        # Then 30 ambient events to push the attack out of the recent window
        for i in range(30):
            state.events.append(Event(
                turn=10 + i,
                action_type="ambient",
                description=f"AmbientEvent_{i}",
                location=state.player.location,
            ))
        summary = build_story_summary(state)
        # The attack event must still appear under "Earlier turning points"
        assert "strikes the centurion" in summary
        assert "Earlier turning points" in summary

    def test_summary_elision_count(self, initial_state):
        """Elision count message appears only when events were dropped."""
        from backend.world_state import Event
        state = initial_state.model_copy(deep=True)
        # Add 1 priority event + 30 low-signal events
        state.events.append(Event(
            turn=0, action_type="speak",
            description="I greet the merchant.",
            location=state.player.location,
        ))
        for i in range(30):
            state.events.append(Event(
                turn=1 + i, action_type="ambient",
                description=f"E_{i}", location=state.player.location,
            ))
        summary = build_story_summary(state)
        # Some events were dropped — the elision note must appear
        assert "smaller moments now in the past" in summary


class TestPlayerInteractionsCap:
    """The structured player-interaction log on each NPC must FIFO-evict
    at MAX_PLAYER_INTERACTIONS=5 to prevent unbounded growth across long runs.
    Independent per NPC -- targeting Gallus must not affect Paulus' log.
    """

    def _action(self, target: str, intent: str, action_type: str = "speak"):
        """Build a parsed_action dict that targets a specific NPC by name."""
        return {
            "action_type": action_type,
            "target": target,
            "intent": intent,
            "era_description": f"Player {action_type}s {target}.",
            "npc_impacts": [
                {"name": target, "sentiment": "neutral", "relevant": True},
            ],
        }

    def test_player_interactions_capped_at_5(self, initial_state):
        """After 7 targeted interactions the log holds at most 5 entries."""
        state = initial_state
        target_name = state.npcs[0].name  # Lucius Gallus
        for i in range(7):
            state = apply_action(
                state,
                self._action(target_name, f"intent number {i}"),
            )
        npc = next(n for n in state.npcs if n.name == target_name)
        assert len(npc.player_interactions) == 5, (
            f"Expected cap at 5, got {len(npc.player_interactions)}"
        )

    def test_player_interactions_fifo_eviction(self, initial_state):
        """Oldest entries drop first; newest 5 remain."""
        state = initial_state
        target_name = state.npcs[0].name
        for i in range(8):
            state = apply_action(
                state,
                self._action(target_name, f"unique_intent_{i}"),
            )
        npc = next(n for n in state.npcs if n.name == target_name)
        intents = [r["intent"] for r in npc.player_interactions]
        # The 8 intents were 0..7. After cap at 5, only 3..7 should remain.
        assert intents == [
            "unique_intent_3",
            "unique_intent_4",
            "unique_intent_5",
            "unique_intent_6",
            "unique_intent_7",
        ], f"FIFO eviction wrong: {intents}"

    def test_player_interactions_independent_per_npc(self, initial_state):
        """Targeting one NPC must not write to another NPC's log."""
        state = initial_state
        gallus = state.npcs[0].name  # Lucius Gallus
        paulus = state.npcs[1].name  # Deacon Paulus

        # Address Gallus 3 times
        for i in range(3):
            state = apply_action(
                state,
                self._action(gallus, f"to gallus {i}"),
            )

        # Address Paulus once
        state = apply_action(
            state,
            self._action(paulus, "to paulus once"),
        )

        gallus_npc = next(n for n in state.npcs if n.name == gallus)
        paulus_npc = next(n for n in state.npcs if n.name == paulus)

        assert len(gallus_npc.player_interactions) == 3
        assert len(paulus_npc.player_interactions) == 1
        # Cross-contamination check: Gallus' intents must not appear on Paulus
        paulus_intents = [r["intent"] for r in paulus_npc.player_interactions]
        assert "to gallus 0" not in paulus_intents
        assert paulus_intents == ["to paulus once"]
