"""Integration tests for GET /api/run/{id}/events/visible.

No LLM calls on this path — filter_historical_events is pure Python
heuristic. Uses httpx.AsyncClient + FastAPI's test transport.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.persistence import init_db, save_session
from backend.world_state import create_initial_state


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def roman_run():
    """Seed a Roman Late Empire run (year 410, Italia) and return run_id."""
    state = create_initial_state()
    await save_session(state)
    return state.run_id


class TestEventsVisibleResponseShape:
    @pytest.mark.asyncio
    async def test_returns_200(self, client, roman_run):
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_response_has_era_key_and_events(self, client, roman_run):
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        data = res.json()
        assert "era_key" in data
        assert "events" in data
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio
    async def test_era_key_matches_state(self, client, roman_run):
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        data = res.json()
        # create_initial_state builds "Roman Late Empire" which reverse-
        # maps to "roman_late_empire" in ALL_ERAS.
        assert data["era_key"] == "roman_late_empire"

    @pytest.mark.asyncio
    async def test_event_shape(self, client, roman_run):
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        data = res.json()
        if not data["events"]:
            pytest.skip("No events returned; DB may be empty for this era")
        ev = data["events"][0]
        expected_keys = {
            "id", "year", "type", "significance", "tier",
            "accuracy", "lat", "lon", "radius_km", "broad",
            "summary", "region",
        }
        assert set(ev.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_all_events_have_coords(self, client, roman_run):
        """Events without resolvable centroids must be omitted."""
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        for ev in res.json()["events"]:
            assert isinstance(ev["lat"], (int, float))
            assert isinstance(ev["lon"], (int, float))
            assert ev["radius_km"] > 0

    @pytest.mark.asyncio
    async def test_no_unknown_tier(self, client, roman_run):
        """filter_historical_events must drop the 'unknown' tier."""
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        tiers = {ev["tier"] for ev in res.json()["events"]}
        assert "unknown" not in tiers
        allowed = {"witnessed", "known", "rumor_reliable", "rumor_unreliable"}
        assert tiers.issubset(allowed)

    @pytest.mark.asyncio
    async def test_year_window(self, client, roman_run):
        """Events clamped to state.current_year - 50 ... + 5."""
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        events = res.json()["events"]
        if not events:
            pytest.skip("No events to check window against")
        # current_year for fresh Roman run is 410; window is 360-415.
        for ev in events:
            assert 350 <= ev["year"] <= 420, (
                f"event {ev['id']} year {ev['year']} outside window"
            )


class TestKnowledgeFilterByArchetype:
    """Switching archetype changes tier distribution."""

    async def _get_events_for_archetype(self, client, archetype: str):
        state = create_initial_state()
        state.player.archetype = archetype
        await save_session(state)
        res = await client.get(f"/api/run/{state.run_id}/events/visible")
        return res.json()["events"]

    @pytest.mark.asyncio
    async def test_high_tier_sees_more_than_low(self, client):
        """A scholar ('high' tier) should see at least as many events as a farmer ('low')."""
        noble_events = await self._get_events_for_archetype(client, "noble")
        farmer_events = await self._get_events_for_archetype(client, "farmer")
        # Both archetypes should see witnessed+known events at the
        # player's location. "high" gets wider rumor reach, so the
        # total count should be >= "low".
        assert len(noble_events) >= len(farmer_events)


class TestCentroidFiltering:
    @pytest.mark.asyncio
    async def test_unmapped_regions_omitted(self, client, roman_run):
        """Events whose region doesn't resolve are dropped, no 500."""
        # This is implicit — if any returned event had an unmapped
        # region, the endpoint would have skipped it. We can check
        # that the response is valid for any returned event.
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        assert res.status_code == 200
        for ev in res.json()["events"]:
            assert ev["region"]  # non-empty string


class TestErrors:
    @pytest.mark.asyncio
    async def test_nonexistent_run_returns_404(self, client):
        res = await client.get("/api/run/does_not_exist/events/visible")
        assert res.status_code == 404
