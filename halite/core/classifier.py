"""
Hybrid intent classifier & local/API router (§6.1, §4 Core layer).
Deterministic two-stage design:
  Stage A: rule-based pre-filter (fast, free, always runs first)
  Stage B: local SLM classification (only when Stage A is inconclusive)

Per §6.1: Stage A is deterministic and free. Stage B is only used when
Stage A can't make a confident decision.
"""
from __future__ import annotations

import re

from halite.models.schemas import AppConfig, ClassifierDecision
from halite.utils.logging_config import logger
from halite.utils.secrets_scanner import scan_for_secrets

# ── Complexity signals (→ lean API) ─────────────────────────────────────────

_COMPLEXITY_KEYWORDS = [
    "refactor",
    "entire project",
    "whole project",
    "multi-file",
    "auth system",
    "payment",
    "3d",
    "webgl",
    "animation library",
    "three.js",
    "react",
    "next.js",
    "vite",
    "full-stack",
    "microservice",
    "database migration",
    "docker",
    "kubernetes",
    "distributed",
    "concurrency",
    "websocket",
    "machine learning",
    "neural network",
]

_COMPLEXITY_PATTERNS = [
    re.compile(r"\b(?:refactor|rewrite|restructure|redesign)\s+(?:the\s+)?(?:entire|whole|all|every)\b"),
    re.compile(r"\b(?:implement|build|create)\s+.+(?:auth|payment|3d|webgl|animation)\b", re.IGNORECASE),
    re.compile(r"\bmultiple\s+files\b"),
    re.compile(r"\b(?:dozens|hundreds)\s+of\s+files\b"),
    re.compile(r"\bcomplex\b"),
]

# ── Simplicity signals (→ lean local) ───────────────────────────────────────

_SIMPLICITY_KEYWORDS = [
    "fix typo",
    "rename variable",
    "add a button",
    "change color",
    "fix bug",
    "fix a typo",
    "rename function",
    "add a comment",
    "small change",
    "quick fix",
    "simple",
    "minor",
]

_SIMPLICITY_PATTERNS = [
    re.compile(r"\b(?:fix|correct)\s+(?:this\s+)?typo\b", re.IGNORECASE),
    re.compile(r"\brename\s+(?:this\s+)?(?:variable|function|class)\b", re.IGNORECASE),
    re.compile(r"\badd\s+a\s+button\b", re.IGNORECASE),
    re.compile(r"\bchange\s+(?:the\s+)?color\b", re.IGNORECASE),
]


class IntentClassifier:
    """
    Two-stage hybrid classifier (§6.1).
    Stage A (rules) always runs first and is free. Stage B (SLM) is
    triggered only when Stage A is inconclusive.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def stage_a_rule_based(self, prompt: str) -> ClassifierDecision | None:
        """
        Deterministic rule-based pre-filter (§6.1 Stage A).
        Returns a final ClassifierDecision if confident, else None (inconclusive).
        """
        prompt_lower = prompt.lower()

        # ── Secret detection → bias toward LOCAL (§6.1 edge case) ──────────
        secrets = scan_for_secrets(prompt)
        if secrets.found:
            logger.info(
                "Secrets detected in prompt — biasing toward LOCAL. matches={}",
                secrets.matches,
            )
            return ClassifierDecision(
                decision="local",
                confidence=min(0.9, 0.6 + secrets.confidence * 0.3),
                reasoning=(
                    f"Likely secrets detected in prompt ({len(secrets.matches)} matches) — "
                    "kept local for privacy."
                ),
            )

        # ── Very short/ambiguous prompts → ALWAYS clarify (§6.1 edge case) ──
        # Fewer than ~6 meaningful words and looks like a vague delegation
        meaningful_words = [w for w in prompt.split() if len(w) > 1]
        if len(meaningful_words) <= 4 and not _looks_specific(prompt_lower):
            return ClassifierDecision(
                decision="clarify",
                confidence=0.9,
                reasoning="Prompt is very short and ambiguous — need clarification.",
            )

        # ── Token-count heuristic ─────────────────────────────────────────
        # Rough token estimate: ~4 chars/token for English
        est_tokens = len(prompt) / 4
        if est_tokens > self.config.classifier_token_threshold:
            return ClassifierDecision(
                decision="api",
                confidence=0.7,
                reasoning=(
                    f"Prompt length ~{int(est_tokens)} estimated tokens exceeds "
                    f"threshold {self.config.classifier_token_threshold} — needs API."
                ),
            )

        # ── Complexity keywords ───────────────────────────────────────────
        complexity_hits = self._count_keyword_hits(prompt_lower, _COMPLEXITY_KEYWORDS)
        complexity_patterns = sum(1 for p in _COMPLEXITY_PATTERNS if p.search(prompt_lower))

        if complexity_hits >= 2 or complexity_patterns >= 1:
            return ClassifierDecision(
                decision="api",
                confidence=0.8,
                reasoning=(
                    f"Complexity signals detected: {complexity_hits} keyword hits, "
                    f"{complexity_patterns} pattern matches — needs larger context/API."
                ),
            )

        # ── Simplicity keywords ───────────────────────────────────────────
        simplicity_hits = self._count_keyword_hits(prompt_lower, _SIMPLICITY_KEYWORDS)
        simplicity_patterns = sum(1 for p in _SIMPLICITY_PATTERNS if p.search(prompt_lower))

        if simplicity_hits >= 1 or simplicity_patterns >= 1:
            return ClassifierDecision(
                decision="local",
                confidence=0.8,
                reasoning=(
                    f"Simplicity signals detected: {simplicity_hits} keyword hits, "
                    f"{simplicity_patterns} pattern matches — simple enough for local."
                ),
            )

        # ── Inconclusive — needs Stage B ─────────────────────────────────
        logger.debug("Stage A inconclusive for prompt ({} chars)", len(prompt))
        return None

    def _count_keyword_hits(self, prompt_lower: str, keywords: list[str]) -> int:
        hits = 0
        for kw in keywords:
            if kw in prompt_lower:
                hits += 1
        return hits

    def classify(self, prompt: str) -> ClassifierDecision:
        """
        Full classification pipeline:
        1. Try Stage A (rule-based).
        2. If conclusive, return it.
        3. If inconclusive, fall back to clarify (Stage B SLM is wired in Phase 4).
        §6.1: never silently default to paid API on failure.
        """
        logger.info("Classifying prompt ({} chars)", len(prompt))

        # Stage A
        decision = self.stage_a_rule_based(prompt)
        if decision is not None:
            logger.info(
                "Stage A decision: {} (confidence={})",
                decision.decision, decision.confidence,
            )
            return decision

        # Stage B would run here (SLM). Until Phase 4, inconclusive → clarify.
        # §6.1: on parse failure / no SLM, default to NEEDS_CLARIFICATION.
        logger.info("Stage A inconclusive — defaulting to clarify (Stage B in Phase 4)")
        return ClassifierDecision(
            decision="clarify",
            confidence=0.5,
            reasoning="Stage A inconclusive, SLM classifier not yet available — asking user.",
        )


def _looks_specific(prompt_lower: str) -> bool:
    """
    Heuristic: does the prompt look specific enough to not need clarification?
    Specific prompts name files, frameworks, specific actions, etc.
    """
    specific_markers = [
        " in ", " file ", " project ", " to ", "from", "using", "with",
        "fix", "add", "change", "make", "build", "create", "delete",
        "read", "write", "update", "remove", "test", "run", "install",
    ]
    return any(marker in prompt_lower for marker in specific_markers)
