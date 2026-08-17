"""SQLite index: page registry, content hashes, run history, heal events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Index:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    chunks INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT NOT NULL,
                    scraped_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    rows INTEGER,
                    added INTEGER,
                    changed INTEGER,
                    removed INTEGER,
                    healthy INTEGER,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS heal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    collector_id TEXT NOT NULL,
                    symptom TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    # ---- pages -----------------------------------------------------------

    def page_hashes(self, source: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, content_hash FROM pages WHERE source = ?", (source,)
            ).fetchall()
        return {row["url"]: row["content_hash"] for row in rows}

    def page_count(self, source: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM pages WHERE source = ?", (source,)
            ).fetchone()
        return int(row["n"])

    def upsert_page(self, url: str, source: str, title: str, body_hash: str,
                    chunks: int, scraped_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pages (url, source, title, content_hash, chunks, last_seen, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    source = excluded.source,
                    title = excluded.title,
                    content_hash = excluded.content_hash,
                    chunks = excluded.chunks,
                    last_seen = excluded.last_seen,
                    scraped_at = excluded.scraped_at
                """,
                (url, source, title, body_hash, chunks, utcnow(), scraped_at),
            )

    def remove_pages(self, urls: list[str]) -> None:
        if not urls:
            return
        with self._connect() as conn:
            conn.executemany("DELETE FROM pages WHERE url = ?", [(u,) for u in urls])

    def source_status(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source, COUNT(*) AS pages, MAX(scraped_at) AS last_refresh
                FROM pages GROUP BY source
                """
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- runs ------------------------------------------------------------

    def start_run(self, source: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (source, started_at) VALUES (?, ?)",
                (source, utcnow()),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, rows: int, added: int, changed: int,
                   removed: int, healthy: Optional[bool], notes: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, rows = ?, added = ?, changed = ?, removed = ?,
                    healthy = ?, notes = ?
                WHERE id = ?
                """,
                (utcnow(), rows, added, changed, removed,
                 1 if healthy is True else (0 if healthy is False else None), notes, run_id),
            )

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- heal events -----------------------------------------------------

    def record_heal(self, source: str, collector_id: str, symptom: str, result: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO heal_events (source, collector_id, symptom, result, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, collector_id, symptom, result, utcnow()),
            )

    def recent_heals(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM heal_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- misc ------------------------------------------------------------

    def export_pages(self, path: Path) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM pages ORDER BY source, url").fetchall()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([dict(row) for row in rows], handle, indent=2, ensure_ascii=False)
