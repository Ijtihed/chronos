"""Player Knowledge Agent — filters WorldState into what the character plausibly knows.

The world model is the simulation truth. The player never sees it.
This module computes a PlayerView from WorldState on every request,
applying geographic, social, and archetype-based filtering.

The Knowledge Matrix determines what a character can know about historical
events based on their archetype tier, the event type, and graph distance
from the event's location. See KNOWLEDGE_MATRIX below.

Design source: context/game logic context/gameplay.md (information system),
               context/game logic context/simulation-and-world.md (world model),
               context/game logic context/historical-context-engine.md (HCE).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.utils import graph_distance as _graph_distance_shared
from backend.world_state import (
    Diorama,
    Pin,
    PinConnection,
    WorldState,
    get_player_location,
)


# ---------------------------------------------------------------------------
# Archetype knowledge tiers
# ---------------------------------------------------------------------------

_ARCHETYPE_TIERS: Dict[str, str] = {
    "scholar": "high",
    "scribe": "high",
    "noble": "high",
    "official": "high",
    "ruler": "high",
    "king": "high",
    "emperor": "high",
    "sultan": "high",
    "general": "high",
    "administrator": "high",
    "diplomat": "high",
    "clergy": "medium",
    "monk": "medium",
    "priest": "medium",
    "deacon": "medium",
    "merchant": "medium",
    "soldier": "medium",
    "military": "medium",
    "mercenary": "medium",
    "craftsman": "medium",
    "artisan": "medium",
    "sailor": "medium",
    "engineer": "medium",
    "healer": "medium",
    "caretaker": "medium",
    "farmer": "low",
    "peasant": "low",
    "laborer": "low",
    "servant": "low",
    "domestic": "low",
    "fisherman": "low",
    "civilian": "low",
    "refugee": "low",
    "freed_slave": "low",
    "orphan": "low",
    "captive": "low",
    "outcast": "low",
    "mystic": "medium",
    "storyteller": "medium",
    "pilgrim": "medium",
}

_TENSION_SIMPLIFIED = {
    "low": "calm",
    "moderate": "uneasy",
    "high": "dangerous",
    "critical": "dangerous",
}


def _knowledge_tier(archetype: str) -> str:
    key = archetype.strip().lower()
    if key in _ARCHETYPE_TIERS:
        return _ARCHETYPE_TIERS[key]
    for token in key.split():
        if token in _ARCHETYPE_TIERS:
            return _ARCHETYPE_TIERS[token]
    return "medium"


def _filter_tension(raw_tension: str, tier: str) -> Optional[str]:
    if tier == "high":
        return raw_tension
    if tier == "medium":
        return _TENSION_SIMPLIFIED.get(raw_tension, raw_tension)
    return None


# ---------------------------------------------------------------------------
# Location graph distance (BFS)
# ---------------------------------------------------------------------------

def graph_distance(
    loc_a: str, loc_b: str, state: WorldState,
) -> int:
    """BFS shortest path between two location IDs. Returns 999 if unreachable."""
    return _graph_distance_shared(loc_a, loc_b, state)


_REGION_TO_LOCATION_HINTS: Dict[str, List[str]] = {
    "byzantine": ["constantinople", "galata"],
    "ottoman": ["adrianople", "constantinople"],
    "anatolia": ["adrianople", "constantinople"],
    "balkans": ["adrianople"],
    "mediterranean": ["constantinople", "galata"],
    "levant": ["acre", "tyre", "jaffa"],
    "italia": ["ariminum", "ravenna", "mediolanum", "firenze", "siena"],
    "scandinavia": ["kaupang", "hedeby", "birka"],
    "wallachia": ["adrianople"],
    "moldavia": ["adrianople"],
    "hungary": ["adrianople"],
    "serbia": ["adrianople"],
    "bulgaria": ["adrianople"],
    "greece": ["constantinople"],
    "venice": ["galata", "constantinople"],
    "genoa": ["galata", "constantinople"],
    "achaea": ["constantinople"],
    "morea": ["constantinople"],
    "thessalonica": ["constantinople"],
    "roman": ["ravenna", "ariminum", "mediolanum"],
    "gaul": ["mediolanum", "ariminum"],
    "pannonia": ["ariminum"],
    "africa": ["ravenna", "ariminum"],
    "north africa": ["ravenna", "ariminum"],
    "visigoth": ["ariminum", "mediolanum"],
    "vandal": ["ravenna"],
    "hun": ["ariminum", "mediolanum"],
    "ravenna": ["ravenna"],
    "ariminum": ["ariminum"],
    "mediolanum": ["mediolanum"],
    # Black Death era
    "firenze": ["firenze"],
    "florence": ["firenze"],
    "siena": ["siena"],
    "avignon": ["avignon"],
    "marseille": ["marseille"],
    "tuscany": ["firenze", "siena"],
    "northern italy": ["firenze", "siena"],
    "provence": ["avignon", "marseille"],
    "france": ["avignon", "marseille"],
    "southern france": ["avignon", "marseille"],
    "frankia": ["avignon", "marseille"],
    "europa": ["firenze", "siena", "avignon", "marseille"],
}


def _resolve_event_location(
    event_region: str, state: WorldState,
) -> Optional[str]:
    """Best-effort mapping from an event's region string to a location ID."""
    region_lower = event_region.lower()
    loc_ids = {loc.id for loc in state.locations}

    for loc in state.locations:
        if region_lower in loc.id.lower() or region_lower in loc.name.lower():
            return loc.id
        if loc.id.lower() in region_lower or loc.name.lower() in region_lower:
            return loc.id

    for hint_key, hint_locs in _REGION_TO_LOCATION_HINTS.items():
        if hint_key in region_lower:
            for candidate in hint_locs:
                if candidate in loc_ids:
                    return candidate

    return None


