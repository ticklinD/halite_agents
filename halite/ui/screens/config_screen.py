"""
Config screen (§7.1).
Set: active backend, Ollama host, API key, default theme, auto_approve_api,
trust level, max iterations. API key stored via keyring, never in plaintext config.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem, Label, Input, Button, Header
from textual.containers import Vertical, Horizontal

from halite.config.settings import load_config, save_config
from halite.config.secrets import store_secret, retrieve_secret
from halite.utils.logging_config import logger


class ConfigScreen(Screen):
    """Settings screen (§7.1)."""

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    DEFAULT_CSS = """
    ConfigScreen {
        layout: vertical;
    }
    #config-content {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #config-content Static {
        margin-bottom: 1;
    }
    #config-back {
        dock: bottom;
        height: 3;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status: Static | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        cfg = load_config()

        with Vertical(id="config-content"):
            self._status = Static("")
            yield self._status
            yield Static(f"[b]Current configuration[/b]\n")
            yield Static(f"Default backend : {cfg.default_backend}")
            yield Static(f"Ollama host     : {cfg.ollama_host}")
            yield Static(f"API provider    : {cfg.api_provider}")
            yield Static(f"auto_approve_api: {cfg.auto_approve_api}")
            yield Static(f"Trust level     : {cfg.trust_level}")
            yield Static(f"Max iterations  : {cfg.max_agent_iterations}")
            yield Static(f"Theme            : {cfg.theme}")

            key_present = retrieve_secret("anthropic_api_key") is not None
            yield Static(f"\nAPI key: {'✓ configured' if key_present else '✗ not set'}")

            yield Static("\n[b]Actions[/b]")
            yield Static("  • /trust manual|auto  — set confirmation behaviour")
            yield Static("  • Run /config in chat is read-only for now; edit ~/.halite/config.toml directly")

        with Horizontal(id="config-back"):
            yield Static("Esc to return")

    def action_back(self) -> None:
        self.app.pop_screen()
