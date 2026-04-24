"""NPC personality and needs system.

Personality traits are generated from archetype ranges at NPC creation.
Needs are calculated from archetype + traits, then decay each tick.
The needs system drives autonomous NPC behavior without LLM calls.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from backend.utils import tension_index as _tension_index_util
from backend.world_state import NPC, NpcNeeds, PersonalityTraits


# ---------------------------------------------------------------------------
# 1b: Archetype trait ranges
# ---------------------------------------------------------------------------

ARCHETYPE_TRAIT_RANGES: Dict[str, Dict[str, tuple]] = {
    "merchant":  {"ambition": (50, 90), "compassion": (10, 60), "courage": (20, 60), "piety": (10, 50), "pragmatism": (50, 90)},
    "soldier":   {"ambition": (30, 70), "compassion": (20, 60), "courage": (60, 95), "piety": (20, 70), "pragmatism": (40, 80)},
    "priest":    {"ambition": (20, 60), "compassion": (50, 90), "courage": (20, 60), "piety": (70, 100), "pragmatism": (20, 60)},
    "clergy":    {"ambition": (20, 60), "compassion": (50, 90), "courage": (20, 60), "piety": (70, 100), "pragmatism": (20, 60)},
    "farmer":    {"ambition": (10, 50), "compassion": (50, 90), "courage": (20, 60), "piety": (30, 70), "pragmatism": (50, 90)},
    "noble":     {"ambition": (60, 100), "compassion": (10, 50), "courage": (30, 70), "piety": (20, 60), "pragmatism": (40, 80)},
    "scribe":    {"ambition": (30, 70), "compassion": (30, 70), "courage": (10, 40), "piety": (30, 70), "pragmatism": (50, 90)},
    "refugee":   {"ambition": (10, 40), "compassion": (60, 100), "courage": (20, 60), "piety": (20, 70), "pragmatism": (70, 100)},
    "general":   {"ambition": (60, 100), "compassion": (10, 50), "courage": (70, 100), "piety": (20, 60), "pragmatism": (50, 80)},
}

_DEFAULT_RANGES = {"ambition": (20, 80), "compassion": (20, 80), "courage": (20, 80), "piety": (20, 80), "pragmatism": (20, 80)}


def generate_personality(archetype: str) -> PersonalityTraits:
    """Generate personality traits by sampling within the archetype's ranges."""
    ranges = ARCHETYPE_TRAIT_RANGES.get(archetype, _DEFAULT_RANGES)
    return PersonalityTraits(
        ambition=random.randint(*ranges["ambition"]),
        compassion=random.randint(*ranges["compassion"]),
        courage=random.randint(*ranges["courage"]),
        piety=random.randint(*ranges["piety"]),
        pragmatism=random.randint(*ranges["pragmatism"]),
    )


# ---------------------------------------------------------------------------
# 1c: Need weight calculation
# ---------------------------------------------------------------------------

ARCHETYPE_BASE_NEEDS: Dict[str, Dict[str, float]] = {
    "merchant":  {"trade": 40, "profit": 40},
    "soldier":   {"duty": 40, "honor": 40},
    "priest":    {"faith": 40, "community": 40},
    "clergy":    {"faith": 40, "community": 40},
    "farmer":    {"harvest": 40, "family": 40},
    "noble":     {"power": 40, "reputation": 40},
    "scribe":    {"knowledge": 40, "order": 40},
    "refugee":   {"survival": 40, "safety": 40},
    "general":   {"duty": 40, "power": 40},
}


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def calculate_needs(archetype: str, traits: PersonalityTraits) -> NpcNeeds:
    """Calculate initial need values from archetype base + trait formula."""
    base = ARCHETYPE_BASE_NEEDS.get(archetype, {})

    def b(name: str) -> float:
        return base.get(name, 0.0)

    needs = NpcNeeds(
        survival=_clamp(40 + traits.pragmatism * 0.4),
        safety=_clamp(30 + traits.pragmatism * 0.3 + traits.courage * -0.1),
        family=_clamp(20 + traits.compassion * 0.5),
        social=_clamp(20 + traits.compassion * 0.4 + traits.ambition * 0.1),
        trade=_clamp(b("trade") + traits.ambition * 0.3 + traits.pragmatism * 0.2),
        profit=_clamp(b("profit") + traits.ambition * 0.4),
        power=_clamp(10 + traits.ambition * 0.5),
        reputation=_clamp(20 + traits.ambition * 0.3 + traits.piety * 0.1),
        honor=_clamp(10 + traits.courage * 0.4 + traits.piety * 0.2),
        duty=_clamp(b("duty") + 10 + traits.courage * 0.3 + traits.piety * 0.3),
        loyalty=_clamp(20 + traits.compassion * 0.2 + traits.courage * 0.2),
        faith=_clamp(b("faith") + 10 + traits.piety * 0.6),
        knowledge=_clamp(b("knowledge") + traits.ambition * 0.2),
        order=_clamp(20 + traits.piety * 0.3 + traits.pragmatism * 0.2),
        community=_clamp(b("community") + 20 + traits.compassion * 0.4 + traits.piety * 0.1),
        harvest=_clamp(b("harvest")),
        stability=_clamp(30 + traits.pragmatism * 0.3),
    )
    return needs


