"""World state model and mutation logic for Phase 0.

Everything here is hardcoded to the Roman Late Empire (~410 AD) scenario.
Phase 1 replaces create_initial_state with random era + character generation.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Era(BaseModel):
    name: str
    year: int
    description: str


class Character(BaseModel):
    id: str
    name: str
    role: str
    location: str
    description: str
    disposition: str


class NPC(Character):
    relationship_to_player: str


class Location(BaseModel):
    name: str
    description: str
    political_tension: str


class Event(BaseModel):
    turn: int
    action_type: str
    description: str
    target: Optional[str] = None


class WorldState(BaseModel):
    era: Era
    player: Character
    npcs: List[NPC]
    location: Location
    events: List[Event]
    turn: int


TENSION_LEVELS = ["low", "moderate", "high", "critical"]


def create_initial_state() -> WorldState:
    return WorldState(
        era=Era(
            name="Roman Late Empire",
            year=410,
            description=(
                "The Western Roman Empire crumbles. Emperor Honorius cowers in "
                "Ravenna while Alaric's Visigoths march south through Italia. "
                "The legions are stretched thin, the grain supply from Africa is "
                "uncertain, and provincial towns brace for what comes next."
            ),
        ),
        player=Character(
            id="player",
            name="Marcus Aurelius Corvinus",
            role="Grain merchant",
            location="Ariminum",
            description=(
                "A middling grain merchant in Ariminum who has built modest "
                "connections supplying the local garrison. With the legions "
                "withdrawing and the Visigoths advancing, your livelihood — "
                "and your life — are increasingly uncertain."
            ),
            disposition="anxious",
        ),
        npcs=[
            NPC(
                id="centurion_gallus",
                name="Lucius Gallus",
                role="Centurion of the garrison at Ariminum",
                location="Ariminum",
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
            ),
            NPC(
                id="deacon_paulus",
                name="Deacon Paulus",
                role="Christian deacon at the Basilica of Ariminum",
                location="Ariminum",
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
            ),
        ],
        location=Location(
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
        ),
        events=[],
        turn=0,
    )


def apply_action(state: WorldState, action: dict) -> WorldState:
    """Apply a parsed action to the world state. Returns a new state object."""
    new = state.model_copy(deep=True)
    new.turn += 1

    new.events.append(
        Event(
            turn=new.turn,
            action_type=action.get("action_type", "other"),
            description=action.get("era_description", "Something happened."),
            target=action.get("target"),
        )
    )

    npc_impacts = action.get("npc_impacts")
    if npc_impacts and isinstance(npc_impacts, list):
        _apply_npc_impacts(new, npc_impacts)
    else:
        _apply_target_fallback(new, action)

    # World entropy: tension creeps up every 3 turns (the Visigoths are coming)
    tension_idx = (
        TENSION_LEVELS.index(new.location.political_tension)
        if new.location.political_tension in TENSION_LEVELS
        else 2
    )
    if new.turn % 3 == 0 and tension_idx < len(TENSION_LEVELS) - 1:
        new.location.political_tension = TENSION_LEVELS[tension_idx + 1]

    return new


def _apply_npc_impacts(state: WorldState, impacts: list) -> None:
    """Shift NPC dispositions based on LLM-judged sentiment impacts."""
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
    """Fallback: shift disposition based on direct target only (pre-npc_impacts compat)."""
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


def build_story_summary(state: WorldState) -> str:
    """Build a running narrative of everything that has happened in the game.

    Fed into both prompt templates so the LLM has full context,
    not just the latest action.
    """
    if not state.events:
        return "The game has just begun. No actions have been taken yet."

    lines = [f"It is now turn {state.turn}. Here is what has happened so far:"]
    for ev in state.events:
        target_note = f" (involving {ev.target})" if ev.target else ""
        lines.append(f"- Turn {ev.turn}: {ev.description}{target_note}")

    npc_notes = [f"{npc.name} is {npc.disposition}" for npc in state.npcs]
    lines.append(f"Current state of people nearby: {'; '.join(npc_notes)}.")
    lines.append(
        f"Political tension in {state.location.name}: "
        f"{state.location.political_tension}."
    )
    return "\n".join(lines)


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
