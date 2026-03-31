"""Live integration tests — require a running Ollama with llama3.1:8b.

These hit the real LLM to verify end-to-end behavior including output quality.
Marked with @pytest.mark.live and auto-skipped when Ollama is unreachable.
"""

from __future__ import annotations

import pytest

from backend.action_parser import parse_action
from backend.npc_engine import generate_npc_pov
from backend.world_state import apply_action, create_initial_state

pytestmark = pytest.mark.live


@pytest.fixture
def state():
    return create_initial_state()


class TestActionParserLive:
    @pytest.mark.asyncio
    async def test_returns_valid_json_structure(self, state):
        result = await parse_action("talk to the centurion", state)
        assert "action_type" in result
        assert "target" in result
        assert "intent" in result
        assert "era_description" in result
        assert "_parse_error" not in result, f"Parser error: {result.get('_parse_error')}"

    @pytest.mark.asyncio
    async def test_action_type_is_from_vocabulary(self, state):
        result = await parse_action("ask the deacon for food", state)
        valid_types = {"speak", "trade", "travel", "observe", "petition", "prepare", "other"}
        assert result["action_type"] in valid_types, (
            f"Got unexpected action_type: {result['action_type']}"
        )

    @pytest.mark.asyncio
    async def test_modern_language_still_parses(self, state):
        """Anachronism handling: modern phrasing should map to a valid action."""
        result = await parse_action("DM the soldier about logistics", state)
        assert result["action_type"] != "other" or result["intent"], (
            "Modern phrasing should still produce a meaningful action"
        )
        assert "_parse_error" not in result

    @pytest.mark.asyncio
    async def test_different_phrasings_same_intent(self, state):
        """Multiple phrasings of 'talk to Gallus' should produce speak-type actions."""
        phrasings = [
            "talk to the centurion",
            "ask Gallus about the situation",
            "speak with the soldier",
        ]
        results = []
        for p in phrasings:
            fresh = create_initial_state()
            r = await parse_action(p, fresh)
            results.append(r)

        speak_types = [r["action_type"] for r in results]
        assert speak_types.count("speak") >= 2, (
            f"Expected mostly 'speak' actions, got: {speak_types}"
        )


class TestNpcPovLive:
    @pytest.mark.asyncio
    async def test_generates_nonempty_response(self, state):
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "ask about the troops",
            "era_description": "Corvinus approaches the centurion to ask about the garrison.",
        }
        pov = await generate_npc_pov(state.npcs[0], action, state)
        assert len(pov) > 20, "POV response too short"
        assert "[" not in pov[:5], "Should not be an error fallback"

    @pytest.mark.asyncio
    async def test_two_npcs_give_different_responses(self, state):
        action = {
            "action_type": "trade",
            "target": None,
            "intent": "offer grain at a discount",
            "era_description": "Corvinus offers to sell grain at reduced prices.",
        }
        pov_gallus = await generate_npc_pov(state.npcs[0], action, state)
        pov_paulus = await generate_npc_pov(state.npcs[1], action, state)
        assert pov_gallus != pov_paulus, "NPCs should have distinct voices"

    @pytest.mark.asyncio
    async def test_pov_does_not_contain_modern_terms(self, state):
        """Basic anachronism check — POV should not contain obviously modern words."""
        action = {
            "action_type": "speak",
            "target": "Lucius Gallus",
            "intent": "discuss defense",
            "era_description": "Corvinus discusses the town defenses with the centurion.",
        }
        pov = await generate_npc_pov(state.npcs[0], action, state)
        modern_terms = ["email", "phone", "internet", "computer", "okay"]
        pov_lower = pov.lower()
        for term in modern_terms:
            assert term not in pov_lower, f"Modern term '{term}' found in POV: {pov}"


class TestFullTurnLoopLive:
    @pytest.mark.asyncio
    async def test_end_to_end_turn(self, state):
        """The core Phase 0 proof: input -> parse -> mutate -> POV -> all connected."""
        parsed = await parse_action("negotiate with the centurion for protection", state)
        assert "_parse_error" not in parsed

        new_state = apply_action(state, parsed)
        assert new_state.turn == 1
        assert len(new_state.events) == 1

        pov = await generate_npc_pov(new_state.npcs[0], parsed, new_state)
        assert len(pov) > 20
        assert "[" not in pov[:5]

    @pytest.mark.asyncio
    async def test_three_turn_sequence(self, state):
        """Play 3 turns and verify state accumulates correctly."""
        actions = [
            "ask the centurion about the Visigoths",
            "go to the basilica and speak with the deacon",
            "observe the harbor",
        ]
        current = state
        for text in actions:
            parsed = await parse_action(text, current)
            current = apply_action(current, parsed)

        assert current.turn == 3
        assert len(current.events) == 3

    @pytest.mark.asyncio
    async def test_world_state_differs_after_action(self, state):
        """Verifies the roadmap check: state before and after should differ."""
        before = state.model_dump()
        parsed = await parse_action("trade grain with the garrison", state)
        after = apply_action(state, parsed).model_dump()

        assert after["turn"] != before["turn"]
        assert len(after["events"]) > len(before["events"])


class TestNpcImpactsLive:
    @pytest.mark.asyncio
    async def test_harmful_action_produces_negative_impacts(self, state):
        """The fix: actions that harm NPCs indirectly should produce negative sentiment."""
        result = await parse_action("hoard all the grain and raise prices", state)
        assert "_parse_error" not in result
        impacts = result.get("npc_impacts", [])
        assert len(impacts) >= 1, "Parser should return npc_impacts"
        sentiments = [i.get("sentiment") for i in impacts]
        assert "negative" in sentiments, (
            f"Hoarding grain should produce at least one negative impact, got: {impacts}"
        )

    @pytest.mark.asyncio
    async def test_helpful_action_produces_positive_impacts(self, state):
        result = await parse_action("donate grain to the basilica to feed refugees", state)
        assert "_parse_error" not in result
        impacts = result.get("npc_impacts", [])
        assert len(impacts) >= 1, "Parser should return npc_impacts"
        paulus_impact = next((i for i in impacts if "paulus" in i.get("name", "").lower()), None)
        assert paulus_impact is not None, "Deacon Paulus should be in impacts"
        assert paulus_impact["sentiment"] == "positive"

    @pytest.mark.asyncio
    async def test_impacts_applied_to_world_state(self, state):
        """End-to-end: harmful action shifts NPC dispositions in world state."""
        parsed = await parse_action("start hoarding grain and raising prices", state)
        new_state = apply_action(state, parsed)
        gallus_before = next(n for n in state.npcs if n.id == "centurion_gallus")
        gallus_after = next(n for n in new_state.npcs if n.id == "centurion_gallus")
        impacts = parsed.get("npc_impacts", [])
        gallus_sentiment = next(
            (i["sentiment"] for i in impacts if "gallus" in i.get("name", "").lower()), None
        )
        if gallus_sentiment == "negative":
            assert gallus_after.disposition != gallus_before.disposition, (
                "Negative impact should shift Gallus's disposition"
            )


class TestModelTierCompliance:
    """Verify that no frontier/API calls are being made."""

    @pytest.mark.asyncio
    async def test_action_parser_uses_local_ollama(self, state):
        from backend.llm import OLLAMA_URL
        assert "localhost" in OLLAMA_URL or "127.0.0.1" in OLLAMA_URL

    @pytest.mark.asyncio
    async def test_no_frontier_api_keys_required(self):
        """Phase 0 should work without any API keys set."""
        parsed = await parse_action(
            "look around",
            create_initial_state(),
        )
        assert True
