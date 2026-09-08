"""
History screen — browse and resume past sessions (§6.3).
Up/Down arrows select, Enter loads, Esc cancels, text filter narrows.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label, Input, Header
from textual.containers import Vertical, Horizontal
from pathlib import Path
from uuid import UUID
from datetime import datetime

from halite.models.schemas import Session
from halite.utils.logging_config import logger


class HistoryScreen(Screen):
    """Session history browser (§6.3)."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "load", "Load selected"),
    ]

    DEFAULT_CSS = """
    HistoryScreen {
        layout: vertical;
    }
    #history-header {
        height: 4;
        dock: top;
        padding: 0 1;
    }
    #history-list {
        height: 1fr;
        border-top: solid $accent;
    }
    #history-list ListItem {
        padding: 0 1;
    }
    #history-footer {
        height: 1;
        dock: bottom;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sessions: list[Session] = []
        self._list: ListView | None = None
        self._filter_input: Input | None = None
        self._status: Static | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="history-header"):
            yield Static("][ Session History — ↑/↓ select, Enter load, Esc back", classes="hint")
            self._filter_input = Input(placeholder="Filter by title/path...", id="filter")
            yield self._filter_input
        self._list = ListView(id="history-list")
        yield self._list
        self._status = Static("")
        yield self._status

    def on_mount(self) -> None:
        self._load_sessions("")
        if self._filter_input:
            self._filter_input.focus()

    def _load_sessions(self, query: str) -> None:
        """Load sessions into the list, newest first (§6.3)."""
        if self._list is None:
            return
        store = self.app.history  # type: ignore[attr-defined]
        if query:
            self._sessions = store.search_sessions(query, limit=100)
        else:
            self._sessions = store.list_sessions(limit=100)

        self._list.clear()
        for s in self._sessions:
            title = self._first_user_message(s.id) or "No messages"
            ts = s.last_active_at.strftime("%Y-%m-%d %H:%M")
            path = str(s.project_path) if s.project_path else "no project"
            label_str = f"{ts}  {s.active_model or '—'}  {path}\n    {title[:60]}"
            self._list.append(ListItem(Label(label_str)))

        if self._status:
            self._status.update(f"  {len(self._sessions)} sessions")

    def _first_user_message(self, session_id: UUID) -> str | None:
        """Get the first user message of a session (used as title, §6.3)."""
        msgs = self.app.history.get_messages(session_id)  # type: ignore[attr-defined]
        for m in msgs:
            if m.role == "user":
                return m.content[:80]
        return None

    def on_input_submitted(self, event) -> None:
        """Handle filter input."""
        if event.input is self._filter_input:
            self._load_sessions(event.value.strip())

    def on_list_view_selected(self, event) -> None:
        """Handle selection (Enter) — §6.3: Enter loads the session."""
        index = event.list_view.index
        if 0 <= index < len(self._sessions):
            session = self._sessions[index]
            self._load_session(session)

    def _load_session(self, session: Session) -> None:
        """Load a session into the active chat view (§6.3)."""
        # Check project folder still exists (§6.3 edge case)
        if session.project_path and not Path(session.project_path).exists():
            logger.warning(
                "Session {} project no longer exists: {}",
                session.id, session.project_path,
            )
            self.app._get_chat_screen()._show_system_message(  # type: ignore[attr-defined]
                f"Project folder no longer exists: {session.project_path}\n"
                "Chat loaded read-only. Use /open <path> to set a valid project."
            )

        # Set current session and load messages
        self.app.current_session = session  # type: ignore[attr-defined]
        self.app.active_model = session.active_model  # type: ignore[attr-defined]
        self.app.active_backend = session.backend  # type: ignore[attr-defined]

        from halite.utils.logging_config import set_correlation_context
        set_correlation_context(session_id=str(session.id))

        messages = self.app.history.get_messages(session.id)  # type: ignore[attr-defined]
        self.app._get_chat_screen().load_messages(messages)  # type: ignore[attr-defined]

        if self.app.status_bar:  # type: ignore[attr-defined]
            self.app.status_bar.model_name = session.active_model or "none"  # type: ignore[attr-defined]
            self.app.status_bar.backend = session.backend  # type: ignore[attr-defined]
            if session.project_path:
                self.app.status_bar.project_path = str(session.project_path)  # type: ignore[attr-defined]

        logger.info("Session loaded into chat: {}", session.id)
        self.app.pop_screen()  # type: ignore[attr-defined]

    def action_cancel(self) -> None:
        """Esc — cancel without changing anything (§6.3)."""
        self.app.pop_screen()

    def action_load(self) -> None:
        """Enter — load the selected session."""
        if self._list and self._list.index is not None:
            index = self._list.index
            if 0 <= index < len(self._sessions):
                self._load_session(self._sessions[index])
