"""
FileTool — read/write/delete/list files with sandboxing and diff generation (§6.4).
Any path resolving outside the project root is rejected unless whitelisted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Awaitable

from halite.models.schemas import ToolResult, FileToolArgs
from halite.tools.base import BaseTool
from halite.utils.logging_config import logger


# Optional callback for confirmation prompts — set by the app
_DIFF_CALLBACK: Callable[[Path, str, str], Awaitable[bool]] | None = None


def set_diff_callback(cb: Callable[[Path, str, str], Awaitable[bool]]) -> None:
    """Set a callback for diff-preview confirmations (§6.4)."""
    global _DIFF_CALLBACK
    _DIFF_CALLBACK = cb


class FileTool(BaseTool):
    """Sandboxed file operations tool."""

    name = "file"

    def __init__(self) -> None:
        self._whitelisted: list[Path] = []

    def whitelist(self, path: str | Path) -> None:
        """Explicitly whitelist a path for this session (§6.4)."""
        p = Path(path).expanduser().resolve()
        if p not in self._whitelisted:
            self._whitelisted.append(p)
            logger.info("FileTool whitelisted path: {}", p)

    def _resolve(self, raw_path: str, project_root: Path | None) -> Path:
        """Resolve a path and enforce the sandbox (must be within project root or whitelisted)."""
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            if project_root is None:
                p = (Path.cwd() / p).resolve()
            else:
                p = (project_root / p).resolve()
        else:
            p = p.resolve()

        # Sandbox check
        if project_root is not None:
            root = project_root.resolve()
            if p == root or root in p.parents:
                return p
            # Check whitelist
            for wl in self._whitelisted:
                if p == wl or wl in p.parents or p in wl.parents:
                    return p
            logger.warning("Path '{}' is outside project root and not whitelisted", p)
            raise PermissionError(f"Path outside project root: {p}")

        return p

    def validate_args(self, args: dict[str, Any]) -> bool:
        try:
            FileToolArgs(**args)
            return True
        except Exception:
            return False

    async def execute(self, args: dict[str, Any], project_root: Path | None = None) -> ToolResult:
        operation = args.get("operation")
        try:
            if operation == "read":
                return await self._read(args, project_root)
            elif operation == "write":
                return await self._write(args, project_root)
            elif operation == "delete":
                return await self._delete(args, project_root)
            elif operation == "list":
                return await self._list(args, project_root)
            elif operation == "diff":
                return await self._diff(args, project_root)
            else:
                return ToolResult(
                    tool_call_id=args.get("_call_id", ""),
                    success=False, output="", error=f"Unknown op: {operation}",
                )
        except Exception as exc:
            logger.exception("FileTool {} failed: {}", operation, str(exc))
            return ToolResult(
                tool_call_id=args.get("_call_id", ""),
                success=False, output="",
                error=str(exc),
            )

    async def _read(self, args: dict[str, Any], project_root: Path | None) -> ToolResult:
        path = self._resolve(args["path"], project_root)
        content = path.read_text(encoding="utf-8")
        return ToolResult(
            tool_call_id=args.get("_call_id", ""),
            success=True,
            output=f"--- {path} ---\n{content}",
        )

    async def _write(self, args: dict[str, Any], project_root: Path | None) -> ToolResult:
        path = self._resolve(args["path"], project_root)
        content = args.get("content") or ""

        # Diff-preview before overwrite (§6.4)
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if old != content:
                if _DIFF_CALLBACK is not None:
                    ok = await _DIFF_CALLBACK(path, old, content)
                    if not ok:
                        logger.info("Write to {} rejected by user confirmation", path)
                        return ToolResult(
                            tool_call_id=args.get("_call_id", ""),
                            success=False, output="",
                            error="Write cancelled by user confirmation",
                        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        result = f"Wrote {len(content)} bytes to {path}"
        if not path.exists():
            result += " (new file)"
        logger.info(result)
        return ToolResult(
            tool_call_id=args.get("_call_id", ""),
            success=True, output=result,
            artifacts=[str(path)],
        )

    async def _delete(self, args: dict[str, Any], project_root: Path | None) -> ToolResult:
        path = self._resolve(args["path"], project_root)
        if not path.exists():
            return ToolResult(
                tool_call_id=args.get("_call_id", ""),
                success=False, output="", error=f"Not found: {path}",
            )
        path.unlink()
        logger.info("Deleted file: {}", path)
        return ToolResult(
            tool_call_id=args.get("_call_id", ""),
            success=True, output=f"Deleted: {path}",
        )

    async def _list(self, args: dict[str, Any], project_root: Path | None) -> ToolResult:
        path = self._resolve(args["path"], project_root)
        if not path.exists():
            return ToolResult(
                tool_call_id=args.get("_call_id", ""),
                success=False, output="", error=f"Not found: {path}",
            )

        recursive = args.get("recursive", False)
        if path.is_file():
            return ToolResult(
                tool_call_id=args.get("_call_id", ""),
                success=True, output=f"- {path}",
            )

        # Skip common ignore dirs (respect .gitignore-like patterns)
        ignore = {"node_modules", ".git", "venv", ".venv", "__pycache__", "dist", "build", ".cache"}

        if recursive:
            entries = []
            for p in path.rglob("*"):
                if any(seg in ignore for seg in p.parts):
                    continue
                entries.append(p)
        else:
            entries = sorted(
                [p for p in path.iterdir() if p.name not in ignore],
                key=lambda p: (p.is_file(), p.name),
            )

        lines = []
        for p in entries:
            if p.is_dir():
                lines.append(f"  [D] {p.name}/")
            else:
                size = p.stat().st_size if p.exists() else 0
                lines.append(f"  [F] {p.name} ({size} bytes)")

        return ToolResult(
            tool_call_id=args.get("_call_id", ""),
            success=True,
            output=f"--- {path} ({len(lines)} entries) ---\n" + "\n".join(lines),
        )

    async def _diff(self, args: dict[str, Any], project_root: Path | None) -> ToolResult:
        """Generate a diff of a file vs its on-disk version (§6.4)."""
        path = self._resolve(args["path"], project_root)
        if not path.exists():
            return ToolResult(
                tool_call_id=args.get("_call_id", ""),
                success=False, output="", error=f"Not found: {path}",
            )

        content = args.get("content") or path.read_text(encoding="utf-8")
        old = path.read_text(encoding="utf-8")

        import difflib
        diff_lines = list(difflib.unified_diff(
            old.splitlines(), content.splitlines(),
            fromfile=f"old/{path.name}", tofile=f"new/{path.name}", lineterm="",
        ))

        return ToolResult(
            tool_call_id=args.get("_call_id", ""),
            success=True,
            output="\n".join(diff_lines) if diff_lines else "(no changes)",
        )
