"""
All shared Pydantic models (§8).
Every cross-module data structure is a Pydantic model — no bare dicts/TypedDicts at module boundaries.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Session & Message models ────────────────────────────────────────────────

class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    model_used: str | None = None
    tokens: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCall(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "running", "success", "failed"] = "pending"


class ToolResult(BaseModel):
    tool_call_id: UUID
    success: bool
    output: str
    error: str | None = None
    artifacts: list[str] = []  # using str instead of Path for JSON serialisation


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_path: Path | None = None
    active_model: str = ""
    backend: Literal["local_ollama", "local_llamacpp", "api"] = "local_ollama"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)


# ── Classifier models ───────────────────────────────────────────────────────

class ClassifierDecision(BaseModel):
    decision: Literal["local", "api", "clarify"]
    confidence: float
    reasoning: str
    clarifying_questions: list[str] | None = None


# ── Project context ─────────────────────────────────────────────────────────

class ProjectContext(BaseModel):
    root_path: Path
    detected_stack: str | None = None
    package_manager: str | None = None
    git_present: bool = False


# ── Review finding ──────────────────────────────────────────────────────────

class ReviewFinding(BaseModel):
    file_path: str  # str for JSON serialisation, converted to Path on use
    line: int | None = None
    severity: Literal["info", "warning", "critical"]
    category: Literal["bug", "performance", "security"]
    description: str


# ── Usage tracking ──────────────────────────────────────────────────────────

class UsageRecord(BaseModel):
    session_id: UUID
    provider: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── App configuration ───────────────────────────────────────────────────────

class AppConfig(BaseModel):
    """Root configuration model — persisted as TOML (§7.1)."""
    default_backend: Literal["local_ollama", "local_llamacpp", "api"] = "local_ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_classifier_model: str = "qwen2.5:0.5b"
    ollama_default_model: str | None = None
    # If None, Halite auto-detects the first model installed locally at startup.
    llamacpp_model_path: str | None = None
    llamacpp_models_dir: str | None = None
    api_provider: str = "anthropic"
    auto_approve_api: bool = False
    trust_level: Literal["manual", "auto"] = "manual"
    max_agent_iterations: int = 8
    browser_timeout: int = 15
    classifier_token_threshold: int = 400
    classifier_local_confidence_threshold: float = 0.7
    classifier_api_confidence_threshold: float = 0.3
    theme: str = "dark"
    log_retention_days: int = 7
    debug_mode: bool = False


# ── Tool input schemas (each tool defines its own typed args) ────────────────

class FileToolArgs(BaseModel):
    operation: Literal["read", "write", "delete", "list", "diff"]
    path: str
    content: str | None = None
    recursive: bool = False


class TerminalToolArgs(BaseModel):
    command: str
    timeout: int = 30
    cwd: str | None = None


class BrowserToolArgs(BaseModel):
    operation: Literal["open", "screenshot", "dom_check"]
    url: str
    full_page: bool = True
    timeout: int = 15


# ── Model capability registry entry ─────────────────────────────────────────

class ModelCapability(BaseModel):
    """Per-model tool-calling support metadata (§7.8)."""
    name: str
    supports_native_tools: bool = True
    context_window: int = 4096
    notes: str = ""


# ── App-level state carried in session ──────────────────────────────────────

class TaskState(BaseModel):
    """Checkpoint for in-progress tasks (§7.6)."""
    session_id: UUID
    task_description: str
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    active_file: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
