"""SQLite session persistence for game state.

Each run is stored as a JSON blob keyed by run_id.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import aiosqlite

from backend.world_state import WorldState

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
