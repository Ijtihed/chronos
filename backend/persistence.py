"""SQLite session persistence for game state and turn logs.

Sessions: live WorldState as a JSON blob keyed by run_id.
Turn logs: append-only per-turn audit trail with state diffs (not full clones).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import aiosqlite

from backend.world_state import WorldState

logger = logging.getLogger("chronos.persistence")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chronos.db"


async def _configure_connection(db: aiosqlite.Connection) -> None:
    """Apply performance PRAGMAs to a freshly opened connection."""
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA busy_timeout = 5000")
    await db.execute("PRAGMA cache_size = -65536")
    await db.execute("PRAGMA temp_store = MEMORY")


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open a configured database connection as an async context manager."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await _configure_connection(db)
        yield db


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await _configure_connection(db)
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
        # Phase 3 Step 3.1: illustration trigger audit column.
        # SQLite has no ADD COLUMN IF NOT EXISTS — try/except is the
        # idiomatic pattern (same shape as the QID unique-index block
        # above). Safe on second+ startups.
        try:
            await db.execute(
                "ALTER TABLE turn_logs ADD COLUMN illustration_trigger TEXT DEFAULT NULL"
            )
        except Exception:
            pass
        # Two-tier LLM provider migration: per-turn USD cost (0.0 for
        # Ollama-only turns). Same idempotent ALTER pattern.
        try:
            await db.execute(
                "ALTER TABLE turn_logs ADD COLUMN turn_cost_usd REAL DEFAULT 0.0"
            )
        except Exception:
            pass
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
        try:
            await db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_he_qid_unique
                ON historical_events (wikidata_qid)
                WHERE wikidata_qid IS NOT NULL AND wikidata_qid != ''
                """
            )
        except Exception:
            await db.execute(
                """
                DELETE FROM historical_events
                WHERE id NOT IN (
                    SELECT MIN(id) FROM historical_events
                    WHERE wikidata_qid IS NOT NULL AND wikidata_qid != ''
                    GROUP BY wikidata_qid
                ) AND wikidata_qid IS NOT NULL AND wikidata_qid != ''
                """
            )
            await db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_he_qid_unique
                ON historical_events (wikidata_qid)
                WHERE wikidata_qid IS NOT NULL AND wikidata_qid != ''
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
                    'npc_arrival','event_spawn','material_change',
                    'disposition_shift','need_pressure'
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
    async with _connect() as db:
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
    async with _connect() as db:
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
    async with _connect() as db:
        await db.execute("DELETE FROM sessions WHERE run_id = ?", (run_id,))
        await db.commit()


async def list_sessions() -> List[dict]:
    if not DB_PATH.exists():
        return []
    async with _connect() as db:
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
    illustration_trigger: Optional[dict] = None,
    turn_cost_usd: float = 0.0,
) -> None:
    """Append one turn log row. Never updates existing rows.

    `illustration_trigger` is a JSON blob from
    IllustrationTrigger.log_dict() or None if no trigger fired.
    `turn_cost_usd` is the sum of cost_usd across every LLM call made
    during this turn (0.0 for turns that ran entirely on Ollama or had
    no LLM activity at all).
    """
    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO turn_logs (
                run_id, turn_number, player_input, parsed_action,
                ambient_activity, npc_responses, state_changes,
                narrative_output, player_view_snapshot,
                illustration_trigger, turn_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(illustration_trigger) if illustration_trigger else None,
                float(turn_cost_usd),
            ),
        )
        await db.commit()


async def get_turn_logs(run_id: str) -> List[dict]:
    """Retrieve all turn logs for a run, ordered by turn number."""
    if not DB_PATH.exists():
        return []
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, run_id, turn_number, player_input, parsed_action,
                   ambient_activity, npc_responses, state_changes,
                   narrative_output, player_view_snapshot,
                   illustration_trigger, turn_cost_usd, created_at
            FROM turn_logs
            WHERE run_id = ?
            ORDER BY turn_number ASC
            """,
            (run_id,),
        )
        rows = await cursor.fetchall()
        out: List[dict] = []
        for r in rows:
            keys = r.keys()
            trigger_raw = r["illustration_trigger"] if "illustration_trigger" in keys else None
            out.append({
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
                "illustration_trigger": (
                    json.loads(trigger_raw) if trigger_raw else None
                ),
                "turn_cost_usd": (
                    float(r["turn_cost_usd"]) if "turn_cost_usd" in keys and r["turn_cost_usd"] is not None else 0.0
                ),
                "created_at": r["created_at"],
            })
        return out


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
    async with _connect() as db:
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
    async with _connect() as db:
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
    async with _connect() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM historical_events")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def event_exists_by_qid(qid: str) -> bool:
    """Check if an event with this Wikidata QID already exists."""
    if not DB_PATH.exists():
        return False
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT 1 FROM historical_events WHERE wikidata_qid = ? LIMIT 1",
            (qid,),
        )
        return (await cursor.fetchone()) is not None


# ---------------------------------------------------------------------------
# Consequence Queue DB table — DEPRECATED for runtime use
#
# As of 2026-04-06, the runtime consequence queue lives on WorldState
# (state.consequence_queue: List[ScheduledConsequence]) and is persisted
# with save_session/load_session. The DB table remains for auditing and
# analytics only. These functions are no longer called at runtime.
# ---------------------------------------------------------------------------
