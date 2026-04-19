"""glob tool."""

from .glob import NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["NAME", "SPEC", "TOOL", "execute"]
