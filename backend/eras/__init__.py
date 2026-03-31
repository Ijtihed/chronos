"""Era configuration registry.

Each era defines: name, year, region, description, archetype templates,
and location templates. Used by run initialization to generate characters
and seed the world.
"""

from __future__ import annotations

import random
from typing import Dict, List

from backend.eras.roman_late_empire import ERA as ROMAN_LATE_EMPIRE
from backend.eras.viking_age import ERA as VIKING_AGE
from backend.eras.crusader_states import ERA as CRUSADER_STATES
from backend.eras.black_death import ERA as BLACK_DEATH
from backend.eras.fall_of_constantinople import ERA as FALL_OF_CONSTANTINOPLE

ALL_ERAS: Dict[str, dict] = {
    "roman_late_empire": ROMAN_LATE_EMPIRE,
    "viking_age": VIKING_AGE,
    "crusader_states": CRUSADER_STATES,
    "black_death": BLACK_DEATH,
    "fall_of_constantinople": FALL_OF_CONSTANTINOPLE,
}

ERA_KEYS: List[str] = list(ALL_ERAS.keys())


def get_era(key: str) -> dict:
    return ALL_ERAS[key]


def random_era() -> tuple:
    """Return (era_key, era_config) for a random era."""
    key = random.choice(ERA_KEYS)
    return key, ALL_ERAS[key]
