"""Tests for LLM response schemas — validation, defaults, and leak detection."""

import json

import pytest
from pydantic import ValidationError

from backend.llm_schemas import (
    ActionParserResponse,
    AutonomousActionResponse,
    CharacterGenResponse,
    DeathCheckResponse,
    GroundContextResponse,
    NPCPOVResponse,
    NpcImpact,
    action_parser_default,
    autonomous_action_default,
    character_gen_default,
    leaks_raw_numbers,
    scrub_leaked_numbers,
    DEATH_CHECK_SAFE,
)


class TestActionParserResponse:
    def test_valid_input(self):
        data = {
            "action_type": "negotiate",
            "target": "Lucius Gallus",
            "intent": "forge alliance",
            "era_description": "Corvinus approaches the centurion.",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "positive", "reason": "direct"},
            ],
            "is_travel": False,
            "destination": None,
            "is_inaction": False,
        }
        parsed = ActionParserResponse.model_validate(data)
        assert parsed.action_type == "negotiate"
        assert len(parsed.npc_impacts) == 1
        assert parsed.npc_impacts[0].name == "Lucius Gallus"

    def test_missing_fields_get_defaults(self):
        parsed = ActionParserResponse.model_validate({"intent": "do something"})
        assert parsed.action_type == "other"
        assert parsed.is_travel is False
        assert parsed.npc_impacts == []

    def test_malformed_npc_impacts_handled(self):
        data = {
            "action_type": "speak",
            "npc_impacts": ["garbage", None, 42, {"name": "Gallus"}],
        }
        parsed = ActionParserResponse.model_validate(data)
        assert len(parsed.npc_impacts) == 1
        assert parsed.npc_impacts[0].name == "Gallus"

    def test_empty_action_type_becomes_other(self):
        parsed = ActionParserResponse.model_validate({"action_type": ""})
        assert parsed.action_type == "other"

    def test_action_type_normalized_lowercase(self):
        parsed = ActionParserResponse.model_validate({"action_type": "  TRADE  "})
        assert parsed.action_type == "trade"

    def test_default_factory(self):
        d = action_parser_default("hello", "Marcus", "Ariminum")
        assert d.intent == "hello"
        assert "Marcus" in d.era_description

    def test_round_trip(self):
        original = ActionParserResponse(
            action_type="speak", target="Gallus", intent="talk",
            era_description="Talks.", is_travel=False,
        )
        dumped = original.model_dump()
        restored = ActionParserResponse.model_validate(dumped)
        assert restored == original


class TestAutonomousActionResponse:
    def test_valid_input(self):
        data = {
            "action": "Gallus drills his men.",
            "interacts_with": "Deacon Paulus",
            "mood_shift": "grim",
            "wants_to_travel": True,
            "travel_destination": "ravenna",
        }
        parsed = AutonomousActionResponse.model_validate(data)
        assert parsed.action == "Gallus drills his men."
        assert parsed.wants_to_travel is True

    def test_missing_fields_get_defaults(self):
        parsed = AutonomousActionResponse.model_validate({"action": "Rests."})
        assert parsed.interacts_with is None
        assert parsed.wants_to_travel is False

    def test_string_bool_coercion(self):
        parsed = AutonomousActionResponse.model_validate(
            {"action": "Acts.", "wants_to_travel": "true"}
        )
        assert parsed.wants_to_travel is True

    def test_default_factory(self):
        d = autonomous_action_default("Gallus")
        assert "Gallus" in d.action


