"""Region centroid resolution for map visualization.

Loads backend/geo/region_centroids.yaml once at module import, caches,
and provides resolve_region() with exact-match + normalization
fallback.  Returns None for unmapped regions; callers skip those
events rather than erroring.

Normalization fallback handles compound region strings from the
Events DB ingestion, e.g.:
    "Byzantine Empire/Anatolia"         -> "Byzantine Empire"
    "Balkans (Hussite Wars)"            -> "Balkans"
    "Ottoman Empire, Wallachia"         -> "Ottoman Empire"
    "Italy, and Bologna"                -> "Italy"

The polity_context column exists in the historical_events schema but
is NULL for all rows, so there is no DB-side fallback.  If future
ingestion populates it, resolve_region_with_context() can layer on
top without changing the base resolver.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, TypedDict

import yaml

logger = logging.getLogger("chronos.geo.centroids")

_YAML_PATH = Path(__file__).parent / "region_centroids.yaml"


class Centroid(TypedDict):
    lat: float
    lon: float
    radius_km: float
    broad: bool


@lru_cache(maxsize=1)
def load_centroids() -> dict[str, Centroid]:
    """Load and cache the centroid map.

    Raises ValueError if the YAML file is not a mapping or if any
    entry is missing required keys.  Surfaces at module-import time
    for the caller (not at first lookup) so problems are caught early.
    """
    text = _YAML_PATH.read_text()
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(
            f"{_YAML_PATH} must be a YAML mapping, got {type(raw).__name__}"
        )

    out: dict[str, Centroid] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            logger.warning("Skipping non-dict entry for %r", name)
            continue
        try:
            out[name] = {
                "lat": float(entry["lat"]),
                "lon": float(entry["lon"]),
                "radius_km": float(entry["radius_km"]),
                "broad": bool(entry.get("broad", False)),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Malformed centroid entry for {name!r}: {exc}"
            )

    logger.info("Loaded %d region centroids from %s", len(out), _YAML_PATH.name)
    return out


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _normalize_variants(region: str) -> list[str]:
    """Generate candidate keys for a compound region string, in order.

    Strategy:
      1. original string
      2. strip parenthetical annotations ("Balkans (Ottoman Empire)" -> "Balkans")
      3. split on "/" and "," and try each part left-to-right (after
         paren-stripping), trimming whitespace and dropping empties
    """
    candidates = [region]
    stripped = _PAREN_RE.sub("", region).strip()
    if stripped and stripped != region:
        candidates.append(stripped)
    # Split on "/", ",", and " and " / " & ".  Ingestion emits all four.
    parts = [stripped]
    for sep_re in _SPLIT_REGEXES:
        parts = [p for chunk in parts for p in sep_re.split(chunk)]
    for part in (p.strip() for p in parts):
        if not part or part.lower() in _CONNECTIVES:
            continue
        if part not in candidates:
            candidates.append(part)
    return candidates


_CONNECTIVES = frozenset({"and", "or"})

_SPLIT_REGEXES = [
    re.compile(r"\s*/\s*"),
    re.compile(r"\s*,\s*"),
    re.compile(r"\s+and\s+", re.IGNORECASE),
    re.compile(r"\s*&\s*"),
]

# Historical-naming aliases. The events DB carries Latin / English /
# native-language variants ("Italia" vs "Italy", "Byzantium" vs
# "Byzantine Empire"). The same map lives in main.py for event-region
# matching; keep them in sync. Keys are lowercase; the resolver
# matches case-insensitively against the original variant *and* the
# alias-rewritten form.
_REGION_ALIAS_REWRITES: dict[str, str] = {
    "europa": "Europe",
    "european": "Europe",
    "italy": "Italia",
    "italian": "Italia",
    "byzantium": "Byzantine Empire",
    "francia": "France",
    "frankish": "France",
    "gaul": "France",
    "gallia": "France",
    "germany": "Germania",
    "german": "Germania",
    "britain": "Britannia",
    "british": "Britannia",
    "england": "Britannia",
    "english": "Britannia",
    "spain": "Hispania",
    "spanish": "Hispania",
    "iberia": "Hispania",
    "iberian": "Hispania",
    "greek": "Greece",
    "hellenic": "Greece",
    "hellas": "Greece",
    "nordic": "Scandinavia",
    "scandinavian": "Scandinavia",
    "palestine": "Levant",
    "syria": "Levant",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_unmapped_logged: set[str] = set()


def resolve_region(region: Optional[str]) -> Optional[Centroid]:
    """Look up a region's centroid.  None if no variant matches.

    Tries exact match first, then strips parentheticals, then splits
    on "/" and "," and tries each part left-to-right.  Each variant
    is also rewritten through the historical-naming alias map so
    "Europa" -> "Europe", "Italy" -> "Italia", etc.  Logs unmapped
    regions once per string for dev visibility (debug level).
    """
    if not region:
        return None
    centroids = load_centroids()
    for key in _normalize_variants(region):
        if key in centroids:
            return centroids[key]
        # Alias rewrite (case-insensitive). Lets the resolver follow
        # the same Latin/English aliasing the events_visible endpoint
        # uses, instead of every YAML entry having to list every
        # historical spelling.
        rewritten = _REGION_ALIAS_REWRITES.get(key.lower())
        if rewritten and rewritten in centroids:
            return centroids[rewritten]
    if region not in _unmapped_logged:
        logger.debug("Unmapped region: %r", region)
        _unmapped_logged.add(region)
    return None


# ---------------------------------------------------------------------------
# Event-text place extraction
#
# Most historical events in the corpus are tagged with a broad region
# ("Byzantine Empire", "Italia") but the text mentions a specific
# place ("Thessalonica sold to Venice...", "outside the gates of
# Hexamilion"). Scanning the summary for known centroid names lets us
# place the event near the specific city instead of the broad
# region's geometric centroid, where every event would otherwise
# stack on a single point.
#
# Strategy:
#   1. Tokenize all centroid names; build a longest-first list of
#      candidate keys for prefix matching.
#   2. Iterate centroid names in length order, longest first, and
#      look for an exact whole-word match in the summary.
#   3. Among matches, pick the one with the smallest radius_km
#      (i.e. most specific). Cities (radius ~30-80km) beat regions
#      (radius ~400km) which beat broad areas (radius_km >= 1000,
#      flagged broad: true).
#   4. Fall back to the region-only resolver if no place is found.
#
# Performance: the candidate list is sorted once and cached. Each
# event scan is O(N centroids) string-contains, fine for ~120 entries.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _place_lookup_keys() -> list[str]:
    """Return centroid names sorted by length descending so that
    'Holy Roman Empire' is checked before 'Roman' before 'Rome'."""
    return sorted(load_centroids().keys(), key=lambda k: -len(k))


_WORD_BOUND_CACHE: dict[str, "re.Pattern[str]"] = {}


def _word_pattern(name: str) -> "re.Pattern[str]":
    """Return a cached case-insensitive whole-word regex for `name`."""
    pat = _WORD_BOUND_CACHE.get(name)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        _WORD_BOUND_CACHE[name] = pat
    return pat


def find_place_in_text(text: Optional[str]) -> Optional[Centroid]:
    """Look for a known centroid name as a whole word in `text`.

    Returns the most specific (smallest-radius) match. Used by callers
    that have an event summary and want a per-event place rather than
    a per-region centroid.
    """
    if not text:
        return None
    centroids = load_centroids()
    matches: list[tuple[float, Centroid]] = []
    for name in _place_lookup_keys():
        if _word_pattern(name).search(text):
            matches.append((centroids[name]["radius_km"], centroids[name]))
    if not matches:
        return None
    # Smallest radius first — the most specific named place wins.
    matches.sort(key=lambda t: t[0])
    return matches[0][1]


def resolve_event_location(
    region: Optional[str],
    summary: Optional[str] = None,
) -> Optional[Centroid]:
    """Resolve an event's coordinates with progressive precision.

    Order of preference:
      1. Specific place mentioned in `summary` (city, named region).
      2. Region centroid (existing resolve_region behavior).

    Returns None if neither yields a centroid. Callers that don't have
    a summary keep using resolve_region directly.
    """
    place = find_place_in_text(summary)
    if place is not None:
        # If the event is tagged with a small region, prefer that
        # only when the summary's place lookup would land somewhere
        # broader. Otherwise the place-in-text wins.
        region_resolved = resolve_region(region)
        if region_resolved is None:
            return place
        if place["radius_km"] <= region_resolved["radius_km"]:
            return place
        return region_resolved
    return resolve_region(region)


# ---------------------------------------------------------------------------
# Deterministic jitter
#
# Even after place extraction, many events still resolve to the same
# region centroid (e.g. "the Byzantine Empire is collapsing" with no
# city named). Without offset they stack on one pixel and read as a
# single super-saturated dot. A small deterministic angular offset
# keyed by a stable identifier spreads them visibly while keeping
# repeated requests stable (no random-walk between turns).
# ---------------------------------------------------------------------------

import hashlib
import math


def jitter_point(
    lat: float, lon: float, key: str, radius_km: float,
) -> tuple[float, float]:
    """Return a deterministic offset of (lat, lon) keyed by `key`.

    The offset varies in angle and magnitude with the hash of `key`.
    Same key + same radius -> same offset every time.

    Magnitude tuning notes (apr 2026):
      - Small regions (cities, ~30-200km radius) jitter by <= 10-30km.
        Radius/6 keeps events clearly inside the region.
      - Broad regions (~1000km+) used to jitter up to 250km. That
        leaks events into the wrong polity (Rome-to-Naples is 250km).
        Cap shrunk to 100km for broad regions, with a sub-linear curve
        so multi-event clusters still spread visibly without crossing
        national boundaries.
      - Floor at 8km so a 50km city still spreads its events apart.
    """
    if not key:
        return lat, lon
    h = hashlib.md5(key.encode("utf-8")).digest()
    angle = (h[0] / 256.0) * 2 * math.pi
    radial = (h[1] / 256.0)
    if radius_km >= 800:
        # Broad regions: tight cap so events don't cross polities.
        drift_km = min(100.0, max(15.0, radius_km / 12.0)) * radial
    else:
        drift_km = min(60.0, max(6.0, radius_km / 6.0)) * radial
    dlat = (drift_km / 111.0) * math.sin(angle)
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    dlon = (drift_km / (111.0 * cos_lat)) * math.cos(angle)
    return lat + dlat, lon + dlon


def resolution_path(region: Optional[str]) -> Optional[str]:
    """Classify how a region resolved, for coverage diagnostics.

    Returns one of: "exact", "normalized", or None if unresolved.
    Used by the coverage-stats script, not in hot paths.
    """
    if not region:
        return None
    centroids = load_centroids()
    variants = _normalize_variants(region)
    if not variants:
        return None
    if variants[0] in centroids:
        return "exact"
    for key in variants[1:]:
        if key in centroids:
            return "normalized"
    return None
