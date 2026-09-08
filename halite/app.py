"""
The main Halite Textual App (§4 UI layer).
Messages and handlers connect the UI to the core router, storage, and tool executor.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from textual.app import App
from textual import events
from textual.widgets import Footer

from halite.models.schemas import Message, Session
from halite.config.settings import load_config, save_config, AppConfig
from halite.config.secrets import get_secret_backend_info
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers
from halite.storage.history import HistoryStore
from halite.storage.db import init_db
from halite.models.local_provider import OllamaProvider
from halite.models.capability_registry import CapabilityRegistry
from halite.tools.base import ToolExecutor
from halite.ui.screens.chat_screen import ChatScreen, MessageSubmitted
from halite.ui.screens.history_screen import HistoryScreen
from halite.ui.screens.config_screen import ConfigScreen
from halite.ui.screens.debug_screen import DebugScreen
from halite.ui.widgets.status_bar import StatusBar
from halite.ui.widgets.log_panel import LogPanel
from halite.ui.widgets.diff_view import DiffView
from halite.utils.logging_config import (
    setup_logging, install_exception_hook, logger,
    set_correlation_context,
)


class HaliteApp(App):
    """The Halite TUI application."""

    TITLE = "Halite"
    SUB_TITLE = "Hybrid TUI Coding Agent"

    CSS_PATH = "ui/styles/app.tcss"

    # ChatScreen is the default screen (not pushed — it's the app's base screen)
    DEFAULT_SCREEN = "chat"
    SCREENS = {
        "chat": ChatScreen,
        "history": HistoryScreen,
        "config": ConfigScreen,
        "debug": DebugScreen,
    }

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, debug: bool = False) -> None:
        super().__init__()
        self.debug_mode = debug

        # Load config
        self.config: AppConfig = load_config()

        # Logging
        setup_logging(debug=self.config.debug_mode or debug)
        install_exception_hook()

        logger.info("Halite starting — debug={}", self.debug_mode)

        # Storage
        self.history = HistoryStore()

        # Model state — set before session creation (session references model)
        self.active_model = ""
        self.active_backend = self.config.default_backend

        # Session
        self.current_session: Session | None = None
        self.new_session()

        # Router / model layer
        self.ollama = OllamaProvider(host=self.config.ollama_host)
        self.capabilities = CapabilityRegistry()

        # Tool executor
        self.executor = ToolExecutor(project_root=self.current_session.project_path)

        # Register all tools (§6.4)
        from halite.tools.registry import ToolRegistry
        ToolRegistry(self.executor)
        from halite.tools.file_tool import set_diff_callback
        from halite.tools.terminal_tool import set_dangerous_callback
        set_diff_callback(self._confirm_diff)
        set_dangerous_callback(self._confirm_dangerous)

        # Command dispatcher
        self.dispatcher = CommandDispatcher()
        register_handlers(self.dispatcher, self)

        # UI references
        self.status_bar: StatusBar | None = None
        self.log_panel: LogPanel | None = None
        self.diff_view: DiffView | None = None

        # Detect available models
        self._detect_models()

        logger.info(
            "Halite initialised — session={}, backend={}, secret_backend={}",
            self.current_session.id,
            self.active_backend,
            get_secret_backend_info(),
        )

    # ── Textual lifecycle ────────────────────────────────────────────────────

    def compose(self):
        # Shared chrome: status bar, log panel, diff view, footer.
        # ChatScreen is the default screen (see DEFAULT_SCREEN).
        self.status_bar = StatusBar()
        yield self.status_bar
        self.log_panel = LogPanel()
        yield self.log_panel
        self.diff_view = DiffView()
        yield self.diff_view
        yield Footer()

    # ── Session management ──────────────────────────────────────────────────

    def new_session(self) -> None:
        """Create a new session and persist it (§7.3 /new)."""
        session = Session(
            id=uuid4(),
            project_path=self.config_project_root(),
            active_model=self.active_model or "",
            backend=self.active_backend,
        )
        self.current_session = session
        self.history.create_session(session)
        set_correlation_context(session_id=str(session.id))
        logger.info("New session created: {}", session.id)
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.model_name = self.active_model or "none"
            self.status_bar.backend = self.active_backend

    def config_project_root(self) -> Path | None:
        """Get the configured project root (from config if set, else cwd)."""
        return Path.cwd()

    # ── Model discovery ────────────────────────────────────────────────────

    def _detect_models(self) -> None:
        """Sync pre-seed of the active model (called before the loop is live).

        If the user configured `ollama_default_model`, use it.
        Otherwise the async `_discover_models()` fills in the first
        installed model once the event loop is running.
        """
        if self.config.ollama_default_model:
            self.active_model = self.config.ollama_default_model
            logger.info("Using configured default model: {}", self.active_model)
        elif self.active_backend == "api":
            self.active_model = "claude-sonnet-4-20250514"
        else:
            self.active_model = ""
            logger.info("No default model configured — will auto-discover from Ollama")

    async def _discover_models(self) -> None:
        """Async: query the Ollama daemon for installed models (§7.8).

        Picks the first installed model (preferring one matching the
        user's `ollama_default_model`, or the classifier model, then any).
        Called from on_mount; never blocks startup.
        """
        if self.active_backend != "local_ollama":
            return
        try:
            models = await self.ollama.list_models()
        except Exception as exc:
            logger.warning("Model discovery failed: {}", exc)
            return

        if not models:
            logger.warning(
                "Ollama is running but has no models installed. "
                "Run `ollama pull <model>` and restart, or use /model."
            )
            return

        names = [m.get("name", "") for m in models]
        logger.info("Installed Ollama models: {}", names)

        # Preference order: configured default → classifier model → first
        preferred = self.config.ollama_default_model
        if preferred and preferred in names:
            pick = preferred
        elif self.config.ollama_classifier_model in names:
            pick = self.config.ollama_classifier_model
        else:
            pick = names[0]

        self.active_model = pick
        logger.info("Active model selected: {}", pick)

        # Reflect in status bar and session record
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.model_name = pick
            self.status_bar.backend = self.active_backend
        if self.current_session:
            self.current_session.active_model = pick
            self.current_session.backend = self.active_backend

    # ── Confirmation callbacks (§6.4, §7.4) ─────────────────────────────────

    async def _confirm_diff(self, path: Path, old_content: str, new_content: str) -> bool:
        """
        Confirm a file write that would overwrite existing content (§6.4).
        Returns True to proceed, False to cancel.
        In 'auto' trust level, non-destructive writes proceed without asking.
        """
        if self.config.trust_level == "auto":
            logger.debug("Auto trust — write to {} proceeds without diff confirmation", path)
            return True

        # Manual trust — ask the user via the chat
        chat = self._get_chat_screen()
        chat._show_system_message(
            f"Overwrite existing file {path}? This shows a diff first."
        )
        # For Phase 1, default to showing diff via the diff view and pending confirmation
        if self.diff_view:
            self.diff_view.show_diff(str(path), old_content, new_content)
        # In Phase 3 this becomes an interactive yes/no. For now:
        return True

    async def _confirm_dangerous(self, command: str, reason: str) -> bool:
        """
        Confirm a dangerous command (§6.4, §7.4).
        Always asks, regardless of auto-approve settings.
        """
        chat = self._get_chat_screen()
        chat._show_error_message(f"DANGEROUS COMMAND blocked: {command}\n  Reason: {reason}")
        # This is wired to a proper interactive confirmation in Phase 3/8.
        return False

    # ── Message handling ────────────────────────────────────────────────────

    def on_message_submitted(self, event: MessageSubmitted) -> None:
        """Handle a user message submitted from the chat screen."""
        logger.debug("MessageSubmitted received: {}", event.text[:60])
        asyncio.create_task(self._handle_user_input(event.text))

    async def _handle_user_input(self, text: str) -> None:
        """Process user input in the async context."""
        # Set turn correlation id
        turn_id = str(uuid4())[:8]
        set_correlation_context(
            session_id=str(self.current_session.id) if self.current_session else None,
            turn_id=turn_id,
        )

        # Check if it's a command
        result = await self.dispatcher.dispatch(text)

        if result.handled:
            # Handle command results
            logger.debug("Command handled: {}", result.message[:100])

            # Special UI actions
            if result.action == "quit":
                await self.action_quit()
                return
            elif result.action == "clear_chat":
                self._get_chat_screen().clear_chat()
            elif result.action == "new_session":
                self.new_session()
                self._get_chat_screen().clear_chat()

            # Show any message from the command
            if result.message:
                self._get_chat_screen()._show_system_message(result.message)

            # Persist the command as a user message
            self._persist_message("user", text)
            return

        # Not a command — treat as chat input
        self._persist_message("user", text)
        await self._handle_chat_message(text)

    def _get_chat_screen(self) -> ChatScreen:
        """Get the chat screen instance."""
        return self.screen  # type: ignore

    def _persist_message(self, role: str, content: str, model_used: str | None = None) -> None:
        """Persist a message to SQLite and update correlation context."""
        if self.current_session is None:
            logger.warning("No active session — cannot persist message")
            return

        msg = Message(
            session_id=self.current_session.id,
            role=role,  # type: ignore
            content=content,
            model_used=model_used,
        )
        self.history.add_message(msg)

    async def _handle_chat_message(self, text: str) -> None:
        """Handle a normal (non-command) chat message by routing to a model."""
        logger.info("Chat message received ({} chars)", len(text))

        # Get the chat screen
        chat = self._get_chat_screen()

        # Build message list for the model
        history = self.history.get_messages(self.current_session.id)
        messages: list[dict] = []
        for m in history:
            if m.role in ("user", "assistant"):
                messages.append({"role": m.role, "content": m.content})

        # Route to the active backend
        await self._route_and_respond(messages, chat, turn_id=f"{uuid4()}"[:8])

    async def _route_and_respond(self, messages: list[dict], chat: ChatScreen, turn_id: str) -> None:
        """
        Route to the appropriate backend based on the active backend/model,
        get a response, display it, and persist it (§4 Router).
        """
        # Display a "thinking" indicator
        chat._show_system_message("  ···")

        response = ""
        try:
            if self.active_backend == "api":
                from halite.models.api_provider import APIProvider
                from halite.config.secrets import retrieve_secret
                key = retrieve_secret("anthropic_api_key")
                if not key:
                    chat._show_error_message(
                        "No Anthropic API key configured. Use /config to add one, "
                        "or /model to switch to a local model."
                    )
                    return
                provider = APIProvider(api_key=key, model=self.active_model)
                response = await provider.chat(messages)
                await provider.close()
            else:
                # Local via Ollama
                response = await self.ollama.chat(self.active_model, messages)

            # Remove the thinking indicator (redraw by re-rendering)
            chat._show_assistant_message(response)
            logger.info("Response received ({} chars)", len(response))

            # Persist assistant message
            dog = Message(
                session_id=self.current_session.id,
                role="assistant",
                content=response,
                model_used=self.active_model,
            )
            self.history.add_message(dog)

        except Exception as exc:
            logger.exception("Failed to get model response: {}", str(exc))
            chat._show_error_message(f"Failed to get model response: {exc}")

    # ── Lifecycle handlers ──────────────────────────────────────────────────

    async def on_mount(self) -> None:
        """App is mounted — final init."""
        # Push the chat screen as the main UI (screens are class-registered)
        self.push_screen("chat")

        # Async model discovery (if not already set via config)
        if not self.active_model:
            await self._discover_models()

        # Update status bar
        if self.status_bar:
            self.status_bar.update_all(
                model=self.active_model or "none",
                backend=self.active_backend,
                project=str(self.current_session.project_path) if self.current_session and self.current_session.project_path else ".",
                cost="$0.00",
                trust=self.config.trust_level,
            )
        logger.info("Halite UI mounted")

    async def action_quit(self) -> None:
        """Clean shutdown with autosave checkpoints (§7.6)."""
        logger.info("Halite shutting down")

        # Close resources
        try:
            await self.ollama.close()
        except Exception:
            pass
        try:
            self.history.close()
        except Exception:
            pass

        self.exit()


def main() -> None:
    """Entry point."""
    import sys

    # Parse --debug flag
    debug = "--debug" in sys.argv

    app = HaliteApp(debug=debug)
    app.run()


if __name__ == "__main__":
    main()
