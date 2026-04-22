"""memory tool."""

from .memory import DESCRIPTION, NAME, SPEC, execute

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "max_result_size_chars": 20_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "execute", "DESCRIPTION"]
