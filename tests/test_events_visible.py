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
    async def test_year_window_uses_player_lifetime(self, client, roman_run):
        """Events clamped to (birth_year .. current_year + 5).

        Roman starter character: birth_year=375, current_year=410. So
        no event before year 375 should appear, and none after 415.
        """
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        events = res.json()["events"]
        if not events:
            pytest.skip("No events to check window against")
        for ev in events:
            assert 375 <= ev["year"] <= 415, (
                f"event {ev['id']} year {ev['year']} outside lifetime window"
            )

    @pytest.mark.asyncio
    async def test_local_significance_dropped(self, client, roman_run):
        """Map-facing endpoint omits 'local' significance events.

        local-significance items remain in the DB for HCE / NPC
        grounding pipelines but are noise on the player's map.
        """
        res = await client.get(f"/api/run/{roman_run}/events/visible")
        events = res.json()["events"]
        for ev in events:
            assert ev["significance"] in {"civilizational", "regional"}, (
                f"event {ev['id']} sig={ev['significance']} should not appear"
            )

    @pytest.mark.asyncio
    async def test_regional_events_constrained_to_era_region(
        self, client, roman_run,
    ):
        """Regional-significance events must share at least one meaningful
        keyword with the era's home region. Civilizational events
        bypass this check.

        Roman Late Empire era region is 'Italia'. Regional events
        from 'Britannia' or 'Persia' should be filtered. Civilizational
        events from any region remain.
        """
        from backend.main import _event_in_player_region

        res = await client.get(f"/api/run/{roman_run}/events/visible")
        events = res.json()["events"]
        era_region = "Italia"
        for ev in events:
            if ev["significance"] == "civilizational":
                continue
            assert _event_in_player_region(ev["region"] or "", era_region), (
                f"regional event {ev['id']} region={ev['region']!r} "
                f"shares no keyword with era region {era_region!r}"
            )

    def test_region_token_helper(self):
        """Canonical region tokenizer behavior — covers stopwords,
        slashes, parens, multi-region descriptors."""
        from backend.main import _region_tokens, _event_in_player_region

        assert _region_tokens("Italia") == frozenset({"italia"})
        # Stopwords stripped.
        assert _region_tokens("Byzantine Empire") == frozenset({"byzantine"})
        # Slashes and other punctuation become whitespace.
        assert _region_tokens("Byzantine Empire/Anatolia") == frozenset(
            {"byzantine", "anatolia"}
        )
        assert _region_tokens("Byzantine Empire (Wallachia)") == frozenset(
            {"byzantine", "wallachia"}
        )
        # Non-overlap returns False.
        assert not _event_in_player_region("Persia", "Italia")
        assert not _event_in_player_region("Hungary", "Byzantine Empire")
        # Overlap (even one token) returns True.
        assert _event_in_player_region(
            "Byzantine Empire/Anatolia",
            "Byzantine Empire and the Ottoman frontier",
        )
        # Empty strings return False (don't crash, don't pass).
        assert not _event_in_player_region("", "Italia")
        assert not _event_in_player_region("Italia", "")

    def test_region_aliases_collapse(self):
        """Historical naming variants (Italia/Italy, Byzantium/Byzantine,
        Gaul/France) must collapse to the same canonical token so the
        overlap check works across the events corpus."""
        from backend.main import _region_tokens, _event_in_player_region

        # Italia / Italy / Italian collapse.
        assert _region_tokens("Italia") == _region_tokens("Italy")
        assert _region_tokens("Italian peninsula") == frozenset(
            {"italia", "peninsula"}
        )

        # Cross-pair: an Italia event reads as in-region for an
        # Italy-named era (and vice versa).
        assert _event_in_player_region("Italia", "Northern Italy and Southern France")
        assert _event_in_player_region(
            "Italian cities", "Northern Italy and Southern France",
        )

        # Byzantium / Byzantine collapse.
        assert _event_in_player_region("Byzantium", "Byzantine Empire")
        # Gaul / France / Frankish collapse.
        assert _event_in_player_region("Gaul", "France")
        assert _event_in_player_region("Frankish kingdom", "France")

    @pytest.mark.asyncio
    async def test_lifetime_window_fallback_when_birth_year_missing(
        self, client,
    ):
        """If birth_year is unset/sentinel, fall back to a sensible
        50-year window so test sessions and migrations still work."""
        state = create_initial_state()
        state.player.birth_year = 0  # unset / sentinel
        await save_session(state)
        res = await client.get(f"/api/run/{state.run_id}/events/visible")
        assert res.status_code == 200
        events = res.json()["events"]
        if not events:
            pytest.skip("No events returned to check window against")
        # current_year=410, fallback window=50, so 360..415.
        for ev in events:
            assert 360 <= ev["year"] <= 415


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


class TestPlaceLabelsEndpoint:
    """GET /api/geo/places/labels feeds the zoom-dependent city
    labels on the map. Pure read of the centroids YAML; no run state
    or LLM involvement."""

    @pytest.mark.asyncio
    async def test_returns_200_and_shape(self, client):
        res = await client.get("/api/geo/places/labels")
        assert res.status_code == 200
        data = res.json()
        assert "places" in data
        assert isinstance(data["places"], list)
        assert len(data["places"]) > 50  # we have ~120 centroids
        sample = data["places"][0]
        assert set(sample.keys()) == {"name", "lat", "lon", "tier", "radius_km"}
        assert sample["tier"] in {"city", "town", "region"}

    @pytest.mark.asyncio
    async def test_excludes_broad_regions(self, client):
        """Broad regions (radius_km > 500) like 'Mediterranean' or
        'Europe' must NOT appear; rendering them as a single label
        point is meaningless."""
        res = await client.get("/api/geo/places/labels")
        data = res.json()
        for p in data["places"]:
            assert p["radius_km"] <= 500, (
                f"{p['name']} radius={p['radius_km']} should be excluded"
            )

    @pytest.mark.asyncio
    async def test_known_cities_present(self, client):
        """Sanity check: the cities we hand-mapped for event placement
        are surfaced as label tier 'city'."""
        res = await client.get("/api/geo/places/labels")
        data = res.json()
        names = {p["name"]: p for p in data["places"]}
        for required in ("Rome", "Constantinople", "Venice", "Florence"):
            assert required in names, f"{required} missing from labels"
            assert names[required]["tier"] == "city"
