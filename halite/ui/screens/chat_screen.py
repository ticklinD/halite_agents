"""
Chat screen — the main interaction screen (§4 UI layer).
Handles message display, user input, and chat history rendering.
"""
from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, RichLog, Input, Header
from textual import events
from textual.containers import Vertical, Horizontal
from rich.markdown import Markdown
from rich.text import Text

from halite.models.schemas import Message
from halite.utils.logging_config import logger


class ChatScreen(Screen):
    """Main chat screen with message display and input."""

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
    }
    #chat-display {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }
    #input-bar {
        height: 3;
        padding: 0 1;
        border-top: solid $accent;
    }
    #input-bar Input {
        height: 3;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._messages: list[Message] = []
        self._input: Input | None = None
        self._chat_display: RichLog | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="chat-display-container"):
            self._chat_display = RichLog(id="chat-display", highlight=True, markup=True, wrap=True)
            yield self._chat_display
        with Horizontal(id="input-bar"):
            self._input = Input(placeholder="Type a message or /command...", id="chat-input")
            yield self._input

    def on_mount(self) -> None:
        """Focus the input on mount."""
        if self._input:
            self._input.focus()
        # Show welcome message
        self._show_system_message(
            "Welcome to Halite! A hybrid TUI coding agent.\n"
            "Type a message to start, or /help for commands.\n"
            "Active project: none. Use /open <path> to set one."
        )

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
            self._chat_display.write(Text(f"You: ", style="bold cyan") + text)

    def _show_assistant_message(self, text: str) -> None:
        """Display an assistant message in the chat."""
        if self._chat_display:
            self._chat_display.write(Text("Halite: ", style="bold green") + text)

    def _show_system_message(self, text: str) -> None:
        """Display a system/info message in the chat."""
        if self._chat_display:
            self._chat_display.write(Text(text, style="dim italic"))

    def _show_error_message(self, text: str) -> None:
        """Display an error message in the chat."""
        if self._chat_display:
            self._chat_display.write(Text(f"Error: {text}", style="bold red"))

    def _show_tool_result(self, tool_name: str, output: str, success: bool) -> None:
        """Display a tool result in the chat."""
        if self._chat_display:
            style = "green" if success else "red"
            status = "OK" if success else "FAIL"
            self._chat_display.write(
                Text(f"  └─ {tool_name} [{status}]: ", style=f"bold {style}") + output[:500]
            )

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
