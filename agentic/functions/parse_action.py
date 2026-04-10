"""parse_action — extract a function call action from LLM output."""

from __future__ import annotations

import json
import re


def parse_action(text: str) -> dict | None:
    """Extract {"call": "name", "args": {...}} from LLM output, or None.

    Searches for JSON with a "call" key in markdown fences or bare JSON.
    """
    # Try markdown-fenced JSON
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict) and "call" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # Try bare JSON (supports nested objects like args: {...})
    match = re.search(r"\{[^{}]*\"call\".*\}", text, re.DOTALL)
    if match:
        # Find the balanced JSON by trying progressively shorter substrings
        candidate = match.group(0)
        for end in range(len(candidate), 0, -1):
            try:
                obj = json.loads(candidate[:end])
                if isinstance(obj, dict) and "call" in obj:
                    return obj
            except json.JSONDecodeError:
                continue

    return None
