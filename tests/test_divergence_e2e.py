"""End-to-end divergence + density + target-miss tests.

Uses tests._divergence_harness to exercise the real scheduling and
stage-2 validation paths with LLM calls mocked.

Three test groups:

  TestDivergenceE2E:
    Player action contradicting Sack of Rome 410 produces the real
    observable effects: an entry in state.historical_divergences and
    supersession of any canonical-event-sourced consequence queue
    entries.

  TestDensity:
    Per-action-type breakdown of scheduled vs fired vs superseded.
    Flags any type with >25% supersession rate.

  TestTargetMissFallback:
    Target-dependent handlers (hostile, betray, save) schedule a
    rumor fallback when the target string doesn't match any NPC,
    rather than silently scheduling nothing.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.persistence import init_db
from backend.world_state import create_initial_state
from tests._divergence_harness import make_parsed, run_player_turn


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def _init_db_module():
    """Ensure the historical_events table exists for divergence tests."""
    await init_db()


# ---------------------------------------------------------------------------
# Item A: Divergence E2E
# ---------------------------------------------------------------------------

class TestDivergenceE2E:
    """A player action contradicting canonical history fires divergence.

    Canonical event under test: Sack of Rome 410
      id=881, year=410, type=war, region=Italia, canonical=True,
      event text contains "Sack of Rome".

    The Roman Late Empire starting state places the player in Ariminum
    in year 410 with era.region="Italia". A player action with
    action_type="prevent" (maps to war) and target="Rome" (substring
    match against "Sack of Rome") at significance >= 0.6 should:
      - Add an entry to state.historical_divergences
      - Reference the canonical event by id/text
      - Mark consequences sourced from the canonical event as
        superseded (behavior of mark_consequence_superseded_mem)
    """

    @pytest.mark.xfail(
        reason=(
            "Requires the historical_events table to be seeded (Sack of Rome 410). "
            "`build_events_db.py` is not part of CI because it hits Wikidata SPARQL + "
            "Wikipedia. Either add a fixture that inserts the minimum Roman canonical "
            "events, or stand up a tiny seed-events JSON the harness can load."
        ),
        strict=False,
    )
    @pytest.mark.asyncio
    async def test_prevent_sack_of_rome_registers_divergence(self):
        state = create_initial_state()
        parsed = make_parsed(
            action_type="prevent",
            significance_score=0.8,
            target="Rome",
            intent="stop Alaric from sacking Rome",
            era_description=(
                "Corvinus sets out to warn Rome of the approaching Visigoths."
            ),
        )
        snap = await run_player_turn(state, parsed)

        assert len(snap.divergences_appended) >= 1, (
            "Expected at least one historical divergence entry"
        )
        divergence = snap.divergences_appended[0]
        event_text = divergence.get("canonical_event", "").lower()
        assert "rome" in event_text, (
            f"Divergence event text should reference Rome, got: {event_text!r}"
        )
        assert divergence.get("action_type") == "prevent"
        assert "turn" in divergence

    @pytest.mark.asyncio
    async def test_no_divergence_for_unrelated_target(self):
        """A prevent action with an unrelated target does not fire."""
        state = create_initial_state()
        parsed = make_parsed(
            action_type="prevent",
            significance_score=0.8,
            target="the granary fire",
            intent="prevent a small fire",
            era_description="Corvinus puts out a minor fire.",
        )
        snap = await run_player_turn(state, parsed)

        # The target string "the granary fire" has no substring overlap
        # with any canonical event text, so divergence should NOT fire.
        assert len(snap.divergences_appended) == 0

    @pytest.mark.asyncio
    async def test_low_significance_skips_divergence(self):
        """Divergence only runs at sig >= 0.6 (gated in _execute_turn)."""
        state = create_initial_state()
        parsed = make_parsed(
            action_type="prevent",
            significance_score=0.55,  # Below 0.6 gate
            target="Rome",
            intent="minor intervention",
            era_description="Trivial action.",
        )
        snap = await run_player_turn(state, parsed)
        assert len(snap.divergences_appended) == 0


# ---------------------------------------------------------------------------
# Item B: Density verification
# ---------------------------------------------------------------------------

_TARGETED_TYPES = frozenset({"attack", "threaten", "steal", "betray", "save"})

# Every action_type with a specific dispatch handler.  For targeted
# types we supply a valid NPC so the specific (non-fallback) path
# fires, yielding the "best case" density we want to measure.
_DENSITY_CASES = [
    ("attack",    "Lucius Gallus"),
    ("threaten",  "Lucius Gallus"),
    ("steal",     "Lucius Gallus"),
    ("betray",    "Lucius Gallus"),
    ("trade",     None),
    ("negotiate", None),
    ("petition",  None),
    ("fight",     None),
    ("siege",     None),
    ("alliance",  None),
    ("defend",    None),
    ("prevent",   None),
    ("hoard",     None),
    ("save",      "Lucius Gallus"),
]


class TestDensity:
    """Per-action-type breakdown: scheduled vs fired vs superseded."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action_type,target", _DENSITY_CASES)
    async def test_scheduled_at_least_one_at_sig_06(self, action_type, target):
        state = create_initial_state()
        parsed = make_parsed(
            action_type=action_type,
            significance_score=0.6,
            target=target,
            era_description=f"Test: {action_type}.",
        )
        snap = await run_player_turn(state, parsed)
        assert snap.count_scheduled() >= 1, (
            f"{action_type}: scheduled 0 at sig 0.6"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action_type,target", _DENSITY_CASES)
    async def test_supersession_rate_below_25pct(self, action_type, target):
        state = create_initial_state()
        parsed = make_parsed(
            action_type=action_type,
            significance_score=0.6,
            target=target,
            era_description=f"Test: {action_type}.",
        )
        snap = await run_player_turn(state, parsed)

        scheduled = snap.count_scheduled()
        superseded = snap.count_superseded()
        rate = superseded / scheduled if scheduled else 0.0
        assert rate <= 0.25, (
            f"{action_type}: supersession rate {rate:.0%} "
            f"({superseded}/{scheduled}) exceeds 25% threshold"
        )

    @pytest.mark.asyncio
    async def test_collect_full_density_table(self):
        """Smoke test that builds the density report for human inspection.

        Runs every action type and asserts invariants hold. The actual
        table is printed to stdout for the report.
        """
        table = []
        for action_type, target in _DENSITY_CASES:
            state = create_initial_state()
            parsed = make_parsed(
                action_type=action_type,
                significance_score=0.6,
                target=target,
                era_description=f"Test: {action_type}.",
            )
            snap = await run_player_turn(state, parsed)
            table.append({
                "action_type": action_type,
                "scheduled": snap.count_scheduled(),
                "fired": snap.count_fired(),
                "superseded": snap.count_superseded(),
                "pending": snap.count_pending(),
            })

        for row in table:
            assert row["scheduled"] == (
                row["fired"] + row["superseded"] + row["pending"]
            ), f"Mismatch in {row}"
            print(
                f"{row['action_type']:>10s}  scheduled={row['scheduled']}  "
                f"fired={row['fired']}  superseded={row['superseded']}  "
                f"pending={row['pending']}"
            )


# ---------------------------------------------------------------------------
# Item C: Target-miss fallback
# ---------------------------------------------------------------------------

class TestTargetMissFallback:
    """Target-dependent handlers fall back to a rumor when target misses.

    The 4 affected handlers: _cq_hostile (attack, threaten, steal),
    _cq_betray, _cq_save. Each replaces (does not stack with) its
    specific consequence with a single rumor at player location when
    the target string doesn't match any NPC.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action_type", [
        "attack", "threaten", "steal", "betray", "save",
    ])
    async def test_target_miss_still_schedules_one(self, action_type):
        state = create_initial_state()
        parsed = make_parsed(
            action_type=action_type,
            significance_score=0.5,
            target="NonexistentPerson",  # Will not match any NPC
            era_description=f"Test: {action_type} with missing target.",
        )
        snap = await run_player_turn(state, parsed)
        assert snap.count_scheduled() >= 1, (
            f"{action_type} with missing target scheduled 0 consequences"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action_type", [
        "attack", "threaten", "steal", "save",
    ])
    async def test_target_miss_produces_rumor(self, action_type):
        """The fallback is specifically a rumor at player location."""
        state = create_initial_state()
        parsed = make_parsed(
            action_type=action_type,
            significance_score=0.5,
            target="NonexistentPerson",
            era_description=f"Test: {action_type} fallback.",
        )
        snap = await run_player_turn(state, parsed)
        rumors = [o for o in snap.consequence_outcomes
                  if o.effect_type == "rumor"]
        assert len(rumors) >= 1, (
            f"{action_type} target-miss did not produce a rumor fallback"
        )

    @pytest.mark.asyncio
    async def test_betray_target_miss_produces_rumor(self):
        """Betray with missing target → single rumor, NOT tension+disposition."""
        state = create_initial_state()
        parsed = make_parsed(
            action_type="betray",
            significance_score=0.5,
            target="NonexistentPerson",
            era_description="Test: betray fallback.",
        )
        snap = await run_player_turn(state, parsed)

        effect_types = [o.effect_type for o in snap.consequence_outcomes]
        assert "rumor" in effect_types
        # Fallback REPLACES the normal behavior — should not see disposition_shift
        assert "disposition_shift" not in effect_types, (
            f"betray target-miss should not produce disposition_shift, "
            f"got effects: {effect_types}"
        )

    @pytest.mark.asyncio
    async def test_target_match_still_fires_specific_handler(self):
        """Confirm target-match path still works (no regression)."""
        state = create_initial_state()
        parsed = make_parsed(
            action_type="betray",
            significance_score=0.5,
            target="Lucius Gallus",
            era_description="Test: betray with valid target.",
        )
        snap = await run_player_turn(state, parsed)

        effect_types = {o.effect_type for o in snap.consequence_outcomes}
        assert "tension_shift" in effect_types
        assert "disposition_shift" in effect_types
        # No rumor fallback when target matches
        rumors = [o for o in snap.consequence_outcomes
                  if o.effect_type == "rumor"]
        assert len(rumors) == 0, (
            f"betray with matched target should not produce rumor, "
            f"got: {rumors}"
        )
