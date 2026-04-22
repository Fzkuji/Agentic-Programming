"""clarify tool."""

from .clarify import DESCRIPTION, NAME, SPEC, execute

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "max_result_size_chars": 10_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "execute", "DESCRIPTION"]
