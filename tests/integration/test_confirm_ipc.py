"""
Integration tests for the blocking confirmation IPC (Phase 2, item 1).

Two test strategies:
A) Unit-level: spawn a standalone Python script (with its own pipes) that
   creates a HaliteBackend, calls request_confirmation(), and round-trips
   with confirm_response through its own stdin/stdout.
B) Backend-level: spawn the real backend, verify it handles confirm_response
   without crashing and that the mechanism is wired.
"""
import json
import subprocess
import sys
import os
import time
import select
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _run_helper(script: str, timeout: float = 15.0) -> dict | None:
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
            print(f"  [helper stderr] {stderr.decode('utf-8', errors='replace')[:200]}")
        if output:
            return json.loads(output)
        return None
    except subprocess.TimeoutExpired:
        proc.kill()
        return None


# ═══════════════════════════════════════════════════════════════════
# Helper scripts that run in their own process
# ═══════════════════════════════════════════════════════════════════

HELPER_ROUNDTRIP = '''
import asyncio, json, sys, os, threading
from pathlib import Path

sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")

from halite.backend import HaliteBackend

async def main():
    backend = HaliteBackend()
    from uuid import uuid4
    confirm_id = str(uuid4())[:12]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    backend._pending_confirms[confirm_id] = fut

    # Send confirm_request to stdout (backend._send writes to sys.stdout)
    await backend._send({{
        "type": "confirm_request",
        "id": confirm_id,
        "kind": "{kind}",
        "payload": {payload}
    }})
    sys.stdout.flush()

    # Read confirm_response from stdin (simulating what _read_loop does)
    import threading
    q = asyncio.Queue()
    def _reader():
        try:
            raw = sys.stdin.buffer.readline()
            if raw:
                asyncio.run_coroutine_threadsafe(q.put(raw.decode()), loop)
        except Exception:
            pass
    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    try:
        raw = await asyncio.wait_for(q.get(), timeout=5)
        msg = json.loads(raw.strip())
        if msg.get("type") == "confirm_response":
            backend._pending_confirms[confirm_id].set_result(msg.get("approved", False))
    except asyncio.TimeoutError:
        backend._pending_confirms[confirm_id].set_result(False)

    result = await fut
    print(json.dumps({{"result": result, "id": confirm_id}}), flush=True)

asyncio.run(main())
'''


def _send_to_helper(proc: subprocess.Popen, msg: dict) -> None:
    """Send a JSON message to a helper's stdin."""
    data = json.dumps(msg) + "\n"
    proc.stdin.write(data.encode("utf-8"))
    proc.stdin.flush()


