"""
Anthropic API provider adapter (§5).
Sends requests to Anthropic's API. Requires an API key stored via secrets module.
This module is Phase 4 integration, but the provider class is needed now
for the router to reference. Kept minimal — full integration when we reach Phase 4.
"""
from __future__ import annotations

from halite.utils.logging_config import logger


class APIProvider:
    """
    Anthropic API adapter (§5 required provider).
    Minimal working implementation — full streaming + tool-use added in Phase 4.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None  # lazy init — only created if key is present

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed — run: pip install anthropic")
        return self._client

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """Send a chat completion request to Anthropic API."""
        client = self._ensure_client()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
            )
            content = response.content[0].text if response.content else ""
            logger.debug(
                "API chat complete — model={}, tokens_in={}, tokens_out={}",
                self.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return content
        except Exception as exc:
            logger.error("API chat failed for model={}: {}", self.model, exc)
            return f"[ERROR: API request failed — {exc}]"

    async def chat_with_usage(self, messages: list[dict], temperature: float = 0.7) -> tuple[str, int, int]:
        """
        Send a chat completion and return (content, input_tokens, output_tokens).
        Used by the router to track usage/cost (§7.2).
        """
        client = self._ensure_client()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
            )
            content = response.content[0].text if response.content else ""
            return content, response.usage.input_tokens, response.usage.output_tokens
        except Exception as exc:
            logger.error("API chat_with_usage failed: {}", exc)
            return f"[ERROR: {exc}]", 0, 0

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
