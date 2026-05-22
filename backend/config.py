"""Runtime configuration for CHRONOS.

Reads environment variables (and `.env` if present) for LLM provider
selection, model IDs, cost caps, and feature flags.

Values here are read **once** at module import. Downstream code imports
them by name; tests can monkeypatch the module attributes when needed.

Model tier policy and cost cap values live in
`.cursor/rules/chronos-model-tier.mdc` and
`context/game logic context/roadmap.md`. This module is the runtime
realization of those docs — if the two disagree, the docs win.
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path

try:
    from dotenv import load_dotenv
    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)
except ImportError:
    pass

logger = logging.getLogger("chronos.config")


# ---------------------------------------------------------------------------
# Global random seed (opt-in, for reproducibility)
# ---------------------------------------------------------------------------
#
# world_drift, world_events, npc_personality, character_gen, eras, and
# world_engine all reach for `random` at module load and at runtime.
# Production play wants real randomness — the world should feel different
# every run. Tests and reproducible-bug investigations want determinism.
#
# `CHRONOS_RANDOM_SEED` opt-in: set to any integer (e.g. `42`) and we
# seed Python's global `random` at config import. Unset = real entropy.
# Setting it to "0" still counts as a seed (0 is a valid seed); only an
# unset / empty value means "don't touch the seed".
#
# This is the lightest possible change that lets tests pin behaviour
# without rewriting every `random.foo()` call site to thread a Random
# instance.

_RAW_SEED = os.environ.get("CHRONOS_RANDOM_SEED", "").strip()
CHRONOS_RANDOM_SEED: int | None = None
if _RAW_SEED:
    try:
        CHRONOS_RANDOM_SEED = int(_RAW_SEED)
        random.seed(CHRONOS_RANDOM_SEED)
        logger.info(
            "CHRONOS_RANDOM_SEED set to %d -- world drift / events are deterministic this process",
            CHRONOS_RANDOM_SEED,
        )
    except ValueError:
        logger.warning(
            "CHRONOS_RANDOM_SEED=%r is not an integer; ignoring (using system entropy).",
            _RAW_SEED,
        )


# ---------------------------------------------------------------------------
# Gemini (quality tier)
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str | None = (os.environ.get("GEMINI_API_KEY") or "").strip() or None

# Model name sent to the Gemini API. CHRONOS_QUALITY_MODEL is accepted as a
# deprecated alias for one migration cycle; use CHRONOS_GEMINI_MODEL going forward.
CHRONOS_GEMINI_MODEL: str = (
    os.environ.get("CHRONOS_GEMINI_MODEL")
    or os.environ.get("CHRONOS_QUALITY_MODEL")
    or "gemini-2.5-flash-lite"
)
# Flag for startup_log deprecation warning (true if only old name was set).
_QUALITY_MODEL_NAME_DEPRECATED: bool = bool(
    os.environ.get("CHRONOS_QUALITY_MODEL") and not os.environ.get("CHRONOS_GEMINI_MODEL")
)

# Hard ceiling on concurrent in-flight Gemini requests.
# Paid tier (300 RPM) comfortably absorbs 15 concurrent; ceiling is 20.
# No env var can push above the ceiling — enforced here AND asserted in
# _get_gemini_semaphore().
GEMINI_MAX_CONCURRENT_CEILING: int = 20
CHRONOS_GEMINI_MAX_CONCURRENT: int = min(
    GEMINI_MAX_CONCURRENT_CEILING,
    int(os.environ.get("CHRONOS_GEMINI_MAX_CONCURRENT", "15")),
)


# ---------------------------------------------------------------------------
# Pricing (Flash-Lite family)
# ---------------------------------------------------------------------------
#
# Gemini 3.1 Flash-Lite: $0.25 / $1.50 per M input / output (preview
# tier, account-gated — not available on every API key). The default
# CHRONOS_QUALITY_MODEL points here when the preview is accessible.
#
# Gemini 2.5 Flash-Lite: $0.10 / $0.40 per M input / output (stable,
# GA, usable with any AI Studio key). Used in practice when the 3.1
# preview is gated from generateContent.
#
# The _PER_M constants below match whichever model is *actually* set
# in CHRONOS_QUALITY_MODEL. If you change models, update both rows.

GEMINI_INPUT_PER_M_USD: float = 0.10   # Gemini 2.5 Flash-Lite input
GEMINI_OUTPUT_PER_M_USD: float = 0.40  # Gemini 2.5 Flash-Lite output

# Legacy aliases (used in llm_provider and tests; kept for backward compat)
GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD = GEMINI_INPUT_PER_M_USD
GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD = GEMINI_OUTPUT_PER_M_USD

# TODO: Update from ECB reference rate periodically. If EUR/USD volatility
# exceeds ±5% (e.g. rate moves to 0.85 or 0.99), recompute the soft/hard
# caps in EUR or switch accounting to USD throughout. The caps are in EUR
# but the underlying billing is USD, so forex drift silently shifts the
# real cap.
USD_TO_EUR: float = 0.92


# ---------------------------------------------------------------------------
# Per-run cost caps (EUR)
# ---------------------------------------------------------------------------

COST_CAP_SOFT_EUR: float = 1.00
COST_CAP_HARD_EUR: float = 2.00


# ---------------------------------------------------------------------------
# Circuit breaker (Gemini → NoOp fallback)
# ---------------------------------------------------------------------------

GEMINI_CIRCUIT_FAIL_THRESHOLD: int = 3
GEMINI_CIRCUIT_FAIL_WINDOW_S: float = 60.0
GEMINI_CIRCUIT_OPEN_DURATION_S: float = 300.0


# ---------------------------------------------------------------------------
# Startup logging
# ---------------------------------------------------------------------------

def startup_log(log: logging.Logger | None = None) -> None:
    """Log effective LLM configuration at server startup.

    Never logs the API key value — only whether one is present.

    Also surfaces a loud warning when the configured model name doesn't
    match the pricing constants — per chronos-model-tier policy, the
    two have to move together so cost accounting stays honest. Without
    this, switching to a preview model silently undercounts cost by 2-3x.
    """
    log = log or logger
    if _QUALITY_MODEL_NAME_DEPRECATED:
        log.warning(
            "CHRONOS_QUALITY_MODEL is deprecated; rename to CHRONOS_GEMINI_MODEL "
            "in your .env. The value is still honoured this cycle."
        )
    if GEMINI_API_KEY:
        log.info(
            "Gemini provider enabled: model=%s, max_concurrent=%d",
            CHRONOS_GEMINI_MODEL,
            CHRONOS_GEMINI_MAX_CONCURRENT,
        )
        # Pricing-vs-model coherence check. The price-per-million tokens
        # are hand-set to gemini-2.5-flash-lite by default; if the operator
        # switches CHRONOS_GEMINI_MODEL to a preview model with different
        # pricing, they MUST also update the constants below or the
        # per-run cost cap silently shifts. We warn loudly rather than
        # asserting: a preview-pricing key with stale constants will be
        # *under*-counted, which lets the run blow past the EUR cap.
        is_25_pricing = (
            abs(GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD - 0.10) < 1e-6
            and abs(GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD - 0.40) < 1e-6
        )
        if CHRONOS_GEMINI_MODEL != "gemini-2.5-flash-lite" and is_25_pricing:
            log.warning(
                "Model=%s but pricing constants are tuned for "
                "gemini-2.5-flash-lite ($0.10 / $0.40 per M). Cost accounting "
                "may be wrong by 2-3x; update "
                "GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD / "
                "GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD in backend/config.py "
                "to match the model you're actually using, OR switch back "
                "to gemini-2.5-flash-lite.",
                CHRONOS_GEMINI_MODEL,
            )
    else:
        log.warning(
            "GEMINI_API_KEY not set — all LLM calls will return NoOp responses. "
            "Set GEMINI_API_KEY in .env to enable Gemini."
        )
