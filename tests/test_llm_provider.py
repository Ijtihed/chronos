"""Tests for the all-Gemini LLM provider.

Covers:
  * Circuit breaker open/close/half-close transitions
  * Gemini cost calculation against known token counts
  * Cost-cap state transitions (none → soft_crossed → hard)
  * Routing: all calls go to Gemini when key present
  * NoOp fallback: returned when Gemini raises, key missing, or circuit open
  * `tier` parameter is a no-op — doesn't change routing
  * ContextVar bucket: accumulates UsageInfo; warns when inactive
  * Concurrency semaphore: caps concurrent Gemini requests
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import config, llm_provider
from backend.llm_provider import (
    GeminiCircuitBreaker,
    UsageInfo,
    _gemini_cost,
    call_llm,
    track_turn_cost,
)


# ---------------------------------------------------------------------------
# Pricing / cost calc
# ---------------------------------------------------------------------------


class TestGeminiCostCalculation:
    def test_zero_tokens_is_zero(self):
        assert _gemini_cost(0, 0) == 0.0

    def test_input_only(self):
        # 1M input tokens at config.GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD / M
        assert _gemini_cost(1_000_000, 0) == pytest.approx(
            config.GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD
        )

    def test_output_only(self):
        assert _gemini_cost(0, 1_000_000) == pytest.approx(
            config.GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD
        )

    def test_mixed_known_total(self):
        exp = (
            10_000 * config.GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD
            + 4_000 * config.GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD
        ) / 1_000_000
        assert _gemini_cost(10_000, 4_000) == pytest.approx(exp)

    def test_typical_turn_estimate(self):
        # Ballpark: one autonomous_action call ~ 1500 in, 200 out
        exp = (
            1_500 * config.GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD
            + 200 * config.GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD
        ) / 1_000_000
        assert _gemini_cost(1_500, 200) == pytest.approx(exp)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = GeminiCircuitBreaker()
        assert not cb.is_open()

    def test_opens_at_threshold(self):
        cb = GeminiCircuitBreaker(fail_threshold=3, fail_window_s=60.0)
        cb.record_failure(RuntimeError("a"))
        cb.record_failure(RuntimeError("b"))
        assert not cb.is_open()
        cb.record_failure(RuntimeError("c"))
        assert cb.is_open()

    def test_success_clears_failures(self):
        cb = GeminiCircuitBreaker(fail_threshold=3)
        cb.record_failure(None)
        cb.record_failure(None)
        cb.record_success()
        cb.record_failure(None)
        cb.record_failure(None)
        assert not cb.is_open()

    def test_reopens_after_open_duration(self):
        cb = GeminiCircuitBreaker(
            fail_threshold=1, fail_window_s=60.0, open_duration_s=0.01,
        )
        cb.record_failure(None)
        assert cb.is_open()
        import time
        time.sleep(0.02)
        # After the open window expires, is_open() half-closes the circuit.
        assert not cb.is_open()

    def test_failures_outside_window_dont_count(self):
        cb = GeminiCircuitBreaker(
            fail_threshold=2, fail_window_s=0.01,
        )
        cb.record_failure(None)
        import time
        time.sleep(0.02)
        cb.record_failure(None)
        # The first failure aged out; only one in-window → not open.
        assert not cb.is_open()

    def test_reset_clears_state(self):
        cb = GeminiCircuitBreaker(fail_threshold=1)
        cb.record_failure(None)
        assert cb.is_open()
        cb.reset()
        assert not cb.is_open()


# ---------------------------------------------------------------------------
# Cost cap state transitions (exercises main._enforce_cost_caps)
# ---------------------------------------------------------------------------


class TestCostCapStateTransitions:
    def _make_state(self, cost_usd: float = 0.0, cap_state: str = "none"):
        # Minimal mock — _enforce_cost_caps only reads run_id, cost,
        # cap_state and logs.
        s = MagicMock()
        s.run_id = "test_run"
        s.cumulative_cost_usd = cost_usd
        s.cost_cap_state = cap_state
        return s

    def test_below_soft_stays_none(self):
        from backend.main import _enforce_cost_caps

        s = self._make_state(cost_usd=0.5 / config.USD_TO_EUR)  # ~€0.46
        _enforce_cost_caps(s)
        assert s.cost_cap_state == "none"

    def test_crosses_soft_cap(self):
        from backend.main import _enforce_cost_caps

        # €1.05 worth of USD
        usd = 1.05 / config.USD_TO_EUR
        s = self._make_state(cost_usd=usd, cap_state="none")
        _enforce_cost_caps(s)
        assert s.cost_cap_state == "soft_crossed"

    def test_crosses_hard_cap(self):
        from backend.main import _enforce_cost_caps

        usd = 2.10 / config.USD_TO_EUR
        s = self._make_state(cost_usd=usd, cap_state="soft_crossed")
        _enforce_cost_caps(s)
        assert s.cost_cap_state == "hard"

    def test_hard_is_terminal(self):
        """Hard cap shouldn't degrade back to soft_crossed even if cost decreases."""
        from backend.main import _enforce_cost_caps

        usd = 0.5 / config.USD_TO_EUR
        s = self._make_state(cost_usd=usd, cap_state="hard")
        _enforce_cost_caps(s)
        assert s.cost_cap_state == "hard"

    def test_soft_to_hard_skips_none(self):
        from backend.main import _enforce_cost_caps

        usd = 2.10 / config.USD_TO_EUR
        s = self._make_state(cost_usd=usd, cap_state="none")
        _enforce_cost_caps(s)
        assert s.cost_cap_state == "hard"


