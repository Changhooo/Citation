from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from .config import get_settings


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with tx() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                query TEXT NOT NULL,
                scholar_mirror TEXT NOT NULL,
                target_result_id TEXT,
                cited_by_count INTEGER DEFAULT 0,
                cited_by_url TEXT,
                status TEXT NOT NULL DEFAULT 'created',
                current_page INTEGER DEFAULT 0,
                max_pages INTEGER,
                needs_user_action INTEGER DEFAULT 0,
                message TEXT,
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scholar_results (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                title TEXT NOT NULL,
                authors_text TEXT,
                year INTEGER,
                venue TEXT,
                snippet TEXT,
                result_url TEXT,
                pdf_url TEXT,
                cited_by_count INTEGER DEFAULT 0,
                cited_by_url TEXT,
                page_number INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS author_evidence (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                result_id TEXT NOT NULL REFERENCES scholar_results(id) ON DELETE CASCADE,
                author_name TEXT NOT NULL,
                title_type TEXT NOT NULL,
                evidence_url TEXT NOT NULL,
                evidence_snippet TEXT,
                confidence REAL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'candidate',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pdf_assets (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                result_id TEXT NOT NULL REFERENCES scholar_results(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                url TEXT,
                path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                match_confidence REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS citation_contexts (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                result_id TEXT NOT NULL REFERENCES scholar_results(id) ON DELETE CASCADE,
                page INTEGER,
                marker TEXT,
                before_sentence TEXT,
                hit_sentence TEXT NOT NULL,
                after_sentence TEXT,
                sentiment TEXT NOT NULL DEFAULT 'neutral',
                confidence REAL DEFAULT 0,
                reason_zh TEXT,
                material_zh TEXT,
                review_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None

