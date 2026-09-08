"""
Base tool ABC + ToolExecutor choke point (§6.4).
All tool execution goes through ToolExecutor so sandboxing,
logging, and confirmation prompts apply uniformly.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from halite.models.schemas import ToolCall, ToolResult, FileToolArgs, TerminalToolArgs, BrowserToolArgs
from halite.utils.logging_config import logger


class BaseTool(ABC):
    """Abstract base class for all tools the agent can invoke (§6.4)."""

    name: str = "base"

    @abstractmethod
    async def execute(self, args: dict[str, Any], project_root: Path | None = None) -> ToolResult:
        """Execute the tool with validated arguments. Returns a ToolResult."""
        ...

    def validate_args(self, args: dict[str, Any]) -> bool:
        """Validate arguments against the tool's schema. Override in subclasses."""
        return True


class ToolExecutor:
    """
    Central choke point for all tool execution (§6.4).
    Handles validation, logging, per-file locking, and error wrapping (§10).
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root
        self._tools: dict[str, BaseTool] = {}
        self._file_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Called during app init."""
        self._tools[tool.name] = tool
        logger.debug("Tool registered: {}", tool.name)

    def _get_file_lock(self, file_path: str) -> asyncio.Lock:
        """Get or create a per-file lock (§6.4 — serialize same-file calls)."""
        if file_path not in self._file_locks:
            self._file_locks[file_path] = asyncio.Lock()
        return self._file_locks[file_path]

    async def run(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool call with full error handling (§10).
        1. Lookup tool in registry
        2. Validate arguments
        3. Acquire per-file lock if file operation
        4. Execute with try/except
        5. Return typed ToolResult (never raise)
        """
        logger.info(
            "Tool execution: tool={}, call_id={}, args_preview={}",
            tool_call.tool_name,
            str(tool_call.id)[:8],
            str(tool_call.arguments)[:200],
        )

        # Step 1: Registry lookup
        tool = self._tools.get(tool_call.tool_name)
        if tool is None:
            logger.warning("Unknown tool requested: {}", tool_call.tool_name)
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=f"Unknown tool: {tool_call.tool_name}",
            )

        # Step 2: Validate args
        if not tool.validate_args(tool_call.arguments):
            logger.warning(
                "Invalid arguments for tool {}: {}",
                tool_call.tool_name,
                tool_call.arguments,
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=f"Invalid arguments for {tool_call.tool_name}",
            )

        # Step 3: Per-file lock for file operations
        file_path = tool_call.arguments.get("path", "")
        file_lock = self._get_file_lock(file_path) if file_path else None

        # Step 4: Execute with error handling (§10 module-boundary wrapping)
        try:
            # Inject the tool-call ID into args so tools can build ToolResult properly
            exec_args = dict(tool_call.arguments)
            exec_args["_call_id"] = tool_call.id

            if file_lock:
                async with file_lock:
                    result = await tool.execute(exec_args, self.project_root)
            else:
                result = await tool.execute(exec_args, self.project_root)

            logger.info(
                "Tool success: tool={}, call_id={}, output_len={}",
                tool_call.tool_name,
                str(tool_call.id)[:8],
                len(result.output),
            )
            return result

        except Exception as exc:
            logger.exception(
                "Tool execution failed: tool={}, call_id={}, error={}",
                tool_call.tool_name,
                str(tool_call.id)[:8],
                str(exc),
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=f"Tool error: {exc}",
            )

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
