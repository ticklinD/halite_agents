"""
Slash command dispatcher (§4, §9).
Parses /commands from chat input and routes to the appropriate handler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from halite.utils.logging_config import logger


@dataclass
class CommandResult:
    """Result of a slash command execution."""
    handled: bool
    message: str = ""
    action: str | None = None  # optional action hint for the UI (e.g. "navigate", "clear", "quit")


# Type alias for command handlers
CommandHandler = Callable[..., Coroutine[Any, Any, CommandResult]]


class CommandDispatcher:
    """
    Parses /commands and routes to registered handlers.
    Commands are registered as (name -> handler) pairs.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self._command_pattern = re.compile(r"^/(\w+)(?:\s+(.*))?$", re.DOTALL)

    def register(self, name: str, handler: CommandHandler) -> None:
        """Register a command handler."""
        self._handlers[name] = handler
        logger.debug("Command registered: /{}", name)

    def parse(self, text: str) -> tuple[str, str] | None:
        """
        Parse a /command from user input.
        Returns (command_name, args_string) or None if not a command.
        """
        text = text.strip()
        if not text.startswith("/"):
            return None

        match = self._command_pattern.match(text)
        if match is None:
            return None

        cmd_name = match.group(1).lower()
        args = match.group(2) or ""
        return cmd_name, args.strip()

    async def dispatch(self, text: str) -> CommandResult:
        """
        Parse and dispatch a command. Returns CommandResult.
        If not a command or not registered, returns CommandResult(handled=False).
        """
        parsed = self.parse(text)
        if parsed is None:
            return CommandResult(handled=False)

        cmd_name, args = parsed
        handler = self._handlers.get(cmd_name)

        if handler is None:
            logger.debug("Unknown command: /{}", cmd_name)
            return CommandResult(
                handled=True,
                message=f"Unknown command: /{cmd_name}. Type /help for available commands.",
            )

        logger.info("Dispatching command: /{} args='{}'", cmd_name, args[:100])
        try:
            result = await handler(args)
            return result
        except Exception as exc:
            logger.exception("Command /{} failed: {}", cmd_name, str(exc))
            return CommandResult(
                handled=True,
                message=f"Command /{cmd_name} failed: {exc}",
            )

    def list_commands(self) -> list[str]:
        """Return all registered command names."""
        return sorted(self._handlers.keys())
