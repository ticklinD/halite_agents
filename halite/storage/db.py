"""
SQLite connection management and schema migrations (§6.3, §7.2, §7.6).
Database lives at ~/.halite/sessions.db.
Integrity checks on startup; corrupt DB is backed up, not crashed on.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from halite.utils.logging_config import logger

DB_DIR = Path.home() / ".halite"
DB_FILE = DB_DIR / "sessions.db"


def _ensure_db_dir() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a new SQLite connection with WAL mode and foreign keys enabled."""
    _ensure_db_dir()
    conn = sqlite3.connect(str(DB_FILE), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> sqlite3.Connection:
    """
    Initialise the database schema. Safe to call multiple times (CREATE IF NOT EXISTS).
    Runs integrity check on existing DB; backs up corrupt DBs (§6.3).
    Returns the open connection.
    """
    _ensure_db_dir()

    # Integrity check on existing DB
    if DB_FILE.exists():
        try:
            conn = sqlite3.connect(str(DB_FILE), timeout=10)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result[0] != "ok":
                raise RuntimeError(f"Integrity check failed: {result[0]}")
        except Exception as exc:
            # Back up corrupt DB (§6.3)
            import time
            backup = DB_DIR / f"sessions.db.corrupt-{int(time.time())}"
            DB_FILE.rename(backup)
            logger.warning(
                "SQLite DB was corrupt; backed up to {} and created fresh. Error: {}",
                backup, exc,
            )

    conn = get_connection()

    # ── Schema ───────────────────────────────────────────────────────────────

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project_path TEXT,
            active_model TEXT NOT NULL DEFAULT '',
            backend TEXT NOT NULL DEFAULT 'local_ollama',
            created_at TEXT NOT NULL,
            last_active_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
            content TEXT NOT NULL,
            model_used TEXT,
            tokens INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tool_calls (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'success', 'failed')),
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            tokens_in INTEGER NOT NULL,
            tokens_out INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS task_checkpoints (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_description TEXT NOT NULL,
            completed_steps TEXT NOT NULL DEFAULT '[]',
            pending_steps TEXT NOT NULL DEFAULT '[]',
            active_file TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_records(session_id);
        CREATE INDEX IF NOT EXISTS idx_tool_calls_message ON tool_calls(message_id);
    """)

    conn.commit()
    logger.info("Database initialised at {}", DB_FILE)
    return conn