# ---------------------------------------------------------------------------
# Knowledge Matrix
# ---------------------------------------------------------------------------

KNOWLEDGE_MATRIX: Dict[tuple, Dict[str, int]] = {
    ("high", "war"):              {"known": 5, "rumor": 10},
    ("high", "political"):        {"known": 4, "rumor": 8},
    ("high", "epidemic"):         {"known": 3, "rumor": 7},
    ("high", "economic"):         {"known": 4, "rumor": 8},
    ("high", "religious"):        {"known": 5, "rumor": 10},
    ("high", "famine"):           {"known": 3, "rumor": 6},
    ("high", "natural_disaster"): {"known": 3, "rumor": 7},
    ("high", "cultural"):         {"known": 4, "rumor": 8},
    ("medium", "war"):            {"known": 3, "rumor": 6},
    ("medium", "political"):      {"known": 2, "rumor": 5},
    ("medium", "epidemic"):       {"known": 2, "rumor": 5},
    ("medium", "economic"):       {"known": 3, "rumor": 6},
    ("medium", "religious"):      {"known": 2, "rumor": 4},
    ("medium", "famine"):         {"known": 2, "rumor": 4},
    ("medium", "natural_disaster"):{"known": 2, "rumor": 5},
    ("medium", "cultural"):       {"known": 2, "rumor": 4},
    ("low", "war"):               {"known": 1, "rumor": 3},
    ("low", "political"):         {"known": 0, "rumor": 2},
    ("low", "epidemic"):          {"known": 1, "rumor": 3},
    ("low", "economic"):          {"known": 1, "rumor": 2},
    ("low", "religious"):         {"known": 1, "rumor": 2},
    ("low", "famine"):            {"known": 1, "rumor": 3},
    ("low", "natural_disaster"):  {"known": 1, "rumor": 3},
    ("low", "cultural"):          {"known": 0, "rumor": 2},
}

# Domain expertise overrides: certain archetypes get bonus reach for
# specific event types regardless of their base tier.
_ARCHETYPE_OVERRIDES: Dict[str, Dict[str, int]] = {
    "merchant":  {"economic": 1},
    "farmer":    {"famine": 1},
    "peasant":   {"famine": 1},
    "clergy":    {"religious": 1},
    "monk":      {"religious": 1},
    "priest":    {"religious": 1},
    "deacon":    {"religious": 1},
    "soldier":   {"war": 1},
    "military":  {"war": 1},
    "mercenary": {"war": 1},
    "sailor":    {"economic": 1},
    "healer":    {"epidemic": 1},
}