# ---------------------------------------------------------------------------
# track_turn_cost bucket
# ---------------------------------------------------------------------------


class TestTrackTurnCost:
    def test_activates_bucket(self):
        usage = UsageInfo(
            provider="gemini", model="m", input_tokens=100,
            output_tokens=50, cost_usd=0.001, duration_s=0.1,
        )
        with track_turn_cost() as bucket:
            llm_provider._record_usage(usage, "test")
        assert len(bucket) == 1
        assert bucket[0] is usage

    def test_multiple_calls_aggregate(self):
        u1 = UsageInfo("gemini", "m", 1, 1, 0.01, 0.1)
        u2 = UsageInfo("noop", "noop", 0, 0, 0.0, 0.0)
        with track_turn_cost() as bucket:
            llm_provider._record_usage(u1, "a")
            llm_provider._record_usage(u2, "b")
        assert len(bucket) == 2
        assert sum(u.cost_usd for u in bucket) == pytest.approx(0.01)

    def test_warns_when_no_bucket_active(self, caplog):
        llm_provider._unwrapped_warnings_seen.clear()
        u = UsageInfo("noop", "noop", 0, 0, 0.0, 0.0)
        import logging
        with caplog.at_level(logging.WARNING, logger="chronos.llm"):
            llm_provider._record_usage(u, "unique_warn_site_xyz")
        assert any(
            "unique_warn_site_xyz" in r.message for r in caplog.records
        )

    def test_warn_is_deduped_per_site(self, caplog):
        llm_provider._unwrapped_warnings_seen.clear()
        u = UsageInfo("noop", "noop", 0, 0, 0.0, 0.0)
        import logging
        with caplog.at_level(logging.WARNING, logger="chronos.llm"):
            llm_provider._record_usage(u, "dedup_site_xyz")
            llm_provider._record_usage(u, "dedup_site_xyz")
            llm_provider._record_usage(u, "dedup_site_xyz")
        count = sum(
            1 for r in caplog.records if "dedup_site_xyz" in r.message
        )
        assert count == 1


# ---------------------------------------------------------------------------
# Routing — all-Gemini + NoOp fallback
# ---------------------------------------------------------------------------


