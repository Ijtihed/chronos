"""Tests for the Phase 3b diorama endpoint.

Covers POST /api/run/{id}/diorama/{turn_id}:

  - threshold gate (significance >= 0.85; below returns 422)
  - 404 when turn_id resolves to no turn-log row at all
  - idempotent: second POST for same turn_id returns existing diorama,
    no LLM call
  - allow-list coercion: LLM emits unknown enum values -> safe defaults
  - empty LLM response -> minimal default diorama with single player figure
  - run-cap (30 dioramas/run)
  - hard cost cap refusal (402)
  - PlayerView surfaces dioramas

The LLM call inside `generate_scene_spec` is monkeypatched so tests
are deterministic and don't hit Gemini.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend import persistence
from backend.llm_schemas import (
    SceneDirectorResponse,
    _SceneCamera,
    _SceneCharacter,
    _SceneMood,
)
from backend.world_state import create_initial_state


# ── helpers ───────────────────────────────────────────────────────────


def _stub_director(monkeypatch, response):
    """Replace backend.main.generate_scene_spec with a fake that
    returns a fixed SceneDirectorResponse."""
    from backend import main as main_mod

    async def _fake(**_kw):
        return response

    monkeypatch.setattr(main_mod, "generate_scene_spec", _fake)


def _basic_response():
    return SceneDirectorResponse(
        location_kind="cloister",
        characters=[
            _SceneCharacter(kind="standing", x=-1, z=0, facing=90, is_player=True),
            _SceneCharacter(kind="robed",    x=1,  z=0, facing=270),
        ],
        camera=_SceneCamera(type="low_orbit_slow", initial_phi=65, distance=4.5),
        mood=_SceneMood(mood="amber_low_light", intensity=0.6),
        summary="You and the abbot in the cloister.",
    )


async def _seed_turn_log(run_id, turn_number, significance):
    await persistence.append_turn_log(
        run_id=run_id,
        turn_number=turn_number,
        player_input="confront the abbot",
        parsed_action={"action_type": "speak", "significance_score": significance},
        ambient_activity=[],
        npc_responses=[
            {"npc_id": "abbot", "npc_name": "Abbot Severus",
             "npc_role": "abbot", "sentiment": "negative",
             "text": "He stiffens, refuses to meet your eye."}
        ],
        state_changes={},
        narrative_output="<p>The abbot would not meet your eyes.</p>",
        player_view_snapshot={},
    )


# ── threshold gate ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_below_threshold_returns_422(client, monkeypatch):
    """A turn with significance < 0.85 must NOT produce a diorama --
    even if the frontend mistakenly POSTs."""
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.50)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 422
    detail = res.json().get("detail") or {}
    if isinstance(detail, dict):
        assert detail.get("code") == "below_threshold"


@pytest.mark.asyncio
async def test_diorama_at_threshold_succeeds(client, monkeypatch):
    """significance == 0.85 is the BOUNDARY value -- it should fire."""
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.85)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 200
    body = res.json()
    assert body["saved"] is True
    d = body["diorama"]
    assert d["location_kind"] == "cloister"
    assert len(d["characters"]) == 2


# ── idempotent ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_idempotent_per_turn(client, monkeypatch):
    """Second POST for the same turn returns the existing diorama
    without spending another LLM call. We can't directly observe
    'no LLM call' here, but `saved=False` + `reason=already_exists`
    is the contract."""
    call_count = {"n": 0}

    async def _fake(**_kw):
        call_count["n"] += 1
        return _basic_response()

    from backend import main as main_mod
    monkeypatch.setattr(main_mod, "generate_scene_spec", _fake)

    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    res1 = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res1.status_code == 200
    assert res1.json()["saved"] is True

    res2 = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["saved"] is False
    assert body2.get("reason") == "already_exists"
    assert call_count["n"] == 1  # second POST didn't call LLM


# ── allow-list coercion ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_allow_list_coercion(client, monkeypatch):
    """LLM emits unknown enum values -> safe defaults. The renderer
    NEVER receives a value outside the allow list."""
    weird = SceneDirectorResponse(
        location_kind="UFO_LANDING_PAD",          # not in allow-list
        characters=[
            _SceneCharacter(kind="LEVITATING", x=99, z=-99, facing=720, is_player=True),
            _SceneCharacter(kind="standing", x=2, z=2),
        ],
        camera=_SceneCamera(type="WHIPLASH_PAN", initial_phi=999, distance=99.0),
        mood=_SceneMood(mood="LASER_RAINBOW", intensity=2.0),
        summary="totally normal moment",
    )
    _stub_director(monkeypatch, weird)
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 200
    d = res.json()["diorama"]
    assert d["location_kind"] == "chamber"
    assert d["characters"][0]["kind"] == "standing"
    assert d["characters"][0]["x"] == 3 or d["characters"][0]["x"] == -3  # clamped
    assert d["camera"]["type"] == "low_orbit_slow"
    assert 20 <= d["camera"]["initial_phi"] <= 85
    assert 2.5 <= d["camera"]["distance"] <= 9.0
    assert d["mood"]["mood"] == "amber_low_light"
    assert 0.0 <= d["mood"]["intensity"] <= 1.0


# ── empty LLM response -> minimal default ─────────────────────────────


@pytest.mark.asyncio
async def test_diorama_empty_response_falls_back(client, monkeypatch):
    """If the LLM returns an empty SceneDirectorResponse (NoOp /
    parse fail / circuit open), the endpoint mints a minimal default
    diorama: chamber + single standing player figure."""
    _stub_director(monkeypatch, SceneDirectorResponse())
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 200
    d = res.json()["diorama"]
    assert d["location_kind"] == "chamber"
    assert len(d["characters"]) == 1
    assert d["characters"][0]["kind"] == "standing"
    assert d["characters"][0]["is_player"] is True


# ── 404 / unknown turn ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_404_unknown_run(client):
    res = await client.post("/api/run/no_such_run/diorama/turn-1")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_diorama_no_turn_logs_404(client, monkeypatch):
    """A run with NO turn_logs at all -> 404. Distinct from the
    'pick the most recent if exact match fails' path."""
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 404


# ── run cap ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_run_cap(client, monkeypatch):
    """At 30 dioramas already on the run, the next POST 400s. The
    cap is sized so a typical 10-turn run hits 1-3, so this only
    fires for very long runs."""
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    # Seed the cap directly. (We don't need real turn-log entries for
    # the existing dioramas -- the cap check fires before the
    # turn-log lookup.)
    from backend.world_state import (
        CameraSpec, CharacterFigure, Diorama, MoodSpec,
    )
    state.dioramas = [
        Diorama(
            source_turn_id=f"turn-{i}",
            location_kind="chamber",
            characters=[CharacterFigure(kind="standing", x=0, z=0, is_player=True)],
            camera=CameraSpec(),
            mood=MoodSpec(),
        )
        for i in range(30)
    ]
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=99, significance=0.92)

    res = await client.post(f"/api/run/{rid}/diorama/turn-99")
    assert res.status_code == 400
    detail = res.json().get("detail") or ""
    # FastAPI HTTPException with a string detail surfaces it as a string.
    assert "cap" in (detail if isinstance(detail, str) else str(detail))


# ── hard cost cap ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_hard_cap_refused(client, monkeypatch):
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    state.cost_cap_state = "hard"
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    assert res.status_code == 402
    detail = res.json().get("detail") or {}
    if isinstance(detail, dict):
        assert detail.get("code") == "cost_cap_hard"


# ── PlayerView surfaces dioramas ──────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_surfaces_in_player_view(client, monkeypatch):
    _stub_director(monkeypatch, _basic_response())
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    await client.post(f"/api/run/{rid}/diorama/turn-1")
    pv = (await client.get(f"/api/run/{rid}")).json()
    assert "dioramas" in pv
    assert len(pv["dioramas"]) == 1
    d = pv["dioramas"][0]
    assert d["source_turn_id"] == "turn-1"
    assert d["location_kind"] == "cloister"


# ── character cap ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diorama_character_cap_at_six(client, monkeypatch):
    """LLM emits 9 characters -> we keep at most 6."""
    too_many = SceneDirectorResponse(
        location_kind="market",
        characters=[
            _SceneCharacter(kind="standing", x=i % 4 - 2, z=(i // 4) - 1)
            for i in range(9)
        ],
    )
    _stub_director(monkeypatch, too_many)
    state = create_initial_state()
    await persistence.save_session(state)
    rid = state.run_id
    await _seed_turn_log(rid, turn_number=1, significance=0.92)

    res = await client.post(f"/api/run/{rid}/diorama/turn-1")
    d = res.json()["diorama"]
    assert len(d["characters"]) == 6
