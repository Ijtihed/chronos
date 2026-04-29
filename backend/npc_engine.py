"""Generate NPC point-of-view responses via the LLM provider.

Model tier: QUALITY — this is the most prose-critical call in the game.
Returns structured NPCPOVResponse; stores emotional_state on the NPC.
On JSON parse failure, retries with raw text (still via the same tier
dispatcher so quality-vs-fast routing is preserved on the retry).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template

from pydantic import ValidationError

from backend.grounding_extractor import format_for_prompt as _format_grounding
from backend.hke.retrieve import retrieve_context
from backend.llm_provider import call_llm, load_prompt
from backend.llm_schemas import (
    NPCAddressedResponse,
    NPCPOVResponse,
    leaks_raw_numbers,
    scrub_leaked_numbers,
)
from backend.npc_personality import get_dominant_need, get_urgent_needs
from backend.world_state import (
    NPC,
    WorldState,
    build_story_summary,
    get_player_location,
)

logger = logging.getLogger("chronos.npc_engine")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_pov.md"
_ADDRESSED_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_addressed.md"

# Action types where the player spoke to the NPC (vs. physically acted).
_SPEECH_ACT_TYPES = frozenset({
    "speak", "petition", "negotiate", "threaten", "alliance",
    "trade", "betray", "save",
})


def _strip_json_fence(text: str) -> str:
    """Strip Gemini-style markdown code fences from a JSON response.

    Gemini occasionally wraps its JSON output in ```json ... ``` fences.
    json.loads() rejects the fences; this strips them before parsing.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence line (```json or ```) and closing ``` line
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        return "\n".join(inner).strip()
    return text


_MAX_PRIOR_INTERACTIONS = 3


def _build_player_action_summary(npc: NPC) -> str:
    """Summarise what the PLAYER did to/with this NPC from the structured log.

    Uses npc.player_interactions (turn/year/action_type/intent records) rather
    than npc.stored_povs (NPC's own past voice). Injecting stored_povs verbatim
    caused self-plagiarism: the NPC would read its own prior output and copy its
    own grounded details (wet boots, repeated quotes) into the next response.
    """
    interactions = (npc.player_interactions or [])[-_MAX_PRIOR_INTERACTIONS:]
    if not interactions:
        return "None -- first contact."
    lines = []
    for item in interactions:
        year = item.get("year", "?")
        act = item.get("action_type", "other")
        intent = item.get("intent", "")
        lines.append(f"- Year {year}: {act} -- {intent}")
    return "\n".join(lines)


def _memory_level(npc: NPC) -> str:
    m = npc.memory_of_player
    if m > 0.7:
        return "vivid"
    if m > 0.3:
        return "faint"
    return "barely remember them"


async def generate_npc_pov(
    npc: NPC, action: dict, state: WorldState,
    this_turn_events: list | None = None,
) -> str:
    raw_template = load_prompt(_TEMPLATE_PATH)
    template = Template(raw_template)

    player_loc = get_player_location(state)

    query = action.get("era_description", action.get("intent", ""))
    historical_context = retrieve_context(state.era.name, query) if query else ""

    gc = state.ground_context or {}

    what_knows = gc.get("what_character_knows") or "What anyone in your position would know."
    raw_rumors = gc.get("local_rumors", [])
    if not raw_rumors:
        rumors_str = "Nothing specific."
    elif len(raw_rumors) == 1:
        rumors_str = raw_rumors[0]
    else:
        rumors_str = "; ".join(raw_rumors)

    urgent = get_urgent_needs(npc.needs)
    urgent_str = ", ".join(n.replace("_", " ") for n in urgent) if urgent else "nothing urgent"

    # Build player-action summary (replaces verbatim stored_povs injection).
    player_action_summary = _build_player_action_summary(npc)
    mem_level = _memory_level(npc)
    current_preoccupation = npc.current_preoccupation or "the immediate situation"

    # this_turn_events: cap at 4 to keep prompt short (Fix 5)
    capped_events = (this_turn_events or [])[:4]
    if capped_events:
        scene_lines = "\n".join(
            f"- {e.get('npc_name', 'Someone')}: {e.get('activity', '')}"
            for e in capped_events
            if e.get("npc_id") != npc.id  # exclude the NPC's own action
        )
        this_turn_str = scene_lines if scene_lines else "Nothing notable."
    else:
        this_turn_str = "Nothing notable."

    # Sensory grounding rotation (run-level "do not reuse" list)
    already_used_details = _format_grounding(state.used_grounding_details or [])

    prompt = template.safe_substitute(
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        social_class=npc.social_class or npc.archetype,
        npc_disposition=npc.disposition,
        dominant_need=get_dominant_need(npc.needs).replace("_", " "),
        urgent_needs=urgent_str,
        current_activity=getattr(npc, "current_activity", "") or "Going about their day.",
        relationship_to_player=npc.relationship_to_player,
        player_actions_toward_you=player_action_summary,
        memory_level=mem_level,
        current_preoccupation=current_preoccupation,
        player_name=state.player.name,
        era_description=state.era.description,
        era_feel=gc.get("era_feel", ""),
        material_conditions=gc.get("material_conditions", player_loc.material_conditions),
        what_character_knows=what_knows,
        local_rumors=rumors_str,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        story_so_far=build_story_summary(state),
        historical_context=historical_context or "No additional historical sources available.",
        era_description_of_action=action.get(
            "era_description", "Something has happened in town."
        ),
        action_intent=action.get("intent", "unknown"),
        this_turn_events=this_turn_str,
        already_used_details=already_used_details,
    )

    try:
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=NPCPOVResponse,
            call_site="npc_pov",
        )
        # Gemini sometimes wraps JSON in markdown code fences; strip before parsing.
        raw = _strip_json_fence(raw)
        parsed = NPCPOVResponse.model_validate(json.loads(raw))
        text = parsed.perspective or f"[{npc.name} is silent]"
        if leaks_raw_numbers(text):
            logger.warning("NPC POV for %s leaked raw numbers, scrubbing", npc.name)
            text = scrub_leaked_numbers(text)
        if parsed.emotional_state:
            npc.emotional_state = parsed.emotional_state
        return text
    except (json.JSONDecodeError, ValidationError):
        try:
            raw_text, _ = await call_llm(
                prompt,
                tier="quality",
                call_site="npc_pov.retry",
            )
            if leaks_raw_numbers(raw_text):
                raw_text = scrub_leaked_numbers(raw_text)
            return raw_text
        except Exception as exc:
            return f"[{npc.name} is silent — LLM error: {exc}]"
    except Exception as exc:
        return f"[{npc.name} is silent — LLM error: {exc}]"


async def generate_npc_addressed(
    npc: NPC,
    action: dict,
    state: WorldState,
    player_input: str = "",
    this_turn_events: list | None = None,
) -> dict:
    """Generate a direct reply from an NPC who was addressed by the player.

    Returns a dict with keys: reply (str), internal (str|None), emotional_state (str).
    Replaces the ambient npc_pov call for the targeted NPC -- net new calls per turn: 0.
    """
    raw_template = load_prompt(_ADDRESSED_TEMPLATE_PATH)
    template = Template(raw_template)

    player_loc = get_player_location(state)

    query = action.get("era_description", action.get("intent", ""))
    historical_context = retrieve_context(state.era.name, query) if query else ""

    gc = state.ground_context or {}

    what_knows = gc.get("what_character_knows") or "What anyone in your position would know."
    raw_rumors = gc.get("local_rumors", [])
    rumors_str = "; ".join(raw_rumors) if raw_rumors else "Nothing specific."

    urgent = get_urgent_needs(npc.needs)
    urgent_str = ", ".join(n.replace("_", " ") for n in urgent) if urgent else "nothing urgent"

    player_action_summary = _build_player_action_summary(npc)
    mem_level = _memory_level(npc)
    current_preoccupation = npc.current_preoccupation or "the immediate situation"

    # Build player_action_description: "said to you: '...'" vs "did X to you"
    action_type = action.get("action_type", "other")
    if action_type in _SPEECH_ACT_TYPES and player_input:
        player_action_desc = f'said to you directly: "{player_input}"'
    elif action_type in _SPEECH_ACT_TYPES:
        player_action_desc = f"spoke to you: {action.get('intent', 'said something')}"
    else:
        player_action_desc = (
            action.get("era_description")
            or f"acted toward you: {action.get('intent', 'something happened')}"
        )

    # this_turn_events: cap at 4, exclude this NPC's own action
    capped_events = (this_turn_events or [])[:4]
    if capped_events:
        scene_lines = "\n".join(
            f"- {e.get('npc_name', 'Someone')}: {e.get('activity', '')}"
            for e in capped_events
            if e.get("npc_id") != npc.id
        )
        this_turn_str = scene_lines if scene_lines else "Nothing notable."
    else:
        this_turn_str = "Nothing notable."

    # Sensory grounding rotation (run-level "do not reuse" list)
    already_used_details = _format_grounding(state.used_grounding_details or [])

    prompt = template.safe_substitute(
        npc_name=npc.name,
        npc_role=npc.role,
        npc_description=npc.description,
        social_class=npc.social_class or npc.archetype,
        npc_disposition=npc.disposition,
        dominant_need=get_dominant_need(npc.needs).replace("_", " "),
        urgent_needs=urgent_str,
        current_activity=getattr(npc, "current_activity", "") or "Going about their day.",
        current_preoccupation=current_preoccupation,
        relationship_to_player=npc.relationship_to_player,
        player_actions_toward_you=player_action_summary,
        memory_level=mem_level,
        player_name=state.player.name,
        era_description=state.era.description,
        era_feel=gc.get("era_feel", ""),
        material_conditions=gc.get("material_conditions", player_loc.material_conditions),
        what_character_knows=what_knows,
        local_rumors=rumors_str,
        location_name=player_loc.name,
        year=state.current_year or state.era.year_start,
        story_so_far=build_story_summary(state),
        historical_context=historical_context or "No additional historical sources available.",
        player_action_description=player_action_desc,
        this_turn_events=this_turn_str,
        already_used_details=already_used_details,
    )

    fallback = {"reply": f"[{npc.name} says nothing]", "internal": None, "emotional_state": ""}

    try:
        raw, _ = await call_llm(
            prompt,
            tier="quality",
            schema=NPCAddressedResponse,
            call_site="npc_addressed",
        )
        raw = _strip_json_fence(raw)
        parsed = NPCAddressedResponse.model_validate(json.loads(raw))
        reply = parsed.reply or f"[{npc.name} says nothing]"
        if leaks_raw_numbers(reply):
            reply = scrub_leaked_numbers(reply)
        internal = parsed.internal
        if internal and leaks_raw_numbers(internal):
            internal = scrub_leaked_numbers(internal)
        if parsed.emotional_state:
            npc.emotional_state = parsed.emotional_state
        return {"reply": reply, "internal": internal or None, "emotional_state": parsed.emotional_state}
    except (json.JSONDecodeError, ValidationError):
        try:
            raw_text, _ = await call_llm(
                prompt,
                tier="quality",
                call_site="npc_addressed.retry",
            )
            return {"reply": raw_text, "internal": None, "emotional_state": ""}
        except Exception as exc:
            return {**fallback, "reply": f"[{npc.name} is silent — LLM error: {exc}]"}
    except Exception as exc:
        return {**fallback, "reply": f"[{npc.name} is silent — LLM error: {exc}]"}
