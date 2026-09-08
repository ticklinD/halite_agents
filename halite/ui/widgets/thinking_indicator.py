"""Thinking/generating indicator for Halite TUI — shows animated spinner while LLM is working."""
from __future__ import annotations

import asyncio
from time import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static


# Braille spinner frames (from unicode-animations — Hermes uses these)
SPINNERS = {
    "helix": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "line": ["-", "\\", "|", "/"],
    "pulse": ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"],
}

DEFAULT_SPINNER = "helix"
DEFAULT_INTERVAL = 80  # ms between frames


class ThinkingIndicator(Widget):
    """Animated thinking/generating indicator.

    Shows a spinning braille character + status text while the model is working.
    Disappears when idle.

    Usage:
        indicator = ThinkingIndicator()
        indicator.start_thinking("Generating...")
        indicator.stop_thinking()
    """

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: auto;
        max-height: 3;
        padding: 0 1;
        display: none;
    }
    ThinkingIndicator.active {
        display: block;
    }
    ThinkingIndicator .spinner-char {
        width: 2;
        color: $accent;
        text-style: bold;
    }
    ThinkingIndicator .thinking-text {
        width: 1fr;
        color: $text-muted;
        text-style: italic;
    }
    ThinkingIndicator .thinking-timer {
        width: auto;
        color: $text-muted 50%;
        min-width: 6;
        text-align: right;
    }
    """

    _frame_index: int = 0
    _start_time: float = 0.0
    _interval: float = DEFAULT_INTERVAL / 1000.0
    _spinner: list[str] = SPINNERS[DEFAULT_SPINNER]
    _active: reactive[bool] = reactive(False, layout=True)
    _label: reactive[str] = reactive("Thinking...")
    _elapsed_text: reactive[str] = reactive("")

    def __init__(self, spinner: str = DEFAULT_SPINNER, **kwargs) -> None:
        super().__init__(**kwargs)
        self._spinner = SPINNERS.get(spinner, SPINNERS[DEFAULT_SPINNER])

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(self._spinner[0], classes="spinner-char", id="spinner-char")
            yield Label(self._label, classes="thinking-text", id="thinking-label")
            yield Label(self._elapsed_text, classes="thinking-timer", id="thinking-timer")

    def start_thinking(self, label: str | None = None) -> None:
        """Start the thinking animation."""
        if label:
            self._label = label
        self._start_time = time()
        self._frame_index = 0
        self._active = True
        self.add_class("active")
        self.set_interval(self._interval, self._tick)
        # Update elapsed time every 100ms
        self.set_interval(0.1, self._update_elapsed)

    def stop_thinking(self) -> None:
        """Stop the thinking animation and hide."""
        self._active = False
        self.remove_class("active")
        self._elapsed_text = ""

    def update_label(self, label: str) -> None:
        """Update the thinking label text."""
        self._label = label
        label_widget = self.query_one("#thinking-label", Label)
        label_widget.update(label)

    def _tick(self) -> None:
        """Advance spinner frame."""
        if not self._active:
            return
        self._frame_index = (self._frame_index + 1) % len(self._spinner)
        char_widget = self.query_one("#spinner-char", Static)
        char_widget.update(self._spinner[self._frame_index])

    def _update_elapsed(self) -> None:
        """Update elapsed time display."""
        if not self._active:
            return
        elapsed = time() - self._start_time
        if elapsed < 10:
            self._elapsed_text = f"{elapsed:.1f}s"
        else:
            self._elapsed_text = f"{int(elapsed)}s"
        try:
            timer_widget = self.query_one("#thinking-timer", Label)
            timer_widget.update(self._elapsed_text)
        except Exception:
            pass


class StreamingCursor(Widget):
    """A blinking cursor shown during streaming output."""

    DEFAULT_CSS = """
    StreamingCursor {
        height: 1;
        width: 1;
    }
    """

    _visible: reactive[bool] = reactive(True)
    _streaming: reactive[bool] = reactive(False)
    _interval_id: object | None = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("▍" if self._visible else " ", id="cursor")

    def start_streaming(self) -> None:
        """Start the blinking cursor."""
        self._streaming = True
        self._visible = True
        if self._interval_id is None:
            self._interval_id = self.set_interval(0.42, self._blink)

    def stop_streaming(self) -> None:
        """Stop the blinking cursor."""
        self._streaming = False
        self._visible = False
        if self._interval_id:
            self._interval_id = None
        try:
            cursor = self.query_one("#cursor", Static)
            cursor.update(" ")
        except Exception:
            pass

    def _blink(self) -> None:
        if not self._streaming:
            return
        self._visible = not self._visible
        try:
            cursor = self.query_one("#cursor", Static)
            cursor.update("▍" if self._visible else " ")
        except Exception:
            pass
