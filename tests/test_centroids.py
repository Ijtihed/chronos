"""Unit tests for backend.geo.centroids — region centroid resolution."""

from __future__ import annotations

import pytest

from backend.geo.centroids import (
    load_centroids,
    resolve_region,
    resolution_path,
    _normalize_variants,
)


class TestLoadCentroids:
    def test_returns_dict(self):
        d = load_centroids()
        assert isinstance(d, dict)
        assert len(d) > 30, "expected ~50+ entries"

    def test_cached(self):
        assert load_centroids() is load_centroids()

    def test_entry_shape(self):
        d = load_centroids()
        italia = d["Italia"]
        assert set(italia.keys()) == {"lat", "lon", "radius_km", "broad"}
        assert isinstance(italia["lat"], float)
        assert isinstance(italia["lon"], float)
        assert isinstance(italia["radius_km"], float)
        assert isinstance(italia["broad"], bool)

    def test_broad_flag_set_on_mediterranean(self):
        assert load_centroids()["Mediterranean"]["broad"] is True

    def test_broad_flag_default_false(self):
        assert load_centroids()["Italia"]["broad"] is False


class TestResolveRegion:
    def test_exact_match(self):
        c = resolve_region("Italia")
        assert c is not None
        assert c["lat"] == 42.5
        assert c["lon"] == 12.5

    def test_case_sensitive(self):
        # The YAML keys are canonical-cased; we don't lowercase.
        # "italia" should not exact-match "Italia".
        c_exact = resolve_region("Italia")
        c_lower = resolve_region("italia")
        assert c_exact is not None
        # Lowercase input may or may not normalize — documenting current behavior.
        # If it ever matches, revisit case handling.
        assert c_lower is None

    def test_paren_stripped(self):
        """'Balkans (Hussite Wars)' -> strip to 'Balkans'."""
        c = resolve_region("Balkans (Hussite Wars)")
        assert c is not None
        assert c["lat"] == 43.0

    def test_slash_split(self):
        """'Byzantine Empire/Anatolia' -> first part matches."""
        c = resolve_region("Byzantine Empire/Anatolia")
        assert c is not None
        assert c["radius_km"] >= 500

    def test_comma_split(self):
        """'Ottoman Empire, Wallachia' -> first part matches."""
        c = resolve_region("Ottoman Empire, Wallachia")
        assert c is not None

    def test_and_split(self):
        """'Denmark and Friesland' -> 'Denmark' matches."""
        c = resolve_region("Denmark and Friesland")
        assert c is not None

    def test_unknown_returns_none(self):
        assert resolve_region("Atlantis") is None

    def test_empty_returns_none(self):
        assert resolve_region("") is None
        assert resolve_region(None) is None

    def test_nonsense_compound_returns_none(self):
        """'Unknown' (literal string from DB) -> None."""
        assert resolve_region("Unknown") is None


class TestNormalizeVariants:
    def test_original_first(self):
        v = _normalize_variants("Italia")
        assert v[0] == "Italia"

    def test_paren_strip_added(self):
        v = _normalize_variants("Balkans (Hussite Wars)")
        assert "Balkans" in v

    def test_slash_split(self):
        v = _normalize_variants("A/B/C")
        assert "A" in v and "B" in v and "C" in v

    def test_connective_and_filtered_after_split(self):
        """'and' as a standalone candidate is filtered; real parts remain."""
        v = _normalize_variants("Italy, and Bologna")
        assert "and" not in [x.lower() for x in v]
        assert "Italy" in v
        # "Italy, and Bologna" resolves via "Italy"; "and Bologna" with
        # leading "and " is kept as-is (won't match any centroid, harmless).

    def test_and_as_separator(self):
        v = _normalize_variants("Denmark and Friesland")
        assert "Denmark" in v
        assert "Friesland" in v

    def test_ampersand_separator(self):
        v = _normalize_variants("Balkans & Eastern Europe")
        assert "Balkans" in v
        assert "Eastern Europe" in v

    def test_no_duplicates(self):
        v = _normalize_variants("Italia")
        assert len(v) == len(set(v))


class TestResolutionPath:
    def test_exact(self):
        assert resolution_path("Italia") == "exact"

    def test_normalized(self):
        assert resolution_path("Balkans (Hussite Wars)") == "normalized"

    def test_unmapped(self):
        assert resolution_path("Atlantis") is None

    def test_empty(self):
        assert resolution_path(None) is None
        assert resolution_path("") is None


