"""Phase 2.6 (Spatial Substrate) — war-table terrain endpoint smoke tests.

Verifies that GET /api/geo/terrain/{era_key} returns a valid PNG with
the expected bbox headers for every starter era. Intentionally narrow:
the war-table's frontend already validates dimensions, so backend
tests focus on contract (status, content-type, headers, era coverage).

Skips silently if Pillow isn't installed in the test environment so a
fresh checkout doesn't hard-fail before someone has run pip install.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL", reason="Pillow not installed; war-table terrain unavailable")

from fastapi.testclient import TestClient  # noqa: E402

from backend.geo.terrain import ERA_BBOX, get_bbox  # noqa: E402
from backend.main import app  # noqa: E402


client = TestClient(app)


@pytest.mark.parametrize("era_key", list(ERA_BBOX.keys()))
def test_terrain_endpoint_returns_png_for_each_era(era_key: str) -> None:
    resp = client.get(f"/api/geo/terrain/{era_key}")
    assert resp.status_code == 200, f"{era_key}: {resp.status_code}"
    assert resp.headers["content-type"] == "image/png"
    body = resp.content
    # PNG magic bytes.
    assert body[:8] == b"\x89PNG\r\n\x1a\n", f"{era_key}: not a PNG"


@pytest.mark.parametrize("era_key", list(ERA_BBOX.keys()))
def test_terrain_endpoint_includes_bbox_headers(era_key: str) -> None:
    resp = client.get(f"/api/geo/terrain/{era_key}")
    assert resp.status_code == 200
    bbox = get_bbox(era_key)
    assert bbox is not None
    assert float(resp.headers["X-Terrain-Bbox-South"]) == pytest.approx(bbox.south_lat)
    assert float(resp.headers["X-Terrain-Bbox-West"]) == pytest.approx(bbox.west_lon)
    assert float(resp.headers["X-Terrain-Bbox-North"]) == pytest.approx(bbox.north_lat)
    assert float(resp.headers["X-Terrain-Bbox-East"]) == pytest.approx(bbox.east_lon)


def test_terrain_endpoint_unknown_era_404s() -> None:
    resp = client.get("/api/geo/terrain/no_such_era")
    assert resp.status_code == 404


def test_terrain_endpoint_caches_for_a_day() -> None:
    resp = client.get(f"/api/geo/terrain/{next(iter(ERA_BBOX))}")
    assert "Cache-Control" in resp.headers
    assert "max-age=86400" in resp.headers["Cache-Control"]
