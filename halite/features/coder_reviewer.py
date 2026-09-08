"""
Coder + Reviewer agent (§6.2).
Build workflow: plan → scaffold → build → serve → visual review → fix → deliver.
Review workflow: scan → static review → (optional) dynamic review → report.
Full implementation is Phase 5. This module holds the model + entry points.
"""
from __future__ import annotations

from pathlib import Path

from halite.models.schemas import ReviewFinding
from halite.utils.logging_config import logger


class CoderReviewer:
    """Coder + Reviewer agent implementation entry points."""

    def __init__(self, executor, model_provider) -> None:
        self.executor = executor
        self.provider = model_provider

    async def build_project(self, prompt: str, project_root: Path) -> list[Path]:
        """Build a web project from a prompt (§6.2 build workflow)."""
        logger.info("CoderReviewer.build_project: prompt={}, root={}", prompt[:60], project_root)
        # Phase 5 implementation
        raise NotImplementedError("Build workflow implemented in Phase 5")

    async def review_project(self, project_root: Path) -> list[ReviewFinding]:
        """Static review of an existing project (§6.2 review workflow)."""
        logger.info("CoderReviewer.review_project: root={}", project_root)
        # Phase 5 implementation
        raise NotImplementedError("Review workflow implemented in Phase 5")
