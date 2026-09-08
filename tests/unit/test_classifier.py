"""Unit tests for the hybrid intent classifier (§6.1 Stage A)."""
import pytest

from halite.config.settings import AppConfig
from halite.core.classifier import IntentClassifier
from halite.core.router import Router


@pytest.fixture
def classifier():
    return IntentClassifier(AppConfig())


class TestClassifierStageA:
    def test_simple_prompt_leans_local(self, classifier):
        d = classifier.classify("fix typo in the README file")
        assert d.decision == "local"

    def test_complex_prompt_leans_api(self, classifier):
        d = classifier.classify(
            "refactor the entire project to use React and add a WebGL animation library"
        )
        assert d.decision == "api"

    def test_ambiguous_short_prompt_clarifies(self, classifier):
        d = classifier.classify("fix this")
        assert d.decision == "clarify"

    def test_long_prompt_leans_api(self, classifier):
        long_prompt = "please help me " + "implement a feature that does many things " * 40
        d = classifier.classify(long_prompt)
        assert d.decision == "api"

    def test_secrets_bias_local(self, classifier):
        d = classifier.classify(
            "my key is sk-ant-abcdefghijklmnopqrstuvwxyz123456 and I need a big 3D payment system"
        )
        assert d.decision == "local"  # secrets bias overrides complexity

    def test_simple_rename(self, classifier):
        d = classifier.classify("rename variable x to y in main.py")
        assert d.decision == "local"


class TestRouter:
    def setup_method(self):
        self.cfg = AppConfig()
        self.router = Router(self.cfg)

    def test_local_no_confirm(self):
        from halite.models.schemas import ClassifierDecision
        d = ClassifierDecision(decision="local", confidence=0.9, reasoning="x")
        backend, confirm = self.router.resolve_backend(d)
        assert backend == "local"
        assert confirm is False

    def test_api_requires_confirm_by_default(self):
        from halite.models.schemas import ClassifierDecision
        d = ClassifierDecision(decision="api", confidence=0.9, reasoning="x")
        backend, confirm = self.router.resolve_backend(d)
        assert backend == "api"
        assert confirm is True  # §6.1 gate on by default

    def test_api_auto_approved_when_configured(self):
        from halite.models.schemas import ClassifierDecision
        self.cfg.auto_approve_api = True
        d = ClassifierDecision(decision="api", confidence=0.9, reasoning="x")
        backend, confirm = self.router.resolve_backend(d)
        assert backend == "api"
        assert confirm is False

    def test_manual_override_wins(self):
        from halite.models.schemas import ClassifierDecision
        self.router.set_manual_override("local")
        d = ClassifierDecision(decision="api", confidence=0.9, reasoning="x")
        backend, _ = self.router.resolve_backend(d)
        assert backend == "local"

    def test_clarify_routes_nowhere(self):
        from halite.models.schemas import ClassifierDecision
        d = ClassifierDecision(decision="clarify", confidence=0.5, reasoning="x")
        backend, confirm = self.router.resolve_backend(d)
        assert backend == "none"
        assert confirm is False