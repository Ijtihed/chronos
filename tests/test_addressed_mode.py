"""Tests for Change 1 -- Addressed-mode NPC POV.

Covers:
  - _split_addressed: target found at location, target elsewhere,
    target nonexistent, no target
  - NPCAddressedResponse schema: optional internal field, empty string coercion
  - generate_npc_addressed: prompt contains player_action_description,
    speech vs non-speech distinction
  - npc_addressed.md prompt template: all placeholders fill
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.llm_schemas import NPCAddressedResponse
from backend.world_state import NPC, NpcNeeds, PersonalityTraits, create_initial_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_npc(location="test_loc", **kwargs) -> NPC:
    defaults = dict(
        id="npc_test_0",
        name="Helena",
        role="merchant",
        archetype="merchant",
        social_class="commoner",
        location=location,
        description="A sharp trader.",
        disposition="cautious",
        relationship_to_player="Stranger",
        memory_of_player=0.0,
        personality=PersonalityTraits(),
        needs=NpcNeeds(),
        current_preoccupation="the trade routes closing",
    )
    defaults.update(kwargs)
    return NPC(**defaults)


# ---------------------------------------------------------------------------
# NPCAddressedResponse schema
# ---------------------------------------------------------------------------

class TestNPCAddressedResponseSchema:
    def test_full_valid_response(self):
        r = NPCAddressedResponse.model_validate({
            "reply": "Three times now. What do you want?",
            "internal": "Desperate or stupid.",
            "emotional_state": "wary",
        })
        assert r.reply == "Three times now. What do you want?"
        assert r.internal == "Desperate or stupid."
        assert r.emotional_state == "wary"

    def test_missing_internal_is_none(self):
        r = NPCAddressedResponse.model_validate({
            "reply": "I have nothing to say.",
            "emotional_state": "dismissive",
        })
        assert r.internal is None

    def test_empty_string_internal_coerced_to_none(self):
        r = NPCAddressedResponse.model_validate({
            "reply": "Get out.",
            "internal": "",
            "emotional_state": "hostile",
        })
        assert r.internal is None

    def test_whitespace_only_internal_coerced_to_none(self):
        r = NPCAddressedResponse.model_validate({
            "reply": "Fine.",
            "internal": "   ",
            "emotional_state": "neutral",
        })
        assert r.internal is None

    def test_null_internal_stays_none(self):
        r = NPCAddressedResponse.model_validate({
            "reply": "Yes.",
            "internal": None,
            "emotional_state": "calm",
        })
        assert r.internal is None


# ---------------------------------------------------------------------------
# _split_addressed routing logic
# ---------------------------------------------------------------------------

class TestSplitAddressed:
    def _make_state_with_npc(self, npc_location=None):
        state = create_initial_state()
        player_loc = state.player.location
        npc = _make_npc(location=npc_location or player_loc, name="Helena")
        state.npcs = [npc]
        return state, npc, player_loc

    def test_target_at_player_location_is_addressed(self):
        from backend.main import _split_addressed
        state, npc, player_loc = self._make_state_with_npc()
        parsed = {"target": "Helena", "action_type": "speak"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is npc
        assert ambient == []

    def test_target_elsewhere_is_not_addressed(self):
        from backend.main import _split_addressed
        state, npc, _ = self._make_state_with_npc(npc_location="ravenna")
        parsed = {"target": "Helena", "action_type": "speak"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is None
        assert npc in ambient

    def test_no_target_returns_all_ambient(self):
        from backend.main import _split_addressed
        state, npc, _ = self._make_state_with_npc()
        parsed = {"target": None, "action_type": "other"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is None
        assert npc in ambient

    def test_empty_target_string_returns_all_ambient(self):
        from backend.main import _split_addressed
        state, npc, _ = self._make_state_with_npc()
        parsed = {"target": "", "action_type": "speak"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is None

    def test_partial_name_match(self):
        from backend.main import _split_addressed
        state, npc, _ = self._make_state_with_npc()
        # "hel" matches "Helena"
        parsed = {"target": "hel", "action_type": "speak"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is npc

    def test_nonexistent_target_returns_all_ambient(self):
        from backend.main import _split_addressed
        state, npc, _ = self._make_state_with_npc()
        parsed = {"target": "nobody_named_this", "action_type": "speak"}
        addressed, ambient = _split_addressed([npc], parsed, state)
        assert addressed is None
        assert npc in ambient


# ---------------------------------------------------------------------------
# generate_npc_addressed -- prompt content checks
# ---------------------------------------------------------------------------

class TestGenerateNpcAddressed:
    @pytest.mark.asyncio
    async def test_speech_act_uses_said_to_you_format(self):
        from backend.npc_engine import generate_npc_addressed
        state = create_initial_state()
        npc = state.npcs[0]
        action = {"action_type": "speak", "intent": "asking about boats", "era_description": "..."}
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"reply": "No boats.", "internal": null, "emotional_state": "curt"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_addressed(npc, action, state, player_input="Can you help me with boats?")

        assert captured
        assert 'said to you directly' in captured[0]
        assert 'Can you help me with boats?' in captured[0]

    @pytest.mark.asyncio
    async def test_non_speech_act_uses_action_format(self):
        from backend.npc_engine import generate_npc_addressed
        state = create_initial_state()
        npc = state.npcs[0]
        action = {
            "action_type": "attack",
            "intent": "striking the guard",
            "era_description": "The player lunges at the guard.",
        }
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"reply": "You dare!", "internal": null, "emotional_state": "hostile"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_addressed(npc, action, state, player_input="I attack the guard")

        assert captured
        # Should NOT use "said to you directly"
        assert 'said to you directly' not in captured[0]
        # Should use era_description
        assert 'lunges at the guard' in captured[0]

    @pytest.mark.asyncio
    async def test_returns_dict_with_reply_and_internal(self):
        from backend.npc_engine import generate_npc_addressed
        state = create_initial_state()
        npc = state.npcs[0]
        action = {"action_type": "speak", "intent": "greeting"}

        async def mock_llm(prompt, **kw):
            return (
                '{"reply": "What do you want?", "internal": "Not this again.", "emotional_state": "wary"}',
                0.0,
            )

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(npc, action, state, player_input="Hello")

        assert result["reply"] == "What do you want?"
        assert result["internal"] == "Not this again."
        assert result["emotional_state"] == "wary"

    @pytest.mark.asyncio
    async def test_handles_missing_internal_gracefully(self):
        from backend.npc_engine import generate_npc_addressed
        state = create_initial_state()
        npc = state.npcs[0]
        action = {"action_type": "speak", "intent": "greeting"}

        async def mock_llm(prompt, **kw):
            return ('{"reply": "Go away.", "emotional_state": "dismissive"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(npc, action, state)

        assert result["reply"] == "Go away."
        assert result["internal"] is None

    @pytest.mark.asyncio
    async def test_current_preoccupation_in_prompt(self):
        from backend.npc_engine import generate_npc_addressed
        state = create_initial_state()
        npc = state.npcs[0]
        npc.current_preoccupation = "my outstanding debts"
        action = {"action_type": "speak", "intent": "test"}
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"reply": "Yes.", "internal": null, "emotional_state": "neutral"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_addressed(npc, action, state)

        assert captured
        assert "my outstanding debts" in captured[0]


# ---------------------------------------------------------------------------
# npc_addressed.md -- all placeholders fill
# ---------------------------------------------------------------------------

class TestNpcAddressedPrompt:
    def test_all_placeholders_fill(self):
        from pathlib import Path
        from string import Template
        from backend.llm_provider import load_prompt
        from backend.world_state import build_story_summary, get_player_location

        PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
        raw = load_prompt(PROMPTS_DIR / "npc_addressed.md")
        state = create_initial_state()
        npc = state.npcs[0]
        player_loc = get_player_location(state)

        result = Template(raw).safe_substitute(
            npc_name=npc.name,
            npc_role=npc.role,
            npc_description=npc.description,
            social_class=npc.social_class or npc.archetype,
            npc_disposition=npc.disposition,
            dominant_need="duty",
            urgent_needs="nothing urgent",
            current_activity="Going about their day.",
            current_preoccupation="the trade routes closing",
            relationship_to_player=npc.relationship_to_player,
            player_actions_toward_you="None -- first contact.",
            memory_level="faint",
            player_name=state.player.name,
            era_description=state.era.description,
            era_feel="The city holds its breath.",
            material_conditions="Grain is scarce.",
            what_character_knows="What anyone would know.",
            local_rumors="Nothing specific.",
            location_name=player_loc.name,
            year=state.current_year or state.era.year_start,
            story_so_far=build_story_summary(state),
            historical_context="No sources available.",
            player_action_description='said to you directly: "Can you help me?"',
            this_turn_events="Nothing notable.",
            already_used_details="",
        )
        assert "$" not in result, f"Unfilled placeholders: {result}"


# ---------------------------------------------------------------------------
# JSON contract -- Addressed-mode response shapes Gemini returns in practice
#
# Gemini's JSON-mode output is mostly stable but the `internal` field
# specifically has shown three observed patterns: present-with-value, present-
# but-empty (""), and entirely absent. The schema and frontend BOTH have to
# render these correctly. These tests pin the contract so a future schema
# loosening or prompt rewrite can't break the addressed-mode flow silently.
# ---------------------------------------------------------------------------

class TestAddressedJSONContract:
    """End-to-end contract tests for the four JSON shapes Gemini returns."""

    def _state_and_npc(self):
        state = create_initial_state()
        return state, state.npcs[0]

    def _mock_llm(self, raw_response: str):
        async def _llm(prompt, **kw):
            return (raw_response, 0.0)
        return _llm

    @pytest.mark.asyncio
    async def test_addressed_response_with_internal_field(self):
        """Standard case: reply + non-empty internal + emotional_state."""
        from backend.npc_engine import generate_npc_addressed

        state, npc = self._state_and_npc()
        action = {"action_type": "speak", "intent": "asks about ships"}
        raw = (
            '{"reply": "No ships today.", '
            '"internal": "He keeps coming back. Why?", '
            '"emotional_state": "wary"}'
        )

        with patch("backend.npc_engine.call_llm", side_effect=self._mock_llm(raw)):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(
                    npc, action, state, player_input="Are there boats?"
                )

        assert result["reply"] == "No ships today."
        assert result["internal"] == "He keeps coming back. Why?"
        assert result["emotional_state"] == "wary"

    @pytest.mark.asyncio
    async def test_addressed_response_with_null_internal(self):
        """JSON null for internal -- schema validator coerces to None."""
        from backend.npc_engine import generate_npc_addressed

        state, npc = self._state_and_npc()
        action = {"action_type": "speak", "intent": "asks about debt"}
        raw = '{"reply": "Pay me.", "internal": null, "emotional_state": "curt"}'

        with patch("backend.npc_engine.call_llm", side_effect=self._mock_llm(raw)):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(
                    npc, action, state, player_input="When can I pay you?"
                )

        assert result["reply"] == "Pay me."
        assert result["internal"] is None, (
            "JSON null must render as Python None for frontend conditional"
        )
        assert result["emotional_state"] == "curt"

    @pytest.mark.asyncio
    async def test_addressed_response_with_empty_internal(self):
        """Empty string for internal -- coerce_internal validator must
        normalise this to None so the frontend's truthy check works."""
        from backend.npc_engine import generate_npc_addressed

        state, npc = self._state_and_npc()
        action = {"action_type": "speak", "intent": "asks for help"}
        raw = '{"reply": "Can\'t help.", "internal": "", "emotional_state": "tired"}'

        with patch("backend.npc_engine.call_llm", side_effect=self._mock_llm(raw)):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(
                    npc, action, state, player_input="Help me?"
                )

        assert result["reply"] == "Can't help."
        assert result["internal"] is None, (
            "Empty string must coerce to None to avoid rendering an empty <p>"
        )

    @pytest.mark.asyncio
    async def test_addressed_response_with_missing_internal_field(self):
        """Field entirely absent -- Pydantic default takes over (None)."""
        from backend.npc_engine import generate_npc_addressed

        state, npc = self._state_and_npc()
        action = {"action_type": "speak", "intent": "greets"}
        raw = '{"reply": "Hello.", "emotional_state": "neutral"}'

        with patch("backend.npc_engine.call_llm", side_effect=self._mock_llm(raw)):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                result = await generate_npc_addressed(
                    npc, action, state, player_input="Hi."
                )

        assert result["reply"] == "Hello."
        assert result["internal"] is None, (
            "Missing field must default to None per NPCAddressedResponse schema"
        )
        assert result["emotional_state"] == "neutral"
