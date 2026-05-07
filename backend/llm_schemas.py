"""Pydantic response schemas for every LLM call in CHRONOS.

Every json.loads(raw) from an LLM call must validate through one of these
models. On ValidationError, callers use the safe default — never crash,
never raise to the player.

Inspired by TWU's llmSchemas.ts / Zod validation layer, rebuilt for
CHRONOS's architecture.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class NpcImpact(BaseModel):
    name: str = ""
    sentiment: str = "neutral"
    reason: str = ""
    relevant: Optional[bool] = None


# ---------------------------------------------------------------------------
# ActionParserResponse — action_parser.py
# ---------------------------------------------------------------------------

class ActionParserResponse(BaseModel):
    action_type: str = "other"
    target: Optional[str] = None
    intent: str = ""
    era_description: str = ""
    npc_impacts: List[NpcImpact] = Field(default_factory=list)
    is_travel: bool = False
    destination: Optional[str] = None
    is_inaction: bool = False
    significance_score: float = Field(default=0.2, ge=0.0, le=1.0)

    @field_validator("npc_impacts", mode="before")
    @classmethod
    def coerce_npc_impacts(cls, v):
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if isinstance(item, dict):
                valid_keys = set(NpcImpact.model_fields.keys())
                out.append(NpcImpact(**{k: val for k, val in item.items()
                                        if k in valid_keys}))
            elif isinstance(item, NpcImpact):
                out.append(item)
        return out

    @field_validator("significance_score", mode="before")
    @classmethod
    def clamp_significance(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.2
        return max(0.0, min(1.0, f))

    @field_validator("action_type", mode="before")
    @classmethod
    def coerce_action_type(cls, v):
        if not isinstance(v, str) or not v.strip():
            return "other"
        return v.strip().lower()


def action_parser_default(player_input: str, player_name: str,
                          location_name: str) -> ActionParserResponse:
    return ActionParserResponse(
        action_type="other",
        target=None,
        intent=player_input,
        era_description=f"{player_name} attempts something in {location_name}.",
        is_travel=False,
        destination=None,
        is_inaction=False,
    )


# ---------------------------------------------------------------------------
# AutonomousActionResponse — world_engine.py (player skip + NPC autonomous)
# ---------------------------------------------------------------------------

class AutonomousActionResponse(BaseModel):
    action: str = ""
    new_activity: str = ""
    interacts_with: Optional[str] = None
    mood_shift: Optional[str] = None
    wants_to_travel: bool = False
    travel_destination: Optional[str] = None

    @field_validator("wants_to_travel", mode="before")
    @classmethod
    def coerce_wants_to_travel(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        return False


def autonomous_action_default(character_name: str) -> AutonomousActionResponse:
    return AutonomousActionResponse(
        action=f"{character_name} goes about their day.",
        interacts_with=None,
    )


# ---------------------------------------------------------------------------
# DeathCheckResponse — death_engine.py
# ---------------------------------------------------------------------------

class DeathCheckResponse(BaseModel):
    could_die: bool = False
    death_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    cause: Optional[str] = None

    @field_validator("death_risk", mode="before")
    @classmethod
    def clamp_death_risk(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))

    @field_validator("could_die", mode="before")
    @classmethod
    def coerce_could_die(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        return False


DEATH_CHECK_SAFE = DeathCheckResponse(could_die=False, death_risk=0.0, cause=None)


# ---------------------------------------------------------------------------
# CharacterGenResponse — character_gen.py (player + NPC generation)
# ---------------------------------------------------------------------------

class CharacterGenResponse(BaseModel):
    name: str = ""
    description: str = ""
    disposition: str = "cautious"
    relationship_to_player: str = ""
    current_activity: str = ""


def character_gen_default(role: str, location_name: str,
                          index: Optional[int] = None) -> CharacterGenResponse:
    name = "Unknown Wanderer" if index is None else f"NPC {index}"
    return CharacterGenResponse(
        name=name,
        description=f"A {role} in {location_name}.",
        disposition="cautious" if index is not None else "anxious",
        relationship_to_player="" if index is None else f"Aware of the newcomer.",
        current_activity=f"Going about their duties as a {role}.",
    )


# ---------------------------------------------------------------------------
# NPCEffect — bounded mutation from LLM-influenced NPC interactions
# ---------------------------------------------------------------------------

class NPCEffect(BaseModel):
    """What an NPC interaction can actually change. The LLM proposes,
    the engine validates and applies. Nothing outside this model can
    be mutated by LLM output."""
    npc_id: str
    disposition_shift: Optional[int] = None  # -1, 0, or 1 only
    location_change: Optional[str] = None

    @field_validator("disposition_shift", mode="before")
    @classmethod
    def clamp_disposition_shift(cls, v):
        if v is None:
            return None
        try:
            i = int(v)
        except (TypeError, ValueError):
            return 0
        return max(-1, min(1, i))


# ---------------------------------------------------------------------------
# NPCPOVResponse — structured NPC POV (ambient mode)
# ---------------------------------------------------------------------------

class NPCPOVResponse(BaseModel):
    npc_id: str = ""
    perspective: str = ""
    emotional_state: str = ""
    information_known: List[str] = Field(default_factory=list)
    information_unknown: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NPCAddressedResponse — structured NPC response (addressed mode)
# ---------------------------------------------------------------------------

class NPCAddressedResponse(BaseModel):
    """Response schema for NPCs who are directly addressed by the player.

    `reply`    -- 1-2 sentences spoken directly at the player (always present)
    `internal` -- 1 sentence private thought, may be omitted by the model
    `emotional_state` -- one-word mood
    """
    reply: str = ""
    internal: Optional[str] = None
    emotional_state: str = ""

    @field_validator("internal", mode="before")
    @classmethod
    def coerce_internal(cls, v):
        """Accept empty string or None for internal thought; normalise to None."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


