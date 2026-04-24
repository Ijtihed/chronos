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