def _get_overrides(archetype: str) -> Dict[str, int]:
    key = archetype.strip().lower()
    if key in _ARCHETYPE_OVERRIDES:
        return _ARCHETYPE_OVERRIDES[key]
    for token in key.split():
        if token in _ARCHETYPE_OVERRIDES:
            return _ARCHETYPE_OVERRIDES[token]
    return {}


def classify_event_knowledge(
    tier: str,
    archetype: str,
    event_type: str,
    distance: int,
    intermediary_hops: int = 0,
) -> str:
    """Determine knowledge quality for a single event.

    Returns one of: "witnessed", "known", "rumor_reliable",
    "rumor_unreliable", or "unknown".
    """
    if distance == 0:
        return "witnessed"

    thresholds = KNOWLEDGE_MATRIX.get((tier, event_type))
    if thresholds is None:
        thresholds = {"known": 1, "rumor": 3}

    overrides = _get_overrides(archetype)
    bonus = overrides.get(event_type, 0)
    known_max = thresholds["known"] + bonus
    rumor_max = thresholds["rumor"] + bonus

    if distance <= known_max:
        return "known"

    if distance <= rumor_max:
        acc = rumor_accuracy(distance, known_max, intermediary_hops)
        return "rumor_reliable" if acc >= 0.5 else "rumor_unreliable"

    return "unknown"


# ---------------------------------------------------------------------------
# Rumor accuracy
# ---------------------------------------------------------------------------

def rumor_accuracy(
    distance: int,
    known_threshold: int,
    intermediary_hops: int = 0,
) -> float:
    """Compute accuracy of a rumor based on distance and intermediaries.

    Returns 0.3-1.0. Values < 0.5 indicate the rumor may contain errors.
    Values >= 0.8 indicate reliable secondhand knowledge.
    """
    base = 1.0 - (distance - known_threshold) * 0.15
    penalty = intermediary_hops * 0.1
    return max(0.3, base - penalty)


# ---------------------------------------------------------------------------
# Historical event filtering (from pre-fetched Events DB results)
# ---------------------------------------------------------------------------

class HistoricalEventView(BaseModel):
    """A historical event filtered through the character's knowledge."""
    year: int
    event: str
    event_type: str
    significance: str
    knowledge_quality: str  # "witnessed" | "known" | "rumor_reliable" | "rumor_unreliable"
    accuracy: Optional[float] = None
    region: Optional[str] = None


def filter_historical_events(
    events: List[Dict[str, Any]],
    state: WorldState,
) -> List[HistoricalEventView]:
    """Filter pre-fetched historical_events rows through the Knowledge Matrix.

    `events` is a list of dicts from query_historical_events().
    Returns only events the character can plausibly know about.
    """
    tier = _knowledge_tier(state.player.archetype)
    archetype = state.player.archetype
    player_loc_id = state.player.location
    results: List[HistoricalEventView] = []

    for ev in events:
        event_loc_id = _resolve_event_location(ev.get("region", ""), state)
        if event_loc_id is None:
            dist = 999
        else:
            dist = graph_distance(player_loc_id, event_loc_id, state)

        ev_type = ev.get("type", "cultural")
        thresholds = KNOWLEDGE_MATRIX.get((tier, ev_type))
        known_max = (thresholds["known"] if thresholds else 1) + \
            _get_overrides(archetype).get(ev_type, 0)

        # Each hop beyond the known threshold represents an intermediary
        intermediaries = max(0, dist - known_max) if dist > known_max else 0

        quality = classify_event_knowledge(
            tier, archetype, ev_type, dist, intermediaries,
        )
        if quality == "unknown":
            continue

        acc = None
        if quality.startswith("rumor"):
            acc = rumor_accuracy(dist, known_max, intermediaries)

        results.append(HistoricalEventView(
            year=ev.get("year", 0),
            event=ev.get("event", ""),
            event_type=ev.get("type", "cultural"),
            significance=ev.get("significance", "regional"),
            knowledge_quality=quality,
            accuracy=acc,
            region=ev.get("region"),
        ))

    return results


# ---------------------------------------------------------------------------
# PlayerView sub-models
# ---------------------------------------------------------------------------

class VisibleNPCHere(BaseModel):
    """NPC at the player's current location — full detail."""
    id: str
    name: str
    role: str
    archetype: str
    disposition: str
    description: str
    relationship_to_player: str
    last_pov: Optional[str] = None


