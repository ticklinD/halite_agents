"""
Command handlers for slash commands (§9).
Each handler is an async function that takes args: str and returns CommandResult.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from halite.commands.dispatcher import CommandResult
from halite.utils.logging_config import logger

if TYPE_CHECKING:
    from halite.app import HaliteApp


def register_handlers(dispatcher, app: "HaliteApp") -> None:
    """Register all slash command handlers with the dispatcher."""

    async def cmd_debug(args: str) -> CommandResult:
        """Toggle the live log panel (§10, /debug)."""
        app.debug_mode = not app.debug_mode
        if app.debug_panel:
            app.debug_panel.visible = app.debug_panel.visible is False
        state = "ON" if app.debug_mode else "OFF"
        logger.info("Debug panel toggled: {}", state)
        return CommandResult(handled=True, message=f"Debug panel {state}")

    async def cmd_clear(args: str) -> CommandResult:
        """Clear the visible chat (does not delete history) — /clear."""
        return CommandResult(handled=True, action="clear_chat", message="Chat cleared")

    async def cmd_exit(args: str) -> CommandResult:
        """Quit with autosave checkpoint — /exit."""
        logger.info("User requested exit via /exit")
        return CommandResult(handled=True, action="quit", message="Goodbye")

    async def cmd_help(args: str) -> CommandResult:
        """Show available commands."""
        commands = dispatcher.list_commands()
        help_text = "Available commands:\n" + "\n".join(f"  /{c}" for c in commands)
        return CommandResult(handled=True, message=help_text)

    async def cmd_new(args: str) -> CommandResult:
        """Start a new session — /new."""
        return CommandResult(handled=True, action="new_session", message="New session started")

    async def cmd_model(args: str) -> CommandResult:
        """List and switch active model — /model."""
        # §6.1: when user explicitly switches models, reset task stickiness
        # so the new backend takes effect immediately.
        app._current_task_backend = None

        # Query Ollama live for installed models
        local_models: list[str] = []
        try:
            models = await app.ollama.list_models()
            local_models = [m.get("name", m.get("model", "")) for m in models]
        except Exception as exc:
            logger.warning("Failed to list Ollama models: {}", exc)

        # Configured API models (from the default built-in registry)
        api_models = [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
        ]

        # Build the response
        lines = ["Available models:"]
        lines.append("")
        if local_models:
            lines.append("  Local (Ollama):")
            for name in local_models:
                marker = " *" if name == app.active_model else ""
                lines.append(f"    {name}{marker}")
        else:
            lines.append("  Local (Ollama): (none installed)")
        lines.append("")
        lines.append("  API:")
        for name in api_models:
            marker = " *" if name == app.active_model else ""
            lines.append(f"    {name}{marker}")

        message = "\n".join(lines)

        return CommandResult(handled=True, action="show_models", message=message)

    async def cmd_history(args: str) -> CommandResult:
        """Browse and resume past sessions — /history (§6.3)."""
        try:
            sessions = app.history.list_sessions(limit=50)
            # Build entries with message count + first-message preview
            entries = []
            for s in sessions:
                msgs = app.history.get_messages(s.id)
                user_msgs = [m for m in msgs if m.role == "user"]
                preview = user_msgs[0].content[:80] if user_msgs else "(no messages)"
                entries.append({
                    "id": str(s.id),
                    "project_path": str(s.project_path) if s.project_path else None,
                    "active_model": s.active_model,
                    "backend": s.backend,
                    "created_at": s.created_at.isoformat(),
                    "last_active_at": s.last_active_at.isoformat(),
                    "message_count": len(msgs),
                    "preview": preview,
                })

            await app._send({
                "type": "history_data",
                "sessions": entries,
            })
            return CommandResult(
                handled=True,
                action="show_history",
                message=f"History: {len(entries)} session(s)",
            )

        except Exception as exc:
            logger.exception("cmd_history failed: {}", exc)
            return CommandResult(handled=True, message=f"History failed: {exc}")

    async def cmd_config(args: str) -> CommandResult:
        """Open settings screen — /config (§7.1)."""
        try:
            from halite.config.settings import load_config
            cfg = load_config()
            fields = [
                {"key": "default_backend", "label": "Default backend", "value": cfg.default_backend, "type": "select", "options": ["local_ollama", "local_llamacpp", "api"], "help": "Backend used when no task stickiness is active"},
                {"key": "ollama_host", "label": "Ollama host", "value": cfg.ollama_host, "type": "string", "help": "Base URL of the Ollama server"},
                {"key": "ollama_classifier_model", "label": "Classifier model", "value": cfg.ollama_classifier_model, "type": "string", "help": "SLM used for Stage B classification"},
                {"key": "ollama_default_model", "label": "Default Ollama model", "value": cfg.ollama_default_model or "", "type": "string", "help": "Auto-detects first installed model if empty"},
                {"key": "llamacpp_model_path", "label": "llama.cpp model path", "value": cfg.llamacpp_model_path or "", "type": "string", "help": "Path to GGUF for llama.cpp backend"},
                {"key": "llamacpp_models_dir", "label": "llama.cpp models dir", "value": cfg.llamacpp_models_dir or "", "type": "string", "help": "Directory to scan for GGUF models"},
                {"key": "api_provider", "label": "API provider", "value": cfg.api_provider, "type": "select", "options": ["anthropic", "openai"], "help": "Cloud provider for API backend"},
                {"key": "auto_approve_api", "label": "Auto-approve API calls", "value": str(cfg.auto_approve_api), "type": "boolean", "help": "Skip confirmation for API backend calls"},
                {"key": "trust_level", "label": "Trust level", "value": cfg.trust_level, "type": "select", "options": ["manual", "auto"], "help": "manual = confirm all risky ops; auto = skip non-destructive confirmation"},
                {"key": "max_agent_iterations", "label": "Max agent iterations", "value": str(cfg.max_agent_iterations), "type": "number", "help": "Cap on tool-call loop iterations"},
                {"key": "browser_timeout", "label": "Browser timeout (s)", "value": str(cfg.browser_timeout), "type": "number", "help": "Timeout for BrowserTool navigation"},
                {"key": "classifier_token_threshold", "label": "Classifier token threshold", "value": str(cfg.classifier_token_threshold), "type": "number", "help": "Above this, Stage B SLM re-checks"},
                {"key": "classifier_local_confidence_threshold", "label": "Local confidence threshold", "value": str(cfg.classifier_local_confidence_threshold), "type": "number", "help": "Stage A must exceed this to route local"},
                {"key": "classifier_api_confidence_threshold", "label": "API confidence threshold", "value": str(cfg.classifier_api_confidence_threshold), "type": "number", "help": "Below this, Stage B must confirm API routing"},
                {"key": "theme", "label": "Theme", "value": cfg.theme, "type": "select", "options": ["dark", "light"], "help": "UI theme"},
                {"key": "log_retention_days", "label": "Log retention (days)", "value": str(cfg.log_retention_days), "type": "number", "help": "Logs older than this are pruned"},
                {"key": "debug_mode", "label": "Debug mode", "value": str(cfg.debug_mode), "type": "boolean", "help": "Verbose logging"}
            ]

            await app._send({
                "type": "config_data",
                "fields": fields,
            })
            return CommandResult(
                handled=True,
                action="show_config",
                message="Config editor",
            )

        except Exception as exc:
            logger.exception("cmd_config failed: {}", exc)
            return CommandResult(handled=True, message=f"Config failed: {exc}")

    async def cmd_usage(args: str) -> CommandResult:
        """Show token/cost usage — /usage."""
        # Calculate real usage from DB
        records = app.history.get_session_usage(app.current_session.id) if app.current_session else []
        session_tokens_in = sum(r.tokens_in for r in records)
        session_tokens_out = sum(r.tokens_out for r in records)
        session_cost = sum(r.cost_usd for r in records)

        lifetime = app.history.get_lifetime_usage()
        lifetime_tokens_in = sum(r.tokens_in for r in lifetime)
        lifetime_tokens_out = sum(r.tokens_out for r in lifetime)
        lifetime_cost = sum(r.cost_usd for r in lifetime)

        msg = (
            f"── Usage ──\n"
            f"Session:  {session_tokens_in:,} in / {session_tokens_out:,} out  |  ${session_cost:.4f}\n"
            f"Lifetime: {lifetime_tokens_in:,} in / {lifetime_tokens_out:,} out  |  ${lifetime_cost:.4f}"
        )
        return CommandResult(handled=True, message=msg)

    async def cmd_trust(args: str) -> CommandResult:
        """Switch trust level — /trust manual|auto."""
        level = args.strip().lower()
        if level not in ("manual", "auto"):
            return CommandResult(handled=True, message="Usage: /trust manual  or  /trust auto")

        from halite.config.settings import load_config, save_config
        cfg = load_config()
        cfg.trust_level = level
        save_config(cfg)
        app.config = cfg
        state = "AUTO (non-destructive ops proceed without confirmation)" if level == "auto" else "MANUAL (all ops require confirmation)"
        logger.info("Trust level changed to: {}", level)
        return CommandResult(handled=True, message=f"Trust level: {state}")

    async def cmd_open(args: str) -> CommandResult:
        """Set the active project folder — /open <path>."""
        from pathlib import Path
        path = Path(args).expanduser().resolve()
        if not path.exists():
            return CommandResult(handled=True, message=f"Path does not exist: {path}")
        if not path.is_dir():
            return CommandResult(handled=True, message=f"Not a directory: {path}")

        app.project_root = path
        if app.current_session:
            app.current_session.project_path = path
            app.history.update_session(app.current_session)
        logger.info("Active project set to: {}", path)
        return CommandResult(handled=True, message=f"Active project: {path}")

    async def cmd_test(args: str) -> CommandResult:
        """Generate + run tests for a project — /test <path>."""
        return CommandResult(handled=True, action="run_tests", message="Test generation (Phase 7)")

    async def cmd_document(args: str) -> CommandResult:
        """Generate ARCHITECTURE.md + docs.pdf — /document."""
        return CommandResult(handled=True, action="run_document", message="Documentation generation (Phase 7)")

    async def cmd_undo(args: str) -> CommandResult:
        """Revert last agent-made change via git — /undo."""
        return CommandResult(handled=True, action="run_undo", message="Undo (Phase 8)")

    # Register all handlers
    dispatcher.register("debug", cmd_debug)
    dispatcher.register("clear", cmd_clear)
    dispatcher.register("exit", cmd_exit)
    dispatcher.register("help", cmd_help)
    dispatcher.register("new", cmd_new)
    dispatcher.register("model", cmd_model)
    dispatcher.register("history", cmd_history)
    dispatcher.register("config", cmd_config)
    dispatcher.register("usage", cmd_usage)
    dispatcher.register("trust", cmd_trust)
    dispatcher.register("open", cmd_open)
    dispatcher.register("test", cmd_test)
    dispatcher.register("document", cmd_document)
    dispatcher.register("undo", cmd_undo)
