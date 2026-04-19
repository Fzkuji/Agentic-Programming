"""edit tool."""

from .edit import NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["NAME", "SPEC", "TOOL", "execute"]
