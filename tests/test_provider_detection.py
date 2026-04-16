"""Tests for provider auto-detection, create_runtime, and lazy imports."""

import importlib
import json
import os
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


    def test_detect_provider_raises_when_nothing_available(self, monkeypatch):
        """detect_provider() raises RuntimeError when no provider is found."""
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

    def test_detect_provider_inside_claude_code_env(self, monkeypatch):
        """Caller env detection picks up CLAUDECODE=1."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        from agentic import providers
        importlib.reload(providers)

        assert providers.detect_provider() == ("claude-code", "sonnet")

    def test_load_provider_config_from_file(self, monkeypatch, tmp_path):
        """_load_provider_config reads ~/.agentic/config.json."""
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)

        config_dir = tmp_path / ".agentic"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "default_provider": "openai",
            "default_model": "gpt-4.1-nano"
        }))
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) if p == "~" else p)

        from agentic import providers
        importlib.reload(providers)

        result = providers._load_provider_config()
        assert result == ("openai", "gpt-4.1-nano")

    def test_load_provider_config_file_uses_default_model(self, monkeypatch, tmp_path):
        """Config file without default_model falls back to registry default."""
        monkeypatch.delenv("AGENTIC_PROVIDER", raising=False)
        monkeypatch.delenv("AGENTIC_MODEL", raising=False)

        config_dir = tmp_path / ".agentic"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"default_provider": "anthropic"}))
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) if p == "~" else p)

        from agentic import providers
        importlib.reload(providers)

        result = providers._load_provider_config()
        assert result == ("anthropic", "claude-sonnet-4-6")


class TestCreateRuntime:
    """Tests for create_runtime() factory."""

    def test_unknown_provider_raises(self):
        """create_runtime raises ValueError for unknown provider names."""
        from agentic import providers
        with pytest.raises(ValueError, match="Unknown provider"):
            providers.create_runtime(provider="nonexistent")

    def test_explicit_provider_loads_correct_class(self, monkeypatch):
        """create_runtime with explicit provider loads the right module."""
        # Mock the codex module since it doesn't need an API key, just a CLI path
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None)

        from agentic import providers
        rt = providers.create_runtime(provider="codex")
        assert type(rt).__name__ == "CodexRuntime"

    def test_model_override(self, monkeypatch):
        """create_runtime passes model override to the runtime."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None)

        from agentic import providers
        rt = providers.create_runtime(provider="codex", model="o4-mini")
        assert rt.model == "o4-mini"


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
