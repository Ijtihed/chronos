"""End-to-end integration tests for LLM provider cost tracking.

Verifies that a full turn pipeline correctly:

  * accumulates usage into state.cumulative_cost_usd via ContextVar
  * persists turn_cost_usd into the turn_logs table
  * surfaces cost_usd / cost_eur / cost_cap_state in the player_view
  * transitions through cap states: none → soft_crossed → hard
  * blocks further turns with 402 once hard cap is crossed
    (tested across all 5 turn-advancing endpoints / paths)

Patches call_llm directly so tests run offline without a real Gemini key.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend import config
from backend import llm_provider
from backend import main as main_module
from backend.llm_provider import UsageInfo, _NOOP_USAGE
from backend.persistence import get_turn_logs


def _make_noop_call_llm():
    """Return an AsyncMock for call_llm that always returns a NoOp."""
    return AsyncMock(return_value=("...", _NOOP_USAGE))


def _make_fake_call_llm(cost_per_call: float = 0.000675):
    """Return an async callable that injects synthetic Gemini cost per call.

    Unlike a plain AsyncMock, this also calls _record_usage so the cost
    actually lands in the active track_turn_cost() ContextVar bucket.
    """
    usage = UsageInfo(
        provider="gemini", model="gemini-2.5-flash-lite",
        input_tokens=1500, output_tokens=200,
        cost_usd=cost_per_call, duration_s=0.1,
    )

    async def _fake(prompt, **kw):
        from backend.llm_provider import _record_usage
        _record_usage(usage, kw.get("call_site", "fake"))
        return "mock narrative text", usage

    return _fake


class TestCostTrackingEndToEnd:
    @pytest.mark.asyncio
    async def test_noop_turn_yields_zero_cost(self, client, monkeypatch):
        """When call_llm returns NoOp ($0), cost stays 0 in player_view."""
        noop = _make_noop_call_llm()
        monkeypatch.setattr(llm_provider, "call_llm", noop)
        for mod in ("backend.npc_engine", "backend.world_engine",
                    "backend.hce", "backend.action_parser",
                    "backend.death_engine", "backend.character_gen"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid = (await client.post("/api/run")).json()["run_id"]
        resp = await client.post(
            f"/api/run/{rid}/turn", json={"player_input": "speak"},
        )
        assert resp.status_code == 200
        pv = resp.json()["player_view"]
        assert pv["cost_usd"] == 0.0
        assert pv["cost_cap_state"] == "none"
        logs = await get_turn_logs(rid)
        assert logs
        assert logs[-1]["turn_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_gemini_call_accumulates_cost(self, client, monkeypatch):
        """Injected Gemini cost lands in cumulative_cost_usd + player_view + turn_logs."""
        fake = _make_fake_call_llm(0.000675)
        monkeypatch.setattr(llm_provider, "call_llm", fake)
        for mod in ("backend.npc_engine", "backend.world_engine",
                    "backend.hce", "backend.action_parser",
                    "backend.death_engine", "backend.character_gen"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", fake)
            except AttributeError:
                pass

        rid = (await client.post("/api/run")).json()["run_id"]
        resp = await client.post(
            f"/api/run/{rid}/turn", json={"player_input": "speak"},
        )
        assert resp.status_code == 200
        pv = resp.json()["player_view"]
        assert pv["cost_usd"] > 0.0
        assert pv["cost_eur"] == pytest.approx(
            pv["cost_usd"] * config.USD_TO_EUR, rel=1e-6,
        )
        logs = await get_turn_logs(rid)
        # turn_cost_usd is the per-turn delta; pv["cost_usd"] is cumulative
        # (includes run-creation cost), so delta ≤ cumulative and both > 0.
        assert logs[-1]["turn_cost_usd"] > 0.0
        assert logs[-1]["turn_cost_usd"] <= pv["cost_usd"]

    @pytest.mark.asyncio
    async def test_cap_state_surfaces_in_player_view(self, client):
        """Soft-crossed cap_state flows into player_view correctly."""
        rid = (await client.post("/api/run")).json()["run_id"]

        from backend.persistence import load_session, save_session

        state = await load_session(rid)
        state.cost_cap_state = "soft_crossed"
        state.cumulative_cost_usd = 1.10  # ~€1.01
        await save_session(state)

        resp = await client.get(f"/api/run/{rid}")
        assert resp.status_code == 200
        pv = resp.json()
        assert pv["cost_cap_state"] == "soft_crossed"
        assert pv["cost_usd"] == pytest.approx(1.10)
        assert pv["cost_cap_soft_eur"] == config.COST_CAP_SOFT_EUR
        assert pv["cost_cap_hard_eur"] == config.COST_CAP_HARD_EUR


class TestFinalizeAndCapEnforcement:
    """Unit-level checks on _finalize_turn_cost + _enforce_cost_caps that
    complement the end-to-end tests above."""

    def test_finalize_sums_bucket_and_updates_state(self):
        from backend.world_state import create_initial_state

        state = create_initial_state()
        bucket = [
            UsageInfo("gemini", "x", 1, 1, 0.25, 0.1),
            UsageInfo("gemini", "x", 1, 1, 0.10, 0.1),
            UsageInfo("noop", "noop", 0, 0, 0.0, 0.0),
        ]
        delta = main_module._finalize_turn_cost(state, bucket)
        assert delta == pytest.approx(0.35)
        assert state.cumulative_cost_usd == pytest.approx(0.35)

    def test_finalize_crosses_soft_cap(self):
        from backend.world_state import create_initial_state

        state = create_initial_state()
        state.cumulative_cost_usd = 0.90 / config.USD_TO_EUR
        bucket = [
            UsageInfo(
                "gemini", "x", 1, 1,
                0.20 / config.USD_TO_EUR,  # pushes total over €1.00
                0.1,
            ),
        ]
        main_module._finalize_turn_cost(state, bucket)
        assert state.cost_cap_state == "soft_crossed"

    def test_finalize_crosses_hard_cap(self):
        from backend.world_state import create_initial_state

        state = create_initial_state()
        state.cumulative_cost_usd = 1.90 / config.USD_TO_EUR
        state.cost_cap_state = "soft_crossed"
        bucket = [
            UsageInfo(
                "gemini", "x", 1, 1,
                0.20 / config.USD_TO_EUR,
                0.1,
            ),
        ]
        main_module._finalize_turn_cost(state, bucket)
        assert state.cost_cap_state == "hard"


# ---------------------------------------------------------------------------
# Hard-cap 402 gate — five turn-advancing paths
# ---------------------------------------------------------------------------


class TestHardCapGate:
    """For each turn-advancing endpoint / dispatch path, verify:

    * Response is 402
    * Body has code="cost_cap_hard"
    * state.turn did not increment
    * No LLM call was made (mock assert_not_called or call count unchanged)
    """

    async def _capped_run(self, client) -> tuple[str, int]:
        """Create a run, force cap=hard, return (run_id, original_turn)."""
        rid = (await client.post("/api/run")).json()["run_id"]
        from backend.persistence import load_session, save_session
        state = await load_session(rid)
        original_turn = state.turn
        state.cost_cap_state = "hard"
        state.cumulative_cost_usd = config.COST_CAP_HARD_EUR / config.USD_TO_EUR + 0.50
        await save_session(state)
        return rid, original_turn

    @pytest.mark.asyncio
    async def test_turn_active_hard_cap_returns_402(self, client, monkeypatch):
        """/turn with active run + hard cap → 402, no LLM call during turn, turn unchanged."""
        noop = _make_noop_call_llm()
        for mod in ("backend.llm_provider", "backend.npc_engine",
                    "backend.world_engine", "backend.hce",
                    "backend.action_parser", "backend.death_engine"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid, original_turn = await self._capped_run(client)
        # Clear calls made during run creation (generate_run) before asserting.
        noop.reset_mock()
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "speak"})

        assert resp.status_code == 402
        d = resp.json()["detail"]
        assert d["code"] == "cost_cap_hard"
        assert d["cost_eur"] >= config.COST_CAP_HARD_EUR
        noop.assert_not_called()
        from backend.persistence import load_session
        state = await load_session(rid)
        assert state.turn == original_turn

    @pytest.mark.asyncio
    async def test_turn_dead_observing_hard_cap_returns_402(self, client, monkeypatch):
        """/turn with dead_observing + hard cap → 402 (newly enforced path)."""
        noop = _make_noop_call_llm()
        for mod in ("backend.llm_provider", "backend.npc_engine",
                    "backend.world_engine", "backend.hce",
                    "backend.action_parser", "backend.death_engine"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid, _ = await self._capped_run(client)
        noop.reset_mock()

        from backend.persistence import load_session, save_session
        state = await load_session(rid)
        state.run_status = "dead_observing"
        await save_session(state)

        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "wait"})

        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "cost_cap_hard"
        noop.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_hard_cap_returns_402(self, client, monkeypatch):
        """/skip with hard cap → 402, no LLM call during skip."""
        noop = _make_noop_call_llm()
        for mod in ("backend.llm_provider", "backend.npc_engine",
                    "backend.world_engine", "backend.hce"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid, _ = await self._capped_run(client)
        noop.reset_mock()
        resp = await client.post(f"/api/run/{rid}/skip", json={"ticks": 1})

        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "cost_cap_hard"
        noop.assert_not_called()

    @pytest.mark.asyncio
    async def test_travel_path_hard_cap_returns_402(self, client, monkeypatch):
        """Travel-intent input with hard cap → 402 at entry gate, no LLM call, turn unchanged."""
        noop = _make_noop_call_llm()
        for mod in ("backend.llm_provider", "backend.npc_engine",
                    "backend.world_engine", "backend.hce",
                    "backend.action_parser", "backend.death_engine"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid, original_turn = await self._capped_run(client)
        noop.reset_mock()
        resp = await client.post(
            f"/api/run/{rid}/turn", json={"player_input": "travel north to the next city"},
        )

        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "cost_cap_hard"
        noop.assert_not_called()
        from backend.persistence import load_session
        state = await load_session(rid)
        assert state.turn == original_turn

    @pytest.mark.asyncio
    async def test_inaction_path_hard_cap_returns_402(self, client, monkeypatch):
        """Inaction-intent input with hard cap → 402 at entry gate, no LLM call, turn unchanged."""
        noop = _make_noop_call_llm()
        for mod in ("backend.llm_provider", "backend.npc_engine",
                    "backend.world_engine", "backend.hce",
                    "backend.action_parser", "backend.death_engine"):
            try:
                monkeypatch.setattr(f"{mod}.call_llm", noop)
            except AttributeError:
                pass

        rid, original_turn = await self._capped_run(client)
        noop.reset_mock()
        resp = await client.post(
            f"/api/run/{rid}/turn", json={"player_input": "wait and do nothing"},
        )

        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "cost_cap_hard"
        noop.assert_not_called()
        from backend.persistence import load_session
        state = await load_session(rid)
        assert state.turn == original_turn
