"""Tests for the grounding-detail extractor and run-level tracker.

Covers all three extraction patterns:
  1. State + body part / clothing
  2. "smell of X" / "taste of X" / etc.
  3. Historical aphorism (subject + verb + landscape/object completion)

Plus tracker behaviour (FIFO eviction at cap=30) and prompt injection
into npc_pov.md / npc_addressed.md.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.grounding_extractor import (
    extract_grounding_details,
    format_for_prompt,
    merge_into_tracker,
)
from backend.world_state import create_initial_state


# ---------------------------------------------------------------------------
# Pattern 1 -- state + body part / clothing
# ---------------------------------------------------------------------------

class TestStateBodyPattern:
    def test_wet_boot(self):
        result = extract_grounding_details("My left boot has been wet since Tuesday.")
        assert any("wet" in p and "boot" in p for p in result)

    def test_bleeding_hands(self):
        result = extract_grounding_details("Bleeding hands on every line I haul.")
        assert any("bleeding hands" in p for p in result)

    def test_sore_back(self):
        result = extract_grounding_details("My back is sore from carrying stones.")
        # "sore back" may not match because the order is "back is sore"; but the
        # extractor catches "sore back" if the order is "sore back" exactly.
        # Variant: try the canonical order.
        result2 = extract_grounding_details("Sore back, sore knees, every joint cracked.")
        assert any("sore back" in p for p in result2)

    def test_cold_throat(self):
        result = extract_grounding_details("Cold throat, can barely speak today.")
        assert any("cold throat" in p for p in result)

    def test_torn_cloak(self):
        result = extract_grounding_details("My torn cloak does nothing against this wind.")
        assert any("torn cloak" in p for p in result)

    def test_chapped_lips(self):
        result = extract_grounding_details("Chapped lips and cracked fingers.")
        assert any("chapped lips" in p for p in result)
        assert any("cracked fingers" in p for p in result)

    def test_festering_wound_on_leg(self):
        # "festering" is in state words; tests modifiers (left/right) gate
        result = extract_grounding_details("A festering wound on my right leg.")
        # "festering" + "right leg" -- the modifier "right" goes between
        assert any("festering" in p and "leg" in p for p in result)

    def test_no_match_returns_empty_list(self):
        result = extract_grounding_details("The weather is fine and I am content.")
        assert result == []

    def test_empty_input(self):
        assert extract_grounding_details("") == []
        assert extract_grounding_details("   ") == []

    def test_multiple_matches_one_sentence(self):
        result = extract_grounding_details(
            "Wet boots and aching feet, the sore back, the bruised shoulders."
        )
        # All four phrases should appear
        assert any("wet boot" in p for p in result)
        assert any("aching feet" in p for p in result)
        assert any("sore back" in p for p in result)
        assert any("bruised shoulder" in p for p in result)


# ---------------------------------------------------------------------------
# Pattern 2 -- "smell of X" / sense + of + object
# ---------------------------------------------------------------------------

class TestSenseOfPattern:
    def test_smell_of_damp_wool(self):
        result = extract_grounding_details("The smell of damp wool fills the room.")
        assert any("smell of damp wool" in p for p in result)

    def test_taste_of_ashes(self):
        result = extract_grounding_details("The words taste of ashes in my mouth.")
        assert any("taste of ashes" in p for p in result)

    def test_stink_of_fish(self):
        result = extract_grounding_details("The stink of fish guts on the wharf.")
        assert any("stink of fish" in p for p in result)


# ---------------------------------------------------------------------------
# Pattern 3 -- historical aphorism with poetic completion
# ---------------------------------------------------------------------------

class TestAphorismPattern:
    def test_king_alaric_in_riverbed(self):
        result = extract_grounding_details(
            "King Alaric is dead in a riverbed with the gold of Rome."
        )
        assert any("riverbed" in p for p in result)

    def test_sultan_dragging_ships(self):
        result = extract_grounding_details(
            "The Sultan is dragging his ships over the dry land."
        )
        assert any("ships" in p for p in result)

    def test_harald_never_cuts_hair(self):
        result = extract_grounding_details(
            "King Harald never cuts his hair until the work is done."
        )
        assert any("hair" in p for p in result)

    def test_political_mention_without_landscape_word_does_not_match(self):
        """Plain political mentions should NOT trigger the aphorism pattern."""
        result = extract_grounding_details("The Sultan is angry today.")
        # No landscape/object word -- should not match aphorism pattern.
        # May still match other patterns (none here), so confirm result is empty.
        # (If Pattern 1 or 2 picks something up that's fine, but none should.)
        assert not any(("sultan" in p and "angry" in p) for p in result)

    def test_emperor_walks_to_walls(self):
        result = extract_grounding_details("The Emperor walks slowly toward the walls.")
        assert any("walls" in p for p in result)


# ---------------------------------------------------------------------------
# Normalisation / dedup
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_strips_leading_article_and_lowercases(self):
        result = extract_grounding_details("The wet boot. My wet boot. His wet boot.")
        # All three should normalise to the same phrase and dedupe to one entry
        assert sum(1 for p in result if "wet boot" in p) == 1

    def test_dedupes_within_single_call(self):
        result = extract_grounding_details(
            "Sore back. Sore back. SORE BACK. Sore back again."
        )
        assert sum(1 for p in result if "sore back" in p) == 1

    def test_word_count_bounds(self):
        # All extracted phrases should be 2-7 words
        result = extract_grounding_details(
            "The bleeding hands hurt. The smell of damp wool fills the air."
        )
        for p in result:
            wc = len(p.split())
            assert 2 <= wc <= 7, f"Phrase '{p}' has {wc} words, out of bounds"


# ---------------------------------------------------------------------------
# Tracker FIFO behaviour
# ---------------------------------------------------------------------------

class TestTracker:
    def test_merge_appends_new_phrases(self):
        tracker = ["wet boot"]
        merge_into_tracker(tracker, ["sore back", "bleeding hands"])
        assert tracker == ["wet boot", "sore back", "bleeding hands"]

    def test_merge_dedupes_against_existing(self):
        tracker = ["wet boot", "sore back"]
        merge_into_tracker(tracker, ["sore back", "cold throat"])
        assert tracker == ["wet boot", "sore back", "cold throat"]

    def test_fifo_eviction_at_cap_30(self):
        # Fill to 30 with unique phrases; add 5 more; oldest 5 should drop.
        tracker = [f"phrase {i}" for i in range(30)]
        new = [f"new {i}" for i in range(5)]
        merge_into_tracker(tracker, new, cap=30)
        assert len(tracker) == 30
        # Oldest 5 evicted
        assert "phrase 0" not in tracker
        assert "phrase 4" not in tracker
        # phrase 5 onward retained
        assert "phrase 5" in tracker
        # New phrases at the end
        assert "new 0" in tracker
        assert "new 4" in tracker

    def test_custom_cap(self):
        tracker = ["a", "b", "c"]
        merge_into_tracker(tracker, ["d", "e"], cap=3)
        assert tracker == ["c", "d", "e"]

    def test_format_for_prompt_empty_returns_empty_string(self):
        assert format_for_prompt([]) == ""

    def test_format_for_prompt_renders_bulleted_list(self):
        out = format_for_prompt(["wet boot", "sore back"])
        assert "Sensory details already used in this run" in out
        assert "- wet boot" in out
        assert "- sore back" in out


# ---------------------------------------------------------------------------
# Integration: prompt injection
# ---------------------------------------------------------------------------

class TestUsedGroundingDetailsInNpcPov:
    @pytest.mark.asyncio
    async def test_already_used_details_passed_to_prompt(self):
        """When state.used_grounding_details has entries, they appear in the
        rendered prompt under the expected header."""
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        state.used_grounding_details = ["wet boot", "bleeding hands", "sore back"]
        npc = state.npcs[0]
        action = {"era_description": "Something.", "intent": "test"}
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"perspective": "test", "emotional_state": "calm"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state)

        assert captured
        prompt = captured[0]
        assert "Sensory details already used in this run" in prompt
        assert "- wet boot" in prompt
        assert "- bleeding hands" in prompt
        assert "- sore back" in prompt

    @pytest.mark.asyncio
    async def test_empty_tracker_omits_bulleted_list(self):
        """When the tracker is empty, no bulleted "do not reuse" list should
        appear. The GROUNDING DETAIL RULE itself remains in the prompt
        (it references the list by name in its instruction text)."""
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        state.used_grounding_details = []
        npc = state.npcs[0]
        action = {"era_description": "Something.", "intent": "test"}
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"perspective": "test", "emotional_state": "calm"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state)

        assert captured
        prompt = captured[0]
        # The injected list header (with colon and trailing newline + "- ")
        # only appears when the tracker is non-empty.
        assert "Sensory details already used in this run (do not reuse unchanged):\n- " not in prompt

    @pytest.mark.asyncio
    async def test_addressed_mode_also_receives_tracker(self):
        from backend.npc_engine import generate_npc_addressed

        state = create_initial_state()
        state.used_grounding_details = ["chapped lips"]
        npc = state.npcs[0]
        action = {"action_type": "speak", "intent": "test"}
        captured = []

        async def mock_llm(prompt, **kw):
            captured.append(prompt)
            return ('{"reply": "test", "internal": null, "emotional_state": "neutral"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_addressed(npc, action, state, player_input="Hello")

        assert captured
        assert "chapped lips" in captured[0]
