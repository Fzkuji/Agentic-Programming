"""Tests for provider auto-detection and lazy imports."""

import importlib
import pytest
from unittest.mock import MagicMock, patch

class TestProviderDetection:
    """Tests for detect_provider() and create_runtime() wiring."""

    def test_detect_provider_prefers_explicit_env_config(self, monkeypatch):
        """AGENTIC_PROVIDER / AGENTIC_MODEL override CLI and API auto-detection."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "openai")
        monkeypatch.setenv("AGENTIC_MODEL", "gpt-5.1-mini")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("openai", "gpt-5.1-mini")

    def test_detect_provider_uses_config_default_model_when_model_missing(self, monkeypatch):
        """AGENTIC_PROVIDER alone falls back to the registry default model."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "anthropic")
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("anthropic", "claude-sonnet-4-6")

    def test_detect_provider_accepts_google_generative_ai_api_key(self, monkeypatch):
        """Gemini API auto-detection accepts Google's alternate env var name."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_GENERATIVE_AI_API_KEY", "fallback-key")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("gemini", "gemini-2.5-flash")

    def test_check_providers_marks_env_selected_provider_default(self, monkeypatch):
        """check_providers() marks the configured provider as the auto-selected default."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setenv("AGENTIC_PROVIDER", "gemini")
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        statuses = providers.check_providers()
        assert statuses["gemini"]["default"] is True
        assert statuses["gemini"]["model"] == "gemini-2.5-flash"


class TestInferProviderFromModel:
    """Tests for infer_provider_from_model()."""

    @pytest.mark.parametrize("model,expected", [
        ("claude-sonnet-4-6", "anthropic"),
        ("claude-opus-4-6", "anthropic"),
        ("sonnet", "anthropic"),
        ("opus", "anthropic"),
        ("haiku", "anthropic"),
        ("gpt-4.1", "openai"),
        ("gpt-5.4-mini", "openai"),
        ("o1-preview", "openai"),
        ("o3-mini", "openai"),
        ("o4-mini", "openai"),
        ("gemini-2.5-flash", "gemini"),
        ("gemini-2.5-pro", "gemini"),
    ])
    def test_known_models(self, model, expected):
        from agentic.providers import infer_provider_from_model
        assert infer_provider_from_model(model) == expected

    def test_unknown_model_returns_none(self):
        from agentic.providers import infer_provider_from_model
        assert infer_provider_from_model("llama-3.1-70b") is None

    def test_case_insensitive(self):
        from agentic.providers import infer_provider_from_model
        assert infer_provider_from_model("Claude-Sonnet-4-6") == "anthropic"
        assert infer_provider_from_model("GPT-4.1") == "openai"
        assert infer_provider_from_model("Gemini-2.5-Flash") == "gemini"


class TestModelOnlyDetection:
    """Tests for AGENTIC_MODEL-only provider inference."""

    def _clean_env(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

    def test_model_only_infers_anthropic(self, monkeypatch):
        """Setting AGENTIC_MODEL=claude-sonnet-4-6 without AGENTIC_PROVIDER infers anthropic."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("AGENTIC_MODEL", "claude-sonnet-4-6")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("anthropic", "claude-sonnet-4-6")

    def test_model_only_infers_openai(self, monkeypatch):
        """Setting AGENTIC_MODEL=gpt-5.4 without AGENTIC_PROVIDER infers openai."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("AGENTIC_MODEL", "gpt-5.4")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("openai", "gpt-5.4")

    def test_model_only_infers_gemini(self, monkeypatch):
        """Setting AGENTIC_MODEL=gemini-2.5-pro without AGENTIC_PROVIDER infers gemini."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("AGENTIC_MODEL", "gemini-2.5-pro")

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("gemini", "gemini-2.5-pro")

    def test_unknown_model_falls_through(self, monkeypatch):
        """Unknown model name doesn't match; detection falls through to later steps."""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("AGENTIC_MODEL", "llama-3.1-70b")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        from agentic import providers
        importlib.reload(providers)

        # Falls through to API key detection
        assert providers.detect_provider() == ("anthropic", "claude-sonnet-4-6")


class TestDetectProviderErrors:
    """Tests for error conditions in detect_provider()."""

    def test_no_provider_raises_runtime_error(self, monkeypatch):
        """detect_provider() raises RuntimeError when nothing is available."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.delenv("CODEX_CLI", raising=False)
        monkeypatch.delenv("CODEX_SANDBOX_TYPE", raising=False)

        from agentic import providers
        importlib.reload(providers)

        with pytest.raises(RuntimeError, match="No LLM provider found"):
            providers.detect_provider()

    def test_create_runtime_unknown_provider_raises(self):
        """create_runtime() raises ValueError for unknown provider names."""
        from agentic.providers import create_runtime
        with pytest.raises(ValueError, match="Unknown provider"):
            create_runtime(provider="nonexistent")


class TestProviderLazyImport:
    """Test that providers/__init__.py lazy-loads correctly."""

    def test_unknown_attribute_raises(self):
        """Accessing unknown attribute raises AttributeError."""
        from agentic import providers
        with pytest.raises(AttributeError, match="no attribute"):
            _ = providers.NonExistentRuntime

    def test_all_exports(self):
        """__all__ lists all providers."""
        from agentic import providers
        assert "AnthropicRuntime" in providers.__all__
        assert "OpenAIRuntime" in providers.__all__
        assert "GeminiRuntime" in providers.__all__
        assert "ClaudeCodeRuntime" in providers.__all__
        assert "CodexRuntime" in providers.__all__
        assert "GeminiCLIRuntime" in providers.__all__
