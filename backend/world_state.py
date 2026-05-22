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


# ---------------------------------------------------------------------------
# Phase 2.9 — Pinboard
# ---------------------------------------------------------------------------
#
# The pinboard is the player's curated, spatial layer next to the
# (flat) manuscript. The 3D corridor manuscript that previously owned
# the player's spatial interactions was deleted in this same migration;
# Pin / PinConnection replace `board_state` / `cut_threads` entirely.
#
# Player-perspective rule: `Pin.source_confidence` records what the
# CHARACTER plausibly knew at the time of pinning, classified server-
# side from `PlayerView` (not `WorldState`). This is the first piece
# of persisted state in CHRONOS that explicitly encodes player
# knowledge rather than ground truth. See manuscript-as-artifact.md
# Phase 2.9 and open-questions.md "Phase 2.9 source_confidence".

# Allowed values for Pin.source_confidence. Kept as a string union
# rather than a Literal so the file stays Pydantic-v1-and-v2 compatible
# with no Literal import in the existing world_state module.
PIN_SOURCE_CONFIDENCES = ("observed", "told_by", "rumor", "inferred")
# Allowed values for PinConnection.kind.
#   - "player"        : player-drawn line (Phase 2.9, default).
#   - "auto_proposed" : system-proposed line awaiting player adjudication
#                       (Phase 2.10). Renders faint+dashed; goes away on
#                       reject, becomes "auto" on agree, becomes "auto"
#                       with edited meta on edit.
#   - "auto"          : system-proposed AND player-confirmed (Phase 2.10).
#                       Permanent until cut.
PIN_CONNECTION_KINDS = ("player", "auto_proposed", "auto")


class PinSourceOffset(BaseModel):
    # Character offsets within the source turn's narrative HTML (or
    # plain-text rendering). Stored as integers so the frontend can
    # re-locate the original passage if it ever needs to. Capped on
    # the API surface; 100k is far above any real run's text length.
    start: int = 0
    end: int = 0


