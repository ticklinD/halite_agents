"""
Diff view widget — shows diffs before file writes (§6.4, §6.2).
Displays unified diffs with syntax-highlighted additions/deletions.
"""
from __future__ import annotations

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static, RichLog


class DiffView(Static):
    """Shows a unified diff between old and new file content."""

    DEFAULT_CSS = """
    DiffView {
        dock: bottom;
        height: 15;
        background: $surface;
        border-top: solid $accent;
        display: none;
    }
    DiffView.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._log: RichLog | None = None

    def compose(self) -> ComposeResult:
        self._log = RichLog(highlight=True, markup=True, wrap=True)
        yield self._log

    def show_diff(self, filepath: str, old_content: str, new_content: str) -> None:
        """Show a unified diff for the given file."""
        if self._log is None:
            return
        self._log.clear()

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        import difflib
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"old/{filepath}",
            tofile=f"new/{filepath}",
            lineterm="",
        ))

        if not diff:
            self._log.write("  (no changes)")
        else:
            for line in diff:
                if line.startswith("+++") or line.startswith("---"):
                    self._log.write(Text(line, style="bold"))
                elif line.startswith("+"):
                    self._log.write(Text(line, style="green"))
                elif line.startswith("-"):
                    self._log.write(Text(line, style="red"))
                elif line.startswith("@@"):
                    self._log.write(Text(line, style="cyan"))
                else:
                    self._log.write(line.rstrip())

        self.visible = True

    def show_new_file(self, filepath: str, content: str) -> None:
        """Show a new file being created."""
        if self._log is None:
            return
        self._log.clear()
        self._log.write(Text(f"  New file: {filepath}", style="bold green"))
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            self._log.write(Text(f"+ {i:4d} | {line}", style="green"))
        self.visible = True

    def clear_and_hide(self) -> None:
        """Clear the diff view and hide it."""
        if self._log:
            self._log.clear()
        self.visible = False
