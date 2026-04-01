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


class TestBorderData:
    def test_all_5_border_files_exist(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        for era_key in ["roman_late_empire", "viking_age", "crusader_states",
                        "black_death", "fall_of_constantinople"]:
            f = geo_dir / f"borders_{era_key}.geojson"
            assert f.exists(), f"Missing: {f.name}"

    def test_all_border_files_are_valid_geojson(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        for era_key in ["roman_late_empire", "viking_age", "crusader_states",
                        "black_death", "fall_of_constantinople"]:
            data = json.loads((geo_dir / f"borders_{era_key}.geojson").read_text())
            assert data["type"] == "FeatureCollection", f"{era_key} not FeatureCollection"
            assert len(data["features"]) > 0, f"{era_key} has 0 features"

    def test_border_files_have_name_property(self):
        from pathlib import Path
        geo_dir = Path(__file__).resolve().parent.parent / "frontend" / "geo"
        data = json.loads((geo_dir / "borders_roman_late_empire.geojson").read_text())
        has_name = any(
            f.get("properties", {}).get("NAME")
            for f in data["features"]
        )
        assert has_name, "No features have a NAME property"

    def test_sources_md_exists(self):
        from pathlib import Path
        sources = Path(__file__).resolve().parent.parent / "frontend" / "geo" / "sources.md"
        assert sources.exists(), "sources.md missing"


class TestVisitedLocations:
    def test_initial_state_starts_with_visited(self):
        state = create_initial_state()
        assert "ariminum" in state.visited_locations

    def test_visited_locations_in_state_dump(self):
        state = create_initial_state()
        d = state.model_dump()
        assert "visited_locations" in d
        assert isinstance(d["visited_locations"], list)

    def test_apply_action_tracks_location(self):
        from backend.world_state import apply_action
        state = create_initial_state()
        action = {"action_type": "observe", "era_description": "Waits."}
        new = apply_action(state, action)
        assert state.player.location in new.visited_locations


class TestGeoEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_era_returns_404(self, client):
        _mock_ollama_down()
        resp = await client.get("/api/geo/nonexistent_era")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @respx.mock
    async def test_valid_era_returns_geojson(self, client):
        _mock_ollama_down()
        resp = await client.get("/api/geo/roman_late_empire")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_shows_phase_2(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        resp = await client.get("/api/health")
        assert resp.json()["phase"] == 2
