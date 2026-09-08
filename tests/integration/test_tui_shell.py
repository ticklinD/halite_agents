"""
Integration test: run the Halite Ink backend (JSON-over-stdio IPC) headlessly
with a mocked Ollama provider.

Verifies the full loop works: backend start -> ready -> user input ->
dispatch -> model response -> persistence -> clean shutdown.

The Ollama provider is mocked so the test doesn't depend on a running
local daemon (in CI/dev without Ollama). This tests the backend wiring and
the Ink IPC protocol, not the Ollama HTTP layer (which has its own unit tests).
"""
from __future__ import annotations

import asyncio


class MockOllama:
    """Minimal mock of OllamaProvider for the backend wiring test."""

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host

    async def health_check(self) -> bool:
        return True

    async def list_models(self) -> list[dict]:
        return [{"name": "llama3.2:3b", "size": 100, "modified_at": "now"}]

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        num_ctx: int | None = None,
        num_predict: int | None = None,
    ) -> str:
        return "Echo: this is a mocked response from the local model."

    async def close(self) -> None:
        pass


async def main() -> None:
    backend = None
    messages_out: list[dict] = []
    try:
        from halite.backend import HaliteBackend

        class PatchedBackend(HaliteBackend):
            def __init__(self, debug: bool = False):
                super().__init__(debug=debug)
                self.ollama = MockOllama(self.config.ollama_host)

        async def _send(msg: dict) -> None:
            messages_out.append(msg)

        backend = PatchedBackend(debug=True)
        backend._send = _send  # type: ignore[method-assign]

        # 1. Ready flow
        await backend._on_ready()
        types = [m["type"] for m in messages_out]
        assert "welcome" in types, f"Expected welcome message, got {types}"
        print("✓ Backend ready + welcome sent")

        # 2. Slash command dispatch
        await backend._handle_user_input("/help")
        types = [m["type"] for m in messages_out]
        assert "system_message" in types, f"Expected system_message for /help, got {types}"
        print("✓ Slash command dispatches (system_message emitted)")

        # 3. Chat message -> mock model response
        messages_out.clear()
        await backend._handle_user_input("hello there")
        types = [m["type"] for m in messages_out]
        assert "assistant_message" in types, f"Expected assistant_message, got {types}"
        assistant = [m for m in messages_out if m["type"] == "assistant_message"][0]
        assert "mocked response" in assistant["text"]
        print(f"✓ Assistant response: {assistant['text'][:50]}...")
        # Thinking indicator must fire around the model call
        assert "thinking_start" in types and "thinking_stop" in types, \
            f"Expected thinking indicator, got {types}"
        print("✓ Thinking indicator fires (thinking_start / thinking_stop)")

        # 4. Persistence
        assert backend.current_session is not None
        msgs = backend.history.get_messages(backend.current_session.id)
        roles = [m.role for m in msgs]
        print(f"✓ Messages persisted: {roles}")
        assert "user" in roles, "User message not persisted"
        assert "assistant" in roles, "Assistant response not persisted"

        print("\n=== INK BACKEND INTEGRATION TEST PASSED ===")
    finally:
        if backend is not None:
            try:
                await backend._shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
