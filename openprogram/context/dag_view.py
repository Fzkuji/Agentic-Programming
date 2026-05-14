"""dag_view — render a DAG snapshot as the tree-shaped dicts the legacy
WebUI tree viewer consumes.

The viewer cares about ``@agentic_function`` call nesting: each code
Call is a tree node, its children are code Calls whose ``called_by``
points at it. Top-level entries are code Calls with no caller
recorded in the same graph.

LLM / user Call nodes are not nested into the tree — they aren't
``@agentic_function`` invocations, and the existing viewer doesn't
know how to render them. They stay in the DAG (queryable separately)
and may surface as auxiliary info on their owning code Call later;
this module keeps the visible structure minimal.

Pure functions only — no I/O, no SQLite, no FastAPI. The WebUI route
opens a GraphStore and passes its in-memory ``Graph`` here; tests and
CLI dumpers can do the same with a synthetic Graph.
"""

from __future__ import annotations

from typing import Any, Optional

from openprogram.context.nodes import Call, Graph


def call_to_dict(call: Call) -> dict[str, Any]:
    """Serialize one DAG code Call into the field shape the legacy
    tree viewer expects.

    Field map:
      path         <- call.id                 (unique node key)
      name         <- call.name               (function name)
      node_type    <- "function"              (constant for code Calls)
      params       <- call.input              (sanitized args)
      output       <- call.output             (return value or error dict)
      status       <- call.metadata["status"] ("running" / "success" / "error")
      error        <- output["error"] if status == "error"
      start_time   <- call.created_at         (unix seconds)
      end_time     <- start + metadata.duration_seconds (if known)
      duration_ms  <- metadata.duration_seconds * 1000
      raw_reply    <- ""                      (legacy field; empty for code Calls)
      children     <- []                      (populated by ``dag_to_tree_dicts``)
    """
    meta = call.metadata or {}
    status = meta.get("status") or "success"
    duration_seconds = meta.get("duration_seconds")
    start = call.created_at
    end = (
        start + duration_seconds
        if (duration_seconds is not None and start is not None)
        else None
    )
    duration_ms = (
        int(duration_seconds * 1000)
        if duration_seconds is not None else None
    )

    output = call.output
    error_text: Optional[str] = None
    if status == "error" and isinstance(output, dict):
        error_text = str(output.get("error") or "")

    return {
        "path": call.id,
        "name": call.name or "",
        "node_type": "function",
        "params": call.input or {},
        "output": output,
        "status": status,
        "error": error_text or "",
        "start_time": start,
        "end_time": end,
        "duration_ms": duration_ms,
        "raw_reply": "",
        "children": [],
    }


def dag_to_tree_dicts(graph: Graph) -> list[dict[str, Any]]:
    """Return the root-level ``@agentic_function`` calls in ``graph``
    as a list of tree dicts.

    A code Call is a "root" when its ``called_by`` is empty or points
    at an id that's not itself a code Call in this graph (e.g. it
    was called directly from the dispatcher's user-message turn).
    Children are stitched via ``called_by``; iteration order follows
    each parent's ``seq`` so the tree mirrors execution chronology.
    """
    code_calls = [n for n in graph if n.is_code()]
    code_ids = {n.id for n in code_calls}

    # parent_id -> [children sorted by seq]
    by_parent: dict[str, list[Call]] = {}
    roots: list[Call] = []
    for call in sorted(code_calls, key=lambda n: n.seq):
        caller = call.called_by or ""
        if caller and caller in code_ids:
            by_parent.setdefault(caller, []).append(call)
        else:
            roots.append(call)

    def _build(node: Call) -> dict[str, Any]:
        d = call_to_dict(node)
        d["children"] = [_build(c) for c in by_parent.get(node.id, [])]
        return d

    return [_build(r) for r in roots]


__all__ = ["call_to_dict", "dag_to_tree_dicts"]
