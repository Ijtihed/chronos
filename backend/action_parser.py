"""Parse player natural language into a structured action via LLM.

All LLM calls route to Gemini (tier parameter is a no-op).
Short, highly structured JSON output.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from string import Template

from pydantic import ValidationError

from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import ActionParserResponse
from backend.world_state import (
    WorldState,
    build_story_summary,
    get_location,
    get_player_location,
    npcs_near_player,
)

logger = logging.getLogger("chronos.action_parser")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "action_parser.md"

# ---------------------------------------------------------------------------
# Action-type normalization
#
# LLMs return free-form action_type labels. Downstream code in
# world_state.apply_action, _apply_target_fallback, _schedule_player_
# consequences, and _check_historical_divergence branches on exact
# canonical values.  ALIASES maps known drift variants to those
# canonical types so routing works regardless of the synonym the model
# picks.  Unknown values pass through with a debug log.
#
# Canonical vocabulary (from audit of backend/):
#   speak, trade, petition, threaten, betray, attack, steal, negotiate,
#   defend, fight, siege, alliance, hoard, prevent, save, flee, other
# ---------------------------------------------------------------------------

ALIASES: dict[str, str] = {
    # → speak
    "inquiry":     "speak",
    "ask":         "speak",
    "question":    "speak",
    "interrogate": "speak",
    "converse":    "speak",
    "talk":        "speak",
    "discuss":     "speak",
    "chat":        "speak",
    "convince":    "speak",
    "persuade":    "speak",
    "warn":        "speak",
    # → trade
    "barter":      "trade",
    "buy":         "trade",
    "sell":        "trade",
    "exchange":    "trade",
    "purchase":    "trade",
    # → petition
    "request":     "petition",
    "appeal":      "petition",
    "plead":       "petition",
    "beg":         "petition",
    "supplicate":  "petition",
    "entreat":     "petition",
    # → threaten
    "intimidate":  "threaten",
    "menace":      "threaten",
    "coerce":      "threaten",
    # → betray
    "deceive":     "betray",
    "double-cross":"betray",
    "backstab":    "betray",
    # → attack
    "assault":     "attack",
    "strike":      "attack",
    "hit":         "attack",
    "combat":      "attack",
    "kill":        "attack",
    "murder":      "attack",
    "slay":        "attack",
    # → steal
    "rob":         "steal",
    "loot":        "steal",
    "pilfer":      "steal",
    "pickpocket":  "steal",
    "thieve":      "steal",
    # → negotiate
    "bargain":     "negotiate",
    "diplomacy":   "negotiate",
    "parley":      "negotiate",
    "mediate":     "negotiate",
    "broker":      "negotiate",
    # → defend
    "protect":     "defend",
    "guard":       "defend",
    "shield":      "defend",
    "fortify":     "defend",
    # → fight
    "battle":      "fight",
    "clash":       "fight",
    "duel":        "fight",
    "skirmish":    "fight",
    # → siege
    "besiege":     "siege",
    "blockade":    "siege",
    "encircle":    "siege",
    # → alliance
    "pact":        "alliance",
    "ally":        "alliance",
    "unite":       "alliance",
    "coalition":   "alliance",
    # → hoard
    "stockpile":   "hoard",
    "stash":       "hoard",
    "accumulate":  "hoard",
    # → prevent
    "stop":        "prevent",
    "block":       "prevent",
    "intervene":   "prevent",
    "thwart":      "prevent",
    "avert":       "prevent",
    # → save
    "rescue":      "save",
    # → flee
    "escape":      "flee",
    "run":         "flee",
    "retreat":     "flee",
    "withdraw":    "flee",
    "desert":      "flee",
}


def normalize_action_type(raw: str) -> str:
    """Map a free-form action_type to its canonical form.

    Lookup is case-insensitive.  Unknown values pass through unchanged
    with a debug-level log so new drift patterns surface in telemetry.
    """
    key = raw.strip().lower()
    canonical = ALIASES.get(key)
    if canonical is not None:
        return canonical
    if key not in _CANONICAL_TYPES:
        logger.debug("action_type passthrough (no alias): %r", key)
    return key


_CANONICAL_TYPES = frozenset({
    "speak", "trade", "petition", "threaten", "betray", "attack",
    "steal", "negotiate", "defend", "fight", "siege", "alliance",
    "hoard", "prevent", "save", "flee", "other",
})

_FENCE_RE = re.compile(r"^```(?:\w+)?\s*\n(.*?)```\s*$", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) that Gemini sometimes wraps around JSON."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    return m.group(1).strip() if m else text


async def parse_action(player_input: str, state: WorldState) -> dict:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    try:
        nearby = npcs_near_player(state)
        npc_list = ", ".join(f"{n.name} ({n.role})" for n in nearby)
        player_loc = get_player_location(state)
    except (ValueError, Exception) as exc:
        logger.warning("parse_action: location lookup failed, using fallback: %s", exc)
        return _fallback(player_input, state, str(exc))

    reachable = []
    for nid, cost in player_loc.neighbors.items():
        try:
            dest = get_location(state, nid)
            reachable.append(f"{dest.name} ({nid}, {cost} turns)")
        except ValueError:
            reachable.append(f"{nid} ({cost} turns)")
    reachable_str = ", ".join(reachable) if reachable else "none"

    prompt = template.safe_substitute(
        year=state.current_year or state.era.year_start,
        era_description=state.era.description,
        player_name=state.player.name,
        player_role=state.player.role,
        location_name=player_loc.name,
        location_description=player_loc.description,
        npcs=npc_list,
        story_so_far=build_story_summary(state),
        political_tension=player_loc.political_tension,
        reachable_locations=reachable_str,
        player_input=player_input,
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="fast",
            schema=ActionParserResponse,
            call_site="action_parser",
        )
        parsed = ActionParserResponse.model_validate(json.loads(_strip_fences(raw)))
        result = parsed.model_dump()
        result["action_type"] = normalize_action_type(result["action_type"])
        return result
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Action parser validation failed: %s", exc)
        return _fallback(player_input, state, str(exc))
    except Exception as exc:
        return _fallback(player_input, state, str(exc))


def _fallback(player_input: str, state: WorldState, error: str) -> dict:
    """Build a safe-default parsed action when the LLM call fails.

    The error string is logged at WARNING (the caller already does that
    for ValidationError; this re-logs unconditionally so wrapped Exception
    branches surface too) but is NOT included in the returned dict. The
    parsed_action shape is part of the public /turn response and the
    persisted turn_logs row; leaking `_parse_error` into either makes
    the API contract leaky and pollutes the audit trail with internal
    LLM-failure strings the player should never see. Live tests assert
    `_parse_error` is absent on the happy path; this keeps it absent on
    the unhappy path too.

    Shape must mirror EVERY key downstream code reads via dict.get():
    main.py reads `significance_score` (consequence/divergence gates),
    `npc_impacts` (NPC POV selection / Addressed-mode pre-filtering),
    `action_type` (consequence dispatch), `target` (Addressed-mode
    resolution). The schema `ActionParserResponse` carries those
    defaults via Pydantic, but this dict is the LLM-failure path
    which never goes through the schema. Including the defaults
    explicitly here keeps the dict's shape identical to a successful
    parse (modulo no `relevant=True` NPC impacts), so downstream code
    paths don't branch differently on the fallback path.
    """
    if error:
        logger.warning("Action parser fallback for input %r: %s", player_input[:80], error)
    try:
        loc_name = get_player_location(state).name
    except ValueError:
        loc_name = "the area"
    return {
        "action_type": "other",
        "target": None,
        "intent": player_input,
        "era_description": (
            f"{state.player.name} attempts something in {loc_name}."
        ),
        "is_travel": False,
        "destination": None,
        "is_inaction": False,
        "significance_score": 0.2,
        "npc_impacts": [],
    }
