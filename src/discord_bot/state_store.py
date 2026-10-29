"""Small SQLite store for per-server mood state without retaining chat messages."""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from .mood import (
    MoodSignal,
    MoodSnapshot,
    MoodState,
    apply_decay,
    apply_signal,
)

RECENT_WINDOW_SECONDS = 7 * 24 * 60 * 60
MAX_STORED_REASONS = 12
SIGNAL_COOLDOWN_SECONDS = 20


class MoodStore:
    """Persist bounded mood dimensions and generic reason labels by Discord server."""

    def __init__(self, database_path: str) -> None:
        self._path = Path(database_path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    async def snapshot(self, guild_id: int) -> MoodSnapshot:
        async with self._lock:
            return await asyncio.to_thread(
                self._snapshot_sync, str(guild_id), time.time()
            )

    async def record_signal(
        self,
        guild_id: int,
        signal: MoodSignal,
    ) -> MoodSnapshot:
        async with self._lock:
            return await asyncio.to_thread(
                self._record_signal_sync, str(guild_id), signal, time.time()
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS kiki_mood (
                    guild_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    total_signals INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS kiki_mood_events (
                    id INTEGER PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    occurred_at REAL NOT NULL,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS kiki_mood_events_recent
                    ON kiki_mood_events(guild_id, occurred_at DESC);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _snapshot_sync(self, guild_id: str, now: float) -> MoodSnapshot:
        connection = self._connect()
        try:
            return self._snapshot_in_connection(connection, guild_id, now)
        finally:
            connection.close()

    def _snapshot_in_connection(
        self,
        connection: sqlite3.Connection,
        guild_id: str,
        now: float,
    ) -> MoodSnapshot:
        row = connection.execute(
            "SELECT state_json, updated_at FROM kiki_mood WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        if row is None:
            state = MoodState()
            updated_at = None
        else:
            try:
                saved_state = MoodState.from_dict(json.loads(row["state_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                saved_state = MoodState()
            updated_at = float(row["updated_at"])
            state = apply_decay(saved_state, max(0.0, now - updated_at))
            if now > updated_at:
                connection.execute(
                    "UPDATE kiki_mood SET state_json = ?, updated_at = ? "
                    "WHERE guild_id = ?",
                    (json.dumps(state.as_dict()), now, guild_id),
                )
                connection.commit()
                updated_at = now

        recent_rows = connection.execute(
            "SELECT reason FROM kiki_mood_events "
            "WHERE guild_id = ? AND occurred_at >= ? "
            "ORDER BY occurred_at DESC, id DESC LIMIT 3",
            (guild_id, now - RECENT_WINDOW_SECONDS),
        ).fetchall()
        recent_count_row = connection.execute(
            "SELECT COUNT(*) AS count FROM kiki_mood_events "
            "WHERE guild_id = ? AND occurred_at >= ?",
            (guild_id, now - RECENT_WINDOW_SECONDS),
        ).fetchone()
        return MoodSnapshot(
            state=state,
            recent_reasons=tuple(row["reason"] for row in recent_rows),
            interaction_count=int(recent_count_row["count"]),
            updated_at=updated_at,
        )

    def _record_signal_sync(
        self,
        guild_id: str,
        signal: MoodSignal,
        now: float,
    ) -> MoodSnapshot:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT occurred_at FROM kiki_mood_events "
                "WHERE guild_id = ? AND category = ? "
                "ORDER BY occurred_at DESC, id DESC LIMIT 1",
                (guild_id, signal.category),
            ).fetchone()
            if (
                latest is not None
                and now - float(latest["occurred_at"]) < SIGNAL_COOLDOWN_SECONDS
            ):
                connection.commit()
                return self._snapshot_in_connection(connection, guild_id, now)

            row = connection.execute(
                "SELECT state_json, updated_at, total_signals "
                "FROM kiki_mood WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            if row is None:
                prior_state = MoodState()
                total_signals = 0
            else:
                try:
                    prior_state = MoodState.from_dict(json.loads(row["state_json"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    prior_state = MoodState()
                prior_state = apply_decay(
                    prior_state, max(0.0, now - float(row["updated_at"]))
                )
                total_signals = int(row["total_signals"])

            updated_state = apply_signal(prior_state, signal)
            total_signals += 1
            connection.execute(
                """
                INSERT INTO kiki_mood (guild_id, state_json, updated_at, total_signals)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at,
                    total_signals = excluded.total_signals
                """,
                (
                    guild_id,
                    json.dumps(updated_state.as_dict()),
                    now,
                    total_signals,
                ),
            )
            connection.execute(
                "INSERT INTO kiki_mood_events "
                "(guild_id, occurred_at, category, reason) VALUES (?, ?, ?, ?)",
                (guild_id, now, signal.category, signal.reason),
            )
            connection.execute(
                """
                DELETE FROM kiki_mood_events
                WHERE guild_id = ? AND id NOT IN (
                    SELECT id FROM kiki_mood_events
                    WHERE guild_id = ?
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (guild_id, guild_id, MAX_STORED_REASONS),
            )
            connection.commit()
            return self._snapshot_in_connection(connection, guild_id, now)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
