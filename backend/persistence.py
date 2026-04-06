"""SQLite session persistence for game state and turn logs.

Sessions: live WorldState as a JSON blob keyed by run_id.
Turn logs: append-only per-turn audit trail with state diffs (not full clones).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.world_state import WorldState

logger = logging.getLogger("chronos.persistence")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chronos.db"


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                run_id     TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS turn_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id              TEXT NOT NULL,
                turn_number         INTEGER NOT NULL,
                player_input        TEXT NOT NULL DEFAULT '',
                parsed_action       TEXT NOT NULL DEFAULT '{}',
                ambient_activity    TEXT NOT NULL DEFAULT '[]',
                npc_responses       TEXT NOT NULL DEFAULT '[]',
                state_changes       TEXT NOT NULL DEFAULT '{}',
                narrative_output    TEXT NOT NULL DEFAULT '',
                player_view_snapshot TEXT NOT NULL DEFAULT '{}',
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (run_id) REFERENCES sessions(run_id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_turn_logs_run_turn
            ON turn_logs (run_id, turn_number)
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                year            INTEGER NOT NULL,
                region          TEXT NOT NULL,
                event           TEXT NOT NULL,
                significance    TEXT NOT NULL CHECK(significance IN ('local','regional','civilizational')),
                type            TEXT NOT NULL CHECK(type IN ('war','epidemic','famine','political','religious','economic','natural_disaster','cultural')),
                affects         TEXT NOT NULL,
                canonical       INTEGER DEFAULT 1,
                wikidata_qid    TEXT,
                polity_context  TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_he_era
            ON historical_events (year, region)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_he_type
            ON historical_events (type, significance)
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS consequence_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                source_event_id INTEGER,
                trigger_turn    INTEGER NOT NULL,
                target_type     TEXT NOT NULL CHECK(target_type IN ('location','npc','region','global')),
                target_id       TEXT,
                effect_type     TEXT NOT NULL CHECK(effect_type IN (
                    'tension_shift','rumor','trade_disruption',
                    'npc_arrival','event_spawn','material_change'
                )),
                effect_payload  TEXT NOT NULL,
                fired           INTEGER DEFAULT 0,
                superseded      INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (run_id) REFERENCES sessions(run_id)
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cq_pending
            ON consequence_queue (run_id, trigger_turn, fired, superseded)
            """
        )
        await db.commit()


