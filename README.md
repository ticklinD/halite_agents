# Halite — Hybrid TUI Coding Agent

Local-first, terminal-based coding agent harness. Hybrid local/cloud LLM routing,
agentic coding workflow, schema-validated tool calling, and persistent chat history.

The interactive TUI is built with **[Ink](https://github.com/vadimdemedes/ink)**
(React/Node.js) and renders **inline in your terminal** — it does not take over
the screen like a full-screen TUI. A Python backend (in `halite/backend.py`)
handles all agent logic and communicates with the frontend over JSON stdio.

## Requirement

- Python 3.11+
- Node.js 16+ and npm (for the Ink frontend)
- [Ollama](https://ollama.com) (for local inference) — optional but recommended
- An Anthropic API key (for cloud inference) — optional

## Install

Python dependencies:

```bash
pip install -e .
```

Ink frontend dependencies (Node.js):

```bash
cd halite/ui/ink
npm install
npm run build      # compiles TypeScript to dist/
cd ../..
```

## Run

```bash
./scripts/run.sh            # start the TUI (Node frontend + Python backend)
./scripts/run.sh --debug    # start with debug logging enabled
```

On Windows (PowerShell):

```powershell
.\scripts\run.ps1           # creates .venv if needed, builds Ink, starts the TUI
```

The TUI renders inline (like normal command output) — scrollable chat, a
spinning "Generating…" indicator while the model works, and a status bar with
the active model. Press Enter to send, Ctrl+C to quit.

## Slash Commands

| Command | Description |
|---|---|
| `/model` | Switch active model/backend |
| `/history` | Browse and resume past sessions |
| `/test <path>` | Generate + run tests |
| `/document` | Generate ARCHITECTURE.md + docs.pdf |
| `/open <path>` | Set the active project folder |
| `/new` | Start a new session |
| `/config` | Open settings |
| `/usage` | Show token/cost usage |
| `/undo` | Revert last agent-made change |
| `/trust manual\|auto` | Set confirmation behaviour |
| `/debug` | Toggle live log panel |
| `/clear` | Clear visible chat |
| `/exit` | Quit |

## Configuration

Config lives at `~/.halite/config.toml`. Logs at `~/.halite/logs/`.
API keys stored in the OS keychain (via `keyring`), with an encrypted-file fallback.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- `halite/ui/ink/` — Ink (React) frontend, renders inline. Node.js is the
  parent process and owns the terminal; it spawns the Python backend.
- `halite/backend.py` — Python agent backend (no terminal). JSON-over-stdio IPC.
- `halite/models/` — Ollama (local) and Anthropic (cloud) inference providers.
- `halite/tools/` — schema-validated agent tools (files, terminal, browser, …).

See `PRD.md` in this repository for the full specification.
