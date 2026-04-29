"""Unit tests for npc_engine.

Covers:
  Fix 2/Change 3 -- player_actions_toward_you (was prior_player_interactions),
                    memory_level, current_preoccupation
  Fix 3 -- JSON markdown fence stripping (_strip_json_fence)
  Fix 5 -- this_turn_events passed into prompt context, capped at 4
  Change 3 -- _build_player_action_summary, tick_preoccupation_drift
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.npc_engine import _build_player_action_summary, _memory_level, _strip_json_fence
from backend.world_state import NPC, NpcNeeds, PersonalityTraits, create_initial_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_npc(**kwargs) -> NPC:
    defaults = dict(
        id="npc_test_0",
        name="Test NPC",
        role="soldier",
        archetype="soldier",
        social_class="commoner",
        location="constantinople",
        description="A grizzled veteran.",
        disposition="wary",
        relationship_to_player="Stranger",
        memory_of_player=0.0,
        personality=PersonalityTraits(),
        needs=NpcNeeds(),
    )
    defaults.update(kwargs)
    return NPC(**defaults)


# ---------------------------------------------------------------------------
# Change 3 -- _build_player_action_summary (replaces stored_povs verbatim)
# ---------------------------------------------------------------------------

class TestBuildPlayerActionSummary:
    def test_no_interactions_returns_first_contact(self):
        npc = _make_npc(player_interactions=[])
        result = _build_player_action_summary(npc)
        assert "first contact" in result.lower()

    def test_single_interaction_formatted(self):
        npc = _make_npc(player_interactions=[
            {"turn": 3, "year": 1453, "action_type": "speak", "intent": "asked about boats"}
        ])
        result = _build_player_action_summary(npc)
        assert "speak" in result
        assert "asked about boats" in result
        assert "1453" in result

    def test_last_three_only(self):
        interactions = [
            {"turn": i, "year": 1453, "action_type": "speak", "intent": f"action_{i}"}
            for i in range(1, 6)
        ]
        npc = _make_npc(player_interactions=interactions)
        result = _build_player_action_summary(npc)
        assert "action_3" in result
        assert "action_4" in result
        assert "action_5" in result
        assert "action_1" not in result
        assert "action_2" not in result

    def test_does_not_inject_old_pov_text(self):
        """Verify stored_povs are never used — only player_interactions."""
        npc = _make_npc(
            stored_povs=["My boot is wet. The king never cuts his hair."],
            player_interactions=[
                {"turn": 1, "year": 1453, "action_type": "speak", "intent": "asked about the market"}
            ],
        )
        result = _build_player_action_summary(npc)
        assert "wet" not in result
        assert "king" not in result
        assert "asked about the market" in result

    def test_empty_player_interactions_gives_first_contact(self):
        npc = _make_npc()
        result = _build_player_action_summary(npc)
        assert result != ""
        assert "first contact" in result.lower()


# ---------------------------------------------------------------------------
# Fix 2 — _memory_level
# ---------------------------------------------------------------------------

class TestMemoryLevel:
    def test_high_memory_is_vivid(self):
        npc = _make_npc(memory_of_player=0.8)
        assert _memory_level(npc) == "vivid"

    def test_medium_memory_is_faint(self):
        npc = _make_npc(memory_of_player=0.5)
        assert _memory_level(npc) == "faint"

    def test_low_memory_is_barely(self):
        npc = _make_npc(memory_of_player=0.1)
        assert _memory_level(npc) == "barely remember them"

    def test_boundary_above_0_7_is_vivid(self):
        npc = _make_npc(memory_of_player=0.71)
        assert _memory_level(npc) == "vivid"

    def test_boundary_exactly_0_7_is_faint(self):
        npc = _make_npc(memory_of_player=0.7)
        assert _memory_level(npc) == "faint"

    def test_boundary_exactly_0_3_is_barely(self):
        npc = _make_npc(memory_of_player=0.3)
        assert _memory_level(npc) == "barely remember them"


# ---------------------------------------------------------------------------
# Fix 3 — _strip_json_fence
# ---------------------------------------------------------------------------

class TestStripJsonFence:
    def test_plain_json_unchanged(self):
        raw = '{"perspective": "test", "emotional_state": "calm"}'
        assert _strip_json_fence(raw) == raw

    def test_json_code_fence_stripped(self):
        raw = '```json\n{"perspective": "test", "emotional_state": "calm"}\n```'
        result = _strip_json_fence(raw)
        assert result == '{"perspective": "test", "emotional_state": "calm"}'

    def test_plain_code_fence_stripped(self):
        raw = '```\n{"perspective": "test", "emotional_state": "calm"}\n```'
        result = _strip_json_fence(raw)
        assert result == '{"perspective": "test", "emotional_state": "calm"}'

    def test_stripped_result_is_valid_json(self):
        raw = '```json\n{"perspective": "He ignored me.", "emotional_state": "angry"}\n```'
        result = _strip_json_fence(raw)
        parsed = json.loads(result)
        assert parsed["perspective"] == "He ignored me."
        assert parsed["emotional_state"] == "angry"

    def test_empty_string_unchanged(self):
        assert _strip_json_fence("") == ""

    def test_whitespace_around_fence_handled(self):
        raw = '  ```json\n{"a": 1}\n```  '
        result = _strip_json_fence(raw)
        assert json.loads(result) == {"a": 1}


# ---------------------------------------------------------------------------
# Fix 5 — this_turn_events in generate_npc_pov prompt context
# ---------------------------------------------------------------------------

class TestThisTurnEventsInPrompt:
    """Tests that this_turn_events is passed into the prompt and capped at 4."""

    @pytest.mark.asyncio
    async def test_npc_pov_includes_this_turn_events(self):
        """When this_turn_events is provided, the rendered prompt must contain
        the activity text from those events."""
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        npc = state.npcs[0]
        action = {"era_description": "Someone did something.", "intent": "test"}
        this_turn_events = [
            {"npc_id": "npc_other_1", "npc_name": "Dimitri", "activity": "Hauls his boat."},
        ]

        captured_prompt = []

        async def mock_call_llm(prompt, **kwargs):
            captured_prompt.append(prompt)
            return ('{"perspective": "I see Dimitri.", "emotional_state": "calm"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_call_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state, this_turn_events=this_turn_events)

        assert captured_prompt, "call_llm was never called"
        assert "Hauls his boat." in captured_prompt[0], (
            "this_turn_events activity not found in rendered prompt"
        )

    @pytest.mark.asyncio
    async def test_npc_pov_uses_player_action_summary_not_stored_povs(self):
        """player_actions_toward_you must reflect player_interactions, not stored_povs.

        We use a distinctive string that does not appear elsewhere in the
        prompt template (no example uses zinnewxr12 etc.) to verify the
        stored_povs content does NOT leak through.
        """
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        npc = state.npcs[0]
        # Distinctive, prompt-unique sentinel string -- if this leaks into
        # the prompt, stored_povs is being injected somewhere.
        sentinel = "zinnewxr12 grimble fluvian"
        npc.stored_povs = [f"My past pov contained {sentinel} which is unique."]
        npc.player_interactions = [
            {"turn": 1, "year": 1453, "action_type": "speak", "intent": "asked about the harbor"}
        ]
        action = {"era_description": "Something.", "intent": "test"}

        captured_prompt = []

        async def mock_call_llm(prompt, **kwargs):
            captured_prompt.append(prompt)
            return ('{"perspective": "test", "emotional_state": "calm"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_call_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state)

        assert captured_prompt
        prompt = captured_prompt[0]
        assert "asked about the harbor" in prompt
        assert sentinel not in prompt

    @pytest.mark.asyncio
    async def test_npc_pov_handles_empty_this_turn_events(self):
        """When this_turn_events is empty or None, the prompt renders
        'Nothing notable.' rather than crashing."""
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        npc = state.npcs[0]
        action = {"era_description": "Quiet streets.", "intent": "observe"}

        captured_prompt = []

        async def mock_call_llm(prompt, **kwargs):
            captured_prompt.append(prompt)
            return ('{"perspective": "Nothing happened.", "emotional_state": "bored"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_call_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state, this_turn_events=None)
                await generate_npc_pov(npc, action, state, this_turn_events=[])

        assert len(captured_prompt) == 2
        for p in captured_prompt:
            assert "Nothing notable." in p

    @pytest.mark.asyncio
    async def test_this_turn_events_capped_at_4(self):
        """Even if 10 events are passed, at most 4 appear in the prompt."""
        from backend.npc_engine import generate_npc_pov

        state = create_initial_state()
        npc = state.npcs[0]
        action = {"era_description": "Busy streets.", "intent": "observe"}

        events = [
            {"npc_id": f"npc_other_{i}", "npc_name": f"NPC{i}", "activity": f"Action{i}."}
            for i in range(10)
        ]

        captured_prompt = []

        async def mock_call_llm(prompt, **kwargs):
            captured_prompt.append(prompt)
            return ('{"perspective": "Busy.", "emotional_state": "alert"}', 0.0)

        with patch("backend.npc_engine.call_llm", side_effect=mock_call_llm):
            with patch("backend.npc_engine.retrieve_context", return_value=""):
                await generate_npc_pov(npc, action, state, this_turn_events=events)

        assert captured_prompt
        prompt = captured_prompt[0]
        # Only the first 4 events should appear; events 4-9 must be absent
        for i in range(4):
            assert f"Action{i}." in prompt, f"Action{i} missing from capped prompt"
        for i in range(4, 10):
            assert f"Action{i}." not in prompt, f"Action{i} should be capped out"


# ---------------------------------------------------------------------------
# Change 3 -- tick_preoccupation_drift
# ---------------------------------------------------------------------------

class TestPreoccupationDrift:
    def test_initial_preoccupation_set(self):
        from backend.npc_personality import get_initial_preoccupation, ARCHETYPE_PREOCCUPATIONS
        for arch in ARCHETYPE_PREOCCUPATIONS:
            result = get_initial_preoccupation(arch)
            assert result == ARCHETYPE_PREOCCUPATIONS[arch][0]

    def test_drift_does_not_fire_before_interval(self):
        from backend.npc_personality import tick_preoccupation_drift, ARCHETYPE_PREOCCUPATIONS
        state = create_initial_state()
        npc = state.npcs[0]
        npc.archetype = "soldier"
        npc.current_preoccupation = ARCHETYPE_PREOCCUPATIONS["soldier"][0]
        npc.last_preoccupation_shift_turn = 0
        state.turn = 3  # less than DRIFT_INTERVAL (6)
        original = npc.current_preoccupation
        tick_preoccupation_drift(state)
        assert npc.current_preoccupation == original

    def test_drift_fires_at_interval(self):
        from backend.npc_personality import (
            tick_preoccupation_drift, ARCHETYPE_PREOCCUPATIONS,
            PREOCCUPATION_DRIFT_INTERVAL,
        )
        state = create_initial_state()
        npc = state.npcs[0]
        npc.archetype = "soldier"
        pool = ARCHETYPE_PREOCCUPATIONS["soldier"]
        npc.current_preoccupation = pool[0]
        npc.last_preoccupation_shift_turn = 0
        state.turn = PREOCCUPATION_DRIFT_INTERVAL
        tick_preoccupation_drift(state)
        assert npc.current_preoccupation == pool[1]
        assert npc.last_preoccupation_shift_turn == PREOCCUPATION_DRIFT_INTERVAL

    def test_drift_cycles_back_to_start(self):
        from backend.npc_personality import (
            tick_preoccupation_drift, ARCHETYPE_PREOCCUPATIONS,
            PREOCCUPATION_DRIFT_INTERVAL,
        )
        state = create_initial_state()
        npc = state.npcs[0]
        npc.archetype = "soldier"
        pool = ARCHETYPE_PREOCCUPATIONS["soldier"]
        npc.current_preoccupation = pool[-1]  # last entry
        npc.last_preoccupation_shift_turn = 0
        state.turn = PREOCCUPATION_DRIFT_INTERVAL
        tick_preoccupation_drift(state)
        assert npc.current_preoccupation == pool[0]  # wraps to start

    def test_drift_initializes_empty_preoccupation(self):
        from backend.npc_personality import (
            tick_preoccupation_drift, ARCHETYPE_PREOCCUPATIONS,
            PREOCCUPATION_DRIFT_INTERVAL,
        )
        state = create_initial_state()
        npc = state.npcs[0]
        npc.archetype = "merchant"
        npc.current_preoccupation = ""
        npc.last_preoccupation_shift_turn = 0
        state.turn = PREOCCUPATION_DRIFT_INTERVAL
        tick_preoccupation_drift(state)
        assert npc.current_preoccupation == ARCHETYPE_PREOCCUPATIONS["merchant"][0]

    def test_unknown_archetype_uses_default_pool(self):
        from backend.npc_personality import (
            tick_preoccupation_drift, PREOCCUPATION_DRIFT_INTERVAL,
        )
        state = create_initial_state()
        npc = state.npcs[0]
        npc.archetype = "unknown_archetype_xyz"
        npc.current_preoccupation = ""
        npc.last_preoccupation_shift_turn = 0
        state.turn = PREOCCUPATION_DRIFT_INTERVAL
        tick_preoccupation_drift(state)
        assert npc.current_preoccupation != ""
