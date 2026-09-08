"""
Local/API backend router (§6.1, §4).
Decides which backend serves a task, based on classifier decision + user overrides.
"""
from __future__ import annotations

from halite.models.schemas import AppConfig, ClassifierDecision
from halite.utils.logging_config import logger


class Router:
    """
    Routes tasks between local and API backends (§6.1).
    Respects manual overrides via /model. Enforces the API permission gate:
    classification is automatic, but execution never happens without explicit
    user approval (§6.1 — never auto-execute paid API).
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        # Manual override set by /model — overrides automatic classification
        self.manual_override: str | None = None  # "local" or "api"
        self.pending_api_approval: bool = False

    def is_api_auto_approved(self) -> bool:
        """Whether API calls can proceed without the confirmation gate (§6.1)."""
        return self.config.auto_approve_api

    def resolve_backend(self, decision: ClassifierDecision) -> tuple[str, bool]:
        """
        Resolve which backend to use for a task.
        Returns (backend, needs_user_confirmation).
        backend ∈ {"local", "api"}.
        needs_user_confirmation is True when we're routing to API and
        auto_approve is off (the §6.1 permission gate).
        """
        # Manual override takes precedence (§6.1: /model replaces auto decision)
        if self.manual_override == "local":
            logger.info("Router: manual local override active")
            return "local", False

        if self.manual_override == "api":
            # Manual override to API still requires gate unless auto-approved
            needs_confirm = not self.is_api_auto_approved()
            logger.info("Router: manual API override active (confirm={})", needs_confirm)
            return "api", needs_confirm

        # Automatic classification
        if decision.decision == "local":
            logger.info("Router: classified as LOCAL")
            return "local", False

        if decision.decision == "api":
            needs_confirm = not self.is_api_auto_approved()
            logger.info("Router: classified as API (confirm={})", needs_confirm)
            return "api", needs_confirm

        # decision == "clarify" — don't route to any backend yet
        logger.info("Router: classified as CLARIFY — no backend selected")
        return "none", False

    def set_manual_override(self, backend: str) -> None:
        """Set a manual backend override (via /model)."""
        if backend not in ("local", "api"):
            raise ValueError(f"Invalid backend override: {backend}")
        self.manual_override = backend
        logger.info("Router: manual override set to '{}'", backend)

    def clear_manual_override(self) -> None:
        """Clear the manual override, returning to automatic mode."""
        self.manual_override = None
        logger.info("Router: manual override cleared")

    def approve_api(self) -> None:
        """User approved the API call — clear the pending gate."""
        self.pending_api_approval = False
        logger.info("Router: API call approved by user")

    def decline_api(self) -> None:
        """User declined the API call — stay local."""
        self.pending_api_approval = False
        logger.info("Router: API call declined — staying local")

    def request_api_approval(self) -> None:
        """Mark that an API call is pending user approval."""
        self.pending_api_approval = True
