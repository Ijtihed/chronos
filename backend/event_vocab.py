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
