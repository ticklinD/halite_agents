"""
Entry point for the Halite application.

The TUI is an Ink (Node.js) frontend that spawns this Python backend via
JSON-over-stdio. Running `python -m halite` directly launches the backend
in headless mode (for testing / IPC); use `node halite/ui/ink/dist/index.js`
(or ./scripts/run.sh) for the full interactive TUI.

Note: `scripts/run.sh` is the recommended way to launch Halite, since the
Ink frontend must own the terminal (a TTY). The console script `halite`
below runs the same backend entry point.
"""
import asyncio
import sys

from halite.backend import main as backend_main


def run_cli() -> None:
    """Synchronous console-script entry point (runs the backend loop)."""
    asyncio.run(backend_main())


if __name__ == "__main__":
    sys.exit(run_cli())