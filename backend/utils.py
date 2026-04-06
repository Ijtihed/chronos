"""Shared utility functions used across multiple backend modules.

Consolidates graph distance, tension helpers, and other
small functions that were duplicated across world_drift,
world_events, world_engine, npc_personality, and player_knowledge.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from backend.world_state import WorldState

TENSION_LEVELS = ["low", "moderate", "high", "critical"]

_TENSION_NUMERIC = {"low": 10, "moderate": 40, "high": 70, "critical": 95}


def tension_numeric(tension: str) -> int:
    """Map tension string to a 0-100 scale for threshold checks."""
    return _TENSION_NUMERIC.get(tension, 40)


def tension_index(tension: str) -> int:
    """Map tension string to its index in TENSION_LEVELS (0-3)."""
    if tension in TENSION_LEVELS:
        return TENSION_LEVELS.index(tension)
    return 1


def graph_distance(loc_a: str, loc_b: str, state: "WorldState") -> int:
    """BFS shortest path between two location IDs. Returns 999 if unreachable."""
    if loc_a == loc_b:
        return 0

    adj: Dict[str, Dict[str, int]] = {}
    for loc in state.locations:
        adj[loc.id] = dict(loc.neighbors)

    visited = {loc_a}
    queue: deque = deque([(loc_a, 0)])
    while queue:
        current, dist = queue.popleft()
        for neighbor in adj.get(current, {}):
            if neighbor == loc_b:
                return dist + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    return 999
