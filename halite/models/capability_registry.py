"""
Model Capability Registry (§7.8).
Maps model name → tool-calling support metadata.
Models without native tool support use a prompt-based ReAct format.
Registry is loaded from a built-in default set + user overrides in config.
"""
from __future__ import annotations

from halite.models.schemas import ModelCapability
from halite.utils.logging_config import logger


# ── Built-in registry ───────────────────────────────────────────────────────

_BUILTIN_REGISTRY: dict[str, ModelCapability] = {
    # Ollama models
    "qwen2.5:0.5b": ModelCapability(
        name="qwen2.5:0.5b",
        supports_native_tools=False,
        context_window=32768,
        notes="Small classifier model — no native tool calling; use ReAct format.",
    ),
    "qwen2.5:1.5b": ModelCapability(
        name="qwen2.5:1.5b",
        supports_native_tools=False,
        context_window=32768,
        notes="Small classifier — ReAct format required.",
    ),
    "qwen2.5:3b": ModelCapability(
        name="qwen2.5:3b",
        supports_native_tools=False,
        context_window=32768,
        notes="ReAct format for tool calls.",
    ),
    "qwen2.5:7b": ModelCapability(
        name="qwen2.5:7b",
        supports_native_tools=False,
        context_window=32768,
        notes="Can handle tool calls with structured prompt.",
    ),
    "qwen2.5:14b": ModelCapability(
        name="qwen2.5:14b",
        supports_native_tools=True,
        context_window=32768,
        notes="Good structured output capability.",
    ),
    "llama3.2:1b": ModelCapability(
        name="llama3.2:1b",
        supports_native_tools=False,
        context_window=8192,
        notes="Very small — use only for simple classification, not tool calls.",
    ),
    "llama3.2:3b": ModelCapability(
        name="llama3.2:3b",
        supports_native_tools=False,
        context_window=8192,
        notes="ReAct format required for tool calls.",
    ),
    "llama3.1:8b": ModelCapability(
        name="llama3.1:8b",
        supports_native_tools=True,
        context_window=128000,
        notes="Solid general-purpose model.",
    ),
    "llama3.1:70b": ModelCapability(
        name="llama3.1:70b",
        supports_native_tools=True,
        context_window=128000,
        notes="Large model, may need significant VRAM.",
    ),
    "codellama:7b": ModelCapability(
        name="codellama:7b",
        supports_native_tools=False,
        context_window=16384,
        notes="Code-focused, ReAct format for tool calls.",
    ),
    "codellama:13b": ModelCapability(
        name="codellama:13b",
        supports_native_tools=False,
        context_window=16384,
        notes="Better code understanding, still ReAct for tools.",
    ),
    # API models (always native tool support)
    "claude-sonnet-4-20250514": ModelCapability(
        name="claude-sonnet-4-20250514",
        supports_native_tools=True,
        context_window=200000,
        notes="Anthropic Claude — native tool calling.",
    ),
    "claude-3-5-sonnet-20241022": ModelCapability(
        name="claude-3-5-sonnet-20241022",
        supports_native_tools=True,
        context_window=200000,
        notes="Anthropic Claude — native tool calling.",
    ),
}


class CapabilityRegistry:
    """
    Runtime registry for model capabilities.
    Loaded at init from built-in defaults. Query with get().
    """

    def __init__(self) -> None:
        self._registry: dict[str, ModelCapability] = dict(_BUILTIN_REGISTRY)
        logger.debug("Capability registry loaded with {} models", len(self._registry))

    def get(self, model_name: str) -> ModelCapability:
        """
        Get capability for a model. If unknown, assume no native tools
        (safe default — falls back to ReAct format).
        """
        if model_name in self._registry:
            return self._registry[model_name]

        logger.info(
            "Model '{}' not in capability registry — assuming no native tool support (safe default)",
            model_name,
        )
        return ModelCapability(
            name=model_name,
            supports_native_tools=False,
            context_window=4096,
            notes="Unknown model — assumed no native tool support.",
        )

    def register(self, cap: ModelCapability) -> None:
        """Register a model capability (for dynamically discovered models)."""
        self._registry[cap.name] = cap
        logger.debug("Registered capability for model: {}", cap.name)

    def list_models(self) -> list[ModelCapability]:
        """Return all registered capabilities."""
        return list(self._registry.values())

    def has_native_tools(self, model_name: str) -> bool:
        """Quick check: does this model support native tool calling?"""
        return self.get(model_name).supports_native_tools