class VisibleNPCKnown(BaseModel):
    """NPC at a previously visited location — limited detail."""
    id: str
    name: str
    archetype: str
    last_known_location: str


class VisibleEvent(BaseModel):
    """An event the player knows about."""
    turn: int
    description: str
    location: Optional[str] = None
    knowledge_type: str  # "witnessed" | "known" | "rumor_reliable" | "rumor_unreliable"


class Rumor(BaseModel):
    """Unconfirmed information from nearby locations."""
    description: str
    source_location: Optional[str] = None


class VisibleLocation(BaseModel):
    """A location as the player character understands it."""
    id: str
    name: str
    description: str
    political_tension: Optional[str] = None
    lat: float = 0.0
    lon: float = 0.0
    neighbors: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# PlayerView (top-level)
# ---------------------------------------------------------------------------

class PlayerView(BaseModel):
    """What the player's character can plausibly know.

    Computed from WorldState on every request. Never stored.
    """
    run_id: str
    run_status: str
    turn: int
    current_year: int

    player_name: str
    player_role: str
    player_archetype: str
    player_location: str
    player_description: str
    player_disposition: str

    era_name: str
    era_description: str
    era_region: str

    current_location: VisibleLocation
    visited_locations: List[str]
    known_locations: List[VisibleLocation]

    npcs_here: List[VisibleNPCHere]
    npcs_known: List[VisibleNPCKnown]

    unvisited_npc_counts: List[Dict[str, Any]] = Field(default_factory=list)

    confirmed_events: List[VisibleEvent]
    rumors: List[Rumor]

    historical_events: List[HistoricalEventView] = Field(default_factory=list)

    # LLM cost tracking (see backend/llm_provider.py + backend/world_state.py).
    # USD is authoritative; frontend converts to EUR via config.USD_TO_EUR
    # supplied as cost_eur / cost_cap_soft_eur / cost_cap_hard_eur.
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    cost_cap_state: str = "none"
    cost_cap_soft_eur: float = 1.0
    cost_cap_hard_eur: float = 2.0
    # Phase 2.9: pinboard state surfaced into the PlayerView. The
    # corresponding Pin / PinConnection models are defined in
    # backend/world_state.py; the frontend renders pins+connections
    # next to the legacy manuscript. The 3D corridor's board_state /
    # cut_threads were removed in this same migration; clients that
    # still send a /board POST get a 410 Gone with a redirect-style
    # message pointing at /pinboard.
    pins: List[Pin] = Field(default_factory=list)
    pin_connections: List[PinConnection] = Field(default_factory=list)
    # Phase 3b: stylized 3D dioramas the player has earned through
    # high-significance moments. Surfaced so the frontend can rebuild
    # the WebGL scenes on initial run load (after a refresh, the
    # manuscript scrolls past the same insets in the same places).
    dioramas: List[Diorama] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Build function
# ---------------------------------------------------------------------------

