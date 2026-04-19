"""grep tool — ripgrep-powered content search (falls back to Python re if rg missing)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any


NAME = "grep"

DESCRIPTION = (
    "Search file contents for a regular expression. Uses ripgrep when "
    "available, falls back to a Python regex walker otherwise.\n"
    "\n"
    "- Pattern is a standard regex (ripgrep flavor when rg is available).\n"
    "- `path` defaults to cwd; absolute paths recommended.\n"
    "- Output modes: files_with_matches (default), content, count.\n"
    "- Use `glob` for pure filename matching.\n"
)

SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search. Defaults to cwd.",
            },
            "glob": {
                "type": "string",
                "description": "Optional glob filter (e.g. \"*.py\").",
            },
            "output_mode": {
                "type": "string",
                "enum": ["files_with_matches", "content", "count"],
                "description": "Output format. Default files_with_matches.",
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Case-insensitive match. Default false.",
            },
        },
        "required": ["pattern"],
    },
}


def _run_rg(pattern: str, path: str, glob: str | None, output_mode: str, case_insensitive: bool) -> str:
    cmd = ["rg", "--no-heading"]
    if case_insensitive:
        cmd.append("-i")
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    else:
        cmd.extend(["-n", "-H"])
    if glob:
        cmd.extend(["--glob", glob])
    cmd.extend(["--", pattern, path])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # rg exits 1 when no matches — that's not an error for us
    if proc.returncode not in (0, 1):
        return f"Error: rg exited {proc.returncode}: {proc.stderr.strip()}"
    out = proc.stdout.rstrip()
    return out or "No matches"


def _run_python_fallback(pattern: str, path: str, glob: str | None, output_mode: str, case_insensitive: bool) -> str:
    import fnmatch

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: invalid regex: {e}"

    files_with_matches: list[str] = []
    content_lines: list[str] = []
    counts: dict[str, int] = {}

    if os.path.isfile(path):
        candidates = [path]
    else:
        candidates = []
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if glob and not fnmatch.fnmatch(f, glob):
                    continue
                candidates.append(fp)

    for fp in candidates:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            continue
        n = 0
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                n += 1
                if output_mode == "content":
                    content_lines.append(f"{fp}:{i}:{line}")
        if n:
            files_with_matches.append(fp)
            counts[fp] = n

    if output_mode == "count":
        if not counts:
            return "No matches"
        return "\n".join(f"{fp}:{n}" for fp, n in counts.items())
    if output_mode == "content":
        if not content_lines:
            return "No matches"
        return "\n".join(content_lines[:500])
    if not files_with_matches:
        return "No matches"
    return "\n".join(files_with_matches[:500])


def execute(pattern: str, path: str | None = None, glob: str | None = None,
            output_mode: str = "files_with_matches", case_insensitive: bool = False,
            **_: Any) -> str:
    root = path or os.getcwd()
    if not os.path.exists(root):
        return f"Error: path not found: {root}"
    if shutil.which("rg"):
        return _run_rg(pattern, root, glob, output_mode, case_insensitive)
    return _run_python_fallback(pattern, root, glob, output_mode, case_insensitive)
