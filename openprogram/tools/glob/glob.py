"""glob tool — find files by name pattern."""

from __future__ import annotations

import glob as _glob
import os

from openprogram.tools._runtime import to_dict_tool, tool


_DESCRIPTION = (
    "Find files matching a glob pattern (like `**/*.py`), sorted by "
    "modification time (newest first).\n"
    "\n"
    "- Use this instead of `find` or `ls` for file discovery.\n"
    "- Supports recursive `**` and standard glob syntax.\n"
    "- `path` defaults to cwd."
)


@tool(
    name="glob",
    description=_DESCRIPTION,
    toolset=["core", "research"],
)
def glob_tool(pattern: str, path: str | None = None) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern, e.g. "**/*.py" or "src/*.ts".
        path: Directory to search in. Absolute path. Defaults to cwd.
    """
    root = path or os.getcwd()
    if not os.path.isabs(root):
        return f"Error: path must be absolute, got {root!r}"
    if not os.path.isdir(root):
        return f"Error: not a directory: {root}"

    full_pattern = os.path.join(root, pattern)
    matches = _glob.glob(full_pattern, recursive=True)
    matches = [m for m in matches if os.path.isfile(m)]
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    if not matches:
        return f"No matches for {pattern!r} under {root}"
    if len(matches) > 500:
        return f"# {len(matches)} matches (showing 500 newest)\n" + "\n".join(matches[:500])
    return f"# {len(matches)} matches\n" + "\n".join(matches)


GLOB = glob_tool
NAME = GLOB.name
DESCRIPTION = _DESCRIPTION
_LEGACY = to_dict_tool(GLOB)
SPEC = _LEGACY["spec"]
execute = _LEGACY["execute"]
