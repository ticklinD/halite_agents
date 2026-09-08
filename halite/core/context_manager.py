"""
Context window management (§7.7).
Tracks token usage per session and, before overflowing the active model's
context window, summarizes older turns into a compact recap rather than
silently truncating or crashing.
"""
from __future__ import annotations

from halite.utils.logging_config import logger


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate (about 4 chars/token for English).
    Good enough for context-window management; provider tokenizers
    are used where exact counts matter (§7.7: using each provider's tokenizer).
    """
    return max(1, len(text) // 4)


class ContextManager:
    """
    Tracks per-session token usage and triggers summarization before overflow.
    """

    def __init__(self, context_window: int = 4096, resume_threshold_ratio: float = 0.85) -> None:
        self.context_window = context_window
        self.resume_threshold = int(context_window * resume_threshold_ratio)
        self._pending: list[dict] = []
        self._running_tokens = 0
        logger.debug(
            "ContextManager: window={}, resume_threshold={}",
            context_window, self.resume_threshold,
        )

    def set_context_window(self, window: int) -> None:
        """Update the context window (e.g. when switching models)."""
        self.context_window = window
        self.resume_threshold = int(window * 0.85)
        logger.debug("ContextManager window updated to {}", window)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the pending list and track token usage."""
        tokens = estimate_tokens(content)
        self._pending.append({"role": role, "content": content})
        self._running_tokens += tokens

    def would_overflow(self) -> bool:
        """Would adding messages overflow the context window?."""
        return self._running_tokens >= self.resume_threshold

    def needs_summarization(self) -> bool:
        """Whether the current pending messages should be summarized."""
        return self._running_tokens >= self.resume_threshold

    def get_messages(self) -> list[dict]:
        """Get the current pending messages (converted to API-ready format)."""
        return list(self._pending)

    def token_count(self) -> int:
        return self._running_tokens

    def summarize_old_turns(self, recent_keep: int = 4) -> dict:
        """
        Summarization strategy — the oldest turns are collapsed into a compact
        recap message. Returns the new message list to send.
        Actual model-based summarization is wired in Phase 8 (§7.7).
        For now this returns the most recent turns (drop-oldest) with a
        marker so the model knows context was compacted.
        """
        n_pending = len(self._pending)

        if n_pending <= recent_keep:
            # Nothing to summarize yet — keep everything
            return {"messages": self.get_messages(), "summarized": False}

        # Keep the most recent turns, compact the rest into a recap marker
        kept = self._pending[-recent_keep:]
        old_count = n_pending - recent_keep

        summary = (
            f"[SYSTEM] {old_count} earlier turns were compacted by the context "
            f"manager to fit within the {self.context_window}-token context window. "
            f"The conversation has been summed up implicitly; focus on the most "
            f"recent turns below."
        )

        # Replace pending with the compacted version
        self._pending = [{"role": "system", "content": summary}] + kept
        self._running_tokens = estimate_tokens(summary) + sum(
            estimate_tokens(m["content"]) for m in kept
        )

        logger.info(
            "ContextManager compacted {} old turns (running_tokens now {})",
            old_count, self._running_tokens,
        )
        return {"messages": self.get_messages(), "summarized": True}

    def clear(self) -> None:
        """Reset the context manager."""
        self._pending = []
        self._running_tokens = 0
