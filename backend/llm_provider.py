"""Unified LLM provider for CHRONOS.

All calls route to Gemini (CHRONOS_GEMINI_MODEL, default gemini-2.5-flash-lite).
The historic fast/quality tier split has been retired — Ollama is no longer used.

The `tier` parameter on `call_llm` is accepted for backward compatibility but
is a no-op; it does not change routing.

Fallback (NoOp):
    When Gemini is unavailable (no key, circuit open, or a call raises), the
    provider returns ("...", UsageInfo(provider="noop", cost_usd=0)) and logs
    a loud WARNING. The circuit breaker still opens after 3 failures in 60s so
    repeated Gemini errors surface immediately rather than silently accumulating.
    Single network blips don't crash turns — the NPC/action text is just empty.

Cost tracking:
    Every call returns a UsageInfo alongside the raw text. Callers ignore
    it; accumulation happens via a ContextVar bucket activated by
    `track_turn_cost()`. This avoids threading UsageInfo through 16 call
    sites.

Design context: see `.cursor/rules/chronos-model-tier.mdc` and
`context/game logic context/roadmap.md` (MODEL TIER POLICY) — this module
is the runtime realization of those policies.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Type

from pydantic import BaseModel

from backend import config

logger = logging.getLogger("chronos.llm")


# Kept for call-site backward compat. Both values are now no-ops — all calls
# go to Gemini regardless of which tier string is passed.
Tier = Literal["quality", "fast"]


# ---------------------------------------------------------------------------
# Usage accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageInfo:
    """Per-call cost + token accounting.

    `cost_usd` is authoritative; EUR conversion happens at render time via
    `config.USD_TO_EUR`.

    provider="noop" marks calls that returned a canned "..." response because
    Gemini was unavailable (no key, circuit open, or a transient error after
    retries). These cost $0 and the turn continues with degraded output.
    """

    provider: Literal["gemini", "noop"]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_s: float


def _gemini_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * config.GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD
        + output_tokens * config.GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD
    ) / 1_000_000.0


# ---------------------------------------------------------------------------
# Per-turn cost bucket (ContextVar)
# ---------------------------------------------------------------------------

_turn_cost_ctx: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "chronos_turn_cost", default=None
)

# Name warnings we've already emitted, so each uncovered call site warns
# at most once per process. Prevents log spam when an endpoint is missing
# the track_turn_cost() wrapper.
_unwrapped_warnings_seen: set[str] = set()


@contextlib.contextmanager
def track_turn_cost():
    """Activate a per-request bucket that collects UsageInfo objects.

    Intended usage at each turn endpoint:

        with track_turn_cost() as bucket:
            ... LLM calls run during the turn ...
        # sum(u.cost_usd for u in bucket) -> state.cumulative_cost_usd
    """
    bucket: list[UsageInfo] = []
    token = _turn_cost_ctx.set(bucket)
    try:
        yield bucket
    finally:
        _turn_cost_ctx.reset(token)


def _record_usage(usage: UsageInfo, call_site: str) -> None:
    bucket = _turn_cost_ctx.get()
    if bucket is None:
        # A call fired outside any track_turn_cost() scope. Cost won't
        # aggregate. Warn at most once per call site so integration bugs
        # surface early.
        if call_site not in _unwrapped_warnings_seen:
            _unwrapped_warnings_seen.add(call_site)
            logger.warning(
                "LLM call from %s fired outside track_turn_cost() — "
                "cost will NOT aggregate into the run total. Wrap the "
                "endpoint handler with track_turn_cost().",
                call_site,
            )
        return
    bucket.append(usage)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class GeminiCircuitBreaker:
    """In-process circuit breaker for Gemini.

    Opens after `FAIL_THRESHOLD` failures inside a rolling `FAIL_WINDOW_S`
    window. Stays open for `OPEN_DURATION_S` after the most recent
    failure, then half-closes (next call is attempted; success closes it,
    failure re-opens it). State is ephemeral — server restart = clean
    slate. This is deliberate, matches the design spec.
    """

    def __init__(
        self,
        fail_threshold: int = config.GEMINI_CIRCUIT_FAIL_THRESHOLD,
        fail_window_s: float = config.GEMINI_CIRCUIT_FAIL_WINDOW_S,
        open_duration_s: float = config.GEMINI_CIRCUIT_OPEN_DURATION_S,
    ) -> None:
        self.fail_threshold = fail_threshold
        self.fail_window_s = fail_window_s
        self.open_duration_s = open_duration_s
        self._failures: list[float] = []
        self._opened_at: Optional[float] = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.open_duration_s:
            logger.info("Gemini circuit CLOSED (half-open window reached)")
            self._opened_at = None
            self._failures.clear()
            return False
        return True

    def record_failure(self, exc: Optional[BaseException] = None) -> None:
        now = time.monotonic()
        cutoff = now - self.fail_window_s
        self._failures = [t for t in self._failures if t >= cutoff]
        self._failures.append(now)
        if (
            self._opened_at is None
            and len(self._failures) >= self.fail_threshold
        ):
            self._opened_at = now
            logger.warning(
                "Gemini circuit OPENED for %.0fs after %d failures in %.0fs. "
                "Last error: %s",
                self.open_duration_s,
                len(self._failures),
                self.fail_window_s,
                exc,
            )

    def record_success(self) -> None:
        if self._opened_at is not None:
            logger.info("Gemini circuit CLOSED (recovery after success)")
        self._opened_at = None
        self._failures.clear()

    def reset(self) -> None:
        self._opened_at = None
        self._failures.clear()


_gemini_circuit = GeminiCircuitBreaker()


# ---------------------------------------------------------------------------
# Gemini client (lazy)
# ---------------------------------------------------------------------------


_gemini_client: Optional[Any] = None
_gemini_semaphore: Optional[asyncio.Semaphore] = None


def _get_gemini_client():
    """Lazy singleton Gemini client. Created on first use."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai  # lazy import so tests can run without deps

        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _gemini_client


