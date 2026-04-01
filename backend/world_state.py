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
    lifespan_turns: List[int] = Field(default=[40, 60])


class Location(BaseModel):
    id: str
    name: str
    description: str
    political_tension: str
    lat: float = 0.0
    lon: float = 0.0
    neighbors: Dict[str, int] = Field(default_factory=dict)


class PlayerCharacter(BaseModel):
    id: str = "player"
    name: str
    role: str
    archetype: str = ""
    location: str
    description: str
    disposition: str
    birth_year: int = 0


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


class Event(BaseModel):
    turn: int
    action_type: str
    description: str
    target: Optional[str] = None
    location: Optional[str] = None


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
    """Apply a parsed action to the world state. Returns a new state object."""
    new = state.model_copy(deep=True)
    new.turn += 1
    new.current_year = int(
        new.era.year_start + new.turn * new.era.years_per_turn
    )

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
    _escalate_tension(new)

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
                npc.disposition = "hostile"


def _update_npc_memory(state: WorldState, action: dict) -> None:
    """Increase memory for NPCs the player interacted with this turn."""
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
        elif npc.memory_of_player > 0:
            npc.memory_of_player = min(1.0, npc.memory_of_player + 0.05)


def _escalate_tension(state: WorldState) -> None:
    """World entropy: tension at player's location creeps up every 3 turns."""
    if state.turn % 3 != 0:
        return
    for loc in state.locations:
        if loc.id != state.player.location:
            continue
        idx = (
            TENSION_LEVELS.index(loc.political_tension)
            if loc.political_tension in TENSION_LEVELS
            else 2
        )
        if idx < len(TENSION_LEVELS) - 1:
            loc.political_tension = TENSION_LEVELS[idx + 1]


# ---------------------------------------------------------------------------
# Story summary (fed into prompts)
# ---------------------------------------------------------------------------

def build_story_summary(state: WorldState) -> str:
    if not state.events:
        return "The game has just begun. No actions have been taken yet."

    player_loc = get_player_location(state)
    lines = [f"It is now turn {state.turn} (year {state.current_year} AD). Here is what has happened so far:"]
    for ev in state.events:
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
    "hostile": "wary",
    "wary": "cautious",
    "grim": "cautious",
    "suspicious": "cautious",
    "cautious": "warming",
    "fervent": "engaged",
    "engaged": "warming",
}

_NEGATIVE_SHIFTS = {
    "warming": "cautious",
    "engaged": "wary",
    "cautious": "wary",
    "wary": "hostile",
    "grim": "hostile",
    "fervent": "suspicious",
    "suspicious": "hostile",
}


def _shift_positive(disposition: str) -> str:
    return _POSITIVE_SHIFTS.get(disposition, disposition)


def _shift_negative(disposition: str) -> str:
    return _NEGATIVE_SHIFTS.get(disposition, disposition)
