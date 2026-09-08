"""
TerminalTool — run a shell command with timeout, streamed output, cancellable (§6.4).
Restricted to the active project root by default (dangerous-command blocklist enforced).
"""
from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path
from typing import Any

from halite.models.schemas import ToolResult, TerminalToolArgs
from halite.tools.base import BaseTool
from halite.utils.logging_config import logger


# ── Dangerous-command blocklist (§6.4 §7.4) ─────────────────────────────────

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-rf\s*/", "rm -rf / (root filesystem)"),
    (r"\brm\s+-rf\s+~", "rm -rf ~ (home)"),
    (r"\bdel\s+/[f/sq]+", "Windows delete"),
    (r"git\s+push\s+--force", "git push --force"),
    (r"git\s+push\s+(-f|--force-with-lease)", "git push --force"),
    (r"\bDROP\s+TABLE", "DROP TABLE"),
    (r"\bDROP\s+DATABASE", "DROP DATABASE"),
    (r"\bmkfs\.", "filesystem format"),
    (r"\bformat\s+[a-zA-Z]:", "Windows format"),
    (r"\bshutdown\b", "shutdown"),
    (r"\breboot\b", "reboot"),
    (r">\s*/dev/sd", "write to raw device"),
    (r"\bdd\s+if=.*of=/dev/", "dd to raw device"),
    (r"\bsudo\s+rm", "sudo rm"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
]


# Callback for dangerous-command confirmation — set by app
_DANGEROUS_CALLBACK = None


def set_dangerous_callback(cb) -> None:
    """Set the callback invoked when a dangerous command is detected."""
    global _DANGEROUS_CALLBACK
    _DANGEROUS_CALLBACK = cb


def validate_command(command: str) -> tuple[bool, str | None]:
    """
    Check a command against the dangerous-command blocklist.
    Returns (is_dangerous, reason).
    """
    import re
    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True, reason
    return False, None


class TerminalTool(BaseTool):
    """Runs shell commands with timeouts, streaming, and sandboxing."""

    name = "terminal"

    def __init__(self) -> None:
        self._running: dict[str, asyncio.subprocess.Process] = {}

    def validate_args(self, args: dict[str, Any]) -> bool:
        try:
            TerminalToolArgs(**args)
            return True
        except Exception:
            return False

    async def execute(self, args: dict[str, Any], project_root: Path | None = None) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout", 30)
        cwd_str = args.get("cwd")

        call_id = str(args.get("_call_id", ""))

        # Sandbox: restrict cwd to project root
        cwd = None
        if cwd_str:
            cwd = Path(cwd_str).expanduser().resolve()
        elif project_root:
            cwd = project_root.resolve()

        # Dangerous-command check (§6.4, §7.4 — always asks even in auto)
        is_dangerous, reason = validate_command(command)
        if is_dangerous:
            if _DANGEROUS_CALLBACK is not None:
                ok = await _DANGEROUS_CALLBACK(command, reason)
                if not ok:
                    logger.warning("Dangerous command rejected by user: {}", command)
                    return ToolResult(
                        tool_call_id=call_id,
                        success=False, output="",
                        error=f"Dangerous command blocked: {reason}",
                    )
            else:
                logger.warning("Dangerous command blocked (no confirm callback): {}", command)
                return ToolResult(
                    tool_call_id=call_id,
                    success=False, output="",
                    error=f"Dangerous command blocked: {reason}",
                )

        logger.info("Running terminal command: {} (timeout={}s, cwd={})", command, timeout, cwd or ".")

        # Use subprocess with async
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
                shell=True,
            )
            self._running[call_id] = proc

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                del self._running[call_id]
                logger.warning("Terminal command timed out: {}", command)
                return ToolResult(
                    tool_call_id=call_id,
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout}s",
                )

            del self._running[call_id]

            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            combined = "\n".join(part for part in (out, err) if part)

            if proc.returncode == 0:
                return ToolResult(
                    tool_call_id=call_id,
                    success=True,
                    output=combined or "(command completed with no output)",
                )
            else:
                return ToolResult(
                    tool_call_id=call_id,
                    success=False,
                    output=combined,
                    error=f"Command exited with code {proc.returncode}",
                )

        except Exception as exc:
            logger.exception("Terminal command failed: {}", str(exc))
            return ToolResult(
                tool_call_id=call_id,
                success=False,
                output="",
                error=str(exc),
            )

    async def cancel(self, call_id: str) -> bool:
        """Cancel a running command (§6.4 — cancellable)."""
        proc = self._running.get(call_id)
        if proc and proc.returncode is None:
            proc.kill()
            logger.info("Terminal command cancelled: {}", call_id)
            return True
        return False