class TestFindPlaceInText:
    def test_finds_specific_city(self):
        from backend.geo.centroids import find_place_in_text
        c = find_place_in_text(
            "Thessalonica is sold to Venice — the Byzantines cannot defend their second city."
        )
        # Both Thessalonica (40.64, 22.93) and Venice (45.44, 12.34) are
        # in the yaml. Smaller radius wins; both ~30-40km so the
        # left-most (any-stable) is acceptable. Just assert it picks
        # one specific city, not the broad Byzantine Empire.
        assert c is not None
        assert c["radius_km"] <= 50

    def test_returns_smallest_radius(self):
        """When 'Roman' and 'Roman Empire' both match, the smaller
        radius wins. Roman is not a centroid; Rome is. The longest-
        match-first ordering ensures 'Holy Roman Empire' beats 'Rome'."""
        from backend.geo.centroids import find_place_in_text
        c = find_place_in_text("The court at Rome convenes.")
        assert c is not None
        # Rome's radius is 50, Roman Empire is 1500 (broad). Rome wins.
        assert c["radius_km"] <= 100

    def test_no_match_returns_none(self):
        from backend.geo.centroids import find_place_in_text
        assert find_place_in_text("A peaceful day. Nothing happens.") is None

    def test_empty_text(self):
        from backend.geo.centroids import find_place_in_text
        assert find_place_in_text("") is None
        assert find_place_in_text(None) is None

    def test_word_boundary_required(self):
        """'Romeo' shouldn't match 'Rome' as a substring."""
        from backend.geo.centroids import find_place_in_text
        c = find_place_in_text("Romeo whispered to himself in the night.")
        # 'Rome' as substring of 'Romeo' must NOT match. Either no match,
        # or some other word in the text matches (none should here).
        assert c is None or c["radius_km"] != 50  # 50 is Rome's radius


class TestResolveEventLocation:
    def test_prefers_place_in_text_over_region(self):
        from backend.geo.centroids import resolve_event_location
        # Region "Byzantine Empire" has radius 1200 (broad). Summary
        # mentions a specific city (Thessalonica). The city wins.
        c = resolve_event_location(
            "Byzantine Empire",
            "Thessalonica falls to the Ottomans.",
        )
        assert c is not None
        assert c["radius_km"] <= 50  # Thessalonica is 40

    def test_falls_back_to_region_when_no_place(self):
        from backend.geo.centroids import resolve_event_location, resolve_region
        c = resolve_event_location(
            "Italia",
            "A general malaise spreads through the provinces.",
        )
        assert c == resolve_region("Italia")

    def test_handles_none_region_with_place(self):
        from backend.geo.centroids import resolve_event_location
        c = resolve_event_location(None, "The fall of Constantinople.")
        assert c is not None
        # Constantinople radius is 50.
        assert c["radius_km"] <= 50

    def test_returns_none_when_neither_resolves(self):
        from backend.geo.centroids import resolve_event_location
        assert resolve_event_location("Atlantis", "Nothing specific.") is None


class TestJitterPoint:
    def test_zero_for_empty_key(self):
        from backend.geo.centroids import jitter_point
        assert jitter_point(40.0, 12.0, "", 100) == (40.0, 12.0)

    def test_deterministic(self):
        from backend.geo.centroids import jitter_point
        a = jitter_point(40.0, 12.0, "event-42", 100)
        b = jitter_point(40.0, 12.0, "event-42", 100)
        assert a == b

    def test_different_keys_different_points(self):
        from backend.geo.centroids import jitter_point
        a = jitter_point(40.0, 12.0, "event-42", 100)
        b = jitter_point(40.0, 12.0, "event-43", 100)
        assert a != b

    def test_offset_bounded_by_radius(self):
        """A 50km city should jitter by < 1 deg lat (~< 60 km)."""
        from backend.geo.centroids import jitter_point
        for k in ["e1", "e2", "e3", "e4", "e5"]:
            lat, lon = jitter_point(40.0, 12.0, k, 50)
            assert abs(lat - 40.0) < 1.0
            assert abs(lon - 12.0) < 1.5  # cos(40deg) ~ 0.77

    def test_broad_region_jitter_capped(self):
        """A 1500km broad region jitters more than a city, but the
        cap stays under ~1 degree (~100km) so events don't cross
        national boundaries."""
        from backend.geo.centroids import jitter_point
        lat_city, _ = jitter_point(40.0, 12.0, "k", 50)
        lat_broad, _ = jitter_point(40.0, 12.0, "k", 1500)
        assert abs(lat_broad - 40.0) >= abs(lat_city - 40.0)
        # Hard cap: broad regions still under ~1.0 deg lat (~111 km).
        for k in ["a", "b", "c", "d", "e", "f", "g"]:
            lat_b, lon_b = jitter_point(40.0, 12.0, k, 1500)
            assert abs(lat_b - 40.0) < 1.0
            assert abs(lon_b - 12.0) < 1.5
