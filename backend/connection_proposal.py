"""Connection-proposal generator (Phase 2.10).

When the player has accumulated >= 3 unconnected pins on the pinboard
and >= 2 turns have passed since the last propose call, the orchestrator
walks the same-turn pin pairs and asks Gemini Flash Lite for a single
one-sentence claim per pair. Each claim is written to a new connection
with `kind = "auto_proposed"`; the player adjudicates (agree / edit /
reject) in the pinboard popup.

Per chronos-model-tier.mdc the call site is logged as
`call_site="connection_proposal"` for cost accounting. Per-call cost
estimate: ~120 input tokens + ~30 output tokens = ~$0.00006. With the
threshold gate, a 10-turn run typically yields 2-4 proposals, so
~$0.0001-$0.0003 per run -- well below the €0.022 median target.

Failure mode: NoOp ("...") falls back per the global llm_provider
contract; the orchestrator sees an empty claim and skips the pair.
The pinboard never blocks on this call.

This module does NOT decide WHICH pairs to propose -- that's the
orchestrator's job (it owns the tombstone check, the same-turn
filter, and the threshold gate). This module only knows how to ask
the LLM for a single claim given two pins.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from typing import Optional

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import ConnectionProposalResponse
from backend.world_state import Pin

logger = logging.getLogger("chronos.connection_proposal")

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "connection_proposal.md"
)
_TEMPLATE_CACHE: Optional[str] = None


def _load_template() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = load_prompt(_TEMPLATE_PATH)
    return _TEMPLATE_CACHE


async def generate_connection_proposal(
    pin_a: Pin,
    pin_b: Pin,
    turn_label: str = "",
) -> str:
    """Ask Gemini for a one-sentence claim linking two pins.

    Returns:
        A trimmed claim string. Empty string means "no connection";
        the caller should NOT write a proposal in that case. Empty
        is also returned on any failure -- the pinboard remains
        whatever it was before the call.
    """
    if not pin_a or not pin_b:
        return ""
    if not pin_a.text or not pin_b.text:
        return ""

    template = Template(_load_template())
    prompt = template.safe_substitute(
        turn_label=(turn_label or "this turn"),
        pin_a_text=pin_a.text,
        pin_a_confidence=pin_a.source_confidence or "inferred",
        pin_a_attribution=pin_a.source_attribution or "",
        pin_b_text=pin_b.text,
        pin_b_confidence=pin_b.source_confidence or "inferred",
        pin_b_attribution=pin_b.source_attribution or "",
    )

    raw = ""
    try:
        raw, _ = await call_llm(
            prompt,
            schema=ConnectionProposalResponse,
            call_site="connection_proposal",
            timeout_s=10.0,
        )
        if not raw:
            return ""
        # NoOp fallback emits "..." on llm_provider's degraded path.
        if raw.strip() in {"...", "…"}:
            return ""
        from backend.utils import strip_json_fences
        parsed = ConnectionProposalResponse.model_validate(json.loads(strip_json_fences(raw)))
        claim = (parsed.claim or "").strip()
        if not claim or claim in {"...", "…"}:
            return ""
        return claim
    except json.JSONDecodeError as exc:
        logger.warning(
            "connection_proposal JSON decode failed: %s; raw=%r",
            exc,
            raw[:120] if raw else "",
        )
        return ""
    except Exception as exc:  # noqa: BLE001 — never block the pinboard on this
        logger.warning("connection_proposal generation failed: %s", exc)
        return ""
