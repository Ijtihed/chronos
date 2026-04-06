"""Tests for the Historical Events DB — schema, persistence helpers, build script components."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from backend.persistence import (
    DB_PATH,
    count_historical_events,
    event_exists_by_qid,
    init_db,
    insert_historical_event,
    query_historical_events,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Use a temp DB for each test to avoid cross-contamination."""
    test_db = tmp_path / "test_chronos.db"
    with patch("backend.persistence.DB_PATH", test_db):
        await init_db()
        yield


class TestHistoricalEventsSchema:
    @pytest.mark.asyncio
    async def test_insert_and_query_round_trip(self):
        row_id = await insert_historical_event(
            year=1453,
            region="Anatolia",
            event="Fall of Constantinople to Ottoman forces",
            significance="civilizational",
            event_type="war",
            affects=["political_stability", "trade", "religion"],
            wikidata_qid="Q8778",
        )
        assert row_id is not None
        assert row_id > 0

        events = await query_historical_events(1400, 1500, "Anatolia")
        assert len(events) == 1
        assert events[0]["year"] == 1453
        assert events[0]["event"] == "Fall of Constantinople to Ottoman forces"
        assert events[0]["significance"] == "civilizational"
        assert events[0]["type"] == "war"
        assert events[0]["affects"] == ["political_stability", "trade", "religion"]
        assert events[0]["canonical"] is True
        assert events[0]["wikidata_qid"] == "Q8778"

    @pytest.mark.asyncio
    async def test_insert_all_valid_types(self):
        valid_types = [
            "war", "epidemic", "famine", "political",
            "religious", "economic", "natural_disaster", "cultural",
        ]
        for i, t in enumerate(valid_types):
            await insert_historical_event(
                year=1400 + i,
                region="Test",
                event=f"Test {t} event",
                significance="regional",
                event_type=t,
                affects=["trade"],
            )
        count = await count_historical_events()
        assert count == len(valid_types)

    @pytest.mark.asyncio
    async def test_insert_all_valid_significance(self):
        for sig in ["local", "regional", "civilizational"]:
            await insert_historical_event(
                year=1453,
                region="Test",
                event=f"Test {sig} event",
                significance=sig,
                event_type="war",
                affects=[],
            )
        count = await count_historical_events()
        assert count == 3

    @pytest.mark.asyncio
    async def test_affects_stored_as_json_array(self):
        await insert_historical_event(
            year=1347,
            region="Mediterranean",
            event="Plague arrives",
            significance="civilizational",
            event_type="epidemic",
            affects=["population", "trade", "religion"],
        )
        events = await query_historical_events(1300, 1400)
        assert events[0]["affects"] == ["population", "trade", "religion"]

    @pytest.mark.asyncio
    async def test_query_filters_by_year_range(self):
        await insert_historical_event(
            year=1200, region="Test", event="Early",
            significance="local", event_type="war", affects=[],
        )
        await insert_historical_event(
            year=1453, region="Test", event="Mid",
            significance="regional", event_type="war", affects=[],
        )
        await insert_historical_event(
            year=1800, region="Test", event="Late",
            significance="local", event_type="war", affects=[],
        )
        events = await query_historical_events(1400, 1500)
        assert len(events) == 1
        assert events[0]["event"] == "Mid"

    @pytest.mark.asyncio
    async def test_query_filters_by_region(self):
        await insert_historical_event(
            year=1453, region="Anatolia", event="In Anatolia",
            significance="regional", event_type="war", affects=[],
        )
        await insert_historical_event(
            year=1453, region="Italia", event="In Italia",
            significance="regional", event_type="war", affects=[],
        )
        events = await query_historical_events(1400, 1500, region="Anatolia")
        assert len(events) == 1
        assert events[0]["region"] == "Anatolia"

    @pytest.mark.asyncio
    async def test_query_filters_by_type(self):
        await insert_historical_event(
            year=1453, region="Test", event="War event",
            significance="regional", event_type="war", affects=[],
        )
        await insert_historical_event(
            year=1453, region="Test", event="Famine event",
            significance="regional", event_type="famine", affects=[],
        )
        events = await query_historical_events(1400, 1500, event_type="famine")
        assert len(events) == 1
        assert events[0]["type"] == "famine"

    @pytest.mark.asyncio
    async def test_canonical_defaults_to_true(self):
        await insert_historical_event(
            year=1453, region="Test", event="Default canonical",
            significance="regional", event_type="war", affects=[],
        )
        events = await query_historical_events(1400, 1500)
        assert events[0]["canonical"] is True

    @pytest.mark.asyncio
    async def test_canonical_false(self):
        await insert_historical_event(
            year=1453, region="Test", event="Game-generated",
            significance="regional", event_type="war", affects=[],
            canonical=False,
        )
        events = await query_historical_events(1400, 1500)
        assert events[0]["canonical"] is False

    @pytest.mark.asyncio
    async def test_polity_context_stored_as_json(self):
        ctx = {"population": 50000, "government": "empire", "military_tech": "advanced"}
        await insert_historical_event(
            year=1453, region="Test", event="With polity context",
            significance="regional", event_type="political", affects=[],
            polity_context=ctx,
        )
        events = await query_historical_events(1400, 1500)
        assert events[0]["polity_context"] == ctx


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_event_exists_by_qid(self):
        assert not await event_exists_by_qid("Q8778")
        await insert_historical_event(
            year=1453, region="Test", event="Test",
            significance="regional", event_type="war", affects=[],
            wikidata_qid="Q8778",
        )
        assert await event_exists_by_qid("Q8778")

    @pytest.mark.asyncio
    async def test_event_exists_negative(self):
        await insert_historical_event(
            year=1453, region="Test", event="Test",
            significance="regional", event_type="war", affects=[],
            wikidata_qid="Q8778",
        )
        assert not await event_exists_by_qid("Q9999")

    @pytest.mark.asyncio
    async def test_count_events(self):
        assert await count_historical_events() == 0
        for i in range(5):
            await insert_historical_event(
                year=1400 + i, region="Test", event=f"Event {i}",
                significance="local", event_type="war", affects=[],
            )
        assert await count_historical_events() == 5


