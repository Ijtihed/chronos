"""Tests for action_parser — normalization of LLM action_type drift.

Offline only: mocks the LLM, never hits Ollama.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.action_parser import ALIASES, normalize_action_type, parse_action
from backend.world_state import create_initial_state


class TestNormalizeActionType:
    """Unit tests for the ALIASES lookup + passthrough logic."""

    def test_alias_inquiry_to_speak(self):
        assert normalize_action_type("inquiry") == "speak"

    def test_alias_barter_to_trade(self):
        assert normalize_action_type("barter") == "trade"

    def test_alias_rescue_to_save(self):
        assert normalize_action_type("rescue") == "save"

    def test_case_insensitive_uppercase(self):
        assert normalize_action_type("INQUIRY") == "speak"

    def test_case_insensitive_mixed(self):
        assert normalize_action_type("Barter") == "trade"

    def test_passthrough_unknown(self):
        result = normalize_action_type("meditate")
        assert result == "meditate"

    def test_canonical_value_unchanged(self):
        assert normalize_action_type("speak") == "speak"
        assert normalize_action_type("trade") == "trade"
        assert normalize_action_type("other") == "other"

    def test_whitespace_stripped(self):
        assert normalize_action_type("  inquiry  ") == "speak"


class TestAliasesIntegrity:
    """Verify ALIASES dict structural invariants."""

    def test_all_values_are_lowercase(self):
        for alias, canonical in ALIASES.items():
            assert canonical == canonical.lower(), f"value {canonical!r} not lowercase"

    def test_all_keys_are_lowercase(self):
        for alias in ALIASES:
            assert alias == alias.lower(), f"key {alias!r} not lowercase"

    def test_no_alias_maps_to_itself(self):
        for alias, canonical in ALIASES.items():
            assert alias != canonical, f"{alias!r} maps to itself"


class TestParseActionNormalization:
    """Integration: verify normalization is applied after the LLM call."""

    @pytest.mark.asyncio
    async def test_llm_drift_normalized_in_parse_action(self):
        state = create_initial_state()
        llm_response = json.dumps({
            "action_type": "inquiry",
            "target": "Lucius Gallus",
            "intent": "ask about the garrison",
            "era_description": "Corvinus asks the centurion about his troops.",
            "is_travel": False,
            "destination": None,
            "is_inaction": False,
            "significance_score": 0.2,
            "npc_impacts": [],
        })
        with patch(
            "backend.action_parser.call_llm",
            new_callable=AsyncMock,
            return_value=(llm_response, None),
        ):
            result = await parse_action("ask Gallus about the garrison", state)
        assert result["action_type"] == "speak"

    @pytest.mark.asyncio
    async def test_canonical_value_survives_parse_action(self):
        state = create_initial_state()
        llm_response = json.dumps({
            "action_type": "trade",
            "target": "Lucius Gallus",
            "intent": "trade grain",
            "era_description": "Corvinus offers grain.",
            "is_travel": False,
            "destination": None,
            "is_inaction": False,
            "significance_score": 0.3,
            "npc_impacts": [],
        })
        with patch(
            "backend.action_parser.call_llm",
            new_callable=AsyncMock,
            return_value=(llm_response, None),
        ):
            result = await parse_action("trade grain with Gallus", state)
        assert result["action_type"] == "trade"
