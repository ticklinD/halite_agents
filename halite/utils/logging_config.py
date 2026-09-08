"""
Structured logging & observability (§10).
- loguru structured logging with rotating daily files.
- Correlation IDs on every log line (session_id + turn_id).
- Global exception hook → crash dump + terminal restore.
- Module-boundary try/except helper.
"""
from __future__ import annotations

import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger as _raw_logger

# ── Log directory ────────────────────────────────────────────────────────────

LOG_DIR = Path.home() / ".halite" / "logs"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Module-level correlation context ────────────────────────────────────────

_correlation_context: dict[str, str] = {}


def set_correlation_context(session_id: str | None = None, turn_id: str | None = None) -> None:
    """Set the active correlation IDs for all subsequent log calls in this context."""
    if session_id is not None:
        _correlation_context["session_id"] = session_id
    if turn_id is not None:
        _correlation_context["turn_id"] = turn_id


def clear_correlation_context() -> None:
    _correlation_context.clear()


# ── Custom formatter ────────────────────────────────────────────────────────

def _correlation_filter(record: dict) -> bool:
    """Inject correlation IDs into every log record."""
    record["extra"]["session_id"] = _correlation_context.get("session_id", "-")
    record["extra"]["turn_id"] = _correlation_context.get("turn_id", "-")
    return True


# ── Logger setup ────────────────────────────────────────────────────────────

_configured = False


def setup_logging(debug: bool = False) -> None:
    """
    Configure loguru for the application.
    Call once at startup. Safe to call multiple times (idempotent).
    """
    global _configured
    if _configured:
        return
    _configured = True

    _ensure_log_dir()

    # Remove default stderr handler
    _raw_logger.remove()

    # Console handler: short messages, always visible
    console_level = "DEBUG" if debug else "INFO"
    _raw_logger.add(
        sys.stderr,
        level=console_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[session_id]}</cyan>:<cyan>{extra[turn_id]}</cyan> | "
            "<level>{message}</level>"
        ),
        filter=_correlation_filter,
        colorize=True,
    )

    # Rotating daily log file: full details, retained for configured days
    today = datetime.now().strftime("%Y-%m-%d")
    _raw_logger.add(
        str(LOG_DIR / f"halite_{today}.log"),
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[session_id]}:{extra[turn_id]} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        filter=_correlation_filter,
        rotation="00:00",       # new file at midnight
        retention="7 days",     # §10: retained 7 days
        compression="gz",
        enqueue=True,           # thread-safe
    )

    # Debug panel log file (only when --debug)
    if debug:
        _raw_logger.add(
            str(LOG_DIR / f"halite_debug_{today}.log"),
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            filter=_correlation_filter,
            rotation="00:00",
            retention="3 days",
            enqueue=True,
        )

    _raw_logger.info("Logging initialised — debug={}, log_dir={}", debug, LOG_DIR)


# ── Expose a clean logger alias ─────────────────────────────────────────────

logger = _raw_logger


# ── Global exception hook (§10) ─────────────────────────────────────────────

_original_excepthook: Callable | None = None


def _halite_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Any,
) -> None:
    """Catch truly uncaught errors: write crash dump, restore terminal, exit."""
    # Restore terminal to cooked mode
    if sys.stdin and sys.stdin.isatty():
        try:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, termios.tcgetattr(sys.stdin.fileno()))
        except Exception:
            pass

    # Write crash dump
    _ensure_log_dir()
    crash_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    crash_file = LOG_DIR / f"crash_{crash_ts}.log"

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    crash_info = (
        f"=== HALITE CRASH DUMP ===\n"
        f"Timestamp : {datetime.now().isoformat()}\n"
        f"Python    : {sys.version}\n"
        f"Platform  : {platform.platform()}\n"
        f"Machine   : {platform.machine()}\n"
        f"Exception : {exc_type.__name__}: {exc_value}\n"
        f"\nTraceback:\n{tb_str}\n"
    )

    crash_file.write_text(crash_info, encoding="utf-8")

    # Also log via loguru if possible
    try:
        _raw_logger.critical(
            "UNCAUGHT EXCEPTION — crash dump written to {} — {}",
            crash_file, str(exc_value),
        )
    except Exception:
        pass

    # Call original hook if it exists
    if _original_excepthook is not None:
        _original_excepthook(exc_type, exc_value, exc_traceback)


def install_exception_hook() -> None:
    """Install the global crash-recovery exception hook (§10)."""
    global _original_excepthook
    _original_excepthook = sys.excepthook
    sys.excepthook = _halite_excepthook
    logger.debug("Global exception hook installed")


# ── Module-boundary try/except helper (§10) ─────────────────────────────────

def wrap_module_call(
    func: Callable,
    *args: Any,
    module_name: str = "unknown",
    **kwargs: Any,
) -> tuple[Any, Exception | None]:
    """
    Execute a function with module-boundary exception handling (§10).
    Returns (result, None) on success, (None, exception) on failure.
    The exception is logged with full context (inputs, stack trace).
    """
    try:
        result = func(*args, **kwargs)
        return result, None
    except Exception as exc:
        logger.exception(
            "Module boundary error in {} — inputs: args={}, kwargs={}",
            module_name,
            str(args)[:500],
            str({k: str(v)[:200] for k, v in kwargs.items()}),
        )
        return None, exc
