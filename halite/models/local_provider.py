"""
Ollama local model adapter (§5, §7.8).
Connects to a running Ollama daemon, lists available models, sends chat completions.
This is a real integration, not a stub.
"""
from __future__ import annotations

import json
import httpx
from typing import AsyncIterator

from halite.models.schemas import ModelCapability
from halite.utils.logging_config import logger


class OllamaProvider:
    """
    Connects to a local Ollama daemon for inference.
    Every method is async. All failures are caught and logged (§10).
    """

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host.rstrip("/")
        # Generous timeout: the first request for a model must also cover the
        # model-load time (Ollama loads the model into memory on first use,
        # which can take a while on slow hardware). 60s was too short and
        # caused spurious "request timed out" errors during cold loads.
        self._client = httpx.AsyncClient(base_url=self.host, timeout=300.0)

    async def health_check(self) -> bool:
        """Check if Ollama daemon is reachable."""
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Ollama health check failed: {}", exc)
            return False

    async def list_models(self) -> list[dict]:
        """Return all locally pulled models with metadata."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            logger.debug("Ollama models found: {}", len(models))
            return models
        except Exception as exc:
            logger.error("Failed to list Ollama models: {}", exc)
            return []

    # Default context window for local inference.
    #
    # Many Ollama models declare a huge context (e.g. Qwen3 defaults to 256K
    # tokens). On low-RAM machines the default KV-cache allocation for that
    # context is enormous (often 1-2 GB), which makes llama-server exhaust
    # memory during load and return HTTP 500 ("timed out waiting for
    # llama-server to start"). Pinning a small context here caps the KV cache
    # so models actually load and respond. (Verified: qwen3.5:0.8b fails to
    # load at the default context but responds in ~8 s with num_ctx=2048.)
    DEFAULT_NUM_CTX: int = 2048

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        num_ctx: int | None = None,
    ) -> str:
        """
        Send a chat completion request to Ollama.
        Returns the assistant message content as a string.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx or self.DEFAULT_NUM_CTX,
            },
        }
        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                # Some models (e.g. Qwen thinking mode) can return their whole
                # reply in the `thinking` field with empty `content`. Fall back
                # so the assistant never produces a blank message.
                content = data.get("message", {}).get("thinking", "") or content
            usage = data.get("eval_count", 0)
            logger.debug(
                "Ollama chat complete — model={}, tokens_eval={}",
                model, usage,
            )
            return content
        except httpx.TimeoutException:
            logger.error("Ollama chat timed out for model={}", model)
            return "[ERROR: Ollama request timed out]"
        except httpx.HTTPStatusError as exc:
            # Surface the actual error body Ollama returned (e.g. a model that
            # failed to load, or an invalid request) so it's diagnosable.
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:
                pass
            logger.error(
                "Ollama chat HTTP error for model={} — {}: {}",
                model, exc.response.status_code, detail,
            )
            return (
                f"[ERROR: Ollama returned {exc.response.status_code} — "
                f"{detail or exc}]"
            )
        except Exception as exc:
            logger.error("Ollama chat failed for model={}: {}", model, exc)
            return f"[ERROR: Ollama request failed — {exc}]"

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion from Ollama, yielding content chunks.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx or self.DEFAULT_NUM_CTX,
            },
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.error("Ollama stream failed for model={}: {}", model, exc)
            yield f"\n[ERROR: Stream failed — {exc}]"

    async def close(self) -> None:
        await self._client.aclose()
