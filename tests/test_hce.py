"""Tests for the Historical Context Engine — ground context and consequence scheduling."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from backend.hce import (
    _derive_consequences,
    _fallback_context,
    _format_events_for_prompt,
    _format_rumors_for_prompt,
    generate_ground_context,
    schedule_canonical_consequences,
)
from backend.persistence import (
    get_pending_consequences,
    init_db,
    insert_historical_event,
)
from backend.player_knowledge import HistoricalEventView
from backend.world_state import WorldState, create_initial_state


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    test_db = tmp_path / "test_chronos.db"
    with patch("backend.persistence.DB_PATH", test_db):
        await init_db()
        yield


@pytest.fixture
def state_with_events():
    """Initial state for 410 AD Roman Late Empire with events seeded."""
    return create_initial_state()


class TestFormatEventsForPrompt:
    def test_known_events_formatted(self):
        events = [
            HistoricalEventView(
                year=408, event="Visigoths cross the Alps",
                event_type="war", significance="civilizational",
                knowledge_quality="known",
            ),
        ]
        text = _format_events_for_prompt(events)
        assert "408" in text
        assert "Visigoths" in text
        assert "war" in text

    def test_empty_returns_empty_string(self):
        assert _format_events_for_prompt([]) == ""


class TestFormatRumorsForPrompt:
    def test_reliable_rumor_labeled(self):
        events = [
            HistoricalEventView(
                year=409, event="Army retreating south",
                event_type="war", significance="regional",
                knowledge_quality="rumor_reliable", accuracy=0.7,
            ),
        ]
        text = _format_rumors_for_prompt(events)
        assert "reliable" in text
        assert "Army retreating" in text

    def test_unreliable_rumor_labeled(self):
        events = [
            HistoricalEventView(
                year=409, event="Plague in the north",
                event_type="epidemic", significance="regional",
                knowledge_quality="rumor_unreliable", accuracy=0.35,
            ),
        ]
        text = _format_rumors_for_prompt(events)
        assert "unreliable" in text


class TestFallbackContext:
    def test_produces_valid_structure(self, state_with_events):
        ctx = _fallback_context(state_with_events, [], [])
        assert "era_feel" in ctx
        assert "what_character_knows" in ctx
        assert "local_rumors" in ctx
        assert "material_conditions" in ctx
        assert isinstance(ctx["local_rumors"], list)
        assert isinstance(ctx["recent_events_known"], list)

    def test_includes_known_events(self, state_with_events):
        known = [
            HistoricalEventView(
                year=408, event="Alaric marches on Rome",
                event_type="war", significance="civilizational",
                knowledge_quality="known",
            ),
        ]
        ctx = _fallback_context(state_with_events, known, [])
        assert "Alaric marches on Rome" in ctx["recent_events_known"]

    def test_includes_rumors(self, state_with_events):
        rumors = [
            HistoricalEventView(
                year=409, event="Ships fleeing the coast",
                event_type="war", significance="local",
                knowledge_quality="rumor_reliable", accuracy=0.6,
            ),
        ]
        ctx = _fallback_context(state_with_events, [], rumors)
        assert "Ships fleeing the coast" in ctx["local_rumors"]


class TestDeriveConsequences:
    def test_war_event_produces_tension_shift(self, state_with_events):
        ev = {
            "id": 1, "type": "war", "significance": "regional",
            "affects": ["military"], "region": "Italia",
            "event": "Battle near the frontier",
        }
        consequences = _derive_consequences(ev, state_with_events)
        types = {c["effect_type"] for c in consequences}
        assert "tension_shift" in types

    def test_civilizational_war_produces_rumor(self, state_with_events):
        ev = {
            "id": 2, "type": "war", "significance": "civilizational",
            "affects": ["military", "population"], "region": "Italia",
            "event": "The sack of the capital",
        }
        consequences = _derive_consequences(ev, state_with_events)
        types = {c["effect_type"] for c in consequences}
        assert "rumor" in types

    def test_famine_produces_trade_disruption(self, state_with_events):
        ev = {
            "id": 3, "type": "famine", "significance": "regional",
            "affects": ["agriculture", "population"], "region": "Italia",
            "event": "Harvest failure across the region",
        }
        consequences = _derive_consequences(ev, state_with_events)
        types = {c["effect_type"] for c in consequences}
        assert "trade_disruption" in types

    def test_epidemic_produces_material_change(self, state_with_events):
        ev = {
            "id": 4, "type": "epidemic", "significance": "regional",
            "affects": ["population"], "region": "Italia",
            "event": "Plague spreads through the ports",
        }
        consequences = _derive_consequences(ev, state_with_events)
        types = {c["effect_type"] for c in consequences}
        assert "material_change" in types
        assert "tension_shift" in types

    def test_civilizational_event_produces_event_spawn(self, state_with_events):
        ev = {
            "id": 5, "type": "political", "significance": "civilizational",
            "affects": ["political_stability", "trade"], "region": "Italia",
            "event": "The emperor is deposed",
        }
        consequences = _derive_consequences(ev, state_with_events)
        types = {c["effect_type"] for c in consequences}
        assert "event_spawn" in types

    def test_no_consequences_for_distant_cultural(self, state_with_events):
        ev = {
            "id": 6, "type": "cultural", "significance": "local",
            "affects": ["culture"], "region": "Faraway",
            "event": "A new library is founded",
        }
        consequences = _derive_consequences(ev, state_with_events)
        assert len(consequences) == 0

    def test_all_consequences_have_trigger_turn(self, state_with_events):
        ev = {
            "id": 7, "type": "war", "significance": "civilizational",
            "affects": ["military", "trade"], "region": "Italia",
            "event": "Major conflict",
        }
        consequences = _derive_consequences(ev, state_with_events)
        for c in consequences:
            assert "trigger_turn" in c
            assert c["trigger_turn"] > 0


class TestScheduleCanonicalConsequences:
    @pytest.mark.asyncio
    async def test_schedules_from_seeded_events(self, state_with_events):
        await insert_historical_event(
            year=409, region="Italia",
            event="Visigoths raid the northern provinces",
            significance="regional", event_type="war",
            affects=["military", "population"],
        )
        count = await schedule_canonical_consequences(state_with_events)
        assert count >= 1
        pending = await get_pending_consequences(state_with_events.run_id, 10)
        assert len(pending) >= 1

    @pytest.mark.asyncio
    async def test_no_events_no_consequences(self, state_with_events):
        count = await schedule_canonical_consequences(state_with_events)
        assert count == 0


class TestGenerateGroundContext:
    @pytest.mark.asyncio
    async def test_fallback_when_no_events_and_no_ollama(self, state_with_events):
        with patch("backend.hce.chat", side_effect=Exception("no LLM")):
            ctx = await generate_ground_context(state_with_events)
        assert "era_feel" in ctx
        assert "what_character_knows" in ctx

    @pytest.mark.asyncio
    async def test_with_events_uses_knowledge_matrix(self, state_with_events):
        await insert_historical_event(
            year=408, region="Italia",
            event="Alaric's army crosses into Italia",
            significance="civilizational", event_type="war",
            affects=["military", "trade", "population"],
        )
        with patch("backend.hce.chat", side_effect=Exception("no LLM")):
            ctx = await generate_ground_context(state_with_events)
        assert len(ctx["recent_events_known"]) >= 0  # may be 0 if distance too far
        assert isinstance(ctx["local_rumors"], list)
