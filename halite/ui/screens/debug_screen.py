"""
Debug screen — splits the TUI into a live log tail pane (§10, /debug).
Shows the current session's debug logs in real time.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, RichLog, Header

from halite.utils.logging_config import LOG_DIR


class DebugScreen(Screen):
    """Live log panel (full-screen) for /debug (§10)."""

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    DEFAULT_CSS = """
    DebugScreen {
        layout: vertical;
    }
    #debug-log {
        height: 1fr;
        border-top: solid $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._log: RichLog | None = None
        self._last_position: int = 0
        self._polling: bool = False

    def set_tail_file(self, path: Path | None) -> None:
        """Set which log file to tail."""
        self._tail_file = path or LOG_DIR / f"halite_{datetime.now().strftime('%Y-%m-%d')}.log"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self._log = RichLog(highlight=True, markup=True, wrap=True, id="debug-log")
        yield self._log
        yield Static("Esc to return")

    def on_mount(self) -> None:
        self._tail_file = LOG_DIR / f"halite_{datetime.now().strftime('%Y-%m-%d')}.log"
        self._polling = True
        self.set_interval(1.0, self._poll_log)

    def _poll_log(self) -> None:
        """Poll the log file for new lines."""
        if not self._polling or self._log is None:
            return
        try:
            if self._tail_file.exists():
                with open(self._tail_file, "r") as f:
                    f.seek(self._last_position)
                    lines = f.readlines()
                    self._last_position = f.tell()
                    for line in lines[-100:]:
                        self._log.write(line.rstrip())
        except Exception:
            pass

    def action_back(self) -> None:
        self._polling = False
        self.app.pop_screen()
