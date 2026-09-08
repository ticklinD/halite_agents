"""
Session, message, and usage persistence layer (§6.3, §7.2).
All operations go through this module — no raw SQL scattered elsewhere.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterator
from uuid import UUID

from halite.models.schemas import Message, Session, UsageRecord, ToolCall
from halite.storage.db import get_connection, init_db
from halite.utils.logging_config import logger


class HistoryStore:
    """Persistent storage for sessions, messages, tool calls, and usage records."""

    def __init__(self) -> None:
        self._conn = init_db()

    # ── Sessions ─────────────────────────────────────────────────────────────

    def create_session(self, session: Session) -> Session:
        """Persist a new session."""
        self._conn.execute(
            "INSERT INTO sessions (id, project_path, active_model, backend, created_at, last_active_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(session.id),
                str(session.project_path) if session.project_path else None,
                session.active_model,
                session.backend,
                session.created_at.isoformat(),
                session.last_active_at.isoformat(),
            ),
        )
        self._conn.commit()
        logger.debug("Session created: {}", session.id)
        return session

    def update_session(self, session: Session) -> None:
        """Update an existing session (e.g. last_active_at, active_model)."""
        self._conn.execute(
            "UPDATE sessions SET active_model=?, backend=?, last_active_at=?, project_path=? WHERE id=?",
            (
                session.active_model,
                session.backend,
                session.last_active_at.isoformat(),
                str(session.project_path) if session.project_path else None,
                str(session.id),
            ),
        )
        self._conn.commit()

    def get_session(self, session_id: UUID) -> Session | None:
        """Retrieve a session by ID."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (str(session_id),)
        ).fetchone()
        if row is None:
            return None
        return Session(
            id=UUID(row["id"]),
            project_path=row["project_path"],
            active_model=row["active_model"],
            backend=row["backend"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_active_at=datetime.fromisoformat(row["last_active_at"]),
        )

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[Session]:
        """List sessions most-recent-first, paginated (§6.3 edge case)."""
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY last_active_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [
            Session(
                id=UUID(row["id"]),
                project_path=row["project_path"],
                active_model=row["active_model"],
                backend=row["backend"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_active_at=datetime.fromisoformat(row["last_active_at"]),
            )
            for row in rows
        ]

    def count_sessions(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return row[0]

    # ── Messages ─────────────────────────────────────────────────────────────

    def add_message(self, msg: Message) -> Message:
        """Persist a message."""
        self._conn.execute(
            "INSERT INTO messages (id, session_id, role, content, model_used, tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(msg.id),
                str(msg.session_id),
                msg.role,
                msg.content,
                msg.model_used,
                msg.tokens,
                msg.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return msg

    def get_messages(self, session_id: UUID) -> list[Message]:
        """Get all messages for a session, in chronological order."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (str(session_id),),
        ).fetchall()
        return [
            Message(
                id=UUID(row["id"]),
                session_id=UUID(row["session_id"]),
                role=row["role"],
                content=row["content"],
                model_used=row["model_used"],
                tokens=row["tokens"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    # ── Tool calls ───────────────────────────────────────────────────────────

    def add_tool_call(self, tc: ToolCall) -> ToolCall:
        """Persist a tool call."""
        self._conn.execute(
            "INSERT INTO tool_calls (id, message_id, tool_name, arguments, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(tc.id),
                str(tc.message_id),
                tc.tool_name,
                json.dumps(tc.arguments, default=str),
                tc.status,
            ),
        )
        self._conn.commit()
        return tc

    def update_tool_call_status(self, tc_id: UUID, status: str) -> None:
        self._conn.execute(
            "UPDATE tool_calls SET status=? WHERE id=?",
            (status, str(tc_id)),
        )
        self._conn.commit()

    # ── Usage records ────────────────────────────────────────────────────────

    def add_usage_record(self, record: UsageRecord) -> None:
        """Log an API usage record (§7.2)."""
        self._conn.execute(
            "INSERT INTO usage_records (session_id, provider, tokens_in, tokens_out, cost_usd, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(record.session_id),
                record.provider,
                record.tokens_in,
                record.tokens_out,
                record.cost_usd,
                record.timestamp.isoformat(),
            ),
        )
        self._conn.commit()

    def get_session_usage(self, session_id: UUID) -> list[UsageRecord]:
        """Get all usage records for a session."""
        rows = self._conn.execute(
            "SELECT * FROM usage_records WHERE session_id=? ORDER BY timestamp ASC",
            (str(session_id),),
        ).fetchall()
        return [
            UsageRecord(
                session_id=UUID(row["session_id"]),
                provider=row["provider"],
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                cost_usd=row["cost_usd"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]

    def get_lifetime_usage(self) -> list[UsageRecord]:
        """Get all usage records across all sessions."""
        rows = self._conn.execute(
            "SELECT * FROM usage_records ORDER BY timestamp ASC"
        ).fetchall()
        return [
            UsageRecord(
                session_id=UUID(row["session_id"]),
                provider=row["provider"],
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                cost_usd=row["cost_usd"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]

    # ── Search / filter for /history ─────────────────────────────────────────

    def search_sessions(self, query: str, limit: int = 50, offset: int = 0) -> list[Session]:
        """Search sessions by keyword in project_path or first user message (§6.3)."""
        rows = self._conn.execute(
            """
            SELECT DISTINCT s.* FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id AND m.role = 'user'
            WHERE s.project_path LIKE ? OR m.content LIKE ?
            ORDER BY s.last_active_at DESC
            LIMIT ? OFFSET ?
            """,
            (f"%{query}%", f"%{query}%", limit, offset),
        ).fetchall()
        return [
            Session(
                id=UUID(row["id"]),
                project_path=row["project_path"],
                active_model=row["active_model"],
                backend=row["backend"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_active_at=datetime.fromisoformat(row["last_active_at"]),
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
