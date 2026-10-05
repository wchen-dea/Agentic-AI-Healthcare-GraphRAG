"""Small SQLite-backed durable outbox for Neo4j -> Qdrant reconciliation."""
from __future__ import annotations

import json
import sqlite3
import time
from hashlib import sha256
from pathlib import Path
from typing import Any


class QdrantOutbox:
    def __init__(self, path: str, *, lease_seconds: int = 300, max_backoff_seconds: int = 3600) -> None:
        self.path = path
        self.lease_seconds = lease_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS qdrant_outbox (
                    task_id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL,
                    leased_until REAL,
                    last_error TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_qdrant_outbox_ready ON qdrant_outbox(status, next_attempt)"
            )
        finally:
            connection.close()

    @staticmethod
    def task_id(item: dict[str, Any]) -> str:
        event_id = str(item.get("event", {}).get("event_id", ""))
        return sha256(event_id.encode("utf-8")).hexdigest()

    def enqueue(self, item: dict[str, Any]) -> str:
        task_id = self.task_id(item)
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO qdrant_outbox(task_id, body, next_attempt) VALUES (?, ?, ?)",
                (task_id, json.dumps(item, separators=(",", ":")), time.time()),
            )
        finally:
            connection.close()
        return task_id

    def claim(self) -> dict[str, Any] | None:
        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT task_id, body, attempts FROM qdrant_outbox
                   WHERE (status = 'pending' AND next_attempt <= ?)
                      OR (status = 'leased' AND leased_until <= ?)
                   ORDER BY next_attempt, task_id LIMIT 1""",
                (now, now),
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            connection.execute(
                "UPDATE qdrant_outbox SET status='leased', leased_until=?, attempts=attempts+1 WHERE task_id=?",
                (now + self.lease_seconds, row["task_id"]),
            )
            connection.execute("COMMIT")
            item = json.loads(row["body"])
            item["_task_id"] = row["task_id"]
            return item
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def acknowledge(self, task_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM qdrant_outbox WHERE task_id=?", (task_id,))
        finally:
            connection.close()

    def fail(self, task_id: str, error: Exception) -> None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT attempts FROM qdrant_outbox WHERE task_id=?", (task_id,)).fetchone()
            attempts = int(row["attempts"]) if row else 1
            delay = min(2 ** max(attempts - 1, 0), self.max_backoff_seconds)
            connection.execute(
                """UPDATE qdrant_outbox SET status='pending', leased_until=NULL,
                   next_attempt=?, last_error=? WHERE task_id=?""",
                (time.time() + delay, str(error)[:1000], task_id),
            )
        finally:
            connection.close()
