"""aiosqlite database setup: sessions and challenge history tables."""
import json
import aiosqlite
from app.config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.database_url)
        _db.row_factory = aiosqlite.Row
        await _create_tables(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _create_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            stage_reached INTEGER NOT NULL DEFAULT 0,
            timestamp REAL NOT NULL,
            timings TEXT NOT NULL DEFAULT '{}',
            passed INTEGER NOT NULL DEFAULT 0,
            reject_reason TEXT
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_agent_id
        ON sessions(agent_id)
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS challenge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            round_num INTEGER NOT NULL,
            challenge_text TEXT NOT NULL,
            response_text TEXT,
            correct INTEGER,
            response_time_s REAL
        )
    """)
    await db.commit()


async def insert_session(
    agent_id: str,
    stage_reached: int,
    timestamp: float,
    timings: dict,
    passed: bool,
    reject_reason: str | None = None,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO sessions
           (agent_id, stage_reached, timestamp, timings, passed, reject_reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (agent_id, stage_reached, timestamp, json.dumps(timings), int(passed), reject_reason),
    )
    await db.commit()
    return cursor.lastrowid


async def fetch_agent_sessions(agent_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM sessions WHERE agent_id = ? ORDER BY timestamp ASC",
        (agent_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
