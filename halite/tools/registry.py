"""
Tool registry — central map of tool name → tool instance (§6.4).
Nothing else references tools directly; everything goes through the registry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from halite.tools.base import BaseTool, ToolExecutor


class ToolRegistry:
    """Registry that wires all tools into the ToolExecutor at init."""

    def __init__(self, executor: "ToolExecutor") -> None:
        self.executor = executor
        self._register_all()

    def _register_all(self) -> None:
        """Register all MVP tools (§6.4)."""
        from halite.tools.file_tool import FileTool
        from halite.tools.terminal_tool import TerminalTool
        from halite.tools.browser_tool import BrowserTool

        self.executor.register(FileTool())
        self.executor.register(TerminalTool())
        self.executor.register(BrowserTool())
