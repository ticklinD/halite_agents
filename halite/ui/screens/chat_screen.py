"""
Chat screen — the main interaction screen (§4 UI layer).
Handles message display, user input, and chat history rendering.
Refactored: Hermes-inspired clean layout with thinking indicator + full scroll.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, RichLog, Static
from rich.text import Text

from halite.models.schemas import Message
from halite.ui.widgets.thinking_indicator import ThinkingIndicator, StreamingCursor
from halite.utils.logging_config import logger


class ChatScreen(Screen):
    """Main chat screen with message display, input, and thinking indicator.

    Layout (top to bottom):
        Header              (1 row, docked)
        [thinking-area]     (0-3 rows, inline, hidden when idle)
        chat-container      (1fr, scrollable — fills all remaining space)
        input-container     (1-6 rows, docked bottom)
        status-bar          (1 row, docked bottom)
        Footer              (1 row, docked bottom)
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._messages: list[Message] = []
        self._input: Input | None = None
        self._chat_display: RichLog | None = None
        self._thinking: ThinkingIndicator | None = None
        self._cursor: StreamingCursor | None = None
        self._thinking_area: Vertical | None = None

    def compose(self) -> ComposeResult:
        # Header — thin, one row
        yield Header(show_clock=True)

        # Thinking area — hidden by default, shown when model is working
        self._thinking_area = Vertical(id="thinking-area")
        with self._thinking_area:
            self._thinking = ThinkingIndicator(spinner="helix")
            yield self._thinking

        # Chat messages — scrollable, takes all remaining space
        self._chat_display = RichLog(
            id="chat-display",
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
        )
        yield self._chat_display  # type: ignore[assignment]

        # Input area — docked to bottom
        with Horizontal(id="input-container"):
            yield Label("❯ ", id="input-prompt")
            self._input = Input(
                placeholder="Type a message or /help for commands…",
                id="user-input",
            )
            yield self._input

        # Status bar — docked to very bottom
        with Horizontal(id="status-bar"):
            yield Label("halite", id="status-model")
            yield Label("ollama", id="status-backend")
            yield Label("", id="status-cost")
            yield Label("/help for commands", id="status-hint")

        yield Footer()

    def on_mount(self) -> None:
        """Focus the input on mount and show welcome."""
        if self._input:
            self._input.focus()
        self._show_welcome()

    def _show_welcome(self) -> None:
        """Show the initial welcome banner."""
        welcome = Text()
        welcome.append("  ╭─────────────────────────────────────────╮\n", style="dim")
        welcome.append("  │ ", style="dim")
        welcome.append("Halite", style="bold bright_cyan")
        welcome.append(" — hybrid TUI coding agent", style="dim")
        welcome.append("\n  │ ", style="dim")
        welcome.append("Type a message to start, or ", style="dim")
        welcome.append("/help", style="bold yellow")
        welcome.append(" for commands", style="dim")
        welcome.append("\n  │ ", style="dim")
        welcome.append("Active project: none", style="dim")
        welcome.append("\n  ╰─────────────────────────────────────────╯", style="dim")
        self._chat_display.write(welcome)

    # ── Message display ────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        text = event.value.strip()
        if not text:
            return

        # Clear the input
        self._input.value = ""

        # Show user message in chat
        self._show_user_message(text)

        # Emit an event that the app can pick up
        self.app.post_message(MessageSubmitted(text))

    def _show_user_message(self, text: str) -> None:
        """Display a user message in the chat."""
        if self._chat_display:
            msg = Text()
            msg.append("❯ ", style="bold bright_blue")
            msg.append(text, style="bright_white")
            self._chat_display.write(msg)

    def _show_assistant_message(self, text: str) -> None:
        """Display an assistant message in the chat."""
        if self._chat_display:
            msg = Text()
            msg.append("◆ ", style="bold bright_green")
            msg.append(text)
            self._chat_display.write(msg)

    def _show_system_message(self, text: str) -> None:
        """Display a system/info message in the chat."""
        if self._chat_display:
            msg = Text()
            msg.append("  ", style="dim")
            msg.append(text, style="dim italic")
            self._chat_display.write(msg)

    def _show_error_message(self, text: str) -> None:
        """Display an error message in the chat."""
        if self._chat_display:
            msg = Text()
            msg.append("✕ ", style="bold red")
            msg.append(text, style="red")
            self._chat_display.write(msg)

    def _show_tool_result(self, tool_name: str, output: str, success: bool) -> None:
        """Display a tool result in the chat."""
        if self._chat_display:
            style = "bright_green" if success else "red"
            status = "OK" if success else "FAIL"
            msg = Text()
            msg.append(f"    └─ {tool_name} ", style=f"bold {style}")
            msg.append(f"[{status}]", style=style)
            msg.append(f" {output[:500]}", style="dim")
            self._chat_display.write(msg)

    # ── Thinking indicator ─────────────────────────────────────────

    def show_thinking(self, label: str = "Thinking…") -> None:
        """Show the thinking indicator — model is processing."""
        if self._thinking:
            self._thinking.start_thinking(label)
            if self._thinking_area:
                self._thinking_area.add_class("active")

    def hide_thinking(self) -> None:
        """Hide the thinking indicator — model finished."""
        if self._thinking:
            self._thinking.stop_thinking()
            if self._thinking_area:
                self._thinking_area.remove_class("active")

    def update_thinking_label(self, label: str) -> None:
        """Update the thinking label text (e.g. 'Generating…', 'Streaming…')."""
        if self._thinking:
            self._thinking.update_label(label)

    # ── Session management ─────────────────────────────────────────

    def clear_chat(self) -> None:
        """Clear the visible chat display."""
        if self._chat_display:
            self._chat_display.clear()
            self._show_system_message("Chat cleared (history preserved).")

    def load_messages(self, messages: list[Message]) -> None:
        """Load messages into the chat display (for session resume)."""
        if self._chat_display:
            self._chat_display.clear()
        for msg in messages:
            if msg.role == "user":
                self._show_user_message(msg.content)
            elif msg.role == "assistant":
                self._show_assistant_message(msg.content)
            elif msg.role == "system":
                self._show_system_message(msg.content)


class MessageSubmitted(events.Event):
    """Event emitted when the user submits a message."""
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