def _get_gemini_semaphore() -> asyncio.Semaphore:
    """Per-event-loop semaphore that caps concurrent Gemini requests.

    Recreated if the current loop differs from the last one seen (test
    suites spin up fresh loops per test).
    """
    global _gemini_semaphore
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (shouldn't happen from an async call); fall
        # back to a fresh semaphore, still respecting the hard ceiling.
        return asyncio.Semaphore(config.CHRONOS_GEMINI_MAX_CONCURRENT)

    sem = _gemini_semaphore
    if sem is None or getattr(sem, "_loop", loop) is not loop:
        limit = config.CHRONOS_GEMINI_MAX_CONCURRENT
        # Belt-and-suspenders: ceiling is already enforced in config, but
        # guard here too so a monkeypatch in tests can never exceed it.
        assert limit <= config.GEMINI_MAX_CONCURRENT_CEILING, (
            f"CHRONOS_GEMINI_MAX_CONCURRENT ({limit}) exceeds hard ceiling "
            f"({config.GEMINI_MAX_CONCURRENT_CEILING}) — refusing to create semaphore"
        )
        sem = asyncio.Semaphore(limit)
        sem._loop = loop  # type: ignore[attr-defined]
        _gemini_semaphore = sem
    return sem


def _gemini_transient_retry(exc: BaseException) -> bool:
    """Return True if the error often clears with backoff (retry-safe).

    Google's API sometimes returns API_KEY_INVALID / 'API key expired' on
    rate-limit or burst traffic — retrying after a short sleep succeeds.
    True expired keys will fail all attempts; call_llm then returns a NoOp
    response and the circuit breaker records the failure.
    """
    s = str(exc).lower()
    if "429" in s or "resource exhausted" in s or "quota" in s:
        return True
    if "503" in s or "504" in s or "timeout" in s:
        return True
    if "invalid_argument" in s and "expired" in s:
        return True
    return False


async def _call_gemini(
    prompt: str,
    *,
    schema: Optional[Type[BaseModel]],
    system: Optional[str],
    json_mode: bool,
    timeout_s: float,
) -> tuple[str, UsageInfo]:
    """Make a single Gemini call and return (text, usage).

    Raises on transport / 4xx / 5xx errors after exhausting retries.
    call_llm catches the raise and returns a NoOp response.

    Retries transient errors up to 3 attempts with exponential backoff so
    rate-limit bursts during character_gen fan-out don't immediately trip
    the circuit breaker.
    """
    client = _get_gemini_client()

    gen_config: dict[str, Any] = {}
    if system:
        gen_config["system_instruction"] = system
    if schema is not None:
        gen_config["response_mime_type"] = "application/json"
        gen_config["response_json_schema"] = schema.model_json_schema()
    elif json_mode:
        gen_config["response_mime_type"] = "application/json"

    sem = _get_gemini_semaphore()
    max_attempts = 3
    last_exc: Optional[BaseException] = None
    start_total = time.monotonic()

    for attempt in range(max_attempts):
        try:
            async with sem:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=config.CHRONOS_GEMINI_MODEL,
                        contents=prompt,
                        config=gen_config if gen_config else None,
                    ),
                    timeout=timeout_s,
                )
            duration = time.monotonic() - start_total

            text = response.text or ""

            meta = getattr(response, "usage_metadata", None)
            input_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
            output_tokens = int(getattr(meta, "candidates_token_count", 0) or 0)
            cost_usd = _gemini_cost(input_tokens, output_tokens)

            return text, UsageInfo(
                provider="gemini",
                model=config.CHRONOS_GEMINI_MODEL,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_s=duration,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1 and _gemini_transient_retry(exc):
                delay = 1.5 * (2 ** attempt)
                logger.warning(
                    "Gemini attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_attempts, type(exc).__name__, delay,
                )
                await asyncio.sleep(delay)
                continue
            raise last_exc from None


# ---------------------------------------------------------------------------
# NoOp response (Gemini unavailable — key missing, circuit open, or error)
# ---------------------------------------------------------------------------

_NOOP_USAGE = UsageInfo(
    provider="noop", model="noop",
    input_tokens=0, output_tokens=0, cost_usd=0.0, duration_s=0.0,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_llm(
    prompt: str,
    *,
    tier: Tier = "quality",
    schema: Optional[Type[BaseModel]] = None,
    system: Optional[str] = None,
    json_mode: bool = False,
    timeout_s: float = 120.0,
    call_site: str = "",
) -> tuple[str, UsageInfo]:
    """Execute an LLM call against Gemini.

    Args:
        prompt: The user prompt.
        tier: Deprecated no-op. Accepted for call-site backward compat; all
            calls route to Gemini regardless of this value.
        schema: Optional Pydantic model class for structured JSON output
            (response_json_schema on the Gemini path).
        system: Optional system prompt.
        json_mode: Request JSON-shaped output without a specific schema.
            Overridden by `schema` if both are provided.
        timeout_s: Per-call timeout in seconds.
        call_site: Short identifier used in warning logs when a call fires
            outside a track_turn_cost() scope (e.g. "npc_pov",
            "action_parser"). Optional but recommended.

    Returns:
        (raw_text, UsageInfo). On Gemini failure returns ("...", noop_usage)
        and logs a WARNING — turns continue with degraded output rather than
        crashing.
    """
    effective_json_mode = json_mode or schema is not None

    if config.GEMINI_API_KEY and not _gemini_circuit.is_open():
        try:
            text, usage = await _call_gemini(
                prompt,
                schema=schema,
                system=system,
                json_mode=effective_json_mode,
                timeout_s=timeout_s,
            )
            _gemini_circuit.record_success()
            _record_usage(usage, call_site or "unknown")
            return text, usage
        except asyncio.CancelledError:
            # Client disconnect / task cancel — propagate immediately so the
            # Gemini request is cancelled cleanly. Not a circuit failure.
            raise
        except Exception as exc:
            _gemini_circuit.record_failure(exc)
            logger.warning(
                "Gemini call failed at call_site=%s (%s: %s) — returning NoOp "
                "response; turn continues with degraded output.",
                call_site or "unknown", type(exc).__name__, exc,
            )
    elif not config.GEMINI_API_KEY:
        logger.error(
            "GEMINI_API_KEY is not set — returning NoOp for call_site=%s. "
            "Set GEMINI_API_KEY in .env to enable Gemini.",
            call_site or "unknown",
        )
    else:
        logger.warning(
            "Gemini circuit breaker is open — returning NoOp for call_site=%s.",
            call_site or "unknown",
        )

    _record_usage(_NOOP_USAGE, call_site or "unknown")
    return "...", _NOOP_USAGE


# ---------------------------------------------------------------------------
# Prompt loader (preserved from old backend/llm.py)
# ---------------------------------------------------------------------------


def load_prompt(path: Path) -> str:
    """Load a prompt template, stripping the metadata header above the first '---'."""
    text = path.read_text()
    parts = text.split("\n---\n", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


async def gemini_ok() -> tuple[bool, str]:
    """Startup smoke test for Gemini.

    Generates a tiny response to verify the key works and the model
    responds. Returns (success, detail_message).

    If GEMINI_API_KEY is unset, returns (False, "no key") — this is
    normal, not an error, just means the quality tier is disabled.
    """
    if not config.GEMINI_API_KEY:
        return False, "GEMINI_API_KEY not set"
    try:
        client = _get_gemini_client()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=config.CHRONOS_GEMINI_MODEL,
                contents="ping",
                config={"max_output_tokens": 5},
            ),
            timeout=10.0,
        )
        text = (response.text or "").strip()
        return True, f"ok ({len(text)} chars returned)"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
