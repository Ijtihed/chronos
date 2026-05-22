"""Pin source-confidence classifier.

Phase 2.9 — when the player pins a passage of text from the manuscript,
the server classifies what the CHARACTER plausibly knew about it at the
time of pinning. The output is one of `observed | told_by | rumor |
inferred` plus an optional NPC attribution. The frontend uses the
classification to render different border styles per pin so uncertainty
is legible at a glance.

This is the first piece of persisted state in CHRONOS that explicitly
encodes player knowledge rather than ground truth. The classifier
reads the turn_logs row for the source turn and inspects:

    - npc_responses[].pov / .internal / .text -> told_by (with attribution)
    - ambient_activity[].activity             -> rumor
    - narrative_output (player POV)           -> observed
    - everything else                         -> inferred (default fallback)

Key shape note: the orchestrator (main.py `_build_npc_responses_mixed`
and `_build_npc_responses`) writes NPC speech under the key `pov` for
ambient NPCs and the key `pov` (reply) plus `internal` (private
thought) for addressed NPCs. The legacy `text` key is also accepted
as a fallback so older runs and synthetic test fixtures still work.

It is deterministic, has no LLM call, and is cheap. It runs once per
pin creation in the POST /api/run/{id}/pin handler and writes its
verdict into the `Pin.source_confidence` and `Pin.source_attribution`
fields.

Composes-with notes
-------------------
- The classifier never touches `WorldState` directly. It reads only
  the saved turn-log row, which is a frozen snapshot of what the
  player saw on that turn. This is the design rule from
  manuscript-as-artifact.md Phase 2.9: pin classification is
  player-perspective, not ground-truth.
- Substring matching uses a simple normalized-whitespace comparison.
  Selection-time text from the browser may have collapsed whitespace
  differently than the saved snapshot, so we normalize both sides
  before comparing.
"""

from __future__ import annotations

from typing import List, Tuple

from backend.persistence import get_turn_logs


def _normalize(s: str) -> str:
    """Collapse all whitespace to single spaces, strip ends. Cheap and
    enough for substring containment checks that survive minor
    cross-context whitespace differences."""
    return " ".join((s or "").split())


def _pick_best_npc_response(text_norm: str, npc_responses: List[dict]) -> Tuple[bool, str]:
    """Returns (matched, attribution). Walks the turn's NPC responses
    and returns the first one whose visible body contains the pinned
    text. Attribution is the NPC's display name.

    Body source priority: `pov` (the production key for both ambient
    POV and addressed-mode reply) > `internal` (addressed-mode private
    thought, also rendered to the player as italic text) > `text`
    (legacy key kept for back-compat with synthetic tests and any older
    persisted rows). Both `pov` and `internal` are concatenated when
    present, since either can carry the highlighted passage.
    """
    for resp in npc_responses or []:
        if not isinstance(resp, dict):
            continue
        # Concatenate every visible field so a pin that straddles the
        # reply and the internal thought still matches. Falls back to
        # the legacy `text` key.
        parts: list[str] = []
        for key in ("pov", "internal", "text"):
            v = resp.get(key)
            if v:
                parts.append(str(v))
        body = _normalize(" ".join(parts))
        if body and text_norm in body:
            return True, str(resp.get("npc_name") or resp.get("npc_id") or "").strip()
    return False, ""


def _matches_ambient(text_norm: str, ambient: List[dict]) -> bool:
    """True if the pinned text is contained inside any ambient
    activity's `activity` description for this turn."""
    for entry in ambient or []:
        if not isinstance(entry, dict):
            continue
        body = _normalize(entry.get("activity") or "")
        if body and text_norm in body:
            return True
    return False


def _matches_player_pov(text_norm: str, narrative: str) -> bool:
    """True if the pinned text appears in the player-POV narrative
    output for this turn. Many turns have a single narrative blob;
    the player's first-person experience lives there."""
    body = _normalize(narrative or "")
    return bool(body) and text_norm in body


async def classify_pin_source(
    *,
    text: str,
    run_id: str,
    source_turn_id: str,
) -> Tuple[str, str]:
    """Classify a pin's source confidence.

    Returns (confidence, attribution) where:
        confidence  : one of "observed" | "told_by" | "rumor" | "inferred"
        attribution : NPC name when confidence == "told_by", else ""

    The default fallback is "inferred", so if the source turn cannot
    be located (deleted run, bad turn id), we still return a valid
    string and the frontend renders the most-conservative border
    style.
    """
    text_norm = _normalize(text)
    if not text_norm:
        return "inferred", ""

    # Walk the turn logs and find the row for `source_turn_id`. The
    # frontend stamps source_turn_id as the DOM id of the turn-block
    # ("turn-<created_at>" or "manuscript-intro").
    #
    # The intro card is not a real turn-log row, but pinning from the
    # intro is treated as observed since the character plausibly knows
    # their own background.
    if source_turn_id == "manuscript-intro":
        return "observed", ""
    # Pin with NO source_turn_id at all -- the player typed something
    # arbitrary (or an older client doesn't stamp the source). We
    # don't know where it came from in the player's perception, so the
    # conservative "inferred" is correct.
    if not source_turn_id:
        return "inferred", ""

    try:
        rows = await get_turn_logs(run_id)
    except Exception:
        return "inferred", ""

    target = None
    for row in rows:
        # turn-block ids are formed as `turn-<created_at_ms>` on the
        # frontend. Match a few plausible shapes; we don't want to be
        # brittle to a renaming.
        cand_ids = {
            f"turn-{row.get('id') or ''}",
            f"turn-{row.get('turn_number') or ''}",
        }
        if source_turn_id in cand_ids:
            target = row
            break
    if target is None:
        # source_turn_id we don't recognize. Still try the most-recent
        # turn -- a fresh pin from the current scroll position is the
        # most-common case, and the frontend's id stamping has drifted
        # before. Worst case we land on inferred, which is the safe
        # default.
        if rows:
            target = rows[-1]
        else:
            return "inferred", ""

    # Order matters: a passage might appear in BOTH the npc_responses
    # block and the rolled-up narrative_output. We prefer the strongest
    # provenance signal (told_by > rumor > observed > inferred).
    matched, npc = _pick_best_npc_response(
        text_norm, target.get("npc_responses") or []
    )
    if matched:
        return "told_by", npc
    if _matches_ambient(text_norm, target.get("ambient_activity") or []):
        return "rumor", ""
    if _matches_player_pov(text_norm, target.get("narrative_output") or ""):
        return "observed", ""
    return "inferred", ""
