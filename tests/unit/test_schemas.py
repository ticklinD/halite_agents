"""Unit tests for the Pydantic schemas (§8)."""
import pytest
from uuid import uuid4
from pydantic import ValidationError

from halite.models.schemas import (
    AppConfig, Message, Session, ToolCall, ToolResult,
    ClassifierDecision, ProjectContext, ReviewFinding, UsageRecord,
)


class TestSchemas:
    def test_message_requires_role_and_content(self):
        with pytest.raises(ValidationError):
            Message(session_id=uuid4())

    def test_message_defaults(self):
        msg = Message(session_id=uuid4(), role="user", content="hi")
        assert msg.role == "user"
        assert msg.content == "hi"
        assert msg.id is not None
        assert msg.tokens is None

    def test_tool_result_requires_call_id(self):
        with pytest.raises(ValidationError):
            ToolResult(success=True, output="x")

    def test_session_defaults(self):
        s = Session()
        assert s.backend == "local_ollama"
        assert s.created_at is not None

    def test_classifier_decision_enum(self):
        d = ClassifierDecision(decision="local", confidence=0.8, reasoning="ok")
        assert d.decision == "local"
        with pytest.raises(ValidationError):
            ClassifierDecision(decision="maybe", confidence=0.5, reasoning="x")

    def test_appconfig_defaults(self):
        cfg = AppConfig()
        assert cfg.default_backend == "local_ollama"
        assert cfg.ollama_host == "http://localhost:11434"
        assert cfg.auto_approve_api is False
        assert cfg.trust_level == "manual"
        assert cfg.max_agent_iterations == 8

    def test_appconfig_rejects_bad_backend(self):
        with pytest.raises(ValidationError):
            AppConfig(default_backend="cloud9")

    def test_review_finding_enum(self):
        f = ReviewFinding(file_path="a.py", severity="critical", category="security", description="x")
        assert f.severity == "critical"
        with pytest.raises(ValidationError):
            ReviewFinding(file_path="a.py", severity="nuke", category="bug", description="x")

    def test_usage_record(self):
        u = UsageRecord(session_id=uuid4(), provider="api", tokens_in=10, tokens_out=5, cost_usd=0.01)
        assert u.cost_usd == 0.01