"""edit tool."""

from .edit import EDIT, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["EDIT", "NAME", "SPEC", "TOOL", "execute"]
