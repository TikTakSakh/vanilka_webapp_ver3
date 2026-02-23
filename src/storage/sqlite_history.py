"""SQLite-backed persistent dialog history."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

import aiosqlite
from beartype import beartype

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
"""


@beartype
class SQLiteDialogHistory:
    """Persistent dialog history backed by SQLite via aiosqlite."""

    def __init__(self, db_path: Path, max_messages: int = 20) -> None:
        self._db_path = db_path
        self._max_messages = max_messages
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open connection and create tables if needed."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.executescript(CREATE_TABLES_SQL)
        await self._db.commit()
        logger.info("SQLite dialog history initialised: %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("SQLite connection closed")

    # ── Core API (same interface as in-memory DialogHistory) ──

    async def upsert_user(self, user_id: int, username: str | None = None) -> None:
        """Register or update a user record."""
        assert self._db is not None
        await self._db.execute(
            """
            INSERT INTO users (user_id, username, first_seen, last_seen)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username  = COALESCE(excluded.username, users.username),
                last_seen = datetime('now')
            """,
            (user_id, username),
        )
        await self._db.commit()

    async def add_message(
        self, user_id: int, role: Literal["user", "assistant"], content: str
    ) -> None:
        """Persist a message and trim old entries beyond the window."""
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )

        # Trim: keep only the last N messages per user
        await self._db.execute(
            """
            DELETE FROM messages
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (user_id, user_id, self._max_messages),
        )
        await self._db.commit()

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """Return the last N messages in OpenAI chat format."""
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT role, content FROM messages
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ) as cursor:
            return [
                {"role": row[0], "content": row[1]}
                async for row in cursor
            ]

    async def clear(self, user_id: int) -> None:
        """Delete all messages for a given user."""
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM messages WHERE user_id = ?", (user_id,)
        )
        await self._db.commit()

    async def get_message_count(self, user_id: int) -> int:
        """Return number of stored messages for a user."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    # ── Admin helpers ──

    async def get_all_user_ids(self) -> list[int]:
        """Return all known user IDs (for broadcast)."""
        assert self._db is not None
        async with self._db.execute("SELECT user_id FROM users") as cursor:
            return [row[0] async for row in cursor]

    async def get_stats(self) -> dict[str, int]:
        """Return aggregate statistics for /stats command."""
        assert self._db is not None

        stats: dict[str, int] = {}

        async with self._db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            stats["total_users"] = row[0] if row else 0

        async with self._db.execute("SELECT COUNT(*) FROM messages") as cur:
            row = await cur.fetchone()
            stats["total_messages"] = row[0] if row else 0

        async with self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE role = 'user'"
        ) as cur:
            row = await cur.fetchone()
            stats["user_messages"] = row[0] if row else 0

        async with self._db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE created_at >= date('now')"
        ) as cur:
            row = await cur.fetchone()
            stats["active_today"] = row[0] if row else 0

        return stats
