"""
Log panel widget — live split-pane log tail (§10, /debug).
Tails the current log file and shows entries in the TUI.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Static, RichLog
from textual.reactive import reactive

from halite.utils.logging_config import LOG_DIR


class LogPanel(Static):
    """Live log panel that tails the active log file."""

    DEFAULT_CSS = """
    LogPanel {
        dock: bottom;
        height: 10;
        background: $surface;
        border-top: solid $accent;
        padding: 0 1;
        overflow-y: auto;
        display: none;
    }
    LogPanel.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._log_widget: RichLog | None = None
        self._tail_task: asyncio.Task | None = None
        self._last_position: int = 0
        self._stopped = True

    def compose(self) -> ComposeResult:
        self._log_widget = RichLog(highlight=True, markup=True, wrap=True)
        yield self._log_widget

    def on_mount(self) -> None:
        """Start tailing when the panel mounts — only if visible."""
        self._stopped = False
        self._start_tail()

    def _start_tail(self) -> None:
        """Start the background log tailing task."""
        if self._tail_task and not self._tail_task.done():
            return
        self._tail_task = asyncio.create_task(self._tail_loop())

    async def _tail_loop(self) -> None:
        """Continuously tail the current day's log file, honouring cancellation."""
        import datetime
        while not self._stopped:
            try:
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                log_file = LOG_DIR / f"halite_{today}.log"
                if log_file.exists():
                    with open(log_file, "r") as f:
                        # Seek to where we left off
                        f.seek(self._last_position)
                        new_lines = f.readlines()
                        self._last_position = f.tell()
                        if new_lines and self._log_widget:
                            for line in new_lines[-50:]:
                                self._log_widget.write(line.rstrip())
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise

    def toggle_visible(self) -> None:
        """Toggle the log panel visibility."""
        self.visible = not self.visible
        if self.visible:
            self._start_tail()

    def stop(self) -> None:
        """Stop the tail task and cancel it."""
        self._stopped = True
        if self._tail_task is not None:
            self._tail_task.cancel()

    async def on_unmount(self) -> None:
        """Ensure the task is cancelled on unmount."""
        self.stop()