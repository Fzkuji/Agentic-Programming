"""glob tool."""

from .glob import GLOB, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["GLOB", "NAME", "SPEC", "TOOL", "execute"]
