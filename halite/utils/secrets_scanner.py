"""
Secrets scanner for detecting API keys, private keys, .env content (§6.1, §6.6).
Used to bias classifier toward local and redact docs before generation.
"""
from __future__ import annotations

import re
import math
from typing import NamedTuple


class ScanResult(NamedTuple):
    found: bool
    matches: list[str]
    confidence: float  # 0.0–1.0, how likely the content contains real secrets


# Patterns that look like secrets
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),                     # OpenAI
    re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}", re.IGNORECASE),               # Anthropic
    re.compile(r"ghp_[A-Za-z0-9]{30,}", re.IGNORECASE),                    # GitHub PAT
    re.compile(r"xoxb-[A-Za-z0-9\-]+", re.IGNORECASE),                     # Slack bot
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),                        # AWS access key
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),                  # PEM private key
    re.compile(r"(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^\s'\"]{6,}", re.IGNORECASE),
]

# Patterns for .env file content
_ENV_PATTERNS: list[re.Pattern] = [
    re.compile(r"^[A-Z_]+=\s*['\"]?[A-Za-z0-9_\-]{16,}", re.MULTILINE),
    re.compile(r"\.env"),  # references to .env files
]


def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string — high entropy = likely random/secret."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def scan_for_secrets(text: str) -> ScanResult:
    """
    Scan text for likely secrets (API keys, private keys, .env content).
    Returns ScanResult with whether secrets were found and a confidence score.
    """
    matches: list[str] = []

    # Check regex patterns
    for pattern in _SECRET_PATTERNS:
        found = pattern.findall(text)
        matches.extend(found)

    # Check .env patterns
    for pattern in _ENV_PATTERNS:
        found = pattern.findall(text)
        matches.extend(found)

    # Entropy-based check for any long alphanumeric strings
    tokens = re.findall(r"[A-Za-z0-9_\-]{20,}", text)
    for token in tokens:
        entropy = _shannon_entropy(token)
        if entropy > 4.0:  # high entropy = likely random/secret
            matches.append(token[:30] + "...")

    if not matches:
        return ScanResult(found=False, matches=[], confidence=0.0)

    # Confidence: more matches = higher confidence
    confidence = min(1.0, len(matches) * 0.25 + 0.3)
    return ScanResult(found=True, matches=matches[:5], confidence=confidence)


def redact_secrets(text: str) -> str:
    """Replace detected secrets with [REDACTED] for safe documentation output."""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    tokens = re.findall(r"[A-Za-z0-9_\-]{20,}", result)
    for token in tokens:
        if _shannon_entropy(token) > 4.0:
            result = result.replace(token, "[REDACTED]")
    return result
