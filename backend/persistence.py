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
    await db.execute("PRAGMA foreign_keys = ON")


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open a configured database connection as an async context manager."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await _configure_connection(db)
        yield db


SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


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


async def seed_historical_events_if_empty() -> None:
    """Bulk-insert the per-era seed JSONs into `historical_events`.

    Each seed entry has: year, region, event, significance, type,
    affects, optional wikidata_qid. The QID column has a unique index
    (`idx_he_qid_unique`) so re-running this with new seeds added later
    will still succeed (existing QIDs are silently skipped).

    Skips entirely when the table already has data — the build script
    output should always win over the curated seed floor.
    """
    if not SEEDS_DIR.exists():
        return
    seed_files = sorted(SEEDS_DIR.glob("*.json"))
    if not seed_files:
        return

    async with _connect() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM historical_events")
        row = await cursor.fetchone()
        existing = row[0] if row else 0
        if existing > 0:
            return

        total = 0
        for seed_path in seed_files:
            try:
                entries = json.loads(seed_path.read_text())
            except Exception as exc:
                logger.warning(
                    "Skipping malformed seed file %s: %s", seed_path.name, exc,
                )
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO historical_events
                            (year, region, event, significance, type,
                             affects, canonical, wikidata_qid, polity_context)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(entry["year"]),
                            entry["region"],
                            entry["event"],
                            entry["significance"],
                            entry["type"],
                            json.dumps(entry.get("affects", []) or []),
                            1 if entry.get("canonical", True) else 0,
                            entry.get("wikidata_qid") or None,
                            None,
                        ),
                    )
                    total += 1
                except Exception as exc:
                    logger.warning(
                        "Seed row in %s skipped (%s): %s",
                        seed_path.name, exc, entry.get("event", "")[:60],
                    )
        await db.commit()
        logger.info(
            "Seeded %d historical events from %d per-era seed files; "
            "run scripts/build_events_db.py for the richer Wikidata ingest.",
            total, len(seed_files),
        )


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
        try:
            return WorldState.model_validate_json(row[0])
        except Exception as exc:
            # Surfaced before this guard, a malformed state_json (mid-
            # release schema break, partial save, on-disk bit flip)
            # propagated up to _load_or_404 and turned into a 500. The
            # API contract for an unknown / unloadable run is 404, so
            # we log loudly and return None. The session row stays in
            # the DB so the user can choose to delete the run, OR an
            # operator can inspect the row.
            logger.warning(
                "load_session: corrupt or schema-mismatched state_json for "
                "run_id=%s (%s: %s) — treating as not found.",
                run_id, type(exc).__name__, exc,
            )
            return None


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

    Returns only what changed — not full clones. The diff lands in
    `turn_logs.state_changes` for every turn, so it is the primary
    audit trail when something looks wrong post-run. Surface anything a
    reader would reasonably want to see; omit anything that adds noise.

    Coverage (besides the obvious turn / location / disposition):
      - new_events / removed_events / event_count_delta — covers
        compaction *and* growth, where the old `len > len` check
        silently dropped removals.
      - npc_changes — disposition / location / memory_of_player.
      - location_changes — political_tension only (other fields are
        either static per era or driven by ground_context refresh).
      - cost_usd / cost_cap_state — surfaces the per-turn cost delta
        and any soft/hard transition.
      - pin_count / pin_connection_count / diorama_count deltas — so
        a turn that creates a pin or mints a diorama is visible in
        the audit log without parsing every pin payload.
      - consequence_queue_depth — tracks the queue's growth /
        firing / supersession in aggregate.
      - new_historical_divergences — appended divergences this turn.
      - ground_context_refreshed — true when ground_context object
        identity changes (arrival or initial generation).
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

    # ── Events: handle growth AND compaction ─────────────────────────
    before_events = before.get("events", []) or []
    after_events = after.get("events", []) or []
    if len(after_events) > len(before_events):
        diff["new_events"] = after_events[len(before_events):]
    elif len(after_events) < len(before_events):
        # state.events was compacted (world_engine compaction kicks in
        # past a length cap). Surface the delta count so the audit log
        # records "the engine pruned N events this turn" rather than
        # silently looking like nothing happened.
        diff["event_count_delta"] = len(after_events) - len(before_events)

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

    # ── Cost cap transitions + per-turn cost delta ───────────────────
    before_cap = before.get("cost_cap_state") or "none"
    after_cap = after.get("cost_cap_state") or "none"
    if before_cap != after_cap:
        diff["cost_cap_state"] = {"from": before_cap, "to": after_cap}
    before_cost = float(before.get("cumulative_cost_usd") or 0.0)
    after_cost = float(after.get("cumulative_cost_usd") or 0.0)
    if after_cost != before_cost:
        # Round to 6 decimal places — Gemini cost is in fractions of a
        # cent; longer floats would just be float-precision noise.
        diff["cost_usd_delta"] = round(after_cost - before_cost, 6)

    # ── Pinboard / diorama count deltas (audit, not full payload) ────
    before_pin_count = len(before.get("pins") or [])
    after_pin_count = len(after.get("pins") or [])
    if after_pin_count != before_pin_count:
        diff["pin_count"] = {"from": before_pin_count, "to": after_pin_count}
    before_conn_count = len(before.get("pin_connections") or [])
    after_conn_count = len(after.get("pin_connections") or [])
    if after_conn_count != before_conn_count:
        diff["pin_connection_count"] = {
            "from": before_conn_count, "to": after_conn_count,
        }
    before_diorama_count = len(before.get("dioramas") or [])
    after_diorama_count = len(after.get("dioramas") or [])
    if after_diorama_count != before_diorama_count:
        diff["diorama_count"] = {
            "from": before_diorama_count, "to": after_diorama_count,
        }

    # ── Consequence queue depth ──────────────────────────────────────
    # Tracks aggregate firing / supersession / scheduling without
    # dumping every queue entry. If you need the per-row detail for a
    # specific run you can pull it from the persisted state JSON.
    before_cq = before.get("consequence_queue") or []
    after_cq = after.get("consequence_queue") or []

    def _cq_buckets(rows: list) -> Dict[str, int]:
        pending = fired = superseded = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            if r.get("fired"):
                fired += 1
            elif r.get("superseded"):
                superseded += 1
            else:
                pending += 1
        return {"pending": pending, "fired": fired, "superseded": superseded}

    before_buckets = _cq_buckets(before_cq)
    after_buckets = _cq_buckets(after_cq)
    if before_buckets != after_buckets:
        diff["consequence_queue"] = {
            "from": before_buckets, "to": after_buckets,
        }

    # ── Historical divergences ───────────────────────────────────────
    before_divs = before.get("historical_divergences") or []
    after_divs = after.get("historical_divergences") or []
    if len(after_divs) > len(before_divs):
        diff["new_historical_divergences"] = after_divs[len(before_divs):]

    # ── Ground context refresh ───────────────────────────────────────
    # Object identity (dict equality) is good enough — the HCE rebuilds
    # the dict on initial generation and on travel arrival; otherwise
    # it's stable across turns.
    if before.get("ground_context") != after.get("ground_context"):
        diff["ground_context_refreshed"] = True

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
    during this turn (0.0 for turns with no LLM activity).
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
        def _safe_json(raw: Any, default: Any = None) -> Any:
            if raw is None:
                return default
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt JSON in turn log (run_id=%s): %r", run_id, raw[:120] if isinstance(raw, str) else raw)
                return default

        for r in rows:
            keys = r.keys()
            trigger_raw = r["illustration_trigger"] if "illustration_trigger" in keys else None
            out.append({
                "id": r["id"],
                "run_id": r["run_id"],
                "turn_number": r["turn_number"],
                "player_input": r["player_input"],
                "parsed_action": _safe_json(r["parsed_action"], {}),
                "ambient_activity": _safe_json(r["ambient_activity"], []),
                "npc_responses": _safe_json(r["npc_responses"], []),
                "state_changes": _safe_json(r["state_changes"], {}),
                "narrative_output": r["narrative_output"],
                "player_view_snapshot": _safe_json(r["player_view_snapshot"], {}),
                "illustration_trigger": _safe_json(trigger_raw),
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
        results = []
        for r in rows:
            try:
                affects = json.loads(r["affects"])
            except (json.JSONDecodeError, TypeError):
                affects = []
            try:
                polity_context = json.loads(r["polity_context"]) if r["polity_context"] else None
            except (json.JSONDecodeError, TypeError):
                polity_context = None
            results.append({
                "id": r["id"],
                "year": r["year"],
                "region": r["region"],
                "event": r["event"],
                "significance": r["significance"],
                "type": r["type"],
                "affects": affects,
                "canonical": bool(r["canonical"]),
                "wikidata_qid": r["wikidata_qid"],
                "polity_context": polity_context,
            })
        return results


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
