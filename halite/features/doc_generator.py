"""
Documentation generation (§6.6).
AST/tree-sitter based architecture docs + reportlab PDF.
Structural facts always come from parsing, never model guesswork.
Full implementation is Phase 7.
"""
from __future__ import annotations

from pathlib import Path

from halite.utils.logging_config import logger


class DocGenerator:
    """Documentation generation entry points (§6.6)."""

    def __init__(self, model_provider) -> None:
        self.provider = model_provider

    async def generate(self, project_root: Path, out_dir: Path) -> dict:
        """Generate ARCHITECTURE.md + docs.pdf (§6.6)."""
        logger.info("DocGenerator.generate: root={}, out={}", project_root, out_dir)
        # Phase 7 implementation
        raise NotImplementedError("Documentation generation implemented in Phase 7")
