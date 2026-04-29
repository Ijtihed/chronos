"""Extract sensory grounding phrases from NPC POV text.

Pure regex; no LLM, no I/O. Used by main.py to populate
WorldState.used_grounding_details after each NPC POV completes,
which is then injected back into subsequent POV prompts as a
"sensory details already used in this run" list.

Three pattern groups:
  1. State + body part / clothing  (wet boot, bleeding hand, sore back)
  2. "stink/smell/taste/etc of X"  (smell of damp wool, taste of ashes)
  3. Historical aphorism             (King Alaric is dead in a riverbed)

Conservative by design: false positives are cheap (LLM picks a different
anchor next turn); missed repetition is what causes the wet-boot problem.
"""

from __future__ import annotations

import re
from typing import List, Set


# ---------------------------------------------------------------------------
# Pattern 1 -- state word + body part or clothing item
# ---------------------------------------------------------------------------

_STATE_WORDS = (
    r"bleeding|aching|sore|wet|dry|cold|hot|chapped|cracked|swollen|bruised|"
    r"bruising|festering|frozen|stiff|numb|trembling|shaking|hungry|stinking|"
    r"raw|torn|threadbare|mended|patched|chilled|shivering|sweating|clenched|"
    r"biting|burning|aching|cramping|throbbing|pounding|itching|gnawing|"
    r"rotting|rotten|broken|blistered|callused|calloused|filthy|stained|"
    r"bloodied|battered|weary|tired|exhausted"
)

_BODY_AND_CLOTHING = (
    r"boot[s]?|foot|feet|hand[s]?|stomach|gut|belly|back|throat|"
    r"tooth|teeth|eye[s]?|head|skull|knee[s]?|shoulder[s]?|bone[s]?|skin|"
    r"cloak|tunic|hood|sleeve[s]?|cap|mantle|apron|breeches|beard|"
    r"hair|nail[s]?|mouth|tongue|pulse|voice|breath|lip[s]?|finger[s]?|"
    r"chest|heart|leg[s]?|arm[s]?|wrist[s]?|ankle[s]?|neck|jaw|"
    r"thigh[s]?|hip[s]?|elbow[s]?|palm[s]?|sole[s]?|spine|ribs?|"
    r"forehead|brow|temple[s]?|ear[s]?|nose|chin|cheek[s]?|gums?|"
    r"shirt|coat|robe[s]?|sandal[s]?|shoe[s]?|gown|veil|scarf|kerchief|"
    r"boots?|leggings?|stockings?|girdle|belt|sash|wool"
)

# Forward order: "wet boot", "bleeding hands", "festering left leg".
_STATE_PATTERN_FWD = re.compile(
    r"\b(?P<state>" + _STATE_WORDS + r")\s+"
    r"(?:(?:left|right|old|new|good|bad)\s+)?"
    r"(?P<part>" + _BODY_AND_CLOTHING + r")\b",
    re.IGNORECASE,
)

# Inverted order: "my boot has been wet", "back is sore", "leg festering".
# We allow up to 5 filler tokens (auxiliary verbs, prepositions, possessives)
# between body part and state word. We re-emit as canonical "state + part"
# so the tracker stays consistent.
_STATE_PATTERN_INV = re.compile(
    r"\b(?P<part>" + _BODY_AND_CLOTHING + r")\b"
    r"(?:\s+\w+){0,5}?\s+"
    r"(?P<state>" + _STATE_WORDS + r")\b",
    re.IGNORECASE,
)

# State word followed by an unrelated noun, then near a body part. E.g.
# "festering wound on my right leg" -- captures "festering ... leg".
_STATE_NEAR_PART = re.compile(
    r"\b(?P<state>" + _STATE_WORDS + r")\b"
    r"(?:\s+\w+){0,4}?\s+"
    r"(?P<part>" + _BODY_AND_CLOTHING + r")\b",
    re.IGNORECASE,
)


def _state_pattern_matches(text: str):
    """Yield canonical 'state part' phrases from forward, inverted, and near matches."""
    seen = set()
    for m in _STATE_PATTERN_FWD.finditer(text):
        canonical = f"{m.group('state').lower()} {m.group('part').lower()}"
        if canonical not in seen:
            seen.add(canonical)
            yield canonical
    for m in _STATE_PATTERN_INV.finditer(text):
        canonical = f"{m.group('state').lower()} {m.group('part').lower()}"
        if canonical not in seen:
            seen.add(canonical)
            yield canonical
    for m in _STATE_NEAR_PART.finditer(text):
        canonical = f"{m.group('state').lower()} {m.group('part').lower()}"
        if canonical not in seen:
            seen.add(canonical)
            yield canonical

# ---------------------------------------------------------------------------
# Pattern 2 -- "stink/smell/taste/etc of X"
# ---------------------------------------------------------------------------

_SENSE_VERBS = (
    r"stink|smell|taste|sound|hum|sting|weight|feel|chill|bite|scrape|crunch"
)

