"""glob tool — find files by name pattern."""

from __future__ import annotations

import glob as _glob
import os
from typing import Any


NAME = "glob"

DESCRIPTION = (
    "Find files matching a glob pattern (like `**/*.py`), sorted by "
    "modification time (newest first).\n"
    "\n"
    "- Use this instead of `find` or `ls` for file discovery.\n"
    "- Supports recursive `**` and standard glob syntax.\n"
    "- `path` defaults to cwd.\n"
)

SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. \"**/*.py\" or \"src/*.ts\".",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Absolute path. Defaults to cwd.",
            },
        },
        "required": ["pattern"],
    },
}


def execute(pattern: str, path: str | None = None, **_: Any) -> str:
    root = path or os.getcwd()
    if not os.path.isabs(root):
        return f"Error: path must be absolute, got {root!r}"
    if not os.path.isdir(root):
        return f"Error: not a directory: {root}"

    # Join pattern relative to root so ** works as expected
    full_pattern = os.path.join(root, pattern)
    matches = _glob.glob(full_pattern, recursive=True)
    # Keep files only; sort newest first
    matches = [m for m in matches if os.path.isfile(m)]
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    if not matches:
        return f"No matches for {pattern!r} under {root}"
    if len(matches) > 500:
        truncated = matches[:500]
        return f"# {len(matches)} matches (showing 500 newest)\n" + "\n".join(truncated)
    return f"# {len(matches)} matches\n" + "\n".join(matches)
