"""Unit tests for tools, storage, secrets, and context manager."""
import asyncio
import pytest
from uuid import uuid4
from pathlib import Path

from halite.models.schemas import ToolCall
from halite.tools.base import ToolExecutor
from halite.tools.registry import ToolRegistry
from halite.tools.terminal_tool import validate_command
from halite.storage.history import HistoryStore
from halite.models.schemas import Message, Session, UsageRecord
from halite.core.context_manager import ContextManager


@pytest.mark.asyncio
class TestTools:
    async def test_file_write_read(self, tmp_path):
        ex = ToolExecutor(project_root=tmp_path)
        ToolRegistry(ex)

        r = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="file",
            arguments={"operation": "write", "path": "a.txt", "content": "hello"},
        ))
        assert r.success
        assert (tmp_path / "a.txt").exists()

        r2 = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="file",
            arguments={"operation": "read", "path": "a.txt"},
        ))
        assert r2.success
        assert "hello" in r2.output

    async def test_unknown_tool_rejected(self, tmp_path):
        ex = ToolExecutor(project_root=tmp_path)
        ToolRegistry(ex)
        r = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="teleport",
            arguments={},
        ))
        assert not r.success
        assert "Unknown tool" in r.error

    async def test_sandbox_blocks_outside_root(self, tmp_path):
        ex = ToolExecutor(project_root=tmp_path)
        ToolRegistry(ex)
        r = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="file",
            arguments={"operation": "read", "path": "/etc/passwd"},
        ))
        assert not r.success
        assert "outside project root" in r.error

    async def test_terminal_runs(self, tmp_path):
        ex = ToolExecutor(project_root=tmp_path)
        ToolRegistry(ex)
        r = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="terminal",
            arguments={"command": "echo hello", "timeout": 5},
        ))
        assert r.success
        assert "hello" in r.output

    async def test_terminal_timeout(self, tmp_path):
        ex = ToolExecutor(project_root=tmp_path)
        ToolRegistry(ex)
        r = await ex.run(ToolCall(
            id=uuid4(), message_id=uuid4(), tool_name="terminal",
            arguments={"command": "sleep 10", "timeout": 1},
        ))
        assert not r.success
        assert "timed out" in r.error


class TestDangerousCommands:
    def test_rm_rf_blocked(self):
        is_dangerous, reason = validate_command("rm -rf /")
        assert is_dangerous
        assert "root" in reason

    def test_git_push_force_blocked(self):
        is_dangerous, _ = validate_command("git push --force origin main")
        assert is_dangerous

    def test_safe_command_allowed(self):
        is_dangerous, _ = validate_command("ls -la && echo hi")
        assert not is_dangerous


class TestStorage:
    def test_session_message_roundtrip(self):
        store = HistoryStore()
        s = Session(project_path="/tmp/x", active_model="m", backend="local_ollama")
        store.create_session(s)

        m = Message(session_id=s.id, role="user", content="test msg")
        store.add_message(m)

        msgs = store.get_messages(s.id)
        assert len(msgs) == 1
        assert msgs[0].content == "test msg"

        sessions = store.list_sessions(limit=10)
        assert any(str(x.id) == str(s.id) for x in sessions)

    def test_usage_record(self):
        store = HistoryStore()
        s = Session()
        store.create_session(s)
        store.add_usage_record(UsageRecord(
            session_id=s.id, provider="api", tokens_in=10, tokens_out=5, cost_usd=0.01
        ))
        usage = store.get_session_usage(s.id)
        assert len(usage) == 1
        assert usage[0].cost_usd == 0.01


class TestContextManager:
    def test_summarization(self):
        cm = ContextManager(context_window=1000)
        for i in range(30):
            cm.add_message("user", f"message {i} with padding " * 5)
        assert cm.needs_summarization()
        result = cm.summarize_old_turns(recent_keep=4)
        assert result["summarized"]
        assert len(result["messages"]) == 5  # 1 summary + 4 kept