class Pin(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str
    # Position on the pinboard panel. The panel is a 2D coordinate
    # space owned by the frontend; the server only sanitizes finite
    # numbers within a sane bbox.
    x: float = 0.0
    y: float = 0.0
    # The turn-block that this pin was lifted from. The frontend uses
    # this to render the pin's "source" label and to re-locate the
    # passage in the manuscript on click.
    source_turn_id: str = ""
    source_offset: PinSourceOffset = Field(default_factory=PinSourceOffset)
    # Player-perspective classification of the pin's source. One of
    # PIN_SOURCE_CONFIDENCES. Defaults to "inferred" so a pin saved
    # without classification (older clients, weird edge cases) renders
    # with the most-conservative border style.
    source_confidence: str = "inferred"
    # If `source_confidence == "told_by"`, the NPC name. Empty
    # otherwise. Kept as a free-form string, not a foreign key, so
    # NPCs that later vanish or change names don't break old pins.
    source_attribution: str = ""
    # Unix-ish creation timestamp (seconds since epoch). Used by the
    # frontend to sort pins by recency in the panel.
    created_at: float = 0.0


class PinConnection(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    from_pin_id: str
    to_pin_id: str
    # Who created the connection. "player" in Phase 2.9; "auto" is
    # reserved for Phase 2.10's auto-proposer (still empty in 2.9).
    kind: str = "player"
    # Whether the player has cut this connection. Cuts are visual +
    # explanatory only in Phase 2.9 — the simulation does NOT rewind.
    # Phase B (simulation rewinding when cut) is still blocked by 3
    # open questions; see open-questions.md "Phase 2.8 Phase B blockers"
    # (carried forward into Phase 2.10).
    cut: bool = False
    # Optional player-typed caption shown on/near the line. Empty by
    # default. Phase 2.9 only writes empty labels (player-drawn lines
    # have no UI to set a label); Phase 2.10's edit-label-and-meta
    # flow will write here.
    label: str = ""
    # Optional structured metadata. Phase 2.9 writes nothing here;
    # Phase 2.10 will populate it with edge-kind, before/after preview
    # text, and any LLM-generated narrative.
    meta: Dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 3b — Diorama
# ---------------------------------------------------------------------------
#
# Stylized 3D vignettes inset in the manuscript when a major event
# fires. Silhouette characters, low-poly setting, slow camera orbit,
# amber-on-black palette. Rendered live in WebGL (Three.js); geometry
# is procedural from primitives -- no external assets.
#
# The Diorama persists the *spec* the renderer reads (location_kind,
# characters, camera, mood). The spec is generated by the
# scene_director LLM call site (Gemini Flash Lite) at the moment the
# trigger fires; once persisted, the renderer is deterministic.
#
# See manuscript-as-artifact.md Phase 3b and visuals.md "two visual
# languages" table.

# Allowed values per spec field. Renderer reads these and falls back
# to a sensible default if a future LLM emits an unknown value.
DIORAMA_LOCATION_KINDS = (
    "interior_columns",     # Roman/Byzantine hall, stoa, basilica
    "exterior_wall",        # city wall, gate, fortress wall
    "throne_room",          # ruler's audience chamber
    "market",               # forum, agora, bazaar
    "road",                 # rural or paved road, traveling
    "ship",                 # deck of a vessel
    "cloister",             # monastery, abbey, religious enclosure
    "chamber",              # private domestic interior, bedchamber
    "field",                # rural field, vineyard, encampment
    "ruin",                 # collapsed/abandoned site
)
DIORAMA_CHARACTER_KINDS = (
    "standing",             # default human upright
    "robed",                # cleric, scholar, magistrate
    "kneeling",             # in submission, in prayer, mourning
    "horseback",            # mounted figure
    "seated",               # ruler, judge, person at table
    "fallen",               # body on the ground (death scenes)
)
DIORAMA_CAMERA_TYPES = (
    "low_orbit_slow",       # default: camera circles slowly at low height
    "high_static",          # bird's-eye, no orbit
    "dolly_in",             # camera slowly pushes in toward focus
    "wide_pan",             # slow lateral pan, static height
)
DIORAMA_MOODS = (
    "amber_low_light",      # default: warm dim, candle/sun-set feel
    "silver_cold",           # cold blue-grey, harsh light
    "twilight_blue",        # deep blue, fading day
    "harsh_noon",           # high contrast, full sun
    "darkness",             # near-total black with single highlight
)


class CharacterFigure(BaseModel):
    """A single silhouette in the diorama. Rendered procedurally from
    primitives by the frontend; this struct only carries the placement
    + kind. `is_player` lets the renderer color the player figure
    differently (slightly warmer, the only "you" in the scene)."""
    kind: str = "standing"
    # Position on the ground plane. The renderer scales these to its
    # internal world units; we keep them as small ints (-3..+3) so the
    # spec is readable and the LLM can reason about layout.
    x: int = 0
    z: int = 0
    # Facing direction in degrees (0 = facing camera origin). Optional;
    # renderer defaults to facing the scene center.
    facing: int = 0
    is_player: bool = False


class CameraSpec(BaseModel):
    """How the renderer's camera behaves. Auto-orbit is the default;
    drag-to-orbit overrides for ~2s of idle then auto resumes."""
    type: str = "low_orbit_slow"
    # Initial polar angle in degrees (0 = horizontal). Camera then
    # orbits per `type`. Renderer clamps to a safe range.
    initial_phi: int = 70
    # Distance from scene center, in world units.
    distance: float = 5.0


class MoodSpec(BaseModel):
    """Lighting + palette toggle. Single string + intensity 0..1."""
    mood: str = "amber_low_light"
    intensity: float = 0.7


class Diorama(BaseModel):
    """Persisted spec the renderer reads to mount a diorama inset.

    The renderer is fully deterministic given a Diorama -- if the
    schema changes, regenerate or version this struct. Caps:
    characters limited to 6, location_kind / mood / camera_type
    validated against the constant lists above (with safe-fallback in
    the renderer for unknown values, so we don't 500 a forward-looking
    LLM emission).
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_turn_id: str = ""
    location_kind: str = "chamber"
    characters: List[CharacterFigure] = Field(default_factory=list)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    mood: MoodSpec = Field(default_factory=MoodSpec)
    # One-line scene description from the LLM, used as a tooltip /
    # alt-text on hover. Optional. Capped at 140 chars.
    summary: str = ""
    created_at: float = 0.0


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
    # Phase 2.9 (2026-05-07): pinboard state. Replaces the deleted
    # corridor's `board_state` (page positions) and `cut_threads`
    # (severed edges). Old sessions with those fields load cleanly
    # via Pydantic's default `extra="ignore"` and the next save
    # rewrites without them. See manuscript-as-artifact.md.
    pins: List[Pin] = Field(default_factory=list)
    pin_connections: List[PinConnection] = Field(default_factory=list)
    # Phase 2.10: pin pairs the player has explicitly REJECTED in the
    # propose/edit/reject flow. Stored as a flat list of [from_id,
    # to_id] pairs; reverse-pair equivalence is checked in code so
    # rejecting (A, B) also blocks (B, A). Used by the proposer to
    # avoid re-suggesting the same connection. Cascade-dropped when
    # either pin is deleted -- the rejection no longer has meaning.
    rejected_pin_pairs: List[List[str]] = Field(default_factory=list)
    # Phase 2.10: turn index at which the auto-proposer last fired.
    # The trigger gate ("auto, but only when >=3 unconnected pins AND
    # >=2 turns since last") reads this to decide whether to call out
    # to the LLM. -1 means "never fired."
    last_propose_turn: int = -1
    # Phase 3b: stylized 3D dioramas inset in the manuscript when a
    # major event fires (significance >= 0.85). One per turn, hard-
    # capped at 30 per run. Persisted as the renderer-ready spec; the
    # frontend rebuilds the WebGL scene from this.
    dioramas: List[Diorama] = Field(default_factory=list)
    # The final erasure passage generated when the last NPC's memory of
    # the player reaches zero. Persisted so the frontend can re-show it
    # if the player reloads an ended run (otherwise the text would only
    # exist in the response that ended the run). Empty until then.
    final_erasure_text: str = ""


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
# NPC name matching
# ---------------------------------------------------------------------------

def _npc_name_matches(query: str, npc_name: str) -> bool:
    """Match a query string against an NPC name using word-boundary logic.

    Prevents false positives from short substrings (e.g. "al" matching
    "Gallius"). Requires that every word in the query appears as a
    complete word in the NPC name.
    """
    query_lower = query.lower().strip()
    name_lower = npc_name.lower()
    if not query_lower:
        return False
    if query_lower == name_lower:
        return True
    query_words = query_lower.split()
    name_words = name_lower.split()
    return all(qw in name_words for qw in query_words)


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
            if _npc_name_matches(name, npc.name):
                if sentiment == "positive":
                    npc.disposition = _shift_positive(npc.disposition)
                elif sentiment == "negative":
                    npc.disposition = _shift_negative(npc.disposition)


def _apply_target_fallback(state: WorldState, action: dict) -> None:
    target_raw = (action.get("target") or "").lower()
    action_type = action.get("action_type", "other")
    for npc in state.npcs:
        if target_raw and _npc_name_matches(target_raw, npc.name):
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
        if any(_npc_name_matches(n, npc.name) for n in affected_names if n):
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

    try:
        player_loc = get_player_location(state)
    except ValueError:
        player_loc = type("_FallbackLoc", (), {
            "name": state.player.location or "an unknown place",
            "political_tension": "unknown",
        })()
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
