"""Canonical event-type vocabulary for world-event detection.

Downstream code checks event.action_type against these sets when scanning
the event log.  Centralizing them here (rather than inline string literals)
keeps vocabulary consistent with action_parser.ALIASES and makes drift-
resistant additions a one-line change.
"""

from __future__ import annotations

EPIDEMIC_TYPES: frozenset[str] = frozenset({"epidemic", "plague", "sickness"})
FAMINE_TYPES: frozenset[str] = frozenset({"famine"})
SIEGE_TYPES: frozenset[str] = frozenset({"siege"})
RELIGIOUS_EVENT_TYPES: frozenset[str] = frozenset({"religious_event", "religious_gathering"})

# Events that must NEVER be compacted out of state.events.  Includes every
# canonical player action_type from action_parser.ALIASES plus death and travel.
# Used by world_state.build_story_summary (which slices) and by world_engine
# compaction (which deletes).  Single source of truth: edit here, not in two
# places.  Anything NOT in this set is treated as ambient and is eligible for
# eviction once it ages out of the recent window.
PRIORITY_EVENT_TYPES: frozenset[str] = frozenset({
    "speak", "trade", "petition", "threaten", "betray", "attack",
    "steal", "negotiate", "defend", "fight", "siege", "alliance",
    "hoard", "prevent", "save", "flee", "death", "travel",
})
