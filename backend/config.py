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

GEMINI_3_1_FLASH_LITE_INPUT_PER_M_USD: float = 0.10   # Gemini 2.5 Flash-Lite input
GEMINI_3_1_FLASH_LITE_OUTPUT_PER_M_USD: float = 0.40  # Gemini 2.5 Flash-Lite output

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
# Circuit breaker (Gemini → Ollama fallback)
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
    else:
        log.warning(
            "GEMINI_API_KEY not set — all LLM calls will return NoOp responses. "
            "Set GEMINI_API_KEY in .env to enable Gemini."
        )
