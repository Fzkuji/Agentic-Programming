"""write tool."""

from .write import WRITE, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["WRITE", "NAME", "SPEC", "TOOL", "execute"]
