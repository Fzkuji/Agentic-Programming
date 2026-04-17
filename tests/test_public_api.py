"""Public API surface tests."""

from agentic import __all__ as public_api


def test_auto_trace_package_is_exported_in_public_api():
    """Top-level package should export auto_trace_package alongside auto_trace_module."""
    assert "auto_trace_package" in public_api
