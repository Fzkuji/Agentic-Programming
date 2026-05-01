"""memory tool — durable key-value store across conversations.

Agents use this for facts they learn once and want to carry forward
(user preferences, project constraints, ongoing findings). Stored in a
single JSON file — simple, inspectable, trivially backed-up. No index,
no vector search; if you need semantic recall, pair this with
``web_search`` over your own notes.

Location priority:
  1. ``$OPENPROGRAM_MEMORY_FILE`` — explicit override
  2. ``$OPENPROGRAM_MEMORY_SCOPE=project`` — ``./.openprogram/memory.json``
  3. OpenProgram profile-global store — ``<state>/memory/memory.json``

Default memory is profile-global, not cwd-local. This keeps long-term
user and agent facts available across folders. Project-local memory is
still possible, but only when explicitly requested.

Five actions:
  - ``set key value``       upsert
  - ``get key``             fetch one
  - ``list``                dump all (keys + short value preview)
  - ``search query``        substring match on keys + values
  - ``delete key``          remove

Values are stored verbatim (strings); complex data should be serialised
by the caller. We deliberately do NOT auto-JSON-encode — the agent can
always ``json.dumps(...)`` itself if it wants nested data, and plain
strings are easier to eyeball in the store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .._helpers import read_string_param


NAME = "memory"

DESCRIPTION = (
    "Persistent key-value memory that survives across conversations. "
    "Actions: set (upsert), get, list (all keys + previews), search "
    "(substring match on keys and values), delete. Values are free-form "
    "strings — JSON-encode them yourself if you need structure."
)


SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "get", "list", "search", "delete"],
                "description": "Which operation to perform.",
            },
            "key": {
                "type": "string",
                "description": "Key name for set/get/delete.",
            },
            "value": {
                "type": "string",
                "description": "Value to store (for action=set).",
            },
            "query": {
                "type": "string",
                "description": "Substring to match against keys and values (for action=search).",
            },
        },
        "required": ["action"],
    },
}


def _store_path() -> Path:
    override = os.environ.get("OPENPROGRAM_MEMORY_FILE")
    if override:
        return Path(override).expanduser().resolve()
    scope = (os.environ.get("OPENPROGRAM_MEMORY_SCOPE") or "").strip().lower()
    if scope in {"project", "workspace", "cwd"}:
        return (Path.cwd() / ".openprogram" / "memory.json").resolve()
    from openprogram.paths import get_memory_dir
    return (get_memory_dir() / "memory.json").resolve()


def _load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        # Corrupted store — return empty rather than crashing; the user
        # can inspect the file manually.
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _save(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _preview(v: str, n: int = 80) -> str:
    v = v.replace("\n", " ")
    return v if len(v) <= n else v[: n - 1] + "…"


def execute(
    action: str | None = None,
    key: str | None = None,
    value: str | None = None,
    query: str | None = None,
    **kw: Any,
) -> str:
    action = (action or read_string_param(kw, "action") or "").lower()
    key = key or read_string_param(kw, "key", "name")
    value = value if value is not None else read_string_param(kw, "value")
    query = query or read_string_param(kw, "query", "q")

    if action not in {"set", "get", "list", "search", "delete"}:
        return "Error: `action` must be one of set/get/list/search/delete."

    path = _store_path()
    data = _load(path)

    if action == "set":
        if not key:
            return "Error: set requires `key`."
        if value is None:
            return "Error: set requires `value`."
        data[key] = value
        _save(path, data)
        return f"Stored {key!r} ({len(value)} chars) at {path}"

    if action == "get":
        if not key:
            return "Error: get requires `key`."
        if key not in data:
            return f"(no value stored for {key!r})"
        return f"# {key}\n{data[key]}"

    if action == "delete":
        if not key:
            return "Error: delete requires `key`."
        if key in data:
            data.pop(key)
            _save(path, data)
            return f"Deleted {key!r} from {path}"
        return f"(no value stored for {key!r})"

    if action == "list":
        if not data:
            return f"Memory is empty at {path}."
        lines = [f"# Memory ({len(data)} keys at {path})"]
        for k in sorted(data):
            lines.append(f"- {k}: {_preview(data[k])}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: search requires `query`."
        q = query.lower()
        hits = [
            (k, v) for k, v in data.items()
            if q in k.lower() or q in v.lower()
        ]
        if not hits:
            return f"No memory entries match {query!r}."
        lines = [f"# Memory search: {query!r} ({len(hits)} matches at {path})"]
        for k, v in sorted(hits):
            lines.append(f"- {k}: {_preview(v)}")
        return "\n".join(lines)

    return f"Error: unhandled action {action!r}"


__all__ = ["NAME", "SPEC", "execute", "DESCRIPTION"]