async def save_session(state: WorldState) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO sessions (run_id, state_json, created_at, updated_at)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(run_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = datetime('now')
            """,
            (state.run_id, state.model_dump_json()),
        )
        await db.commit()


async def load_session(run_id: str) -> Optional[WorldState]:
    if not DB_PATH.exists():
        return None
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT state_json FROM sessions WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return WorldState.model_validate_json(row[0])


async def delete_session(run_id: str) -> None:
    if not DB_PATH.exists():
        return
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM sessions WHERE run_id = ?", (run_id,))
        await db.commit()


async def list_sessions() -> List[dict]:
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """
            SELECT run_id, created_at, updated_at
            FROM sessions ORDER BY updated_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [
            {"run_id": r[0], "created_at": r[1], "updated_at": r[2]}
            for r in rows
        ]


# ---------------------------------------------------------------------------
# State diff — compact delta between two WorldState snapshots
# ---------------------------------------------------------------------------

def compute_state_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a compact diff between two WorldState model_dump() dicts.

    Returns only what changed — not full clones.
    """
    diff: Dict[str, Any] = {}

    for key in ("turn", "current_year", "run_status"):
        if before.get(key) != after.get(key):
            diff[key] = {"from": before.get(key), "to": after.get(key)}

    if before.get("player", {}).get("location") != after.get("player", {}).get("location"):
        diff["player_location"] = {
            "from": before.get("player", {}).get("location"),
            "to": after.get("player", {}).get("location"),
        }

    if before.get("player", {}).get("disposition") != after.get("player", {}).get("disposition"):
        diff["player_disposition"] = {
            "from": before.get("player", {}).get("disposition"),
            "to": after.get("player", {}).get("disposition"),
        }

    before_visited = set(before.get("visited_locations", []))
    after_visited = set(after.get("visited_locations", []))
    new_visited = after_visited - before_visited
    if new_visited:
        diff["new_visited_locations"] = sorted(new_visited)

    before_events = before.get("events", [])
    after_events = after.get("events", [])
    if len(after_events) > len(before_events):
        diff["new_events"] = after_events[len(before_events):]

    npc_changes = []
    before_npcs = {n["id"]: n for n in before.get("npcs", [])}
    after_npcs = {n["id"]: n for n in after.get("npcs", [])}
    for npc_id, after_npc in after_npcs.items():
        before_npc = before_npcs.get(npc_id)
        if before_npc is None:
            npc_changes.append({"npc_id": npc_id, "change": "added"})
            continue
        fields_to_check = ("disposition", "location", "memory_of_player")
        for field in fields_to_check:
            if before_npc.get(field) != after_npc.get(field):
                npc_changes.append({
                    "npc_id": npc_id,
                    "field": field,
                    "from": before_npc.get(field),
                    "to": after_npc.get(field),
                })
    if npc_changes:
        diff["npc_changes"] = npc_changes

    loc_changes = []
    before_locs = {loc["id"]: loc for loc in before.get("locations", [])}
    after_locs = {loc["id"]: loc for loc in after.get("locations", [])}
    for loc_id, after_loc in after_locs.items():
        before_loc = before_locs.get(loc_id)
        if before_loc and before_loc.get("political_tension") != after_loc.get("political_tension"):
            loc_changes.append({
                "location_id": loc_id,
                "field": "political_tension",
                "from": before_loc.get("political_tension"),
                "to": after_loc.get("political_tension"),
            })
    if loc_changes:
        diff["location_changes"] = loc_changes

    return diff


# ---------------------------------------------------------------------------
# Build narrative summary for turn log
# ---------------------------------------------------------------------------

def build_narrative_output(
    ambient: List[dict],
    parsed_action: dict,
    npc_responses: List[dict],
    death: Optional[dict] = None,
    travel: Optional[dict] = None,
    erasure: Optional[str] = None,
) -> str:
    """Construct a human-readable summary of what the player saw this turn."""
    lines: List[str] = []

    if ambient:
        for act in ambient:
            lines.append(f"[{act.get('npc_name', '?')}] {act.get('activity', '')}")

    action_desc = parsed_action.get("era_description", "")
    if action_desc:
        lines.append(f"> {action_desc}")

    for resp in npc_responses:
        lines.append(f"[{resp.get('npc_name', '?')}] {resp.get('pov', '')}")

    if travel:
        lines.append(
            f"Traveled from {travel.get('from', '?')} to {travel.get('to', '?')} "
            f"({travel.get('turns_spent', '?')} turns)."
        )

    if death:
        lines.append(f"DEATH: {death.get('cause', 'unknown')}")

    if erasure:
        lines.append(f"ERASURE: {erasure}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Turn log — append-only
# ---------------------------------------------------------------------------

async def append_turn_log(
    run_id: str,
    turn_number: int,
    player_input: str,
    parsed_action: dict,
    ambient_activity: list,
    npc_responses: list,
    state_changes: dict,
    narrative_output: str,
    player_view_snapshot: dict,
) -> None:
    """Append one turn log row. Never updates existing rows."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO turn_logs (
                run_id, turn_number, player_input, parsed_action,
                ambient_activity, npc_responses, state_changes,
                narrative_output, player_view_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                turn_number,
                player_input,
                json.dumps(parsed_action),
                json.dumps(ambient_activity),
                json.dumps(npc_responses),
                json.dumps(state_changes),
                narrative_output,
                json.dumps(player_view_snapshot),
            ),
        )
        await db.commit()


