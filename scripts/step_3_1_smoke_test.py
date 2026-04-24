#!/usr/bin/env python3
"""Phase 3 Step 3.1 — scene-illustration trigger smoke test.

Exercises the trigger system end-to-end through the real turn-
advancing paths. Five scripted runs, deterministic player inputs,
real Ollama-backed NPC simulation. Logs are inspected afterwards
to confirm trigger plumbing produces sensible audit records.

This is a SMOKE TEST, not a substitute for natural-input playtesting.
Real threshold tuning still requires the user playing varied runs.
It verifies:
  - Triggers fire across the four types at least once.
  - No trigger-system exceptions bubble up.
  - Logs persist to SQLite with the illustration_trigger column
    populated (or explicitly NULL).

Requires:
  - Ollama running locally (same models the main project uses).
  - Python 3.10+ env with project deps installed.
    (Run with `source .venv/bin/activate && python scripts/step_3_1_smoke_test.py`)

Not intended to run inside Cursor sandbox — wall time ~60-90 min.
Run in your own terminal with Ollama active.

Writes per-run details and a summary to scripts/step_3_1_smoke_output.txt.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before any backend import so GEMINI_* / CHRONOS_* match `uvicorn`.
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from backend.character_gen import generate_run
from backend.eras import ALL_ERAS
from backend.llm_provider import ollama_ok, track_turn_cost
from backend.main import (  # noqa: E402 — path insert above
    SkipRequest,
    TurnRequest,
    _execute_skip,
    _execute_turn,
)
from backend.persistence import (  # noqa: E402
    get_turn_logs,
    init_db,
    save_session,
)

OUTPUT_FILE = Path(__file__).parent / "step_3_1_smoke_output.txt"

# A step directive is either a natural-language player input string
# or the sentinel "[[SKIP:N]]" which triggers _execute_skip(ticks=N).
SKIP_PREFIX = "[[SKIP:"
SKIP_SUFFIX = "]]"


def _skip_ticks(spec: str) -> int | None:
    if not (spec.startswith(SKIP_PREFIX) and spec.endswith(SKIP_SUFFIX)):
        return None
    try:
        return int(spec[len(SKIP_PREFIX):-len(SKIP_SUFFIX)])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Run plans — deterministic, designed to exercise each trigger signal.
# ---------------------------------------------------------------------------

RUNS_PLAN: List[Dict[str, Any]] = [
    {
        "name": "Roman Late Empire — short dramatic death",
        "era_key": "roman_late_empire",
        "steps": [
            "I walk through the marketplace, greeting people I know.",
            "I ask the grain seller about rumors from the north.",
            "I share a meal with a soldier returning from the frontier.",
            "I travel to Ravenna.",
            "When the tax collector demands grain, I strike him down with a knife.",
            "I fight the guards who come for me.",
            "I fight on until I can no longer stand.",
            "I press my blade into the next soldier, knowing I will die here.",
        ],
        "post_death_observation_turns": 8,
    },
    {
        "name": "Viking Age — peaceful long life",
        "era_key": "viking_age",
        "steps": [
            "I greet my neighbor at the longhouse.",
            "I trade furs at the harbor.",
            "I go fishing with my cousin.",
            "I tell stories by the fire.",
            "I bring firewood to the elder.",
            "I bargain for a new axe.",
            "I walk the fields.",
            "I mend my boat.",
            "I travel to another settlement for the market.",
            "I trade for honey.",
            "I return home.",
            "I rest through the winter.",
            "I offer prayers at the harvest.",
            "I help raise a barn.",
            "I go to the thing to listen to disputes.",
            "I watch the ships come in.",
            "I repair my tools.",
            "I tell my grandchildren the old stories.",
            "I walk the coast at dusk.",
            "I share bread with a traveler.",
        ],
        "post_death_observation_turns": 0,
    },
    {
        "name": "Black Death — witnessed catastrophe",
        "era_key": "black_death",
        "steps": [
            "I walk through the piazza to hear the news.",
            "I attend morning mass at the duomo.",
            "I greet the bread-seller.",
            "I check on a family I have not seen in weeks.",
            "I visit the apothecary.",
            "I walk out to see what is happening at the city gate.",
            "I sit vigil with the dying in the street.",
            "I return home, shaken.",
            "I pray for those we have lost.",
        ],
        "post_death_observation_turns": 0,
    },
    {
        "name": "Crusader States — significance spread",
        "era_key": "crusader_states",
        "steps": [
            "I petition the lord for grain relief for my village.",
            "I trade spices at the harbor.",
            "I greet a pilgrim at the well.",
            "I negotiate an alliance with the neighboring lord.",
            "I defend the caravan from bandits.",
            "I speak with the priest about doctrine.",
            "I save a merchant's daughter from the flood.",
            "I hoard grain against the coming winter.",
            "I prevent the guard from executing a thief in the marketplace.",
            "I walk the walls at sunset, thinking.",
        ],
        "post_death_observation_turns": 0,
    },
    {
        "name": "Fall of Constantinople — skip-heavy",
        "era_key": "fall_of_constantinople",
        "steps": [
            "I walk along the harbor.",
            f"{SKIP_PREFIX}10{SKIP_SUFFIX}",
            "I pray for the city.",
            f"{SKIP_PREFIX}10{SKIP_SUFFIX}",
            "I visit the marketplace.",
            f"{SKIP_PREFIX}5{SKIP_SUFFIX}",
            "I return home.",
        ],
        "post_death_observation_turns": 0,
    },
]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def _run_one(plan: Dict[str, Any]) -> Dict[str, Any]:
    print(f"\n{'=' * 72}")
    print(f"  {plan['name']}")
    print(f"{'=' * 72}")

    era_key = plan["era_key"]
    era_config = ALL_ERAS[era_key]
    errors: List[str] = []
    run_id: str | None = None

    try:
        t0 = time.monotonic()
        with track_turn_cost():
            state = await generate_run(era_config)
        await save_session(state)
        run_id = state.run_id
        print(
            f"[setup] {era_key} run_id={run_id} player={state.player.name} "
            f"({state.player.archetype}) loc={state.player.location} "
            f"({time.monotonic() - t0:.1f}s)"
        )
    except Exception as exc:
        print(f"[setup] FAILED: {exc}")
        traceback.print_exc()
        return {
            "run_id": None,
            "era_key": era_key,
            "name": plan["name"],
            "turns_executed": 0,
            "errors": [f"setup: {exc}"],
        }

    turns_executed = 0

    for idx, step in enumerate(plan["steps"], 1):
        ticks = _skip_ticks(step)
        t0 = time.monotonic()
        try:
            if ticks is not None:
                print(f"  [{idx:2d}] SKIP {ticks} ticks ...", flush=True)
                await _execute_skip(run_id, SkipRequest(ticks=ticks))
            else:
                preview = step if len(step) <= 72 else step[:69] + "..."
                print(f"  [{idx:2d}] {preview}", flush=True)
                await _execute_turn(run_id, TurnRequest(player_input=step))
            dt = time.monotonic() - t0
            turns_executed += 1
            print(f"       ok ({dt:.1f}s)")
        except Exception as exc:
            dt = time.monotonic() - t0
            print(f"       FAILED after {dt:.1f}s: {exc}")
            traceback.print_exc()
            errors.append(f"step {idx}: {type(exc).__name__}: {exc}")
            break

    obs_turns = plan.get("post_death_observation_turns", 0) or 0
    for i in range(obs_turns):
        t0 = time.monotonic()
        try:
            print(f"  [obs {i + 1:2d}] I wait.", flush=True)
            await _execute_turn(run_id, TurnRequest(player_input="I wait."))
            dt = time.monotonic() - t0
            turns_executed += 1
            print(f"         ok ({dt:.1f}s)")
        except Exception as exc:
            dt = time.monotonic() - t0
            print(f"         FAILED after {dt:.1f}s: {exc}")
            errors.append(f"obs {i + 1}: {type(exc).__name__}: {exc}")
            break

    return {
        "run_id": run_id,
        "era_key": era_key,
        "name": plan["name"],
        "turns_executed": turns_executed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


async def _collect_summary(run_results: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Step 3.1 smoke test — summary")
    lines.append("=" * 72)
    lines.append("")

    per_run_triggers: Dict[str, List[Dict[str, Any]]] = {}
    for r in run_results:
        if not r["run_id"]:
            per_run_triggers[r["name"]] = []
            continue
        try:
            logs = await get_turn_logs(r["run_id"])
        except Exception as exc:
            lines.append(f"[warn] could not fetch turn_logs for {r['run_id']}: {exc}")
            per_run_triggers[r["name"]] = []
            continue
        triggers_in_run: List[Dict[str, Any]] = []
        for log in logs:
            trig = log.get("illustration_trigger")
            if trig:
                triggers_in_run.append({
                    "turn": log["turn_number"],
                    "type": trig.get("type"),
                    "reason": trig.get("reason", ""),
                    "tone_hint": trig.get("tone_hint", ""),
                })
        per_run_triggers[r["name"]] = triggers_in_run

    total_turns = sum(r["turns_executed"] for r in run_results)
    total_triggers = sum(len(v) for v in per_run_triggers.values())
    type_counts: Counter = Counter()
    tone_counts: Counter = Counter()
    for entries in per_run_triggers.values():
        for e in entries:
            type_counts[e["type"]] += 1
            tone_counts[e["tone_hint"] or "<none>"] += 1

    lines.append(f"total turns played (across all runs): {total_turns}")
    lines.append(f"total triggers fired: {total_triggers}")
    lines.append("")
    lines.append("breakdown by trigger_type:")
    for t, n in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {t:<25} {n}")
    lines.append("")
    lines.append("breakdown by tone_hint:")
    for t, n in sorted(tone_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {t:<25} {n}")
    lines.append("")

    # Warnings / sanity flags
    per_run_counts = [(r["name"], len(per_run_triggers.get(r["name"], [])))
                      for r in run_results]
    lines.append("per-run trigger counts:")
    for name, n in per_run_counts:
        flag = ""
        if n > 8:
            flag = "  <-- WARNING: >8 triggers (maybe too loose)"
        elif n == 0:
            flag = "  <-- note: zero triggers"
        lines.append(f"  {n:3d}  {name}{flag}")
    lines.append("")

    zero_narrative_runs = [
        name for name, entries in per_run_triggers.items()
        if not any(e["type"] == "major_narrative_moment" for e in entries)
    ]
    if len(zero_narrative_runs) == len(run_results) and run_results:
        lines.append(
            "WARNING: NO run produced any major_narrative_moment firings. "
            "Thresholds may be too tight (or the scripted actions are not "
            "provoking enough significance)."
        )
    elif zero_narrative_runs:
        lines.append(
            "note: these runs produced zero major_narrative_moment firings:"
        )
        for name in zero_narrative_runs:
            lines.append(f"  - {name}")
    lines.append("")

    lines.append("=" * 72)
    lines.append("Per-run trigger dumps")
    lines.append("=" * 72)
    for r in run_results:
        lines.append("")
        lines.append(f"## {r['name']}")
        lines.append(f"   era={r['era_key']} run_id={r['run_id']} "
                     f"turns_executed={r['turns_executed']}")
        if r["errors"]:
            lines.append(f"   errors: {json.dumps(r['errors'], indent=None)}")
        entries = per_run_triggers.get(r["name"], [])
        if not entries:
            lines.append("   (no triggers fired)")
        else:
            for e in entries:
                lines.append(
                    f"   turn {e['turn']:3d}  {e['type']:<23} "
                    f"tone={e['tone_hint']:<12}  reason: {e['reason']}"
                )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main() -> int:
    print("Phase 3 Step 3.1 — trigger smoke test")
    print("-" * 72)

    # Fail fast if Ollama is down.
    print("[precheck] verifying Ollama reachability...")
    if not await ollama_ok():
        print(
            "\n[fatal] Ollama is not reachable. Start it with:\n"
            "    ollama serve\n"
            "and ensure a model is pulled (e.g. llama3.1:8b).\n"
            "Aborting."
        )
        return 2
    print("[precheck] ollama ok")

    await init_db()

    overall_t0 = time.monotonic()
    results: List[Dict[str, Any]] = []
    for plan in RUNS_PLAN:
        try:
            result = await _run_one(plan)
        except Exception as exc:
            print(f"\n[plan] UNCAUGHT exception in '{plan['name']}': {exc}")
            traceback.print_exc()
            result = {
                "run_id": None,
                "era_key": plan["era_key"],
                "name": plan["name"],
                "turns_executed": 0,
                "errors": [f"uncaught: {type(exc).__name__}: {exc}"],
            }
        results.append(result)

    elapsed = time.monotonic() - overall_t0
    print(f"\n{'=' * 72}")
    print(f"  all runs complete — wall time {elapsed / 60:.1f} min")
    print(f"{'=' * 72}")

    summary = await _collect_summary(results)
    print("\n" + summary)

    OUTPUT_FILE.write_text(summary, encoding="utf-8")
    print(f"\nsummary written to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
