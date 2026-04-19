"""read tool — read a file from disk and return its contents."""

from __future__ import annotations

import os
from typing import Any


NAME = "read"

MAX_LINES_DEFAULT = 2000
MAX_LINE_LENGTH = 2000

DESCRIPTION = (
    "Read a file from disk and return its contents as text, with line numbers "
    "in `cat -n` style (1-based).\n"
    "\n"
    "- Paths MUST be absolute.\n"
    "- By default reads up to 2000 lines from the top. Use `offset` and `limit` "
    "to page through larger files.\n"
    "- Individual lines longer than 2000 characters are truncated with an ellipsis.\n"
    "- Binary files are not supported — use bash if you need hex dumps.\n"
)

SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file to read.",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based). Default 1.",
            },
            "limit": {
                "type": "integer",
                "description": f"Maximum number of lines to return. Default {MAX_LINES_DEFAULT}.",
            },
        },
        "required": ["file_path"],
    },
}


def execute(file_path: str, offset: int = 1, limit: int = MAX_LINES_DEFAULT, **_: Any) -> str:
    if not os.path.isabs(file_path):
        return f"Error: file_path must be absolute, got {file_path!r}"
    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"
    if os.path.isdir(file_path):
        return f"Error: {file_path} is a directory, not a file"

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading {file_path}: {type(e).__name__}: {e}"

    total = len(lines)
    start = max(1, offset) - 1
    end = min(total, start + max(1, limit))
    selected = lines[start:end]

    out_lines = []
    for i, line in enumerate(selected, start=start + 1):
        text = line.rstrip("\n")
        if len(text) > MAX_LINE_LENGTH:
            text = text[:MAX_LINE_LENGTH] + "…[truncated]"
        out_lines.append(f"{i:>6}\t{text}")

    header = f"# {file_path} (lines {start + 1}-{end} of {total})"
    if not out_lines:
        return header + "\n(empty range)"
    return header + "\n" + "\n".join(out_lines)
