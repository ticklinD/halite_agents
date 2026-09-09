"""Tests for usage tracking wiring (Phase 2, item 5)."""
import subprocess
import json
import sys
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
ROOT_TOKEN = "@@ROOT@@"


def _run_helper(script: str, timeout: float = 25.0) -> dict | None:
    """Run a Python helper script and capture its JSON output."""
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
# TEST 1: _compute_cost returns correct values
# ═══════════════════════════════════════════════════════════════════

def test_compute_cost():
    script = '''
import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.backend import HaliteBackend
backend = HaliteBackend()
cost = backend._compute_cost(1_000_000, 1_000_000)
print(json.dumps({"cost": round(cost, 2)}), flush=True)
'''
    result = _run_helper(script)
    assert result is not None
    assert result["cost"] == 90.0
    print(f"  ✓ _compute_cost(1M in, 1M out) = ${result['cost']}")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: _record_usage persists to DB
# ═══════════════════════════════════════════════════════════════════

def test_record_usage_persists():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.backend import HaliteBackend
async def main():
    backend = HaliteBackend()
    sid = backend.current_session.id
    backend.history._conn.execute("DELETE FROM usage_records WHERE session_id=?", (str(sid),))
    backend.history._conn.commit()
    backend._record_usage("anthropic", 5000, 1000)
    records = backend.history.get_session_usage(sid)
    print(json.dumps({
        "count": len(records),
        "tokens_in": records[0].tokens_in if records else 0,
        "tokens_out": records[0].tokens_out if records else 0,
        "cost_positive": records[0].cost_usd > 0 if records else False,
    }), flush=True)
asyncio.run(main())
'''
    result = _run_helper(script)
    assert result is not None
    assert result["count"] == 1
    assert result["tokens_in"] == 5000
    assert result["tokens_out"] == 1000
    assert result["cost_positive"] is True
    print(f"  ✓ _record_usage persists: {result['tokens_in']}in/{result['tokens_out']}out, cost>0")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: /usage shows real data (not always $0)
# ═══════════════════════════════════════════════════════════════════

def test_usage_command_shows_real_data():
    script = '''
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("@@ROOT@@")))
os.chdir("@@ROOT@@")
from halite.backend import HaliteBackend
from halite.commands.handlers import register_handlers
from halite.commands.dispatcher import CommandDispatcher
async def main():
    backend = HaliteBackend()
    dispatcher = CommandDispatcher()
    register_handlers(dispatcher, backend)
    backend._record_usage("anthropic", 10000, 2000)
    result = await dispatcher.dispatch("/usage")
    msg = result.message
    print(json.dumps({
        "handled": result.handled,
        "has_session_tokens": "10,000" in msg or "10000" in msg,
        "has_lifetime": "Lifetime" in msg,
        "not_zero": "$0.0000" not in msg,
    }), flush=True)
asyncio.run(main())
'''
    result = _run_helper(script)
    assert result is not None
    assert result["handled"] is True
    assert result["has_session_tokens"] is True
    assert result["has_lifetime"] is True
    assert result["not_zero"] is True
    print("  ✓ /usage shows real token counts and non-zero cost")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])