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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_unmapped_logged: set[str] = set()


def resolve_region(region: Optional[str]) -> Optional[Centroid]:
    """Look up a region's centroid.  None if no variant matches.

    Tries exact match first, then strips parentheticals, then splits
    on "/" and "," and tries each part left-to-right.  Logs unmapped
    regions once per string for dev visibility (debug level).
    """
    if not region:
        return None
    centroids = load_centroids()
    for key in _normalize_variants(region):
        if key in centroids:
            return centroids[key]
    if region not in _unmapped_logged:
        logger.debug("Unmapped region: %r", region)
        _unmapped_logged.add(region)
    return None


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