class TestDeathCheckResponse:
    def test_valid_input(self):
        data = {"could_die": True, "death_risk": 0.8, "cause": "Arrow to the heart."}
        parsed = DeathCheckResponse.model_validate(data)
        assert parsed.could_die is True
        assert parsed.death_risk == 0.8

    def test_risk_clamped_to_range(self):
        parsed = DeathCheckResponse.model_validate({"death_risk": 5.0})
        assert parsed.death_risk == 1.0

        parsed = DeathCheckResponse.model_validate({"death_risk": -2.0})
        assert parsed.death_risk == 0.0

    def test_non_numeric_risk_defaults_to_zero(self):
        parsed = DeathCheckResponse.model_validate({"death_risk": "high"})
        assert parsed.death_risk == 0.0

    def test_string_bool_coercion(self):
        parsed = DeathCheckResponse.model_validate({"could_die": "yes"})
        assert parsed.could_die is True

    def test_safe_default(self):
        assert DEATH_CHECK_SAFE.could_die is False
        assert DEATH_CHECK_SAFE.death_risk == 0.0

    def test_empty_input_is_safe(self):
        parsed = DeathCheckResponse.model_validate({})
        assert parsed.could_die is False
        assert parsed.death_risk == 0.0


class TestCharacterGenResponse:
    def test_valid_input(self):
        data = {
            "name": "Gallus",
            "description": "A centurion.",
            "disposition": "grim",
            "relationship_to_player": "Professional.",
        }
        parsed = CharacterGenResponse.model_validate(data)
        assert parsed.name == "Gallus"

    def test_defaults(self):
        parsed = CharacterGenResponse.model_validate({})
        assert parsed.disposition == "cautious"

    def test_default_factory_player(self):
        d = character_gen_default("merchant", "Ariminum")
        assert d.name == "Unknown Wanderer"
        assert d.disposition == "anxious"

    def test_default_factory_npc(self):
        d = character_gen_default("soldier", "Ravenna", index=3)
        assert d.name == "NPC 3"
        assert d.disposition == "cautious"


class TestNPCPOVResponse:
    def test_can_construct(self):
        r = NPCPOVResponse(
            npc_id="gallus", perspective="I watch.", emotional_state="wary",
            information_known=["siege"], information_unknown=["fleet"],
        )
        assert r.perspective == "I watch."


class TestGroundContextResponse:
    def test_can_construct(self):
        r = GroundContextResponse(
            era_feel="Tense.", what_character_knows="The walls hold.",
            local_rumors=["Ships leaving."], material_conditions="Food scarce.",
        )
        assert len(r.local_rumors) == 1


class TestLeaksRawNumbers:
    def test_detects_decimal_values(self):
        assert leaks_raw_numbers("memory_of_player is 0.35") is True

    def test_detects_percentage(self):
        assert leaks_raw_numbers("Political tension at 85%") is True

    def test_detects_score_pattern(self):
        assert leaks_raw_numbers("score: 7 out of 10") is True

    def test_detects_memory_leak(self):
        assert leaks_raw_numbers("The memory_of_player value dropped.") is True

    def test_allows_year_numbers(self):
        assert leaks_raw_numbers("It is 410 AD, and the empire crumbles.") is False

    def test_allows_age_numbers(self):
        assert leaks_raw_numbers("He is aged 45 and tired.") is False

    def test_allows_duration_numbers(self):
        assert leaks_raw_numbers("The siege has lasted 3 weeks.") is False

    def test_allows_turn_reference(self):
        assert leaks_raw_numbers("By turn 5, the walls were breached.") is False

    def test_clean_narrative_passes(self):
        text = (
            "The centurion cursed under his breath. Three weeks of this. "
            "The garrison at Ariminum held, but supplies dwindled."
        )
        assert leaks_raw_numbers(text) is False


class TestScrubLeakedNumbers:
    def test_scrubs_memory_reference(self):
        text = "He has memory_of_player: 0.45 and is wary."
        result = scrub_leaked_numbers(text)
        assert "memory_of_player" not in result
        assert "0.45" not in result

    def test_scrubs_score_pattern(self):
        text = "His loyalty score: 7 is concerning."
        result = scrub_leaked_numbers(text)
        assert "score: 7" not in result

    def test_preserves_clean_text(self):
        text = "The garrison holds. Three weeks remain."
        assert scrub_leaked_numbers(text) == text
