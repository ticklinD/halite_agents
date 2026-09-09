"""Tests for the tool-calling agent loop (Phase 2, item 3).

Tests the ReAct parser, tool system prompt, and the agent loop
integration with ToolExecutor.
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestParseToolCalls:
    """Unit tests for _parse_tool_calls static method."""

    def test_single_tool_call(self):
        from halite.backend import HaliteBackend
        text = '''I need to run a command.
<tool_call>
{"name": "terminal", "arguments": {"command": "ls -la"}}
</tool_call>'''
        calls = HaliteBackend._parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "terminal"
        assert calls[0]["arguments"]["command"] == "ls -la"

    def test_multiple_tool_calls(self):
        from halite.backend import HaliteBackend
        text = '''First, read the file:
<tool_call>
{"name": "file", "arguments": {"operation": "read", "path": "/tmp/a.py"}}
</tool_call>
Then run it:
<tool_call>
{"name": "terminal", "arguments": {"command": "python /tmp/a.py"}}
</tool_call>'''
        calls = HaliteBackend._parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0]["name"] == "file"
        assert calls[1]["name"] == "terminal"

    def test_no_tool_calls(self):
        from halite.backend import HaliteBackend
        text = "This is just a normal response with no tool calls."
        calls = HaliteBackend._parse_tool_calls(text)
        assert calls == []

    def test_malformed_json_ignored(self):
        from halite.backend import HaliteBackend
        text = '''<tool_call>
NOT VALID JSON
</tool_call>'''
        calls = HaliteBackend._parse_tool_calls(text)
        assert calls == []

    def test_missing_name_ignored(self):
        from halite.backend import HaliteBackend
        text = '''<tool_call>
{"arguments": {"command": "ls"}}
</tool_call>'''
        calls = HaliteBackend._parse_tool_calls(text)
        assert calls == []

    def test_mixed_text_and_tool_calls(self):
        from halite.backend import HaliteBackend
        text = '''Let me check that for you.
<tool_call>
{"name": "terminal", "arguments": {"command": "pwd"}}
</tool_call>
That should show the directory.'''
        calls = HaliteBackend._parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["arguments"]["command"] == "pwd"


class TestStripToolCalls:
    """Unit tests for _strip_tool_calls."""

    def test_removes_tags(self):
        from halite.backend import HaliteBackend
        text = '''Let me check.
<tool_call>
{"name": "terminal", "arguments": {"command": "ls"}}
</tool_call>
Done.'''
        result = HaliteBackend._strip_tool_calls(text)
        assert "<tool_call>" not in result
        assert "Let me check." in result
        assert "Done." in result

    def test_no_tags_unchanged(self):
        from halite.backend import HaliteBackend
        text = "Just a normal message."
        result = HaliteBackend._strip_tool_calls(text)
        assert result == text


class TestBuildToolSystemPrompt:
    """Test that the tool system prompt contains expected content."""

    def test_prompt_contains_all_tools(self):
        from halite.backend import HaliteBackend
        from halite.config.settings import load_config
        config = load_config()
        backend = HaliteBackend.__new__(HaliteBackend)
        backend.config = config
        from halite.tools.base import ToolExecutor
        from halite.tools.registry import ToolRegistry
        backend.executor = ToolExecutor(project_root=Path("/tmp"))
        ToolRegistry(backend.executor)

        prompt = backend._build_tool_system_prompt()
        assert "terminal" in prompt
        assert "file" in prompt
        assert "browser" in prompt
        assert "<tool_call>" in prompt
        assert "arguments" in prompt


class TestAgentLoopToolExecution:
    """Integration test: verify the agent loop parses a tool call from
    mock model output and executes it through the ToolExecutor."""

    def test_tool_call_executed(self):
        """Simulate a model returning a tool call, verify execution."""
        import asyncio
        from halite.backend import HaliteBackend
        from halite.config.settings import load_config
        from halite.tools.base import ToolExecutor
        from halite.tools.registry import ToolRegistry
        from halite.models.schemas import ToolCall

        async def run():
            backend = HaliteBackend.__new__(HaliteBackend)
            backend.config = load_config()
            backend.config.max_agent_iterations = 3
            backend.executor = ToolExecutor(project_root=Path("/tmp"))
            ToolRegistry(backend.executor)
            from halite.models.capability_registry import CapabilityRegistry
            backend.capabilities = CapabilityRegistry()
            backend.active_model = "qwen3.5:0.8b"
            backend.active_backend = "local"

            # Mock the ollama provider to return a tool call then a final answer
            call_count = [0]
            async def mock_chat(model, messages):
                call_count[0] += 1
                if call_count[0] == 1:
                    return '<tool_call>\n{"name": "terminal", "arguments": {"command": "echo hello"}}\n</tool_call>'
                return "The command ran successfully."
            from halite.models.local_provider import OllamaProvider
            backend.ollama = OllamaProvider.__new__(OllamaProvider)
            backend.ollama.chat = mock_chat

            # Also need _send to be a no-op
            sent = []
            async def mock_send(msg):
                sent.append(msg)
            backend._send = mock_send

            messages = [{"role": "user", "content": "Run echo hello"}]
            result = await backend._run_agent_loop(messages)

            assert result == "The command ran successfully."
            # Verify tool_result was sent to frontend
            tool_results = [m for m in sent if m.get("type") == "tool_result"]
            assert len(tool_results) == 1
            assert tool_results[0]["tool"] == "terminal"
            assert tool_results[0]["success"] is True
            assert "hello" in tool_results[0]["output"]

        asyncio.run(run())

    def test_max_iterations_cap(self):
        """If the model keeps returning tool calls, the loop caps."""
        import asyncio
        from halite.backend import HaliteBackend
        from halite.config.settings import load_config
        from halite.tools.base import ToolExecutor
        from halite.tools.registry import ToolRegistry

        async def run():
            backend = HaliteBackend.__new__(HaliteBackend)
            backend.config = load_config()
            backend.config.max_agent_iterations = 2
            backend.executor = ToolExecutor(project_root=Path("/tmp"))
            ToolRegistry(backend.executor)
            from halite.models.capability_registry import CapabilityRegistry
            backend.capabilities = CapabilityRegistry()
            backend.active_model = "qwen3.5:0.8b"
            backend.active_backend = "local"

            # Always return a tool call — should hit max iterations
            async def mock_chat(model, messages):
                return '<tool_call>\n{"name": "terminal", "arguments": {"command": "ls"}}\n</tool_call>'
            from halite.models.local_provider import OllamaProvider
            backend.ollama = OllamaProvider.__new__(OllamaProvider)
            backend.ollama.chat = mock_chat

            async def mock_send(msg):
                pass
            backend._send = mock_send

            messages = [{"role": "user", "content": "Keep listing"}]
            result = await backend._run_agent_loop(messages)

            # Should return the last model response (which contains tool_call)
            assert "</tool_call>" in result

        asyncio.run(run())


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-x"])
