"""Inner thought generator (Phase 2.7).

Fires the moment the player hits Enter on an action, BEFORE the world
simulates. Returns a single second-person sentence in the character's
voice. The frontend renders it under the input field while the rest
of the turn loads.

This is the first time CHRONOS speaks in the player's own internal
voice. Up to now narration has been third-person ambient (the scene),
NPC POV (other people talking ABOUT the player), or the player's
typed action (their decision, not their feeling). The inner thought
sits in a category nothing else does: the gap between intent and
action made audible.

Design source: prompts/inner_thought.md.
Cost contribution: ~$0.0002 per call → ~€0.002 per 10-turn run, well
under the €1 soft cap.

Failure mode: NoOp ("...") falls back per the global llm_provider
contract; the frontend shows nothing rather than a broken thought.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template

from backend.llm_provider import call_llm
from backend.llm_schemas import InnerThoughtResponse
from backend.world_state import WorldState, get_player_location

logger = logging.getLogger("chronos.inner_thought")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "inner_thought.md"
_TEMPLATE_CACHE: str | None = None


def _load_template() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


async def generate_inner_thought(player_input: str, state: WorldState) -> str:
    """Produce a single-sentence inner thought for the player's typed action.

    Returns a stripped string. Returns "" on any failure — the caller
    is expected to skip rendering when empty.
    """
    if not player_input or not player_input.strip():
        return ""
    try:
        player_loc = get_player_location(state)
    except Exception:
        return ""

    ground = getattr(state, "ground_context", None)
    era_feel = ""
    material_conditions = ""
    if ground is not None:
        era_feel = getattr(ground, "era_feel", "") or ""
        material_conditions = getattr(ground, "material_conditions", "") or ""

    preoccupation = getattr(state.player, "current_preoccupation", "") or ""

    # Story-so-far is intentionally short here — the inner thought is
    # about the FELT moment, not the plot. Long history dilutes the
    # voice and pushes Gemini toward summary mode.
    story_summary = _short_story_summary(state)

    template = Template(_load_template())
    prompt = template.safe_substitute(
        player_name=getattr(state.player, "name", "") or "",
        player_role=getattr(state.player, "role", "") or "",
        player_description=getattr(state.player, "description", "") or "",
        year=getattr(state, "current_year", None) or getattr(state.era, "year_start", ""),
        location_name=player_loc.name,
        location_description=player_loc.description or "",
        political_tension=getattr(player_loc, "political_tension", "") or "",
        era_feel=era_feel,
        material_conditions=material_conditions,
        current_preoccupation=preoccupation,
        story_so_far=story_summary,
        player_input=player_input.strip(),
    )

    try:
        raw, _ = await call_llm(
            prompt,
            schema=InnerThoughtResponse,
            call_site="inner_thought",
            timeout_s=15.0,  # tight: this is racing the rest of the turn
        )
        # NoOp fallback returns "..." which validates as a thought but
        # is not useful prose. Treat short / placeholder responses as empty.
        if not raw or raw.strip() in {"...", "…"}:
            return ""
        parsed = InnerThoughtResponse.model_validate(json.loads(raw))
        thought = parsed.inner_thought.strip()
        if not thought or thought in {"...", "…"}:
            return ""
        return thought
    except json.JSONDecodeError as exc:
        logger.warning("inner_thought JSON decode failed: %s; raw=%r", exc, raw[:120] if "raw" in dir() else "")
        return ""
    except Exception as exc:  # noqa: BLE001 — we never want this to break a turn
        logger.warning("inner_thought generation failed: %s", exc)
        return ""


def _short_story_summary(state: WorldState) -> str:
    """A 2-3 line summary suitable for the inner-thought context.

    Uses a small slice of recent events and recent player actions, not
    the full story-so-far the action_parser uses, because long history
    pushes Gemini toward narrator mode.
    """
    bits: list[str] = []
    events = getattr(state, "events", None) or []
    if events:
        for ev in events[-3:]:
            desc = getattr(ev, "description", None)
            if desc:
                bits.append(desc[:120])
    return " | ".join(bits) if bits else "(early in the run)"
