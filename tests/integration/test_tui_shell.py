"""
Integration test: run the Halite TUI headlessly with a mocked Ollama provider.
Verifies the full loop works: app start -> message submit -> dispatch ->
model response -> persistence -> clean shutdown.

The Ollama provider is mocked so the test doesn't depend on a running
local daemon (in CI/dev without Ollama). This tests the app wiring, not
the Ollama HTTP layer (which has its own unit tests).
"""
from __future__ import annotations

import asyncio
import sys
import os
import uuid

# Ensure we can import halite (repo root = two levels up from tests/integration)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MockOllama:
    """Minimal mock of OllamaProvider for the app wiring test."""

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host

    async def health_check(self) -> bool:
        return True

    async def list_models(self) -> list[dict]:
        return [{"name": "llama3.2:3b", "size": 100, "modified_at": "now"}]

    async def chat(self, model: str, messages: list[dict], temperature: float = 0.7) -> str:
        return "Echo: this is a mocked response from the local model."

    async def close(self) -> None:
        pass


async def main() -> None:
    import halite.app as appmod

    # Patch the app's Ollama provider with the mock
    appmod.HaliteApp.__init__ = _patched_init

    app = appmod.HaliteApp(debug=True)

    async with app.run_test() as pilot:
        # Verify the app is running
        assert app.is_running, "App did not start"
        print("✓ App started")

        # Verify a chat screen is active
        print(f"✓ Active screen: {app.screen.__class__.__name__}")

        # The current session must exist
        assert app.current_session is not None
        print(f"✓ Session created: {app.current_session.id}")

        # Simulate typing a message and submitting
        chat = app.screen
        input_widget = chat._input
        assert input_widget is not None, "Input widget not found"

        await pilot.press("h", "e", "l", "l", "o")
        await pilot.press("enter")
        await pilot.pause(1.0)

        # Verify the user message was persisted
        msgs = app.history.get_messages(app.current_session.id)
        roles = [m.role for m in msgs]
        print(f"✓ Messages persisted after submit: {roles}")
        assert "user" in roles, "User message not persisted"

        # Verify the assistant response was persisted (from the mock)
        assert "assistant" in roles, "Assistant response not persisted"
        assistant_msg = [m for m in msgs if m.role == "assistant"][0]
        print(f"✓ Assistant response: {assistant_msg.content[:50]}...")

        # Test a slash command dispatches properly
        from halite.commands.dispatcher import CommandDispatcher
        d = CommandDispatcher()
        parsed = d.parse("/help")
        assert parsed == ("help", "")
        print("✓ Dispatcher parses /help")

        # Clean shutdown
        await app.action_quit()
        await pilot.pause(0.5)
        print("✓ Clean shutdown completed")


def _patched_init(self, debug: bool = False) -> None:
    """Patched __init__ that swaps the real Ollama provider for the mock."""
    original_init = appmod_original_init
    original_init(self, debug)
    # Replace the provider after original init
    self.ollama = MockOllama(self.config.ollama_host)


# Save the original init for the patch
import halite.app as appmod_ref
appmod_original_init = appmod_ref.HaliteApp.__init__


if __name__ == "__main__":
    asyncio.run(main())
    print("\n=== HEADLESS INTEGRATION TEST PASSED ===")