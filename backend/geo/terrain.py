"""
Phase 2.6 (Spatial Substrate) — DEM heightmap service for the war-table.

Serves a per-era DEM (Digital Elevation Model) PNG clipped to the era's
regional bounding box. The frontend war-table reads this PNG as a
displacement texture for its terrain mesh.

Honest limitation (2026-05-04 kickoff):
    Real DEM data (NASA SRTM 30m or OpenTopography) is not bundled
    in this commit. The endpoint generates a PROCEDURAL heightmap
    from low-frequency noise so the war-table pipeline (endpoint,
    Three.js scene, raycast, marker shadows, border extrusion) can
    be validated end-to-end without a 40MB asset drop.

    A follow-up session will:
      1. Add a build-time script that pulls real SRTM tiles per era
         bounding box, downsamples to 1024x1024, writes 16-bit PNG to
         frontend/geo/terrain/<era>.png .
      2. Switch this endpoint to read the cached PNG when present and
         fall back to the procedural source when it's not.

    The endpoint *contract* is stable. The frontend doesn't need to
    change when real data lands — it already reads grayscale heights.

Per-era bounding boxes are hand-curated here to match the regional
play area for each era. The numbers mirror the ERA_FRAMING table in
frontend/globe.js so the war-table sits where the player would expect
when toggling from the globe.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import NamedTuple

# Pillow is the only image library guaranteed by the existing
# requirements (used elsewhere in scripts). We use it as PIL.Image.
from PIL import Image  # type: ignore[import-not-found]


# Per-era regional bounding box, in lat/lon degrees.
#
# Format: (south_lat, west_lon, north_lat, east_lon)
#
# Curated to comfortably contain each era's playable region plus a
# reasonable visual margin (so the table edge isn't right against the
# action). Sized to keep the aspect roughly readable when projected
# onto a square mesh.
class BBox(NamedTuple):
    south_lat: float
    west_lon: float
    north_lat: float
    east_lon: float


ERA_BBOX: dict[str, BBox] = {
    "roman_late_empire": BBox(36.0, 5.0, 48.0, 22.0),
    "viking_age": BBox(50.0, -10.0, 70.0, 25.0),
    "crusader_states": BBox(28.0, 30.0, 40.0, 42.0),
    "black_death": BBox(40.0, 0.0, 52.0, 18.0),
    "fall_of_constantinople": BBox(36.0, 22.0, 46.0, 35.0),
}


# Output resolution. 1024x1024 keeps the PNG ~1MB after compression
# and is enough detail for the visual register the war-table needs.
# Bumping past 2048 would buy almost nothing because the frontend
# downsamples to its mesh resolution anyway.
TILE_PIXELS = 1024


# Cache directory for real DEM data when (later) baked offline.
_REAL_DEM_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "geo" / "terrain"


def _hash_2d(x: int, y: int, seed: int) -> float:
    """Deterministic [0, 1) noise from a 2D integer cell + seed.

    Cheap integer hash, no numpy dependency, stable across calls so
    the procedural terrain looks identical on every request.
    """
    h = (x * 374761393) ^ (y * 668265263) ^ (seed * 2147483647)
    h = (h ^ (h >> 13)) * 1274126177
    h &= 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def _smooth_noise(x: float, y: float, seed: int) -> float:
    """Bilinear-interpolated value noise sample at floating-point (x, y)."""
    xi = math.floor(x)
    yi = math.floor(y)
    xf = x - xi
    yf = y - yi
    # 5th-order smoothstep for quintic interpolation.
    sx = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
    sy = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
    n00 = _hash_2d(xi, yi, seed)
    n10 = _hash_2d(xi + 1, yi, seed)
    n01 = _hash_2d(xi, yi + 1, seed)
    n11 = _hash_2d(xi + 1, yi + 1, seed)
    nx0 = n00 * (1 - sx) + n10 * sx
    nx1 = n01 * (1 - sx) + n11 * sx
    return nx0 * (1 - sy) + nx1 * sy


def _fbm(x: float, y: float, seed: int, octaves: int = 5) -> float:
    """Fractal Brownian motion — sums octaves of value noise.

    Returns a value in [0, 1) approximately. We use 5 octaves which
    gives mountain-ridge-scale variation at the bbox extent without
    looking obviously tiled.
    """
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0
    for _ in range(octaves):
        total += _smooth_noise(x * frequency, y * frequency, seed) * amplitude
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm if norm > 0 else 0.0


def _generate_procedural_dem(
    bbox: BBox,
    pixels: int = TILE_PIXELS,
    seed: int = 1337,
) -> bytes:
    """Generate a procedural 8-bit grayscale heightmap PNG.

    Real DEMs (16-bit) carry more height precision; for the war-table's
    visual scale (peaks of 200-2000 m squashed into a small tabletop
    surface) 8-bit is plenty. When we swap to real SRTM data we'll
    bump to 16-bit for honesty.

    Returns PNG bytes.
    """
    img = Image.new("L", (pixels, pixels), 0)
    px = img.load()
    if px is None:
        # Pillow returns None only if the image is unrealized; defensively
        # construct via raw bytes instead.
        img = Image.frombytes("L", (pixels, pixels), bytes(pixels * pixels))
        px = img.load()

    # Map the bbox to a normalized [0, scale) noise domain so terrain
    # frequency feels right regardless of how big the bbox is. ~6
    # noise cells across the bbox is the sweet spot for "looks like
    # mountains, not pixel garbage".
    scale_x = 6.0
    scale_y = 6.0 * (bbox.north_lat - bbox.south_lat) / max(0.001, bbox.east_lon - bbox.west_lon)

    for j in range(pixels):
        # Top of image is north_lat by convention.
        nyf = (j / pixels) * scale_y
        for i in range(pixels):
            nxf = (i / pixels) * scale_x
            h = _fbm(nxf, nyf, seed)
            # Add a low-frequency continental bump so we get a
            # gradient across the table rather than uniformly busy noise.
            cont = 0.55 + 0.45 * _smooth_noise(nxf * 0.25, nyf * 0.25, seed + 7)
            v = max(0.0, min(1.0, h * 0.55 + cont * 0.45))
            assert px is not None  # narrowing for the type-checker
            px[i, j] = int(v * 255)  # type: ignore[index]

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def get_terrain_png(era_key: str) -> bytes:
    """Return PNG bytes for the era's DEM tile.

    Prefers a baked file at frontend/geo/terrain/<era_key>.png if
    present (the future real-DEM path). Falls back to a deterministic
    procedural generator so the endpoint is never empty.

    Raises KeyError if the era is unknown.
    """
    if era_key not in ERA_BBOX:
        raise KeyError(era_key)

    real = _REAL_DEM_DIR / f"{era_key}.png"
    if real.exists():
        return real.read_bytes()

    return _generate_procedural_dem(ERA_BBOX[era_key])


def get_bbox(era_key: str) -> BBox | None:
    return ERA_BBOX.get(era_key)