# ---------------------------------------------------------------------------
# GroundContextResponse — future: HCE ground context (Phase 2.5)
# ---------------------------------------------------------------------------

class GroundContextResponse(BaseModel):
    era_feel: str = ""
    what_character_knows: str = ""
    local_rumors: List[str] = Field(default_factory=list)
    material_conditions: str = ""
    recent_events_known: List[str] = Field(default_factory=list)
    recent_events_unknown: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# InnerThoughtResponse — inner_thought.py (Phase 2.7)
# ---------------------------------------------------------------------------

class InnerThoughtResponse(BaseModel):
    """Player's first inner reaction the moment they hit Enter on an action.

    A single sentence, second person ("you..."), in the character's voice.
    Renders under the input field while the rest of the turn loads. See
    prompts/inner_thought.md for the design intent and calibration table.
    """
    inner_thought: str = ""

    @field_validator("inner_thought", mode="before")
    @classmethod
    def coerce_inner_thought(cls, v):
        if v is None:
            return ""
        if not isinstance(v, str):
            return ""
        return v.strip()


# ---------------------------------------------------------------------------
# ConnectionProposalResponse — connection_proposal.py (Phase 2.10)
# ---------------------------------------------------------------------------

class ConnectionProposalResponse(BaseModel):
    """A single one-sentence claim linking two pinned passages from the
    same turn. Empty `claim` is a valid response meaning "no connection
    found"; the orchestrator skips the pair without proposing.

    See prompts/connection_proposal.md for the prompt + design intent.
    The 140-char cap is enforced here so the popup never has to truncate.
    """
    claim: str = ""

    @field_validator("claim", mode="before")
    @classmethod
    def coerce_claim(cls, v):
        if v is None:
            return ""
        if not isinstance(v, str):
            return ""
        s = v.strip()
        # Strip leading/trailing quotes that some LLMs wrap output in.
        if s.startswith('"') and s.endswith('"') and len(s) >= 2:
            s = s[1:-1].strip()
        return s[:140]


