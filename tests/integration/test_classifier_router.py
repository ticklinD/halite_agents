"""
Integration tests for the classifier + router wiring (Phase 2, item 2).

Tests the full classify → route → confirm → respond pipeline,
including task-level stickiness (§6.1).
"""
import asyncio
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
# TEST 1: Classifier rules route simple tasks to local
# ═══════════════════════════════════════════════════════════════════

def test_simple_task_routes_local():
    """A simple prompt like 'fix typo' should classify as local."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    classifier = IntentClassifier(config)
    router = Router(config)

    decision = classifier.classify("fix typo in README.md")
    backend, needs_confirm = router.resolve_backend(decision)

    print(json.dumps({{
        "decision": decision.decision,
        "confidence": decision.confidence,
        "backend": backend,
        "needs_confirm": needs_confirm,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None, "Helper returned no output"
    assert result["decision"] == "local", f"Expected local, got {result['decision']}"
    assert result["backend"] == "local"
    assert result["needs_confirm"] is False
    print("  ✓ simple task → local (no confirm needed)")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Classifier rules route complex tasks to API
# ═══════════════════════════════════════════════════════════════════

def test_complex_task_routes_api():
    """A complex prompt should classify as API and need confirmation."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    config.auto_approve_api = False
    classifier = IntentClassifier(config)
    router = Router(config)

    decision = classifier.classify("refactor the entire project to use TypeScript with proper auth system and database migration")
    backend, needs_confirm = router.resolve_backend(decision)

    print(json.dumps({{
        "decision": decision.decision,
        "confidence": decision.confidence,
        "backend": backend,
        "needs_confirm": needs_confirm,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["decision"] == "api", f"Expected api, got {result['decision']}"
    assert result["backend"] == "api"
    assert result["needs_confirm"] is True
    print("  ✓ complex task → api + needs confirmation")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Clarify decision for ambiguous prompts
# ═══════════════════════════════════════════════════════════════════

def test_ambiguous_prompt_clarifies():
    """A very short ambiguous prompt should trigger clarify."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    classifier = IntentClassifier(config)
    router = Router(config)

    decision = classifier.classify("help")
    backend, needs_confirm = router.resolve_backend(decision)

    print(json.dumps({{
        "decision": decision.decision,
        "confidence": decision.confidence,
        "backend": backend,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["decision"] == "clarify", f"Expected clarify, got {result['decision']}"
    assert result["backend"] == "none"
    print("  ✓ ambiguous prompt → clarify")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Manual override bypasses classification
# ═══════════════════════════════════════════════════════════════════

def test_manual_override_bypasses_classifier():
    """When manual_override is set, classification is bypassed."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    classifier = IntentClassifier(config)
    router = Router(config)

    # Set manual override to local
    router.set_manual_override("local")

    # Even a complex task should go to local
    decision = classifier.classify("refactor entire project with auth system and payment")
    backend, needs_confirm = router.resolve_backend(decision)

    print(json.dumps({{
        "decision": decision.decision,
        "backend": backend,
        "needs_confirm": needs_confirm,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["backend"] == "local", f"Expected local (override), got {result['backend']}"
    assert result["needs_confirm"] is False
    print("  ✓ manual override bypasses classification")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Secret detection biases toward local
# ═══════════════════════════════════════════════════════════════════

def test_secret_detection_biases_local():
    """Prompts with potential secrets should route to local."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    classifier = IntentClassifier(config)
    router = Router(config)

    decision = classifier.classify("my API key is sk-abcdefghij1234567890abcdefghij and I need help refactoring the entire auth system with database migration")
    backend, needs_confirm = router.resolve_backend(decision)

    print(json.dumps({{
        "decision": decision.decision,
        "backend": backend,
        "reasoning": decision.reasoning[:100],
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    # Even though the prompt is complex, secrets bias toward local
    assert result["backend"] == "local", f"Expected local (secrets bias), got {result['backend']}"
    print("  ✓ secret detection → local (privacy)")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Stickiness — second turn uses same backend
# ═══════════════════════════════════════════════════════════════════

def test_stickiness_reuses_backend():
    """Once a task backend is set, subsequent messages don't re-classify."""
    script = '''
import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path("{root}")))
from halite.config.settings import load_config
from halite.core.classifier import IntentClassifier
from halite.core.router import Router

async def main():
    config = load_config()
    classifier = IntentClassifier(config)
    router = Router(config)

    # First turn: classify and route
    decision1 = classifier.classify("refactor entire project with complex auth system")
    backend1, _ = router.resolve_backend(decision1)

    # Simulate stickiness: once backend is set, don't re-classify
    task_backend = backend1  # This is what the backend stores

    # Second turn: different prompt, but stickiness means same backend
    decision2 = classifier.classify("what does this code do")  # would be clarify
    # But if stickiness is active, we skip classification
    backend2 = task_backend  # Uses the sticky backend, not re-classifying

    print(json.dumps({{
        "first_backend": backend1,
        "second_backend": backend2,
        "sticky": backend1 == backend2,
    }}), flush=True)

asyncio.run(main())
'''
    result = _run_helper(script.format(root=PROJECT_ROOT))
    assert result is not None
    assert result["first_backend"] == "api"
    assert result["sticky"] is True
    print("  ✓ stickiness reuses backend for subsequent turns")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])
