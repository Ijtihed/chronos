"""Tests for the Phase 2.9 pinboard endpoints.

Coverage targets the user-facing contract:

  POST /api/run/{id}/pin       — single pin creation + classification
  POST /api/run/{id}/pinboard  — bulk update with partial-update
                                 semantics (positions, deletes,
                                 connection upserts, cuts)
  GET  /api/run/{id}           — surfaces pins + pin_connections via
                                 PlayerView (replacing the corridor's
                                 board_state / cut_threads)
  POST /api/run/{id}/board     — 410 Gone shim with a redirect message

The classifier (`backend.pin_classifier.classify_pin_source`) is exercised
end-to-end via POST /pin against a fresh run. The "told_by", "rumor",
and "observed" branches are covered by seeding turn_logs rows directly
(the classifier reads from there, not from WorldState).
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from backend import persistence
from backend.world_state import create_initial_state


# ── Plain plumbing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pinboard_starts_empty(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.get(f"/api/run/{rid}")
    assert res.status_code == 200
    body = res.json()
    assert "pins" in body
    assert "pin_connections" in body
    assert body["pins"] == []
    assert body["pin_connections"] == []


@pytest.mark.asyncio
async def test_old_board_endpoint_returns_410(client: AsyncClient) -> None:
    """POST /board must fail loudly with a Gone response, not silently
    appear to work. The frontend was changed to call /pinboard instead;
    any client still pointing at /board is buggy and should know."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.post(
        f"/api/run/{rid}/board",
        json={"board_state": {"x": {"x": 1.0, "y": 2.0, "z": 3.0}}},
    )
    assert res.status_code == 410
    detail = res.json().get("detail") or ""
    assert "/pinboard" in detail or "/pin" in detail


