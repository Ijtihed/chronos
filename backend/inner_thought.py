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

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import InnerThoughtResponse
from backend.world_state import WorldState, get_player_location

logger = logging.getLogger("chronos.inner_thought")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "inner_thought.md"
_TEMPLATE_CACHE: str | None = None


def _load_template() -> str:
    """Load the inner-thought prompt with its metadata header stripped.

    The .md file ships with a `# Inner Thought ...` heading + a `>`
    block describing the call site, model, and cost; everything above
    the first `\\n---\\n` divider is design notes, not prompt text the
    LLM should see. Using `load_prompt()` matches every other LLM call
    site in the project (action_parser, npc_pov, etc.).
    """
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = load_prompt(_TEMPLATE_PATH)
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
    # ground_context is persisted as a Dict on WorldState (see
    # world_state.py: `ground_context: Optional[Dict] = None`). Earlier
    # versions used getattr() against it, which always missed because
    # dicts don't expose those keys as attributes -- the prompt was
    # silently degraded. Use dict.get() so era_feel and
    # material_conditions actually reach Gemini.
    if isinstance(ground, dict):
        era_feel = ground.get("era_feel", "") or ""
        material_conditions = ground.get("material_conditions", "") or ""
    elif ground is not None:
        # Defensive: tolerate a rare object-shape if a future caller
        # changes the type. Keeps the code from regressing back to
        # silent-empty if ground_context becomes a Pydantic model.
        era_feel = getattr(ground, "era_feel", "") or ""
        material_conditions = getattr(ground, "material_conditions", "") or ""

    # Story-so-far is intentionally short here — the inner thought is
    # about the FELT moment, not the plot. Long history dilutes the
    # voice and pushes Gemini toward summary mode.
    story_summary = _short_story_summary(state)

    # Note on absent variables: `current_preoccupation` is a per-NPC
    # field rotated by tick_preoccupation_drift; PlayerCharacter has no
    # such field. The inner-thought prompt body deliberately does NOT
    # substitute it, so we don't pass it here either. Adding it would
    # be a dead .substitute() entry.
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
        story_so_far=story_summary,
        player_input=player_input.strip(),
    )

    raw = ""  # Initialize so the JSONDecodeError logger never NameErrors.
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
        from backend.utils import strip_json_fences
        parsed = InnerThoughtResponse.model_validate(json.loads(strip_json_fences(raw)))
        thought = parsed.inner_thought.strip()
        if not thought or thought in {"...", "…"}:
            return ""
        return thought
    except json.JSONDecodeError as exc:
        logger.warning("inner_thought JSON decode failed: %s; raw=%r", exc, raw[:120])
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
