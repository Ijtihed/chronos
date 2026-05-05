"""Phase 2.8 -- detective board persistence endpoint smoke tests.

Verifies that POST /api/run/{run_id}/board:
  * round-trips a valid board_state through state + into player_view
  * sanitizes NaN / +Inf coordinates rather than persisting them
  * 404s on an unknown run_id

Offline-only -- patches no LLM since the endpoint never calls one.
"""

from __future__ import annotations

import math

import pytest
from httpx import AsyncClient

from backend import persistence
from backend.world_state import create_initial_state


@pytest.mark.asyncio
async def test_board_state_roundtrip(client: AsyncClient) -> None:
    """A valid board_state POSTed to /board comes back via GET /run/{id}."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    payload = {
        "board_state": {
            "turn-1700000001": {"x": 1.5, "y": 2.0, "z": 3.0},
            "turn-1700000002": {"x": -4.0, "y": 0.5, "z": 9.0},
            "manuscript-intro": {"x": 0.0, "y": 0.0, "z": 12.0},
        }
    }
    res = await client.post(f"/api/run/{rid}/board", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["saved"] is True
    assert body["page_count"] == 3

    # Round-trip via the run endpoint -- player_view should carry the
    # board_state we just wrote.
    pv_res = await client.get(f"/api/run/{rid}")
    assert pv_res.status_code == 200
    pv = pv_res.json()
    assert "board_state" in pv
    bs = pv["board_state"]
    assert "turn-1700000001" in bs
    assert bs["turn-1700000001"]["x"] == pytest.approx(1.5)
    assert bs["turn-1700000001"]["z"] == pytest.approx(3.0)
    assert bs["manuscript-intro"]["z"] == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_board_state_sanitizes_non_finite(client: AsyncClient) -> None:
    """NaN / Infinity coords get dropped; valid neighbors stay."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    payload = {
        "board_state": {
            "turn-good": {"x": 1.0, "y": 2.0, "z": 3.0},
            # NaN -- should be dropped wholesale (entry has invalid coord).
            "turn-nan": {"x": float("nan"), "y": 0.0, "z": 0.0},
            # +Inf -- same.
            "turn-inf": {"x": 0.0, "y": float("inf"), "z": 0.0},
            # Beyond clamp range -- kept but clamped to 50.
            "turn-far": {"x": 9999.0, "y": 0.0, "z": 0.0},
        }
    }
    # JSON encoding NaN / Infinity needs allow_nan=True (httpx default).
    # We hand-craft the raw JSON to be sure.
    import json as _json
    raw = _json.dumps(payload)
    # Standard json doesn't emit NaN by default; httpx posts with json= which
    # uses orjson/std json. Use the raw string body to ensure NaN reaches us.
    res = await client.post(
        f"/api/run/{rid}/board",
        content=raw.replace('"NaN"', "NaN"),  # no-op normally; defensive
        headers={"Content-Type": "application/json"},
    )
    # FastAPI's pydantic v2 may reject non-finite values during request
    # parsing rather than handing them to our sanitizer. Either is fine
    # for the design intent; we just need to confirm bad data NEVER ends
    # up in the persisted state.
    if res.status_code != 200:
        # Pydantic rejected before our handler. State stays empty.
        pv = (await client.get(f"/api/run/{rid}")).json()
        assert pv["board_state"] == {}
        return
    body = res.json()
    # If parsing succeeded, our sanitizer must have stripped the
    # non-finite entries.
    assert body["page_count"] <= 2  # turn-good + clamped turn-far at most
    pv = (await client.get(f"/api/run/{rid}")).json()
    bs = pv["board_state"]
    assert "turn-good" in bs
    assert "turn-nan" not in bs
    assert "turn-inf" not in bs
    if "turn-far" in bs:
        # Clamp respected.
        assert bs["turn-far"]["x"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_board_state_unknown_run_404(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run/no_such_run_id/board",
        json={"board_state": {}},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_board_state_empty_payload_clears(client: AsyncClient) -> None:
    """POST {} clears any prior board_state -- the player resetting."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    # Seed something.
    await client.post(
        f"/api/run/{rid}/board",
        json={"board_state": {"turn-x": {"x": 1.0, "y": 1.0, "z": 1.0}}},
    )
    # Then clear.
    res = await client.post(f"/api/run/{rid}/board", json={"board_state": {}})
    assert res.status_code == 200
    assert res.json()["page_count"] == 0
    pv = (await client.get(f"/api/run/{rid}")).json()
    assert pv["board_state"] == {}
