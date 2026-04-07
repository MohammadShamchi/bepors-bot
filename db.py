"""
SQLite persistence layer per PRD §5.8.
Uses stdlib sqlite3 in WAL mode. All writes go through an asyncio lock so the
event loop never races with itself on the single connection.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger("bepors.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    lang           TEXT    NOT NULL DEFAULT 'fa',
    search_enabled INTEGER NOT NULL DEFAULT 1,
    format         TEXT    NOT NULL DEFAULT 'compact',
    filters_json   TEXT    NOT NULL DEFAULT '{}',
    blocked        INTEGER NOT NULL DEFAULT 0,
    spam_until     TEXT,
    tips_shown     INTEGER NOT NULL DEFAULT 0,
    total_answers  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL,
    last_seen      TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    user_id INTEGER NOT NULL,
    day     TEXT    NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS global_usage (
    day   TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    user_hash TEXT NOT NULL,
    event     TEXT NOT NULL,
    meta      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(blocked);
"""


class Database:
    """Thin async wrapper around sqlite3. Single connection, serialized via asyncio.Lock."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ---- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        conn = sqlite3.connect(
            self.path,
            isolation_level=None,  # autocommit; we manage transactions explicitly
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(_SCHEMA)
        self._conn = conn
        self._migrate(conn)
        log.info("db connected: %s", self.path)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """
        Additive schema migrations for existing DBs where CREATE TABLE
        IF NOT EXISTS no-ops. Each `ALTER TABLE ... ADD COLUMN` is guarded
        so reruns are safe.
        """
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "tips_shown" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN tips_shown INTEGER NOT NULL DEFAULT 0")
            log.info("migrated: users.tips_shown added")
        if "total_answers" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN total_answers INTEGER NOT NULL DEFAULT 0")
            log.info("migrated: users.total_answers added")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        assert self._conn is not None, "db not connected"
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    # ---- users --------------------------------------------------------------

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return dict(row) if row else None

    async def ensure_user(self, user_id: int, lang: str) -> dict[str, Any]:
        """Create if missing, update last_seen, return the full row."""
        now = _now()
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (user_id, lang, created_at, last_seen)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen
                    """,
                    (user_id, lang, now, now),
                )
                row = cur.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return dict(row)

    async def set_user_field(self, user_id: int, field: str, value: Any) -> None:
        # Whitelist to prevent SQL injection through field name.
        allowed = {
            "lang",
            "search_enabled",
            "format",
            "filters_json",
            "blocked",
            "spam_until",
            "tips_shown",
        }
        if field not in allowed:
            raise ValueError(f"field {field!r} not allowed")
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {field} = ?, last_seen = ? WHERE user_id = ?",
                    (value, _now(), user_id),
                )

    async def incr_total_answers(self, user_id: int) -> int:
        """Atomically bump the user's lifetime answered-question counter and return the new value."""
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    "UPDATE users SET total_answers = total_answers + 1, last_seen = ? WHERE user_id = ?",
                    (_now(), user_id),
                )
                row = cur.execute(
                    "SELECT total_answers FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return int(row["total_answers"]) if row else 0

    async def set_user_filters(self, user_id: int, filters: dict[str, str]) -> None:
        await self.set_user_field(user_id, "filters_json", json.dumps(filters))

    async def delete_user(self, user_id: int) -> None:
        async with self._lock:
            with self._cursor() as cur:
                cur.execute("DELETE FROM usage WHERE user_id = ?", (user_id,))
                cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    async def list_user_ids(self) -> list[int]:
        async with self._lock:
            with self._cursor() as cur:
                rows = cur.execute(
                    "SELECT user_id FROM users WHERE blocked = 0"
                ).fetchall()
                return [r["user_id"] for r in rows]

    # ---- per-user daily usage -----------------------------------------------

    async def incr_usage(self, user_id: int, day: str) -> int:
        """Increment the user's counter for `day`. Returns the new count."""
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usage (user_id, day, count) VALUES (?, ?, 1)
                    ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1
                    """,
                    (user_id, day),
                )
                row = cur.execute(
                    "SELECT count FROM usage WHERE user_id = ? AND day = ?",
                    (user_id, day),
                ).fetchone()
                return int(row["count"]) if row else 0

    async def get_usage(self, user_id: int, day: str) -> int:
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT count FROM usage WHERE user_id = ? AND day = ?",
                    (user_id, day),
                ).fetchone()
                return int(row["count"]) if row else 0

    async def reset_usage(self, user_id: int) -> None:
        async with self._lock:
            with self._cursor() as cur:
                cur.execute("DELETE FROM usage WHERE user_id = ?", (user_id,))

    # ---- global daily cap ---------------------------------------------------

    async def incr_global_usage(self, day: str) -> int:
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO global_usage (day, count) VALUES (?, 1)
                    ON CONFLICT(day) DO UPDATE SET count = count + 1
                    """,
                    (day,),
                )
                row = cur.execute(
                    "SELECT count FROM global_usage WHERE day = ?", (day,)
                ).fetchone()
                return int(row["count"]) if row else 0

    async def get_global_usage(self, day: str) -> int:
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT count FROM global_usage WHERE day = ?", (day,)
                ).fetchone()
                return int(row["count"]) if row else 0

    # ---- events / stats -----------------------------------------------------

    async def log_event(self, user_hash: str, event: str, meta: dict[str, Any] | None = None) -> None:
        async with self._lock:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT INTO events (ts, user_hash, event, meta) VALUES (?, ?, ?, ?)",
                    (_now(), user_hash, event, json.dumps(meta or {})),
                )

    async def count_users_today(self) -> int:
        day = _today_str()
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT COUNT(*) AS c FROM usage WHERE day = ?", (day,)
                ).fetchone()
                return int(row["c"]) if row else 0

    async def count_total_users(self) -> int:
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()
                return int(row["c"]) if row else 0

    async def top_users(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Top users by lifetime answered questions, joined with today's count.
        Returns rows ordered by total_answers DESC.
        """
        day = _today_str()
        async with self._lock:
            with self._cursor() as cur:
                rows = cur.execute(
                    """
                    SELECT
                        u.user_id,
                        u.lang,
                        u.total_answers,
                        u.last_seen,
                        u.blocked,
                        COALESCE(usg.count, 0) AS today_count
                    FROM users u
                    LEFT JOIN usage usg
                      ON usg.user_id = u.user_id AND usg.day = ?
                    ORDER BY u.total_answers DESC, u.last_seen DESC
                    LIMIT ?
                    """,
                    (day, limit),
                ).fetchall()
                return [dict(r) for r in rows]

    async def user_with_today(self, user_id: int) -> dict[str, Any] | None:
        """Single user row + today's count, in one query."""
        day = _today_str()
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    """
                    SELECT
                        u.*,
                        COALESCE(usg.count, 0) AS today_count
                    FROM users u
                    LEFT JOIN usage usg
                      ON usg.user_id = u.user_id AND usg.day = ?
                    WHERE u.user_id = ?
                    """,
                    (day, user_id),
                ).fetchone()
                return dict(row) if row else None

    async def count_errors_today(self) -> int:
        day_prefix = _today_str()
        async with self._lock:
            with self._cursor() as cur:
                row = cur.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE event = 'error' AND ts LIKE ?",
                    (f"{day_prefix}%",),
                ).fetchone()
                return int(row["c"]) if row else 0


# ---- module-level helpers ---------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