# ---------------------------------------------------------------------------
# 1d: Need urgency thresholds
# ---------------------------------------------------------------------------

def _needs_dict(needs: NpcNeeds) -> Dict[str, float]:
    return needs.model_dump()


def get_urgent_needs(needs: NpcNeeds) -> List[str]:
    """Returns needs below 30 (urgent) sorted by value ascending."""
    d = _needs_dict(needs)
    return sorted(
        [k for k, v in d.items() if v < 30],
        key=lambda k: d[k],
    )


def get_critical_needs(needs: NpcNeeds) -> List[str]:
    """Returns needs below 15 (critical — overrides everything else)."""
    d = _needs_dict(needs)
    return sorted(
        [k for k, v in d.items() if v < 15],
        key=lambda k: d[k],
    )


def get_dominant_need(needs: NpcNeeds) -> str:
    """Returns the single most urgent need driving behavior this tick."""
    d = _needs_dict(needs)
    return min(d, key=d.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1e: Need decay per tick
# ---------------------------------------------------------------------------

_FAST_DECAY_NEEDS = frozenset({"survival", "safety", "family"})
_MEDIUM_DECAY_NEEDS = frozenset({
    "social", "trade", "profit", "duty", "honor",
    "loyalty", "community", "harvest", "stability",
})
_SLOW_DECAY_NEEDS = frozenset({
    "power", "reputation", "faith", "knowledge", "order",
})


def _tension_index(tension: str) -> int:
    return _tension_index_util(tension)


def decay_needs(
    npc: NPC,
    world_tension: str,
    era_stability: str = "normal",
    current_turn: int = 0,
) -> NPC:
    """Decay all NPC needs by type-specific rates. Mutates in place."""
    tension_idx = _tension_index(world_tension)
    tension_bonus = tension_idx  # 0-3 extra decay for survival/safety

    d = npc.needs.model_dump()
    for name, val in d.items():
        if name in _FAST_DECAY_NEEDS:
            rate = random.uniform(3, 5) + tension_bonus
        elif name in _MEDIUM_DECAY_NEEDS:
            rate = random.uniform(2, 4)
        else:
            rate = random.uniform(1, 2)

        new_val = max(0.0, val - rate)
        d[name] = new_val

        if new_val < 15 and val >= 15:
            npc.needs_history.append({
                "turn": current_turn,
                "need": name,
                "value": round(new_val, 1),
                "event": "critical_threshold",
            })

    npc.needs = NpcNeeds(**d)
    return npc


# ---------------------------------------------------------------------------
# 1f: Dynamic need shifts from events
# ---------------------------------------------------------------------------

def apply_need_shift(
    npc: NPC,
    event_type: str,
    context: Optional[Dict] = None,
    current_turn: int = 0,
) -> NPC:
    """Apply event-driven need shifts. Some also permanently shift traits."""
    ctx = context or {}
    d = npc.needs.model_dump()
    t = npc.personality.model_dump()
    history_entry = {"turn": current_turn, "event": event_type, "shifts": {}}

    if event_type == "witness_death":
        d["survival"] = _clamp(d["survival"] + 15)
        d["safety"] = _clamp(d["safety"] + 10)
        if t["piety"] > 50:
            d["faith"] = _clamp(d["faith"] + 5)
        history_entry["shifts"] = {"survival": 15, "safety": 10}

    elif event_type == "betrayed":
        d["loyalty"] = _clamp(d["loyalty"] - 20)
        d["social"] = _clamp(d["social"] - 10)
        if t["ambition"] > 60:
            d["power"] = _clamp(d["power"] + 10)
        history_entry["shifts"] = {"loyalty": -20, "social": -10}

    elif event_type == "family_death":
        d["family"] = 100.0
        t["compassion"] = max(0, t["compassion"] - 5)
        history_entry["shifts"] = {"family": "spike_100", "compassion_trait": -5}

    elif event_type == "gain_wealth":
        d["trade"] = _clamp(min(d["trade"], 10.0))
        d["profit"] = _clamp(min(d["profit"], 10.0))
        d["reputation"] = _clamp(d["reputation"] + 20)
        d["safety"] = _clamp(d["safety"] + 15)
        history_entry["shifts"] = {"trade": "drop_10", "profit": "drop_10", "reputation": 20}

    elif event_type == "imprisoned":
        d["survival"] = _clamp(max(d["survival"], 90.0))
        d["safety"] = _clamp(max(d["safety"], 90.0))
        d["power"] = _clamp(d["power"] + 20)
        for k in d:
            if k not in ("survival", "safety", "power"):
                d[k] = _clamp(d[k] * 0.5)
        history_entry["shifts"] = {"survival": "spike_90+", "safety": "spike_90+", "others": "suppressed"}

    elif event_type == "achieve_goal":
        dominant = get_dominant_need(NpcNeeds(**d))
        d[dominant] = _clamp(min(d[dominant], 5.0))
        history_entry["shifts"] = {dominant: "drop_5"}

    elif event_type == "prolonged_peace":
        d["survival"] = _clamp(d["survival"] - 4)
        d["safety"] = _clamp(d["safety"] - 4)
        d["social"] = _clamp(d["social"] + 15)
        d["community"] = _clamp(d["community"] + 15)
        history_entry["shifts"] = {"survival": -4, "safety": -4, "social": 15, "community": 15}

    elif event_type == "religious_event":
        d["faith"] = _clamp(d["faith"] + 30)
        if t["piety"] > 80:
            d["order"] = _clamp(d["order"] + 10)
        t["piety"] = min(100, t["piety"] + 5)
        history_entry["shifts"] = {"faith": "spike", "piety_trait": 5}

    elif event_type == "prolonged_hunger":
        d["survival"] = _clamp(max(d["survival"], 95.0))
        t["pragmatism"] = min(100, t["pragmatism"] + 5)
        t["compassion"] = max(0, t["compassion"] - 5)
        history_entry["shifts"] = {"survival": "spike_95", "pragmatism_trait": 5, "compassion_trait": -5}

    elif event_type == "deep_relationship":
        bound_npc_id = ctx.get("bound_npc_id")
        d["loyalty"] = _clamp(d["loyalty"] + 20)
        d["social"] = _clamp(d["social"] + 20)
        if bound_npc_id:
            history_entry["shifts"] = {"loyalty": 20, "social": 20, "bound_to": bound_npc_id}
        else:
            history_entry["shifts"] = {"loyalty": 20, "social": 20}

    elif event_type == "relationship_death":
        d["loyalty"] = _clamp(d["loyalty"] * 0.2)
        for k in d:
            if k != "survival":
                d[k] = _clamp(d[k] * 0.3)
        history_entry["shifts"] = {"loyalty": "collapse", "others": "suppressed_grief"}

    npc.needs = NpcNeeds(**d)
    npc.personality = PersonalityTraits(**t)
    npc.needs_history.append(history_entry)
    return npc


# ---------------------------------------------------------------------------
# Archetype baseline dispositions (used by drift system)
# ---------------------------------------------------------------------------

ARCHETYPE_BASELINE_DISPOSITION: Dict[str, str] = {
    "merchant": "cautious",
    "soldier":  "guarded",
    "priest":   "formal",
    "clergy":   "formal",
    "farmer":   "wary",
    "noble":    "reserved",
    "scribe":   "neutral",
    "refugee":  "fearful",
    "general":  "commanding",
}


# ---------------------------------------------------------------------------
# NPC Utility Scoring (Sims pattern)
# ---------------------------------------------------------------------------

WORLD_OPPORTUNITIES: Dict[str, Dict] = {
    "trade_caravan_passing": {
        "satisfies": ["trade", "profit", "social"],
    },
    "siege_threat": {
        "satisfies_if_soldier": ["duty", "honor"],
        "threatens": ["survival", "safety", "family"],
    },
    "religious_gathering": {
        "satisfies": ["faith", "community", "social"],
    },
    "political_upheaval": {
        "satisfies_if_noble": ["power", "reputation"],
        "threatens": ["stability", "safety"],
    },
    "food_shortage": {
        "threatens": ["survival", "family", "stability"],
    },
    "travel_opportunity": {
        "satisfies": ["trade", "social", "knowledge"],
        "costs": ["safety", "stability"],
    },
    "conflict_nearby": {
        "threatens": ["survival", "safety", "family"],
    },
    "peaceful_conditions": {
        "satisfies": ["stability", "community", "social"],
    },
    "wealthy_patron_present": {
        "satisfies": ["profit", "reputation", "social"],
    },
    "sick_community_member": {
        "satisfies_if_compassionate": ["community", "social", "faith"],
    },
}


def need_urgency_weight(need_value: float) -> float:
    """Maslow-inspired curve: critical needs weight exponentially."""
    if need_value < 15:
        return 5.0
    if need_value < 30:
        return 3.0
    if need_value < 50:
        return 1.5
    return 1.0


def _get_relevant_needs(
    opportunity: Dict, npc_archetype: str, npc_traits: PersonalityTraits,
) -> List[str]:
    """Resolve which needs an opportunity addresses for this specific NPC."""
    needs: List[str] = []

    needs.extend(opportunity.get("satisfies", []))
    needs.extend(opportunity.get("threatens", []))
    needs.extend(opportunity.get("costs", []))

    if npc_archetype in ("soldier", "general"):
        needs.extend(opportunity.get("satisfies_if_soldier", []))
    if npc_archetype in ("noble",):
        needs.extend(opportunity.get("satisfies_if_noble", []))
    if npc_traits.compassion > 60:
        needs.extend(opportunity.get("satisfies_if_compassionate", []))

    return needs


def score_opportunity(npc: NPC, opportunity_type: str, context: Dict = None) -> float:
    """Score how strongly an NPC is drawn to an opportunity.

    Higher score = more compelling. Uses Maslow-weighted need urgency.
    """
    opp = WORLD_OPPORTUNITIES.get(opportunity_type)
    if not opp:
        return 0.0

    relevant_needs = _get_relevant_needs(opp, npc.archetype, npc.personality)
    if not relevant_needs:
        return 0.0

    needs_dict = npc.needs.model_dump()
    total = 0.0
    for need_name in relevant_needs:
        val = needs_dict.get(need_name, 50.0)
        total += need_urgency_weight(val) * (100.0 - val) / 100.0

    return total


def _detect_opportunities(npc: NPC, state) -> List[str]:
    """Detect which opportunities are present at the NPC's location."""
    from backend.world_state import TENSION_LEVELS

    opportunities: List[str] = []

    try:
        npc_loc = next(l for l in state.locations if l.id == npc.location)
    except StopIteration:
        return ["peaceful_conditions"]

    tension_map = {"low": 10, "moderate": 40, "high": 70, "critical": 95}
    tension = tension_map.get(npc_loc.political_tension, 40)

    if tension >= 80:
        opportunities.append("siege_threat")
    if tension >= 60:
        opportunities.append("conflict_nearby")
        opportunities.append("political_upheaval")
    if tension < 30:
        opportunities.append("peaceful_conditions")
        opportunities.append("travel_opportunity")

    if npc_loc.food_scarcity in ("scarce", "critical"):
        opportunities.append("food_shortage")
    if npc_loc.trade_routes:
        opportunities.append("trade_caravan_passing")

    nearby_npcs = [n for n in state.npcs if n.location == npc.location and n.id != npc.id]
    if any(n.archetype in ("noble",) for n in nearby_npcs):
        opportunities.append("wealthy_patron_present")

    from backend.event_vocab import EPIDEMIC_TYPES, RELIGIOUS_EVENT_TYPES

    has_sick = any(
        e.action_type in EPIDEMIC_TYPES
        and e.location == npc.location
        for e in state.events
    )
    if has_sick:
        opportunities.append("sick_community_member")

    has_religious = any(
        e.action_type in RELIGIOUS_EVENT_TYPES
        and e.location == npc.location
        and e.turn >= state.turn - 2
        for e in state.events
    )
    if has_religious:
        opportunities.append("religious_gathering")

    if not opportunities:
        opportunities.append("peaceful_conditions")

    return opportunities


def choose_autonomous_action(npc: NPC, state) -> str:
    """Score all available opportunities and pick one with deliberate imperfection.

    Returns the opportunity type string. The LLM only narrates this decision.
    Randomly selects from top-3 scoring options weighted by score.
    """
    opportunities = _detect_opportunities(npc, state)

    scored = []
    for opp_type in set(opportunities):
        s = score_opportunity(npc, opp_type)
        scored.append((s, opp_type))

    scored.sort(key=lambda x: -x[0])

    top_n = scored[:3]
    if not top_n:
        return "peaceful_conditions"

    scores = [max(s, 0.1) for s, _ in top_n]
    total = sum(scores)
    weights = [s / total for s in scores]

    r = random.random()
    cumulative = 0.0
    for weight, (_, opp_type) in zip(weights, top_n):
        cumulative += weight
        if r <= cumulative:
            return opp_type

    return top_n[0][1]
