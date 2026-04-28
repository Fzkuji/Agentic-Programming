"""read tool."""

from .read import READ, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["READ", "NAME", "SPEC", "TOOL", "execute"]
