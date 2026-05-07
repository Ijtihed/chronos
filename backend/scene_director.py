"""Scene-director generator (Phase 3b).

When a turn fires with `parsed_action.significance_score >= 0.85`, the
orchestrator calls this module to produce a structured spec for a
**diorama** -- a stylized 3D vignette that will be inset inline in the
player's manuscript. Silhouette characters, low-poly setting, slow
camera orbit. Reads like a memory.

This module does NOT decide WHEN to fire (that's the endpoint's job);
it only knows how to ask Gemini for the spec given a turn-log row and
the current world state. The endpoint converts the LLM response into
a `Diorama` (the canonical persisted form), applying allow-lists to
drop unknown enum values.

Per chronos-model-tier.mdc, the call site is logged as
`call_site="scene_director"` for cost accounting. Per-call estimate:
~250 input + ~80 output tokens = ~$0.0001. Per typical run with the
0.85 threshold gate: ~$0.0002.

Failure mode: NoOp falls back per the global llm_provider contract;
the orchestrator gets an empty spec and writes a minimal default
diorama (chamber + single standing player) so the manuscript still
shows *something* between turn-blocks. We never block the turn on
this call.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

from backend.llm_provider import call_llm
from backend.llm_schemas import SceneDirectorResponse

logger = logging.getLogger("chronos.scene_director")

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "scene_director.md"
)
_TEMPLATE_CACHE: Optional[str] = None


def _load_template() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


def _safe_npc_responses_payload(npc_responses: List[Dict[str, Any]]) -> str:
    """Compact JSON of the NPC responses for the prompt. Trims long
    text bodies to keep the input cheap."""
    out: List[Dict[str, Any]] = []
    for r in (npc_responses or [])[:6]:
        if not isinstance(r, dict):
            continue
        out.append({
            "npc_name": str(r.get("npc_name") or "")[:60],
            "npc_role": str(r.get("npc_role") or "")[:40],
            "sentiment": str(r.get("sentiment") or "neutral")[:20],
            "text": str(r.get("text") or "")[:200],
        })
    return json.dumps(out, ensure_ascii=False)


def _safe_ambient_summary(ambient_activity: List[Dict[str, Any]]) -> str:
    """Build a one-line digest of any ambient activity worth depicting.
    The renderer uses this for context only; it doesn't read it back
    into the spec."""
    if not ambient_activity:
        return ""
    bits: List[str] = []
    for entry in ambient_activity[:4]:
        if not isinstance(entry, dict):
            continue
        body = str(entry.get("activity") or "").strip()
        if body:
            bits.append(body[:120])
    if not bits:
        return ""
    joined = "; ".join(bits)
    return joined[:300]


async def generate_scene_spec(
    *,
    turn_year: int,
    location_name: str,
    player_name: str,
    player_role: str,
    player_action: str,
    action_type: str,
    significance: float,
    npc_responses: List[Dict[str, Any]],
    ambient_activity: List[Dict[str, Any]],
) -> SceneDirectorResponse:
    """Ask Gemini for a diorama spec. Returns a SceneDirectorResponse;
    the endpoint converts it to a Diorama (canonical form).

    Returns:
        Validated `SceneDirectorResponse`. On any failure (NoOp,
        circuit breaker, parse error), returns a default
        SceneDirectorResponse() -- the renderer will produce a
        minimal generic diorama. Callers should always check whether
        `result.characters` is empty and fill in a sensible fallback
        if so.
    """
    template = Template(_load_template())
    prompt = template.safe_substitute(
        turn_year=int(turn_year) if turn_year else 0,
        location_name=(location_name or "")[:200],
        player_name=(player_name or "")[:120],
        player_role=(player_role or "")[:80],
        player_action=(player_action or "")[:300],
        action_type=(action_type or "")[:40],
        significance=f"{float(significance):.2f}",
        npc_responses=_safe_npc_responses_payload(npc_responses),
        ambient_summary=_safe_ambient_summary(ambient_activity),
    )

    raw = ""
    try:
        raw, _ = await call_llm(
            prompt,
            schema=SceneDirectorResponse,
            call_site="scene_director",
            timeout_s=15.0,
        )
        if not raw:
            return SceneDirectorResponse()
        if raw.strip() in {"...", "…"}:
            return SceneDirectorResponse()
        parsed = SceneDirectorResponse.model_validate(json.loads(raw))
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning(
            "scene_director JSON decode failed: %s; raw=%r",
            exc,
            raw[:200] if raw else "",
        )
        return SceneDirectorResponse()
    except Exception as exc:  # noqa: BLE001 — never block a turn
        logger.warning("scene_director generation failed: %s", exc)
        return SceneDirectorResponse()