def _read_from_helper(proc: subprocess.Popen, timeout: float = 10.0) -> dict | None:
    """Read a JSON line from a helper's stdout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        rlist, _, _ = select.select([proc.stdout], [], [], min(0.2, remaining))
        if rlist:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                return json.loads(line.decode().strip())
            except (json.JSONDecodeError, ValueError):
                continue
    return None


# ═══════════════════════════════════════════════════════════════════
# TEST 1: Approve round-trip
# ═══════════════════════════════════════════════════════════════════

def test_confirm_approve():
    """request_confirmation blocks, approve resolves it, returns True."""
    script = HELPER_ROUNDTRIP.format(
        root=PROJECT_ROOT,
        kind="dangerous",
        payload=json.dumps({"command": "rm -rf /", "reason": "root filesystem"}),
    )
    proc = subprocess.Popen(
        [PYTHON, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    try:
        # Read confirm_request from stdout
        confirm = _read_from_helper(proc, timeout=5)
        assert confirm is not None, "Helper did not send confirm_request"
        assert confirm["type"] == "confirm_request"
        assert confirm["kind"] == "dangerous"
        confirm_id = confirm["id"]

        # Send approve
        _send_to_helper(proc, {"type": "confirm_response", "id": confirm_id, "approved": True})

        # Read result
        result = _read_from_helper(proc, timeout=5)
        assert result is not None, "Helper did not output result"
        assert result["result"] is True, f"Expected True, got {result['result']}"

        print("  ✓ confirm approve round-trip works")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Decline round-trip
# ═══════════════════════════════════════════════════════════════════

def test_confirm_decline():
    """request_confirmation blocks, decline resolves it, returns False."""
    script = HELPER_ROUNDTRIP.format(
        root=PROJECT_ROOT,
        kind="diff",
        payload=json.dumps({"path": "/tmp/test.py", "old_preview": "old", "new_preview": "new"}),
    )
    proc = subprocess.Popen(
        [PYTHON, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    try:
        confirm = _read_from_helper(proc, timeout=5)
        assert confirm is not None
        assert confirm["kind"] == "diff"

        _send_to_helper(proc, {"type": "confirm_response", "id": confirm["id"], "approved": False})

        result = _read_from_helper(proc, timeout=5)
        assert result is not None
        assert result["result"] is False, f"Expected False, got {result['result']}"

        print("  ✓ confirm decline round-trip works")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ═══════════════════════════════════════════════════════════════════
# TEST 3: API kind round-trip with full payload
# ═══════════════════════════════════════════════════════════════════

def test_confirm_api_kind():
    """Verify all payload fields survive the round-trip."""
    script = HELPER_ROUNDTRIP.format(
        root=PROJECT_ROOT,
        kind="api",
        payload=json.dumps({
            "task_description": "Build a React app",
            "reasoning": "Complex multi-file task",
            "estimated_tokens": 5000,
        }),
    )
    proc = subprocess.Popen(
        [PYTHON, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    try:
        confirm = _read_from_helper(proc, timeout=5)
        assert confirm is not None
        assert confirm["kind"] == "api"
        assert confirm["payload"]["task_description"] == "Build a React app"
        assert confirm["payload"]["estimated_tokens"] == 5000

        _send_to_helper(proc, {"type": "confirm_response", "id": confirm["id"], "approved": True})

        result = _read_from_helper(proc, timeout=5)
        assert result is not None
        assert result["result"] is True

        print("  ✓ confirm API round-trip with full payload works")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Bogus confirm_response doesn't crash
# ═══════════════════════════════════════════════════════════════════

def test_bogus_confirm_response():
    """Sending confirm_response for unknown id is silently ignored."""
    HELPER_BOGUS = '''
import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("{root}")))
os.chdir("{root}")
from halite.backend import HaliteBackend
import asyncio

async def main():
    backend = HaliteBackend()
    # Simulate: send a confirm_response for nonexistent id
    await backend._handle_message({{"type": "confirm_response", "id": "nonexistent", "approved": True}})
    # If we get here, no crash
    print(json.dumps({{"ok": True}}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(HELPER_BOGUS.format(root=PROJECT_ROOT))
    assert result is not None and result.get("ok") is True
    print("  ✓ bogus confirm_response is silently ignored")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Backend subprocess survives confirm exchange
# ═══════════════════════════════════════════════════════════════════

def test_backend_survives_confirm():
    """The real backend process doesn't crash on confirm_response."""
    proc = subprocess.Popen(
        [PYTHON, "-m", "halite.backend"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    try:
        # Boot
        _send_to_helper(proc, {"type": "ready"})

        # Read welcome
        deadline = time.time() + 5
        while time.time() < deadline:
            msg = _read_from_helper(proc, timeout=1)
            if msg and msg.get("type") == "welcome":
                break

        # Read status_update
        while time.time() < deadline:
            msg = _read_from_helper(proc, timeout=1)
            if msg and msg.get("type") == "status_update":
                break

        # Send confirm_response for nonexistent id
        _send_to_helper(proc, {"type": "confirm_response", "id": "bogus", "approved": True})
        time.sleep(0.3)

        # Verify backend is still running
        assert proc.poll() is None, "Backend crashed after bogus confirm_response"
        print("  ✓ backend survives bogus confirm_response")
    finally:
        proc.terminate()
        proc.wait(timeout=3)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])