class TestTierRouting:
    @pytest.fixture(autouse=True)
    def reset_circuit(self):
        llm_provider._gemini_circuit.reset()
        yield
        llm_provider._gemini_circuit.reset()

    @pytest.mark.asyncio
    async def test_routes_to_gemini_when_key_present(self):
        """When GEMINI_API_KEY is set, calls go to Gemini."""
        mock_gemini = AsyncMock(return_value=(
            "gemini response",
            UsageInfo("gemini", "x", 100, 50, 0.001, 0.2),
        ))
        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with track_turn_cost():
                text, usage = await call_llm("hi", tier="quality", call_site="test")
        assert text == "gemini response"
        assert usage.provider == "gemini"
        mock_gemini.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tier_param_is_noop(self):
        """Both tier='fast' and tier='quality' route to Gemini."""
        mock_gemini = AsyncMock(return_value=(
            "gemini", UsageInfo("gemini", "x", 1, 1, 0.0, 0.1),
        ))
        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with track_turn_cost():
                await call_llm("hi", tier="fast", call_site="test")
                await call_llm("hi", tier="quality", call_site="test")
        assert mock_gemini.await_count == 2

    @pytest.mark.asyncio
    async def test_no_key_returns_noop(self):
        """No GEMINI_API_KEY → NoOp response, no Gemini call."""
        mock_gemini = AsyncMock()
        with patch.object(config, "GEMINI_API_KEY", None), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with track_turn_cost() as bucket:
                text, usage = await call_llm("hi", tier="quality", call_site="test")
        assert text == "..."
        assert usage.provider == "noop"
        assert usage.cost_usd == 0.0
        mock_gemini.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gemini_failure_returns_noop(self):
        """Gemini raise → NoOp response, circuit records the failure."""
        mock_gemini = AsyncMock(side_effect=RuntimeError("transient"))
        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with track_turn_cost() as bucket:
                text, usage = await call_llm("hi", tier="quality", call_site="test")
        assert text == "..."
        assert usage.provider == "noop"
        assert len(llm_provider._gemini_circuit._failures) == 1

    @pytest.mark.asyncio
    async def test_open_circuit_skips_gemini_returns_noop(self):
        """When the circuit is already open, Gemini is never attempted."""
        mock_gemini = AsyncMock()
        for _ in range(config.GEMINI_CIRCUIT_FAIL_THRESHOLD):
            llm_provider._gemini_circuit.record_failure(RuntimeError("x"))
        assert llm_provider._gemini_circuit.is_open()
        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with track_turn_cost():
                text, usage = await call_llm("hi", tier="quality", call_site="test")
        assert text == "..."
        assert usage.provider == "noop"
        mock_gemini.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gemini_cancellation_does_not_open_circuit(self):
        """CancelledError propagates without recording a circuit failure."""
        mock_gemini = AsyncMock(side_effect=asyncio.CancelledError())
        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(llm_provider, "_call_gemini", mock_gemini):
            with pytest.raises(asyncio.CancelledError):
                with track_turn_cost():
                    await call_llm("hi", tier="quality", call_site="test")
        assert len(llm_provider._gemini_circuit._failures) == 0


# ---------------------------------------------------------------------------
# Semaphore / concurrency cap
# ---------------------------------------------------------------------------


class TestGeminiSemaphore:
    @pytest.mark.asyncio
    async def test_semaphore_caps_concurrent_requests(self):
        """With max_concurrent=2 and 10 pending calls, only 2 run at once."""

        in_flight = 0
        peak = 0

        async def fake_generate_content(*, model, contents, config=None):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            resp = MagicMock()
            resp.text = "ok"
            meta = MagicMock()
            meta.prompt_token_count = 10
            meta.candidates_token_count = 5
            resp.usage_metadata = meta
            return resp

        fake_client = MagicMock()
        fake_client.aio.models.generate_content = AsyncMock(
            side_effect=fake_generate_content
        )

        with patch.object(config, "GEMINI_API_KEY", "fake_key"), \
             patch.object(config, "CHRONOS_GEMINI_MAX_CONCURRENT", 2), \
             patch.object(config, "GEMINI_MAX_CONCURRENT_CEILING", 20), \
             patch.object(llm_provider, "_gemini_client", fake_client), \
             patch.object(llm_provider, "_gemini_semaphore", None):
            llm_provider._gemini_circuit.reset()
            with track_turn_cost():
                await asyncio.gather(
                    *[
                        call_llm("hi", tier="quality", call_site="test")
                        for _ in range(10)
                    ]
                )
        assert peak <= 2, f"peak concurrency was {peak}, expected <= 2"
