"""World state model and mutation logic.

Phase 1 expands the model with multiple locations, NPC memory,
player aging, run lifecycle, and session persistence.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Era(BaseModel):
    name: str
    year_start: int
    description: str
    region: str
    years_per_turn: float = 0.25
    lifespan_turns: List[int] = Field(default_factory=lambda: [40, 60])


class Location(BaseModel):
    id: str
    name: str
    description: str
    political_tension: str
    lat: float = 0.0
    lon: float = 0.0
    neighbors: Dict[str, int] = Field(default_factory=dict)
    trade_routes: List[str] = Field(default_factory=list)
    disrupted_routes: List[str] = Field(default_factory=list)
    material_conditions: str = ""
    food_scarcity: str = "normal"  # abundant | normal | scarce | critical


class PlayerCharacter(BaseModel):
    id: str = "player"
    name: str
    role: str
    archetype: str = ""
    location: str
    description: str
    disposition: str
    birth_year: int = 0


class PersonalityTraits(BaseModel):
    ambition: int = 50
    compassion: int = 50
    courage: int = 50
    piety: int = 50
    pragmatism: int = 50


class NpcNeeds(BaseModel):
    survival: float = 50.0
    safety: float = 50.0
    family: float = 50.0
    social: float = 50.0
    trade: float = 0.0
    profit: float = 0.0
    power: float = 0.0
    reputation: float = 0.0
    honor: float = 0.0
    duty: float = 0.0
    loyalty: float = 50.0
    faith: float = 0.0
    knowledge: float = 0.0
    order: float = 0.0
    community: float = 50.0
    harvest: float = 0.0
    stability: float = 50.0


class NPC(BaseModel):
    id: str
    name: str
    role: str
    archetype: str = ""
    social_class: str = ""
    location: str
    description: str
    disposition: str
    relationship_to_player: str
    memory_of_player: float = 0.0
    last_interaction_turn: int = 0
    stored_povs: List[str] = Field(default_factory=list)
    personality: PersonalityTraits = Field(default_factory=PersonalityTraits)
    needs: NpcNeeds = Field(default_factory=NpcNeeds)
    needs_history: List[Dict] = Field(default_factory=list)
    last_simulated_turn: int = 0
    emotional_state: str = ""
    current_activity: str = ""
    # Structured log of what the player did to/with this NPC.
    # Each entry: {turn, year, action_type, intent}. Capped at 5.
    player_interactions: List[Dict] = Field(default_factory=list)
    # Thematic preoccupation — rotates every ~6 turns via archetype pool.
    current_preoccupation: str = ""
    last_preoccupation_shift_turn: int = 0


class Event(BaseModel):
    turn: int
    action_type: str
    description: str
    target: Optional[str] = None
    location: Optional[str] = None


CONSEQUENCE_EFFECT_TYPES = (
    "tension_shift", "rumor", "trade_disruption",
    "npc_arrival", "event_spawn", "material_change",
    "disposition_shift", "need_pressure",
)

CONSEQUENCE_TARGET_TYPES = ("location", "npc", "region", "global")


class ScheduledConsequence(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_event_id: Optional[str] = None
    trigger_turn: int
    target_type: str  # one of CONSEQUENCE_TARGET_TYPES
    target_id: Optional[str] = None
    effect_type: str  # one of CONSEQUENCE_EFFECT_TYPES
    effect_payload: Dict = Field(default_factory=dict)
    superseded: bool = False
    fired: bool = False


class WorldState(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    run_status: str = "active"
    era: Era
    current_year: int = 0
    player: PlayerCharacter
    npcs: List[NPC]
    locations: List[Location]
    events: List[Event] = Field(default_factory=list)
    turn: int = 0
    visited_locations: List[str] = Field(default_factory=list)
    ground_context: Optional[Dict] = None
    ground_context_stale: bool = False
    historical_divergences: List[Dict] = Field(default_factory=list)
    consequence_queue: List[ScheduledConsequence] = Field(default_factory=list)
    # Phase 3 scene-illustration trigger audit (Step 3.1).
    # Entries: {"turn": int, "type": str, "reason": str}.
    # Detection is idempotent: presence of an entry suppresses re-fire.
    illustration_triggers_fired: List[Dict] = Field(default_factory=list)
    # Snapshot of visited_locations from the END of the previous turn.
    # Used to detect first-arrival at a new location this turn without
    # racing the in-turn mutation of visited_locations itself.
    previously_visited_locations: List[str] = Field(default_factory=list)
    # LLM provider cost tracking. Accumulated across all call_llm
    # invocations made during a turn via the track_turn_cost() bucket.
    # USD is authoritative; EUR conversion happens at render time using
    # config.USD_TO_EUR. Persisted with the session JSON.
    cumulative_cost_usd: float = 0.0
    # Cap state machine:
    #   "none"          -> under the soft cap
    #   "soft_crossed"  -> >= soft cap (EUR 1.00 default); banner shown
    #                      in frontend, dismissible; turns still advance
    #   "hard"          -> >= hard cap (EUR 2.00 default); further turn
    #                      advancement is blocked by the API
    cost_cap_state: str = "none"
    # Run-level "do not reuse" list of sensory grounding phrases extracted
    # from past NPC POVs. Capped at 30 entries with FIFO eviction. Injected
    # into npc_pov.md and npc_addressed.md as $already_used_details. Resets
    # per run (new WorldState = empty list).
    used_grounding_details: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENSION_LEVELS = ["low", "moderate", "high", "critical"]


def get_player_location(state: WorldState) -> Location:
    for loc in state.locations:
        if loc.id == state.player.location:
            return loc
    raise ValueError(f"Player location '{state.player.location}' not found")


def get_location(state: WorldState, location_id: str) -> Location:
    for loc in state.locations:
        if loc.id == location_id:
            return loc
    raise ValueError(f"Location '{location_id}' not found")


def npcs_at_location(state: WorldState, location_id: str) -> List[NPC]:
    return [n for n in state.npcs if n.location == location_id]


def npcs_near_player(state: WorldState) -> List[NPC]:
    return npcs_at_location(state, state.player.location)


# ---------------------------------------------------------------------------
# Hardcoded initial state (Phase 0 compat / testing convenience)
# ---------------------------------------------------------------------------

def create_initial_state() -> WorldState:
    """Create a hardcoded Roman Late Empire scenario for testing."""
    from backend.npc_personality import generate_personality, calculate_needs

    soldier_personality = generate_personality("soldier")
    soldier_needs = calculate_needs("soldier", soldier_personality)
    clergy_personality = generate_personality("clergy")
    clergy_needs = calculate_needs("clergy", clergy_personality)

    return WorldState(
        run_id=uuid.uuid4().hex[:12],
        run_status="active",
        era=Era(
            name="Roman Late Empire",
            year_start=410,
            description=(
                "The Western Roman Empire crumbles. Emperor Honorius cowers in "
                "Ravenna while Alaric's Visigoths march south through Italia. "
                "The legions are stretched thin, the grain supply from Africa is "
                "uncertain, and provincial towns brace for what comes next."
            ),
            region="Italia",
            years_per_turn=0.25,
            lifespan_turns=[40, 60],
        ),
        current_year=410,
        player=PlayerCharacter(
            id="player",
            name="Marcus Aurelius Corvinus",
            role="Grain merchant",
            archetype="merchant",
            location="ariminum",
            description=(
                "A middling grain merchant in Ariminum who has built modest "
                "connections supplying the local garrison. With the legions "
                "withdrawing and the Visigoths advancing, your livelihood — "
                "and your life — are increasingly uncertain."
            ),
            disposition="anxious",
            birth_year=375,
        ),
        npcs=[
            NPC(
                id="centurion_gallus",
                name="Lucius Gallus",
                role="Centurion of the garrison at Ariminum",
                archetype="soldier",
                social_class="military",
                location="ariminum",
                description=(
                    "A career soldier nearing forty who served on the Rhine "
                    "frontier and in Pannonia before reassignment to Ariminum. "
                    "Competent, cynical about Rome's leadership, quietly furious "
                    "about the state of his cohort — undermanned, undersupplied, "
                    "ordered to hold a position that may already be indefensible."
                ),
                disposition="grim",
                relationship_to_player=(
                    "Professional acquaintance — Corvinus supplies grain to the "
                    "garrison. Gallus respects the merchant's reliability but "
                    "trusts no civilian fully."
                ),
                memory_of_player=0.3,
                last_interaction_turn=0,
                personality=soldier_personality,
                needs=soldier_needs,
            ),
            NPC(
                id="deacon_paulus",
                name="Deacon Paulus",
                role="Christian deacon at the Basilica of Ariminum",
                archetype="clergy",
                social_class="religious",
                location="ariminum",
                description=(
                    "A young deacon, barely thirty, who came to Ariminum from "
                    "Mediolanum three years ago. Earnest, well-read in "
                    "Augustine's letters, he believes the barbarian threat is "
                    "divine judgment on a sinful empire. He organizes food "
                    "distribution to the poor and has growing influence among "
                    "the common people."
                ),
                disposition="fervent",
                relationship_to_player=(
                    "Occasional customer — Corvinus has sold grain to the "
                    "basilica at fair prices. Paulus considers him decent but "
                    "worldly, too focused on profit when souls are at stake."
                ),
                memory_of_player=0.2,
                last_interaction_turn=0,
                personality=clergy_personality,
                needs=clergy_needs,
            ),
        ],
        locations=[
            Location(
                id="ariminum",
                name="Ariminum",
                description=(
                    "A fortified Roman town on the Adriatic coast where the Via "
                    "Flaminia meets the sea. Once a prosperous waypoint between "
                    "Rome and the northern frontier, Ariminum now feels the weight "
                    "of empire's contraction. The garrison is half its former "
                    "strength. Refugees from the north trickle in with stories of "
                    "Visigoth raids. The harbor still functions, but fewer ships "
                    "arrive each month."
                ),
                political_tension="high",
                lat=44.06,
                lon=12.57,
                neighbors={"ravenna": 2, "mediolanum": 4},
                trade_routes=["ravenna", "mediolanum"],
                material_conditions="Grain still arrives from the south but shipments are irregular. The harbor functions but fewer ships dock each week.",
                food_scarcity="scarce",
            ),
            Location(
                id="ravenna",
                name="Ravenna",
                description=(
                    "The imperial capital of the Western Roman Empire, surrounded "
                    "by marshes that make it nearly impregnable. Emperor Honorius "
                    "hides behind its walls while the empire crumbles. The court "
                    "is rife with intrigue, and the city swells with officials, "
                    "soldiers, and refugees from the north."
                ),
                political_tension="critical",
                lat=44.42,
                lon=12.20,
                neighbors={"ariminum": 2},
                trade_routes=["ariminum"],
                material_conditions="The imperial granaries are stocked but the court consumes more than it admits. Refugees strain resources.",
                food_scarcity="normal",
            ),
            Location(
                id="mediolanum",
                name="Mediolanum",
                description=(
                    "Once the administrative capital of the Western Empire, "
                    "Mediolanum has declined since the court moved to Ravenna. "
                    "Still a major city with a powerful bishop and active trade, "
                    "but increasingly exposed to barbarian raids from the north."
                ),
                political_tension="high",
                lat=45.46,
                lon=9.19,
                neighbors={"ariminum": 4},
                trade_routes=["ariminum"],
                material_conditions="Trade from the north has slowed. The bishop's granary feeds the poor but supplies dwindle.",
                food_scarcity="scarce",
            ),
        ],
        events=[],
        turn=0,
        visited_locations=["ariminum"],
    )


# ---------------------------------------------------------------------------
# State mutation
# ---------------------------------------------------------------------------

def apply_action(state: WorldState, action: dict) -> WorldState:
    """Apply a parsed action to the world state. Returns a new state object.

    Note: does NOT increment turn/year — that is handled by simulate_turn()
    which runs before apply_action in the simulation-first turn loop.
    """
    new = state.model_copy(deep=True)

    if new.player.location not in new.visited_locations:
        new.visited_locations.append(new.player.location)

    new.events.append(
        Event(
            turn=new.turn,
            action_type=action.get("action_type", "other"),
            description=action.get("era_description", "Something happened."),
            target=action.get("target"),
            location=new.player.location,
        )
    )

    npc_impacts = action.get("npc_impacts")
    if npc_impacts and isinstance(npc_impacts, list):
        _apply_npc_impacts(new, npc_impacts)
    else:
        _apply_target_fallback(new, action)

    _update_npc_memory(new, action)

    return new


def _apply_npc_impacts(state: WorldState, impacts: list) -> None:
    for impact in impacts:
        if not isinstance(impact, dict):
            continue
        name = (impact.get("name") or "").lower()
        sentiment = (impact.get("sentiment") or "").lower()
        if not name:
            continue
        for npc in state.npcs:
            if name in npc.name.lower():
                if sentiment == "positive":
                    npc.disposition = _shift_positive(npc.disposition)
                elif sentiment == "negative":
                    npc.disposition = _shift_negative(npc.disposition)


def _apply_target_fallback(state: WorldState, action: dict) -> None:
    target_raw = (action.get("target") or "").lower()
    action_type = action.get("action_type", "other")
    for npc in state.npcs:
        if target_raw and (
            target_raw in npc.name.lower() or target_raw in npc.role.lower()
        ):
            if action_type in ("speak", "trade", "petition"):
                npc.disposition = _shift_positive(npc.disposition)
            elif action_type in ("threaten",):
                npc.disposition = _shift_negative(npc.disposition)


_MAX_PLAYER_INTERACTIONS = 5


def _update_npc_memory(state: WorldState, action: dict) -> None:
    """Increase memory for NPCs the player interacted with this turn.

    Also appends a structured player-interaction record to directly
    targeted/impacted NPCs so npc_engine can summarize what the player
    did without injecting raw NPC POV text back.
    """
    target_raw = (action.get("target") or "").lower()
    impacts = action.get("npc_impacts") or []
    affected_names = {target_raw} if target_raw else set()
    for imp in impacts:
        if isinstance(imp, dict) and imp.get("name"):
            affected_names.add(imp["name"].lower())

    for npc in state.npcs:
        if npc.location != state.player.location:
            continue
        name_lower = npc.name.lower()
        if any(n in name_lower for n in affected_names if n):
            npc.memory_of_player = min(1.0, npc.memory_of_player + 0.15)
            npc.last_interaction_turn = state.turn
            # Log structured player-action record (replaces verbatim POV injection).
            record = {
                "turn": state.turn,
                "year": state.current_year or state.era.year_start,
                "action_type": action.get("action_type", "other"),
                "intent": (action.get("intent") or "")[:120],
            }
            npc.player_interactions.append(record)
            if len(npc.player_interactions) > _MAX_PLAYER_INTERACTIONS:
                npc.player_interactions = npc.player_interactions[-_MAX_PLAYER_INTERACTIONS:]
        elif npc.memory_of_player > 0:
            npc.memory_of_player = min(1.0, npc.memory_of_player + 0.05)


# ---------------------------------------------------------------------------
# Story summary (fed into prompts)
# ---------------------------------------------------------------------------

# Story summary cap: prevents prompt bloat across long runs.
# At 4 ambient events per turn, an uncapped summary reaches ~200 lines by turn 50,
# which dominates every NPC POV prompt. We keep two slices:
#   - the most recent N events (what's happening right now)
#   - high-significance events from earlier (player actions, deaths, divergences)
# and drop low-signal ambient activity older than the recent window.
#
# Priority types live in backend.event_vocab.PRIORITY_EVENT_TYPES so the
# story-summary slice and the long-run state.events compaction
# (world_engine.compact_events) cannot drift apart.
from backend.event_vocab import PRIORITY_EVENT_TYPES as _STORY_SUMMARY_PRIORITY_TYPES

_STORY_SUMMARY_RECENT_CAP = 12


def build_story_summary(state: WorldState) -> str:
    if not state.events:
        return "The game has just begun. No actions have been taken yet."

    player_loc = get_player_location(state)
    lines = [f"It is now turn {state.turn} (year {state.current_year} AD). Here is what has happened so far:"]

    # Two-tier event selection:
    #   1. The N most recent events (what's happening NOW)
    #   2. Older events with priority action_types (player decisions, deaths, travel)
    recent = state.events[-_STORY_SUMMARY_RECENT_CAP:]
    recent_ids = {id(ev) for ev in recent}
    older_priority = [
        ev for ev in state.events[:-_STORY_SUMMARY_RECENT_CAP]
        if ev.action_type in _STORY_SUMMARY_PRIORITY_TYPES
        and id(ev) not in recent_ids
    ]
    # Cap older priority at half the recent budget so the prompt stays bounded
    # even on very long runs with many player actions.
    older_priority = older_priority[-(_STORY_SUMMARY_RECENT_CAP // 2):]

    elided_count = max(
        0,
        len(state.events) - len(recent) - len(older_priority),
    )

    if older_priority:
        lines.append("Earlier turning points:")
        for ev in older_priority:
            target_note = f" (involving {ev.target})" if ev.target else ""
            lines.append(f"- Turn {ev.turn}: {ev.description}{target_note}")
        if elided_count:
            lines.append(f"  (... and {elided_count} smaller moments now in the past)")

    if older_priority:
        lines.append("Recent events:")
    for ev in recent:
        target_note = f" (involving {ev.target})" if ev.target else ""
        lines.append(f"- Turn {ev.turn}: {ev.description}{target_note}")

    nearby = npcs_near_player(state)
    if nearby:
        npc_notes = [f"{npc.name} is {npc.disposition}" for npc in nearby]
        lines.append(f"People nearby: {'; '.join(npc_notes)}.")
    lines.append(
        f"Political tension in {player_loc.name}: "
        f"{player_loc.political_tension}."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Disposition shifts
# ---------------------------------------------------------------------------

_POSITIVE_SHIFTS = {
    "hostile": "fearful",
    "fearful": "wary",
    "wary": "cautious",
    "grim": "guarded",
    "guarded": "cautious",
    "suspicious": "cautious",
    "cautious": "neutral",
    "neutral": "reserved",
    "reserved": "formal",
    "formal": "engaged",
    "fervent": "engaged",
    "engaged": "warming",
    "commanding": "warming",
}

_NEGATIVE_SHIFTS = {
    "warming": "engaged",
    "engaged": "formal",
    "formal": "reserved",
    "reserved": "neutral",
    "commanding": "formal",
    "neutral": "cautious",
    "cautious": "guarded",
    "guarded": "grim",
    "wary": "hostile",
    "grim": "hostile",
    "fearful": "hostile",
    "fervent": "suspicious",
    "suspicious": "hostile",
}


def _shift_positive(disposition: str) -> str:
    return _POSITIVE_SHIFTS.get(disposition, disposition)


def _shift_negative(disposition: str) -> str:
    return _NEGATIVE_SHIFTS.get(disposition, disposition)


def shift_disposition(disposition: str, direction: int) -> str:
    """Apply a bounded ±1 step to a disposition string."""
    if direction > 0:
        return _shift_positive(disposition)
    if direction < 0:
        return _shift_negative(disposition)
    return disposition


# ---------------------------------------------------------------------------
# NPCEffect application — bounded mutation from LLM output
# ---------------------------------------------------------------------------

_ALLOWED_NPC_EFFECT_FIELDS = frozenset({
    "disposition", "location", "needs", "needs_history",
    "personality", "last_simulated_turn", "emotional_state",
})

import logging as _logging
_effect_logger = _logging.getLogger("chronos.npc_effect")


def apply_npc_effect(state: WorldState, effect) -> None:
    """Apply a validated NPCEffect to the matching NPC in-place.

    Only disposition and location can change. If anything else
    changes, it's logged as a boundary violation and rolled back.
    """
    npc = None
    for n in state.npcs:
        if n.id == effect.npc_id:
            npc = n
            break
    if npc is None:
        return

    snapshot_before = npc.model_dump()

    if effect.disposition_shift is not None and effect.disposition_shift != 0:
        npc.disposition = shift_disposition(npc.disposition, effect.disposition_shift)

    if effect.location_change is not None:
        valid_ids = {loc.id for loc in state.locations}
        dest = effect.location_change.lower().strip()
        if dest in valid_ids and dest != npc.location:
            npc.location = dest

    _check_bounded_mutation(npc, snapshot_before)


def _check_bounded_mutation(npc: NPC, snapshot_before: dict) -> None:
    """Assert only allowed fields changed. Log and rollback violations."""
    snapshot_after = npc.model_dump()
    for key in snapshot_before:
        if key in _ALLOWED_NPC_EFFECT_FIELDS:
            continue
        if snapshot_before[key] != snapshot_after[key]:
            _effect_logger.error(
                "Boundary violation: NPC %s field '%s' changed from %r to %r — rolling back",
                npc.id, key, snapshot_before[key], snapshot_after[key],
            )
            setattr(npc, key, snapshot_before[key])