def build_player_view(
    state: WorldState,
    run_id: str,
    historical_events_raw: Optional[List[Dict[str, Any]]] = None,
) -> PlayerView:
    """Filter WorldState into what the player character can plausibly know.

    `historical_events_raw` is an optional pre-fetched list of dicts from
    query_historical_events(). If provided, they are filtered through the
    Knowledge Matrix and included in the PlayerView.
    """
    tier = _knowledge_tier(state.player.archetype)
    player_loc = get_player_location(state)

    visited_set = set(state.visited_locations)
    neighbor_ids: set[str] = set()
    for loc_id in visited_set:
        for loc in state.locations:
            if loc.id == loc_id:
                neighbor_ids.update(loc.neighbors.keys())
    neighbor_ids -= visited_set

    # --- Current location ---
    current_location = VisibleLocation(
        id=player_loc.id,
        name=player_loc.name,
        description=player_loc.description,
        political_tension=_filter_tension(player_loc.political_tension, tier),
        lat=player_loc.lat,
        lon=player_loc.lon,
        neighbors=player_loc.neighbors,
    )

    # --- Known locations (visited, not current) ---
    known_locations: List[VisibleLocation] = []
    for loc in state.locations:
        if loc.id in visited_set and loc.id != state.player.location:
            known_locations.append(VisibleLocation(
                id=loc.id,
                name=loc.name,
                description=loc.description,
                political_tension=_filter_tension(loc.political_tension, tier),
                lat=loc.lat,
                lon=loc.lon,
                neighbors=loc.neighbors,
            ))

    # --- NPCs at current location (full detail) ---
    npcs_here: List[VisibleNPCHere] = []
    for npc in state.npcs:
        if npc.location == state.player.location:
            last_pov = npc.stored_povs[-1] if npc.stored_povs else None
            npcs_here.append(VisibleNPCHere(
                id=npc.id,
                name=npc.name,
                role=npc.role,
                archetype=npc.archetype,
                disposition=npc.disposition,
                description=npc.description,
                relationship_to_player=npc.relationship_to_player,
                last_pov=last_pov,
            ))

    # --- NPCs at visited locations (name + archetype only) ---
    npcs_known: List[VisibleNPCKnown] = []
    for npc in state.npcs:
        if npc.location != state.player.location and npc.location in visited_set:
            loc_name = npc.location
            for loc in state.locations:
                if loc.id == npc.location:
                    loc_name = loc.name
                    break
            npcs_known.append(VisibleNPCKnown(
                id=npc.id,
                name=npc.name,
                archetype=npc.archetype,
                last_known_location=loc_name,
            ))

    # --- Unvisited location NPC counts (for anonymous map dots) ---
    unvisited_npc_counts: List[Dict[str, Any]] = []
    unvisited_loc_ids = {loc.id for loc in state.locations} - visited_set - {state.player.location}
    for loc in state.locations:
        if loc.id in unvisited_loc_ids and loc.lat and loc.lon:
            count = sum(1 for npc in state.npcs if npc.location == loc.id)
            if count > 0:
                unvisited_npc_counts.append({
                    "lat": loc.lat, "lon": loc.lon, "count": count,
                })

    # --- World events (confirmed: current + visited locations) ---
    confirmed_events: List[VisibleEvent] = []
    for ev in state.events:
        if ev.location == state.player.location:
            confirmed_events.append(VisibleEvent(
                turn=ev.turn,
                description=ev.description,
                location=ev.location,
                knowledge_type="witnessed",
            ))
        elif ev.location in visited_set:
            confirmed_events.append(VisibleEvent(
                turn=ev.turn,
                description=ev.description,
                location=ev.location,
                knowledge_type="known",
            ))

    # --- Rumors (events at neighbor locations of visited places) ---
    rumors: List[Rumor] = []
    for ev in state.events:
        if ev.location and ev.location in neighbor_ids:
            if ev.action_type in ("ambient", "ambient_distant"):
                rumors.append(Rumor(
                    description=ev.description,
                    source_location=ev.location,
                ))
    rumors = rumors[-5:]

    # --- Historical events (from Events DB, filtered by Knowledge Matrix) ---
    hist_events: List[HistoricalEventView] = []
    if historical_events_raw:
        hist_events = filter_historical_events(historical_events_raw, state)

    from backend import config as _config  # avoid import cycle at module load

    cost_usd = float(getattr(state, "cumulative_cost_usd", 0.0) or 0.0)
    return PlayerView(
        run_id=run_id,
        run_status=state.run_status,
        turn=state.turn,
        current_year=state.current_year,
        player_name=state.player.name,
        player_role=state.player.role,
        player_archetype=state.player.archetype,
        player_location=state.player.location,
        player_description=state.player.description,
        player_disposition=state.player.disposition,
        era_name=state.era.name,
        era_description=state.era.description,
        era_region=state.era.region,
        current_location=current_location,
        visited_locations=list(state.visited_locations),
        known_locations=known_locations,
        npcs_here=npcs_here,
        npcs_known=npcs_known,
        unvisited_npc_counts=unvisited_npc_counts,
        confirmed_events=confirmed_events,
        rumors=rumors,
        historical_events=hist_events,
        cost_usd=cost_usd,
        cost_eur=cost_usd * _config.USD_TO_EUR,
        cost_cap_state=getattr(state, "cost_cap_state", "none") or "none",
        cost_cap_soft_eur=_config.COST_CAP_SOFT_EUR,
        cost_cap_hard_eur=_config.COST_CAP_HARD_EUR,
        pins=getattr(state, "pins", []) or [],
        pin_connections=getattr(state, "pin_connections", []) or [],
        dioramas=getattr(state, "dioramas", []) or [],
    )
