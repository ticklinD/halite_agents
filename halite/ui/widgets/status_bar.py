"""
Status bar widget — always visible at the bottom of the TUI (§7.3).
Shows: active model, backend, active project path, session cost, trust level.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive

from halite.utils.logging_config import logger


class StatusBar(Static):
    """Live status bar showing model, project, cost, and trust level."""

    # Reactive properties — UI updates automatically when these change
    model_name: reactive[str] = reactive("none")
    backend: reactive[str] = reactive("local")
    project_path: reactive[str] = reactive("no project")
    session_cost: reactive[str] = reactive("$0.00")
    trust_level: reactive[str] = reactive("manual")

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def render(self) -> str:
        return (
            f"  {self.model_name} [{self.backend}]  │  "
            f"{self.project_path}  │  "
            f"cost: {self.session_cost}  │  "
            f"trust: {self.trust_level}  │  "
            f"Type /help for commands"
        )

    def update_all(
        self,
        model: str = "",
        backend: str = "",
        project: str = "",
        cost: str = "",
        trust: str = "",
    ) -> None:
        """Update all status bar fields at once."""
        if model:
            self.model_name = model
        if backend:
            self.backend = backend
        if project:
            self.project_path = project
        if cost:
            self.session_cost = cost
        if trust:
            self.trust_level = trust
        logger.debug("Status bar updated: model={}, backend={}", self.model_name, self.backend)
