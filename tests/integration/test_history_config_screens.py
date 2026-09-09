"""Integration tests for Phase 3 item 1: /history + /config screens.

Covers the backend IPC that drives the Ink HistoryScreen and ConfigScreen:
- cmd_history sends history_data with session entries (message count + preview)
- cmd_config sends config_data with typed fields
- resume_session switches current session and sends resume_ok with messages
- config_update applies + persists and live-updates the backend
- config_update with unknown keys warns and skips
"""
import json
import subprocess
import sys
import os
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
                print(f"  [stderr] {err[:300]}")
        if output:
            return json.loads(output)
        return None
    except subprocess.TimeoutExpired:
        proc.kill()
        return None


# ═══════════════════════════════════════════════════════════════════
# TEST 1: /history sends history_data with sessions
# ═══════════════════════════════════════════════════════════════════

def test_history_sends_history_data():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers
from halite.models.schemas import Session, Message
from uuid import uuid4

async def main():
    backend = HaliteBackend()
    dispatcher = CommandDispatcher()
    register_handlers(dispatcher, backend)
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    # Seed a session with messages directly in the store
    session = Session(id=uuid4(), project_path="/tmp/demo", active_model="qwen3.5:0.8b", backend="local_ollama")
    backend.history.create_session(session)
    backend.history.add_message(Message(
        id=uuid4(), session_id=session.id, role="user",
        content="hello world this is a test message",
        model_used="qwen3.5:0.8b", tokens=10,
    ))
    backend.history.add_message(Message(
        id=uuid4(), session_id=session.id, role="assistant",
        content="hi there", model_used="qwen3.5:0.8b", tokens=5,
    ))

    result = await dispatcher.dispatch("/history")

    history = [m for m in sent if m["type"] == "history_data"]
    print(json.dumps({{
        "handled": result.handled,
        "action": result.action,
        "has_history_data": len(history) > 0,
        "sessions": history[0]["sessions"] if history else [],
        "message": result.message,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["handled"] is True
    assert result["action"] == "show_history"
    assert result["has_history_data"] is True
    assert len(result["sessions"]) >= 1
    # The seeded session should be the most recent (first)
    s = result["sessions"][0]
    assert s["message_count"] == 2
    assert s["preview"] == "hello world this is a test message"
    assert s["active_model"] == "qwen3.5:0.8b"
    print("  ✓ /history sends history_data with count + preview")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: /config sends config_data with all fields
# ═══════════════════════════════════════════════════════════════════

def test_config_sends_config_data():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers
from halite.models.schemas import AppConfig

async def main():
    backend = HaliteBackend()
    dispatcher = CommandDispatcher()
    register_handlers(dispatcher, backend)
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    result = await dispatcher.dispatch("/config")

    cfg = [m for m in sent if m["type"] == "config_data"]
    fields = cfg[0]["fields"] if cfg else []
    keys = {{f["key"]: f for f in fields}}
    # Every AppConfig field should be present
    missing = [name for name in AppConfig.model_fields if name not in keys]
    print(json.dumps({{
        "handled": result.handled,
        "action": result.action,
        "has_config_data": len(cfg) > 0,
        "field_count": len(fields),
        "missing": missing,
        "default_backend_type": keys.get("default_backend", {{}}).get("type"),
        "default_backend_options": keys.get("default_backend", {{}}).get("options"),
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["handled"] is True
    assert result["action"] == "show_config"
    assert result["has_config_data"] is True
    assert result["missing"] == [], f"config_data missing fields: {result['missing']}"
    assert result["default_backend_type"] == "select"
    assert result["default_backend_options"] == ["local_ollama", "local_llamacpp", "api"]
    print("  ✓ /config sends config_data with all AppConfig fields")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: resume_session loads messages + switches current session
# ═══════════════════════════════════════════════════════════════════

def test_resume_session_loads_messages():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.models.schemas import Session, Message
from uuid import uuid4

async def main():
    backend = HaliteBackend()
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    # Create a session with messages
    session = Session(id=uuid4(), project_path="/tmp/demo", active_model="qwen3.5:0.8b", backend="local_ollama")
    backend.history.create_session(session)
    backend.history.add_message(Message(
        id=uuid4(), session_id=session.id, role="user",
        content="how do I sort a list", model_used="qwen3.5:0.8b", tokens=10,
    ))
    backend.history.add_message(Message(
        id=uuid4(), session_id=session.id, role="assistant",
        content="use sorted()", model_used="qwen3.5:0.8b", tokens=5,
    ))

    # Different current session
    backend.new_session()

    await backend._handle_message({{
        "type": "resume_session",
        "session_id": str(session.id),
    }})

    resume = [m for m in sent if m["type"] == "resume_ok"]
    print(json.dumps({{
        "got_resume_ok": len(resume) > 0,
        "session_id": resume[0]["session_id"] if resume else None,
        "messages": resume[0]["messages"] if resume else [],
        "current_session_is_target": str(backend.current_session.id) == str(session.id),
        "stickiness_reset": backend._current_task_backend is None,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["got_resume_ok"] is True
    assert result["session_id"] is not None
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][0]["content"] == "how do I sort a list"
    assert result["current_session_is_target"] is True
    assert result["stickiness_reset"] is True
    print("  ✓ resume_session loads messages + switches session")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: resume_session handles invalid ids gracefully
# ═══════════════════════════════════════════════════════════════════

def test_resume_invalid_id_graceful():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from uuid import uuid4

async def main():
    backend = HaliteBackend()
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    # Invalid UUID
    await backend._handle_message({{
        "type": "resume_session",
        "session_id": "not-a-uuid",
    }})
    # Unknown but valid UUID
    await backend._handle_message({{
        "type": "resume_session",
        "session_id": str(uuid4()),
    }})

    sys_msgs = [m for m in sent if m["type"] == "system_message"]
    has_invalid = any("Invalid" in m["text"] for m in sys_msgs)
    has_notfound = any("not found" in m["text"] for m in sys_msgs)
    resume = [m for m in sent if m["type"] == "resume_ok"]
    print(json.dumps({{
        "invalid_handled": has_invalid,
        "notfound_handled": has_notfound,
        "no_resume_ok": len(resume) == 0,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["invalid_handled"] is True
    assert result["notfound_handled"] is True
    assert result["no_resume_ok"] is True
    print("  ✓ resume invalid ids handled gracefully")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: config_update saves + live-updates backend
# ═══════════════════════════════════════════════════════════════════

def test_config_update_saves_and_live_updates():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
from halite.config.settings import load_config

async def main():
    backend = HaliteBackend()
    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    old_default = backend.config.default_backend
    new_default = "api" if old_default != "api" else "local_ollama"

    await backend._handle_message({{
        "type": "config_update",
        "updates": {{
            "default_backend": new_default,
            "max_agent_iterations": 7,
            "auto_approve_api": False,
        }},
    }})

    saved = [m for m in sent if m["type"] == "config_saved"]
    on_disk = load_config()
    print(json.dumps({{
        "got_saved": len(saved) > 0,
        "saved_message": saved[0]["message"] if saved else "",
        "old_default": old_default,
        "new_default": new_default,
        "live_default": backend.config.default_backend,
        "live_iterations": backend.config.max_agent_iterations,
        "disk_default": on_disk.default_backend,
        "disk_iterations": on_disk.max_agent_iterations,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["got_saved"] is True
    assert result["live_default"] == result["new_default"]
    assert result["old_default"] != result["new_default"]
    assert result["live_iterations"] == 7
    assert result["disk_default"] == result["live_default"]
    assert result["disk_iterations"] == 7
    print("  ✓ config_update saves + live-updates")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: config_update unknown key skipped
# ═══════════════════════════════════════════════════════════════════

def test_config_update_unknown_key_skipped():
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

    await backend._handle_message({{
        "type": "config_update",
        "updates": {{"totally_unknown_key": "x"}},
    }})

    saved = [m for m in sent if m["type"] == "config_saved"]
    print(json.dumps({{
        "got_saved": len(saved) > 0,
        "message": saved[0]["message"] if saved else "",
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["got_saved"] is True
    assert "totally_unknown" not in result["message"]
    print("  ✓ config_update unknown key skipped")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])