_SENSE_PATTERN = re.compile(
    r"\b(?P<verb>" + _SENSE_VERBS + r")\s+of\s+"
    r"(?:the\s+|a\s+|my\s+|his\s+|her\s+|their\s+)?"
    r"(?P<obj>\w+(?:\s+\w+){0,3})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 3 -- historical aphorism (subject + verb + poetic completion)
# ---------------------------------------------------------------------------

# Title or named-figure subjects. "the X" matches "the Sultan", "the Emperor".
_TITLES = (
    r"king|queen|emperor|empress|sultan|caliph|pope|prince|princess|lord|lady|"
    r"bishop|abbot|tsar|khan|doge|consul|patriarch|prophet|messiah|"
    r"the\s+sultan|the\s+emperor|the\s+king|the\s+general|the\s+caliph"
)

_APHORISM_VERBS = (
    r"is|was|are|were|will\s+be|has\s+been|have\s+been|never|always|lies|"
    r"stands|walks|rides|comes|sits|drinks|eats|sleeps|prays|cuts|burns|"
    r"holds|dies|fell|will\s+fall|is\s+dead|is\s+coming|is\s+dragging|"
    r"is\s+returning|is\s+moving|is\s+marching|is\s+sending|is\s+building|"
    r"moves|marches|sends|builds|fights|crushes|destroys|conquers|threatens"
)

# A poetic completion needs at least one landscape/object word to avoid
# matching plain political mentions ("The Sultan is angry"). The completion
# captures 3-6 trailing words including a landscape or object anchor.
_LANDSCAPE_OR_OBJECT = (
    r"riverbed|river|sea|fields?|walls?|gates?|bridge|throne|tomb|grave|"
    r"saddle|ships?|sword|crown|hair|beard|nails?|ash|ashes|dust|fire|smoke|"
    r"snow|ice|stone|stones|silver|gold|harbor|horn|tunnel|hill|mountain|"
    r"tower|cathedral|palace|courtyard|altar|chain|rope|net|forge|bell|bells"
)

_APHORISM_PATTERN = re.compile(
    r"\b(?P<subj>" + _TITLES + r")"
    # Optional 's [noun] (e.g. "Sultan's fleet", "King's cannon")
    r"(?:'s\s+\w+)?\s+"
    # Optional proper-noun name, e.g. "King Alaric", "Sultan Mehmed"
    r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+)?"
    r"(?P<verb>" + _APHORISM_VERBS + r")\s+"
    # Up to 6 filler words then a landscape/object word, then up to 3 trailing
    r"(?P<completion>(?:\w+\s+){0,5}(?:" + _LANDSCAPE_OR_OBJECT + r")(?:\s+\w+){0,3})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_LEADING_DROP = re.compile(r"^(?:the|a|an|my|his|her|their|our|your)\s+", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def _normalise(phrase: str) -> str:
    """Lowercase, strip leading article/possessive, collapse whitespace."""
    s = phrase.strip().lower()
    s = _LEADING_DROP.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


def _word_count(s: str) -> int:
    return len(s.split())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_grounding_details(text: str) -> List[str]:
    """Extract sensory grounding phrases from a single NPC POV string.

    Returns a deduplicated list of normalised short phrases (2-7 words),
    in the order they first appeared in the text.
    """
    if not text or not text.strip():
        return []

    seen: Set[str] = set()
    out: List[str] = []

    def _add(phrase: str) -> None:
        norm = _normalise(phrase)
        if not norm:
            return
        wc = _word_count(norm)
        if wc < 2 or wc > 7:
            return
        if norm in seen:
            return
        seen.add(norm)
        out.append(norm)

    # Pattern 1: state + body/clothing (forward and inverted order)
    for phrase in _state_pattern_matches(text):
        _add(phrase)

    # Pattern 2: sense + of + object
    for m in _SENSE_PATTERN.finditer(text):
        _add(m.group(0))

    # Pattern 3: historical aphorism -- emit a trimmed canonical form
    # of "subject + landscape anchor" so the same aphorism in different
    # phrasings still collides on the tracker.
    _LANDSCAPE_RE = re.compile(_LANDSCAPE_OR_OBJECT, re.IGNORECASE)
    for m in _APHORISM_PATTERN.finditer(text):
        subj = m.group("subj").lower().strip()
        completion = m.group("completion") or ""
        landscape_match = _LANDSCAPE_RE.search(completion)
        if landscape_match:
            anchor = landscape_match.group(0).lower()
            # Canonical: "<subject> ... <landscape anchor>"
            _add(f"{subj} {anchor}")

    return out


def merge_into_tracker(
    tracker: List[str],
    new_phrases: List[str],
    cap: int = 30,
) -> List[str]:
    """Append new phrases to the tracker, dedupe in-place, FIFO-evict to cap.

    Returns the updated list (mutates and returns, for callers that want
    fluent style; callers may also discard the return value).
    """
    existing = set(tracker)
    for phrase in new_phrases:
        if phrase and phrase not in existing:
            tracker.append(phrase)
            existing.add(phrase)
    if len(tracker) > cap:
        # FIFO: drop oldest entries
        del tracker[: len(tracker) - cap]
    return tracker


def format_for_prompt(tracker: List[str]) -> str:
    """Render the tracker as a prompt-ready block, or "" if empty."""
    if not tracker:
        return ""
    lines = ["Sensory details already used in this run (do not reuse unchanged):"]
    for phrase in tracker:
        lines.append(f"- {phrase}")
    return "\n".join(lines)
