# Halite — Hybrid TUI Coding Agent

Local-first, terminal-based coding agent harness. Hybrid local/cloud LLM routing,
agentic coding workflow, schema-validated tool calling, and persistent chat history.

## Requirement

- Python 3.11+
- [Ollama](https://ollama.com) (for local inference) — optional but recommended
- An Anthropic API key (for cloud inference) — optional

## Install

```bash
pip install -e .
```

## Run

```bash
halite            # start the TUI
halite --debug    # start with debug logging enabled
```

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

See `PRD.md` in this repository for the full specification.
