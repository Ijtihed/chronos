"""Phase 2 map tests — coordinates, geo endpoint, marker state."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.eras import ALL_ERAS
from backend.world_state import (
    Location,
    create_initial_state,
    get_player_location,
)

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


def _mock_ollama_down():
    return respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))


class TestLocationCoordinates:
    def test_initial_state_locations_have_coords(self):
        state = create_initial_state()
        for loc in state.locations:
            assert loc.lat != 0.0, f"{loc.id} missing lat"
            assert loc.lon != 0.0, f"{loc.id} missing lon"

    def test_all_eras_have_location_coords(self):
        for era_key, era in ALL_ERAS.items():
            for loc in era["locations"]:
                assert "lat" in loc, f"{era_key}/{loc['id']} missing lat"
                assert "lon" in loc, f"{era_key}/{loc['id']} missing lon"
                assert loc["lat"] != 0.0, f"{era_key}/{loc['id']} lat is 0"
                assert loc["lon"] != 0.0 or loc["id"] == "galata", (
                    f"{era_key}/{loc['id']} lon is 0"
                )

    def test_location_model_accepts_coords(self):
        loc = Location(
            id="test", name="Test", description="Test",
            political_tension="low", lat=41.0, lon=28.0,
        )
        assert loc.lat == 41.0
        assert loc.lon == 28.0

    def test_player_location_has_coords(self):
        state = create_initial_state()
        loc = get_player_location(state)
        assert loc.lat > 0
        assert loc.lon > 0


class TestCoastlineData:
    def test_coastlines_file_exists(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        coastlines = geo_dir / "coastlines.geojson"
        assert coastlines.exists(), "coastlines.geojson missing"

    def test_coastlines_is_valid_geojson(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        data = json.loads((geo_dir / "coastlines.geojson").read_text())
        assert data.get("type") in ("FeatureCollection", "GeometryCollection")


class TestBorderFiles:
    def test_all_five_border_files_exist(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        era_keys = [
            "roman_late_empire", "viking_age", "crusader_states",
            "black_death", "fall_of_constantinople",
        ]
        for key in era_keys:
            path = geo_dir / f"borders_{key}.geojson"
            assert path.exists(), f"borders_{key}.geojson missing"

    def test_all_border_files_are_valid_geojson(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        for path in geo_dir.glob("borders_*.geojson"):
            data = json.loads(path.read_text())
            assert data.get("type") == "FeatureCollection", f"{path.name} not a FeatureCollection"
            assert len(data.get("features", [])) > 0, f"{path.name} has no features"

    def test_border_files_have_multipolygon_geometry(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        for path in geo_dir.glob("borders_*.geojson"):
            data = json.loads(path.read_text())
            for feat in data["features"][:5]:
                gtype = feat.get("geometry", {}).get("type")
                assert gtype in ("Polygon", "MultiPolygon"), (
                    f"{path.name} has unexpected geometry: {gtype}"
                )

    def test_sources_md_exists(self):
        from pathlib import Path
        sources = Path(__file__).resolve().parent.parent / "frontend" / "geo" / "sources.md"
        assert sources.exists(), "sources.md missing"


class TestVisitedLocations:
    def test_initial_state_has_starting_location_visited(self):
        state = create_initial_state()
        assert "ariminum" in state.visited_locations

    def test_visited_locations_in_serialization(self):
        state = create_initial_state()
        dumped = state.model_dump()
        assert "visited_locations" in dumped
        assert "ariminum" in dumped["visited_locations"]


class TestStateSyncForMap:
    """Tests that the state API returns correct data for map rendering.
    These verify the backend side of marker state sync."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_visited_locations_updates_after_travel(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        state_before = (await client.get(f"/api/run/{run_id}")).json()
        assert "ariminum" in state_before["visited_locations"]
        assert "ravenna" not in state_before["visited_locations"]

        import json
        travel_action = json.dumps({
            "action_type": "travel", "target": "Ravenna",
            "intent": "Go to Ravenna", "era_description": "Travels.",
            "is_travel": True, "destination": "ravenna",
            "is_inaction": False, "npc_impacts": [],
        })
        fake_skip = json.dumps({"action": "Rests.", "effect": "Nothing."})
        fake_pov = "I watch."

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        respx.post("http://localhost:11434/api/chat").mock(
            side_effect=[
                httpx.Response(200, json={"message": {"role": "assistant", "content": travel_action}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": fake_skip}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": fake_skip}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": fake_pov}}),
            ]
        )

        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "travel to Ravenna"},
        )

        state_after = (await client.get(f"/api/run/{run_id}")).json()
        assert "ravenna" in state_after["visited_locations"]
        assert state_after["player"]["location"] == "ravenna"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fresh_state_on_every_fetch(self, client):
        """Two consecutive fetches return the same state — no stale cache."""
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        s1 = (await client.get(f"/api/run/{run_id}")).json()
        s2 = (await client.get(f"/api/run/{run_id}")).json()
        assert s1["turn"] == s2["turn"]
        assert s1["visited_locations"] == s2["visited_locations"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_observation_mode_npcs_have_memory_field(self, client):
        """In observation mode, NPC memory_of_player is in the state response."""
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        from backend import persistence
        from backend.death_engine import apply_death
        state = await persistence.load_session(run_id)
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.5
        await persistence.save_session(state)

        resp = (await client.get(f"/api/run/{run_id}")).json()
        assert resp["run_status"] == "dead_observing"
        for npc in resp["npcs"]:
            assert "memory_of_player" in npc

    @pytest.mark.asyncio
    @respx.mock
    async def test_erasure_state_in_api(self, client):
        """Ended run returns run_status=ended so map knows to clear markers."""
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state.run_status = "ended"
        await persistence.save_session(state)

        resp = (await client.get(f"/api/run/{run_id}")).json()
        assert resp["run_status"] == "ended"


class TestGeoEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_era_returns_404(self, client):
        _mock_ollama_down()
        resp = await client.get("/api/geo/nonexistent_era")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_serves_existing_era_borders(self, client):
        resp = await client.get("/api/geo/roman_late_empire")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_shows_phase_2(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        resp = await client.get("/api/health")
        assert resp.json()["phase"] == 2