# ── Single-pin creation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_pin_minimal(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.post(
        f"/api/run/{rid}/pin",
        json={"text": "the abbot would not look me in the eye"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["saved"] is True
    pin = body["pin"]
    assert pin["text"] == "the abbot would not look me in the eye"
    assert pin["source_confidence"] in {"observed", "told_by", "rumor", "inferred"}
    # Empty source_turn_id classifies as "inferred" (no logs).
    assert pin["source_confidence"] == "inferred"

    # GET round-trips it.
    pv = (await client.get(f"/api/run/{rid}")).json()
    assert len(pv["pins"]) == 1


@pytest.mark.asyncio
async def test_create_pin_rejects_empty_text(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.post(f"/api/run/{rid}/pin", json={"text": "   "})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_create_pin_intro_source_is_observed(client: AsyncClient) -> None:
    """source_turn_id == 'manuscript-intro' is treated as observed
    without consulting turn_logs (the character knows their own
    background)."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.post(
        f"/api/run/{rid}/pin",
        json={
            "text": "you are a minor provincial administrator",
            "source_turn_id": "manuscript-intro",
        },
    )
    assert res.status_code == 200
    pin = res.json()["pin"]
    assert pin["source_confidence"] == "observed"


@pytest.mark.asyncio
async def test_create_pin_classifies_told_by(client: AsyncClient) -> None:
    """Seed a turn_log with an NPC response that contains the pin text;
    classifier should label `told_by` and surface the NPC name."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    # Insert a fake turn-log row with an NPC response containing
    # "the garrison has not been paid in three months". The frontend
    # will pin the source_turn_id as "turn-<turn_number>" in this
    # test (any of the candidate id shapes the classifier accepts).
    await persistence.append_turn_log(
        run_id=rid,
        turn_number=1,
        player_input="ask the centurion about pay",
        parsed_action={"action_type": "speak"},
        ambient_activity=[],
        npc_responses=[
            {
                "npc_id": "lucius_gallus",
                "npc_name": "Lucius Gallus",
                "text": "The garrison has not been paid in three months.",
            }
        ],
        state_changes={},
        narrative_output="<p>The centurion looks tired.</p>",
        player_view_snapshot={},
    )

    res = await client.post(
        f"/api/run/{rid}/pin",
        json={
            "text": "garrison has not been paid in three months",
            "source_turn_id": "turn-1",
        },
    )
    assert res.status_code == 200
    pin = res.json()["pin"]
    assert pin["source_confidence"] == "told_by"
    assert pin["source_attribution"] == "Lucius Gallus"


@pytest.mark.asyncio
async def test_create_pin_classifies_rumor(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    await persistence.append_turn_log(
        run_id=rid,
        turn_number=1,
        player_input="walk the market",
        parsed_action={"action_type": "move"},
        ambient_activity=[
            {
                "npc_id": "anon",
                "npc_name": "Anon",
                "activity": "Two merchants whisper that the praetor accepted a bribe.",
                "interacts_with": None,
            }
        ],
        npc_responses=[],
        state_changes={},
        narrative_output="<p>You overhear voices in the crowd.</p>",
        player_view_snapshot={},
    )

    res = await client.post(
        f"/api/run/{rid}/pin",
        json={
            "text": "the praetor accepted a bribe",
            "source_turn_id": "turn-1",
        },
    )
    pin = res.json()["pin"]
    assert pin["source_confidence"] == "rumor"
    assert pin["source_attribution"] == ""


@pytest.mark.asyncio
async def test_create_pin_classifies_observed(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    await persistence.append_turn_log(
        run_id=rid,
        turn_number=1,
        player_input="walk to the gate",
        parsed_action={"action_type": "move"},
        ambient_activity=[],
        npc_responses=[],
        state_changes={},
        narrative_output=(
            "You walk to the gate. Rain has soaked through the thresholds; "
            "the wood smells of mildew."
        ),
        player_view_snapshot={},
    )

    res = await client.post(
        f"/api/run/{rid}/pin",
        json={
            "text": "the wood smells of mildew",
            "source_turn_id": "turn-1",
        },
    )
    pin = res.json()["pin"]
    assert pin["source_confidence"] == "observed"


# ── Bulk pinboard updates ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pinboard_position_update(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={"pin_positions": [{"id": a["id"], "x": 100.5, "y": -42.0}]},
    )
    assert res.status_code == 200
    pv = (await client.get(f"/api/run/{rid}")).json()
    moved = next(p for p in pv["pins"] if p["id"] == a["id"])
    assert moved["x"] == 100.5
    assert moved["y"] == -42.0


@pytest.mark.asyncio
async def test_pinboard_create_and_cut_connection(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    b = (await client.post(f"/api/run/{rid}/pin", json={"text": "beta"})).json()["pin"]

    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={
            "pin_connections": [
                {"from_pin_id": a["id"], "to_pin_id": b["id"], "kind": "player"}
            ]
        },
    )
    assert res.status_code == 200
    assert res.json()["connection_count"] == 1

    pv = (await client.get(f"/api/run/{rid}")).json()
    conn = pv["pin_connections"][0]
    assert conn["from_pin_id"] == a["id"]
    assert conn["to_pin_id"] == b["id"]
    assert conn["cut"] is False

    # Cut by id.
    res2 = await client.post(
        f"/api/run/{rid}/pinboard",
        json={"cut_connection_ids": [conn["id"]]},
    )
    assert res2.json()["cut_count"] == 1


@pytest.mark.asyncio
async def test_pinboard_dedup_connections(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    b = (await client.post(f"/api/run/{rid}/pin", json={"text": "beta"})).json()["pin"]

    payload = {
        "pin_connections": [
            {"from_pin_id": a["id"], "to_pin_id": b["id"]},
            {"from_pin_id": a["id"], "to_pin_id": b["id"]},  # exact dup
            {"from_pin_id": b["id"], "to_pin_id": a["id"]},  # reverse dup
        ]
    }
    res = await client.post(f"/api/run/{rid}/pinboard", json=payload)
    assert res.status_code == 200
    assert res.json()["connection_count"] == 1


@pytest.mark.asyncio
async def test_pinboard_delete_pin_drops_orphaned_connections(
    client: AsyncClient,
) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    b = (await client.post(f"/api/run/{rid}/pin", json={"text": "beta"})).json()["pin"]
    await client.post(
        f"/api/run/{rid}/pinboard",
        json={"pin_connections": [{"from_pin_id": a["id"], "to_pin_id": b["id"]}]},
    )

    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={"delete_pin_ids": [a["id"]]},
    )
    body = res.json()
    assert body["pin_count"] == 1  # only b survives
    assert body["connection_count"] == 0  # the a<->b edge is orphaned, dropped


@pytest.mark.asyncio
async def test_pinboard_partial_update_preserves_other_field(
    client: AsyncClient,
) -> None:
    """Posting only pin_positions must NOT touch pin_connections, and
    vice versa. This is the core semantic that makes the endpoint
    safe to call from independent UI events."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    b = (await client.post(f"/api/run/{rid}/pin", json={"text": "beta"})).json()["pin"]
    await client.post(
        f"/api/run/{rid}/pinboard",
        json={"pin_connections": [{"from_pin_id": a["id"], "to_pin_id": b["id"]}]},
    )

    # Position-only update: connection must survive.
    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={"pin_positions": [{"id": a["id"], "x": 5.0, "y": 5.0}]},
    )
    assert res.json()["connection_count"] == 1


@pytest.mark.asyncio
async def test_pinboard_rejects_orphan_connection(client: AsyncClient) -> None:
    """A connection referencing a non-existent pin id is dropped, not
    saved -- prevents the panel from rendering a line that points at
    nothing."""
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={
            "pin_connections": [
                {"from_pin_id": a["id"], "to_pin_id": "ghost_id_1234"}
            ]
        },
    )
    assert res.status_code == 200
    assert res.json()["connection_count"] == 0


@pytest.mark.asyncio
async def test_pinboard_rejects_self_connection(client: AsyncClient) -> None:
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    a = (await client.post(f"/api/run/{rid}/pin", json={"text": "alpha"})).json()["pin"]
    res = await client.post(
        f"/api/run/{rid}/pinboard",
        json={"pin_connections": [{"from_pin_id": a["id"], "to_pin_id": a["id"]}]},
    )
    assert res.status_code == 200
    assert res.json()["connection_count"] == 0


@pytest.mark.asyncio
async def test_pinboard_404_unknown_run(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run/does_not_exist/pinboard",
        json={"pin_positions": []},
    )
    assert res.status_code == 404