async def get_turn_logs(run_id: str) -> List[dict]:
    """Retrieve all turn logs for a run, ordered by turn number."""
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, run_id, turn_number, player_input, parsed_action,
                   ambient_activity, npc_responses, state_changes,
                   narrative_output, player_view_snapshot, created_at
            FROM turn_logs
            WHERE run_id = ?
            ORDER BY turn_number ASC
            """,
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "run_id": r["run_id"],
                "turn_number": r["turn_number"],
                "player_input": r["player_input"],
                "parsed_action": json.loads(r["parsed_action"]),
                "ambient_activity": json.loads(r["ambient_activity"]),
                "npc_responses": json.loads(r["npc_responses"]),
                "state_changes": json.loads(r["state_changes"]),
                "narrative_output": r["narrative_output"],
                "player_view_snapshot": json.loads(r["player_view_snapshot"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Historical Events DB — build-time + runtime queries
# ---------------------------------------------------------------------------

async def insert_historical_event(
    year: int,
    region: str,
    event: str,
    significance: str,
    event_type: str,
    affects: List[str],
    canonical: bool = True,
    wikidata_qid: Optional[str] = None,
    polity_context: Optional[dict] = None,
) -> int:
    """Insert a single historical event. Returns the new row id."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """
            INSERT INTO historical_events
                (year, region, event, significance, type, affects,
                 canonical, wikidata_qid, polity_context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                year,
                region,
                event,
                significance,
                event_type,
                json.dumps(affects),
                1 if canonical else 0,
                wikidata_qid,
                json.dumps(polity_context) if polity_context else None,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def query_historical_events(
    year_start: int,
    year_end: int,
    region: Optional[str] = None,
    event_type: Optional[str] = None,
) -> List[dict]:
    """Query historical events within a year range, optionally filtered."""
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        clauses = ["year >= ? AND year <= ?"]
        params: list = [year_start, year_end]
        if region:
            clauses.append("region LIKE ?")
            params.append(f"%{region}%")
        if event_type:
            clauses.append("type = ?")
            params.append(event_type)
        where = " AND ".join(clauses)
        cursor = await db.execute(
            f"SELECT * FROM historical_events WHERE {where} ORDER BY year",
            params,
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "year": r["year"],
                "region": r["region"],
                "event": r["event"],
                "significance": r["significance"],
                "type": r["type"],
                "affects": json.loads(r["affects"]),
                "canonical": bool(r["canonical"]),
                "wikidata_qid": r["wikidata_qid"],
                "polity_context": json.loads(r["polity_context"]) if r["polity_context"] else None,
            }
            for r in rows
        ]


async def count_historical_events() -> int:
    """Total number of events in the historical_events table."""
    if not DB_PATH.exists():
        return 0
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM historical_events")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def event_exists_by_qid(qid: str) -> bool:
    """Check if an event with this Wikidata QID already exists."""
    if not DB_PATH.exists():
        return False
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT 1 FROM historical_events WHERE wikidata_qid = ? LIMIT 1",
            (qid,),
        )
        return (await cursor.fetchone()) is not None


# ---------------------------------------------------------------------------
# Consequence Queue — delayed effect scheduling
# ---------------------------------------------------------------------------

async def schedule_consequence(
    run_id: str,
    source_event_id: Optional[int],
    trigger_turn: int,
    target_type: str,
    target_id: Optional[str],
    effect_type: str,
    effect_payload: dict,
) -> int:
    """Schedule a future consequence. Returns the new row id."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """
            INSERT INTO consequence_queue
                (run_id, source_event_id, trigger_turn, target_type,
                 target_id, effect_type, effect_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_event_id,
                trigger_turn,
                target_type,
                target_id,
                effect_type,
                json.dumps(effect_payload),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_consequences(run_id: str, current_turn: int) -> List[dict]:
    """Fetch all unfired, non-superseded consequences due by current_turn."""
    if not DB_PATH.exists():
        return []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM consequence_queue
            WHERE run_id = ? AND trigger_turn <= ? AND fired = 0 AND superseded = 0
            ORDER BY trigger_turn ASC
            """,
            (run_id, current_turn),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "run_id": r["run_id"],
                "source_event_id": r["source_event_id"],
                "trigger_turn": r["trigger_turn"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "effect_type": r["effect_type"],
                "effect_payload": json.loads(r["effect_payload"]),
                "fired": bool(r["fired"]),
                "superseded": bool(r["superseded"]),
            }
            for r in rows
        ]


async def mark_consequence_fired(consequence_id: int) -> None:
    """Mark a consequence as fired after successful application."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE consequence_queue SET fired = 1 WHERE id = ?",
            (consequence_id,),
        )
        await db.commit()


async def mark_consequence_superseded(consequence_id: int) -> None:
    """Mark a consequence as superseded (world diverged, no longer valid)."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE consequence_queue SET superseded = 1 WHERE id = ?",
            (consequence_id,),
        )
        await db.commit()


async def supersede_downstream_consequences(
    run_id: str, source_event_id: int,
) -> int:
    """Mark all unfired consequences from a source event as superseded.

    Used when a player action contradicts a canonical event.
    Returns count of rows affected.
    """
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """
            UPDATE consequence_queue
            SET superseded = 1
            WHERE run_id = ? AND source_event_id = ? AND fired = 0
            """,
            (run_id, source_event_id),
        )
        await db.commit()
        return cursor.rowcount