# ---------------------------------------------------------------------------
# SceneDirectorResponse — scene_director.py (Phase 3b)
# ---------------------------------------------------------------------------

class _SceneCharacter(BaseModel):
    kind: str = "standing"
    x: int = 0
    z: int = 0
    facing: int = 0
    is_player: bool = False


class _SceneCamera(BaseModel):
    type: str = "low_orbit_slow"
    initial_phi: int = 70
    distance: float = 5.0


class _SceneMood(BaseModel):
    mood: str = "amber_low_light"
    intensity: float = 0.7


class SceneDirectorResponse(BaseModel):
    """Structured spec for a Phase 3b diorama. Mirrors the shape that
    backend.world_state.Diorama persists. The two are deliberately
    NOT the same model -- this one is permissive (validates LLM output
    with safe defaults), while Diorama is the canonical persisted
    form. The endpoint converts response -> Diorama, applying the
    DIORAMA_*_KINDS allow-lists to drop unknown values.

    See prompts/scene_director.md.
    """
    location_kind: str = "chamber"
    characters: List[_SceneCharacter] = Field(default_factory=list)
    camera: _SceneCamera = Field(default_factory=_SceneCamera)
    mood: _SceneMood = Field(default_factory=_SceneMood)
    summary: str = ""

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_summary(cls, v):
        if v is None:
            return ""
        if not isinstance(v, str):
            return ""
        s = v.strip()
        if s.startswith('"') and s.endswith('"') and len(s) >= 2:
            s = s[1:-1].strip()
        return s[:140]


# ---------------------------------------------------------------------------
# leaks_raw_numbers — narrative output safety check
# ---------------------------------------------------------------------------

_LEAKY_PATTERNS = [
    re.compile(r"\b\d+\.\d+\b"),
    re.compile(r"\b\d{1,3}\s*%"),
    re.compile(r"\b(?:score|level|rating|value|stat)\s*[:=]\s*\d", re.IGNORECASE),
    re.compile(r"\bmemory[_ ]?of[_ ]?player\b", re.IGNORECASE),
    re.compile(r"\bdisposition[_ ]?shift\b", re.IGNORECASE),
    re.compile(r"\bpolitical[_ ]?tension\s*[:=]\s*\d", re.IGNORECASE),
]

_SAFE_NUMBER_PATTERNS = [
    re.compile(r"\b\d{3,4}\s*AD\b", re.IGNORECASE),
    re.compile(r"\bage[d]?\s+\d{1,3}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\s+(?:weeks?|months?|years?|days?|hours?|turns?)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:turn|chapter|year)\s+\d{1,4}\b", re.IGNORECASE),
]


def leaks_raw_numbers(text: str) -> bool:
    """Return True if narrative text contains patterns that look like
    raw simulation values leaking through."""
    for safe in _SAFE_NUMBER_PATTERNS:
        text = safe.sub("", text)

    for pattern in _LEAKY_PATTERNS:
        if pattern.search(text):
            return True
    return False


def scrub_leaked_numbers(text: str) -> str:
    """Strip patterns that look like leaked simulation internals."""
    scrubbed = text
    scrubbed = re.sub(
        r"\bmemory[_ ]?of[_ ]?player\s*[:=]?\s*[\d.]+",
        "", scrubbed, flags=re.IGNORECASE,
    )
    scrubbed = re.sub(
        r"\b(?:score|level|rating|value|stat)\s*[:=]\s*\d+(?:\.\d+)?",
        "", scrubbed, flags=re.IGNORECASE,
    )
    scrubbed = re.sub(
        r"\bdisposition[_ ]?shift\s*[:=]?\s*\S+",
        "", scrubbed, flags=re.IGNORECASE,
    )
    scrubbed = re.sub(r"  +", " ", scrubbed).strip()
    return scrubbed
