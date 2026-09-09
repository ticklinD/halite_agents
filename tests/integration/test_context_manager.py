"""Tests for ContextManager wiring (Phase 2, item 6).

Verifies that:
- A small context window triggers summarization in _handle_chat_message
- The summarized (compacted) messages are what gets sent to the model
- A large context window passes messages through untouched
"""
import subprocess
import json
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
ROOT_TOKEN = "@@ROOT@@"


def _run_helper(script: str, timeout: float = 25.0) -> dict | None:
    script = script.replace(ROOT_TOKEN, str(PROJECT_ROOT))
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
# TEST 1: small window triggers compaction
# ═══════════════════════════════════════════════════════════════════

def test_small_window_triggers_compaction():
    """With a small context window, many turns get compacted."""
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.backend import HaliteBackend

async def main():
    backend = HaliteBackend()
    # Force a tiny window so any long history triggers summarization
    backend.context_manager.set_context_window(512)
    # Skip classification — go straight to message building
    backend._current_task_backend = "local"

    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    # Stub the model call to capture what messages it would receive
    captured = {}
    async def fake_route(messages):
        captured["messages"] = messages
        # Emulate a response so the loop terminates
        await backend._send({"type": "assistant_message", "text": "ok"})
    backend._route_and_respond = fake_route

    # Seed history with several long turns
    for i in range(10):
        backend._persist_message("user", f"turn {i} " + "x" * 300)
        backend._persist_message("assistant", f"response {i} " + "y" * 300)

    # Now send a message - should trigger compaction
    await backend._handle_chat_message("continue please")

    # The route got messages
    messages = captured.get("messages", [])
    print(json.dumps({
        "got_messages": len(messages) > 0,
        "message_count": len(messages),
        "has_system_compaction": any(
            m.get("role") == "system" and "compacted" in m.get("content", "")
            for m in messages
        ),
        "has_notice": any(
            m.get("type") == "system_message"
            and "compacted" in m.get("text", "")
            for m in sent
        ),
    }), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script)
    assert result is not None
    assert result["got_messages"] is True
    assert result["has_system_compaction"] is True
    assert result["has_notice"] is True
    print("  ✓ small window triggers compaction + notice")
    print(f"    message_count after compaction: {result['message_count']}")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: large window passes everything through
# ═══════════════════════════════════════════════════════════════════

def test_large_window_no_compaction():
    """With a large window, history passes through untouched."""
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.backend import HaliteBackend

async def main():
    backend = HaliteBackend()
    backend.context_manager.set_context_window(1_000_000)
    # Skip classification — go straight to message building
    backend._current_task_backend = "local"

    sent = []
    async def fake_send(msg):
        sent.append(msg)
    backend._send = fake_send

    captured = {}
    async def fake_route(messages):
        captured["messages"] = messages
        await backend._send({"type": "assistant_message", "text": "ok"})
    backend._route_and_respond = fake_route

    for i in range(10):
        backend._persist_message("user", f"turn {i} " + "x" * 300)
        backend._persist_message("assistant", f"response {i} " + "y" * 300)

    await backend._handle_chat_message("continue please")

    messages = captured.get("messages", [])
    print(json.dumps({
        "got_messages": len(messages) > 0,
        "message_count": len(messages),
        "no_system_compaction": not any(
            m.get("role") == "system" and "compacted" in m.get("content", "")
            for m in messages
        ),
    }), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script)
    assert result is not None
    assert result["got_messages"] is True
    assert result["no_system_compaction"] is True
    print("  ✓ large window passes history through untouched")

    # 20 messages should be there (10 user + 10 assistant)
    assert result["message_count"] == 20, f"expected 20, got {result['message_count']}"
    print(f"    message_count: {result['message_count']} (all 20 preserved)")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: context manager unit behavior
# ═══════════════════════════════════════════════════════════════════

def test_context_manager_unit():
    """ContextManager itself: threshold → summarize keeps recent turns."""
    script = '''
import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.core.context_manager import ContextManager

cm = ContextManager(context_window=100)
for i in range(10):
    cm.add_message("user", f"message number {i} with some words to count")
    cm.add_message("assistant", f"reply number {i} with more words here")

needs = cm.needs_summarization()
result = cm.summarize_old_turns(recent_keep=4)
print(json.dumps({
    "needs_summarization": needs,
    "summarized": result["summarized"],
    "message_count": len(result["messages"]),
    "has_compaction_marker": any(
        m.get("role") == "system" and "compacted" in m.get("content", "")
        for m in result["messages"]
    ),
}), flush=True)
'''
    result = _run_helper(script)
    assert result is not None
    assert result["needs_summarization"] is True
    assert result["summarized"] is True
    # 1 system marker + 4 recent turns = 5 messages
    assert result["message_count"] == 5
    assert result["has_compaction_marker"] is True
    print("  ✓ ContextManager: 10 turns → 1 marker + 4 kept = 5 messages")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])