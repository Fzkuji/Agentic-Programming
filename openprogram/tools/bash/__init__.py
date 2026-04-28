"""bash tool — shell command execution."""

from .bash import BASH, NAME, SPEC, execute

TOOL = {"spec": SPEC, "execute": execute}

__all__ = ["BASH", "NAME", "SPEC", "TOOL", "execute"]
