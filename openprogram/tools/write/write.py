"""write tool — create a new file or overwrite an existing one."""

from __future__ import annotations

import os
from typing import Any


NAME = "write"

DESCRIPTION = (
    "Write the given content to a file on disk, creating it (and any missing "
    "parent directories) if it doesn't exist, or overwriting it if it does.\n"
    "\n"
    "- Paths MUST be absolute.\n"
    "- Prefer the `edit` tool for modifying existing files — it sends only the diff "
    "and is safer for concurrent edits. Use `write` for new files or full rewrites.\n"
)

SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file to write.",
            },
            "content": {
                "type": "string",
                "description": "Full file contents to write.",
            },
        },
        "required": ["file_path", "content"],
    },
}


def execute(file_path: str, content: str, **_: Any) -> str:
    if not os.path.isabs(file_path):
        return f"Error: file_path must be absolute, got {file_path!r}"
    parent = os.path.dirname(file_path)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            return f"Error creating directory {parent}: {e}"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return f"Error writing {file_path}: {type(e).__name__}: {e}"
    return f"Wrote {len(content)} bytes to {file_path}"
