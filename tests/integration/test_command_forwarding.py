"""Tests for command action forwarding + /model (Phase 2, item 4)."""
import json
import subprocess
import sys
import os
import time
import select
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _run_helper(script: str, timeout: float = 20.0) -> dict | None:
    """Run a Python helper script and capture its JSON output."""
    proc = subprocess.Popen(
        [PYTHON, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        output = stdout.decode("utf-8", errors="replace").strip()
        if stderr:
            err = stderr.decode("utf-8", errors="replace")
            if err.strip():
                print(f"  [stderr] {err[:200]}")
        if output:
            return json.loads(output)
        return None
    except subprocess.TimeoutExpired:
        proc.kill()
        return None


# ═══════════════════════════════════════════════════════════════════
# TEST 1: /model queries Ollama live and returns real list
# ═══════════════════════════════════════════════════════════════════

def test_model_command_lists_real_models():
    """The /model command should query Ollama list_models() live."""
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers

async def main():
    backend = HaliteBackend()
    dispatcher = CommandDispatcher()
    register_handlers(dispatcher, backend)

    # Dispatch /model
    result = await dispatcher.dispatch("/model")

    print(json.dumps({{
        "handled": result.handled,
        "action": result.action,
        "message": result.message,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["handled"] is True
    assert result["action"] == "show_models"
    assert "Available models" in result["message"]
    # At minimum the API section should be present
    assert "API" in result["message"]
    # Local section should exist (may be empty list if no Ollama models)
    assert "Local" in result["message"]
    print("  ✓ /model returns real model list with sections")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: command_action is forwarded over IPC
# ═══════════════════════════════════════════════════════════════════

def test_command_action_forwarded():
    """Verify the backend sends command_action messages over IPC."""
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers

async def main():
    backend = HaliteBackend()
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    # Simulate user typing /model
    await backend._handle_user_input("/model")

    # Check sent messages for command_action
    actions = [m for m in sent if m.get("type") == "command_action"]
    print(json.dumps({{
        "has_command_action": len(actions) > 0,
        "action": actions[0]["action"] if actions else None,
        "has_message": bool(actions and actions[0].get("message")),
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["has_command_action"] is True
    assert result["action"] == "show_models"
    assert result["has_message"] is True
    print("  ✓ command_action forwarded with action + message")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Normal messages don't send command_action
# ═══════════════════════════════════════════════════════════════════

def test_normal_message_no_command_action():
    """A non-command message should NOT produce a command_action."""
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend

async def main():
    backend = HaliteBackend()
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send
    async def noop_chat(text):
        pass
    backend._handle_chat_message = noop_chat

    # This isn't a command, so no command_action
    await backend._handle_user_input("hello there")

    actions = [m for m in sent if m.get("type") == "command_action"]
    print(json.dumps({{
        "has_command_action": len(actions) > 0,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["has_command_action"] is False
    print("  ✓ non-command input produces no command_action")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])