class TestBuildScriptHelpers:
    """Tests for build_events_db.py helper functions (no network calls)."""

    def test_extract_qid(self):
        from scripts.build_events_db import _extract_qid
        assert _extract_qid("http://www.wikidata.org/entity/Q8778") == "Q8778"
        assert _extract_qid("Q8778") == "Q8778"

    def test_extract_year(self):
        from scripts.build_events_db import _extract_year
        assert _extract_year({"date": {"value": "1453-05-29T00:00:00Z"}}) == 1453
        assert _extract_year({"startDate": {"value": "0410-08-24T00:00:00Z"}}) == 410
        assert _extract_year({}) is None

    def test_build_sparql_query_contains_classes(self):
        from scripts.build_events_db import _build_sparql_query
        query = _build_sparql_query("war", ["Q198", "Q178561"], 1400, 1500, "Anatolia")
        assert "wd:Q198" in query
        assert "wd:Q178561" in query
        assert "1400" in query
        assert "1500" in query

    def test_starter_eras_defined(self):
        from scripts.build_events_db import STARTER_ERAS
        assert len(STARTER_ERAS) >= 40
        era_names = {e["era"] for e in STARTER_ERAS}
        assert "fall_of_constantinople" in era_names
        assert "roman_late_empire" in era_names
        assert "world_war_two" in era_names
        assert "tang_dynasty" in era_names

    def test_starter_eras_cover_full_range(self):
        from scripts.build_events_db import STARTER_ERAS
        earliest = min(e["start"] for e in STARTER_ERAS)
        latest = max(e["end"] for e in STARTER_ERAS)
        assert earliest <= 100, "Should cover early AD"
        assert latest >= 1990, "Should cover late 20th century"

    def test_starter_eras_multiple_regions(self):
        from scripts.build_events_db import STARTER_ERAS
        regions = {e["region"] for e in STARTER_ERAS}
        assert len(regions) >= 10, f"Only {len(regions)} regions — should cover diverse geography"
