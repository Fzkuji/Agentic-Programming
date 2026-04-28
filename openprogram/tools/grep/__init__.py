"""grep tool."""

from .grep import GREP, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["GREP", "NAME", "SPEC", "TOOL", "execute"]
